"""
API路由
"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from typing import Optional, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.services.document_parser import document_parser
from app.services.knowledge_base import kb
from app.services.orchestrator import orchestrator
from app.services.analytics import analytics
from app.models.database import db
from app.config import DOCUMENTS_DIR, MAX_FILE_SIZE, ALLOWED_EXTENSIONS
from pathlib import Path
import os
import shutil
import sqlite3


router = APIRouter()


# 请求/响应模型
class QueryRequest(BaseModel):
    query: str
    frontend_type: Optional[str] = "api"
    include_debug_info: Optional[bool] = False


class IntentSpaceCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    keywords: Optional[str] = ""


class FrontendConfig(BaseModel):
    frontend_type: str
    config: dict
    api_key: Optional[str] = None


class DocumentUpdate(BaseModel):
    intent_space_id: Optional[int] = 0
    reparse: Optional[bool] = False


# 文档上传
@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    intent_space_id: Optional[int] = Query(None)
):
    """上传文档到知识库"""
    try:
        # 验证文件格式
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式。支持的格式: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # 保存文件
        file_path = DOCUMENTS_DIR / file.filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="文件大小超过限制")
            buffer.write(content)
        
        # 解析文档
        doc_id = document_parser.save_parsed_document(
            file.filename, str(file_path), intent_space_id
        )
        
        # 添加到知识库
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT processed_content, metadata FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            import json
            try:
                processed_content = json.loads(row["processed_content"])
                metadata = json.loads(row["metadata"])
                
                # 重新解析文档以获取原始内容
                parse_result = document_parser.parse_document(str(file_path), file.filename)
                raw_content = parse_result["raw_content"]
                
                # 添加到知识库
                kb.add_document(doc_id, raw_content, metadata, intent_space_id)
            except Exception as e:
                # 即使失败也返回成功，因为文档已经保存到数据库
                pass
        
        return {
            "message": "文档上传成功",
            "doc_id": doc_id,
            "filename": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


# 查询
@router.post("/query")
async def query_knowledge_base(request: QueryRequest):
    """查询知识库（优化：使用异步调用）"""
    try:
        import asyncio
        
        # 异步意图分类（如果支持）
        if hasattr(orchestrator, 'async_ai_client') and orchestrator.async_ai_client:
            detected_intent, confidence = await orchestrator.classify_intent_async(request.query)
        else:
            # 回退到同步版本
            detected_intent, confidence = orchestrator.classify_intent(request.query)
        
        # 路由查询
        route_info = orchestrator.route_query(
            request.query, detected_intent, confidence, request.frontend_type
        )
        intent_space_id = route_info["intent_space_id"]
        
        # 知识库搜索（本地操作，很快）
        search_results = kb.search(request.query, intent_space_id, top_k=5)
        
        # 异步生成响应（如果支持）
        if hasattr(kb, 'generate_response_async'):
            response_text = await kb.generate_response_async(
                request.query, search_results, request.frontend_type
            )
        else:
            # 回退到同步版本
            response_text = kb.generate_response(
                request.query, search_results, request.frontend_type
            )
        
        # 记录查询
        response_status = "success" if search_results else "no_match"
        analytics.log_query(
            request.query, intent_space_id, detected_intent, confidence,
            response_text, response_status, request.frontend_type
        )
        
        response_data = {
            "query": request.query,
            "detected_intent": detected_intent,
            "confidence": confidence,
            "response": response_text  # 这是自然语言回答，Teams/Telegram等前端只使用这个字段
        }
        
        # 只在需要调试信息时返回原始文档内容
        if request.include_debug_info:
            response_data["results"] = [
                {
                    "doc_id": r["doc_id"],
                    "content": r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"],
                    "score": r["score"]
                }
                for r in search_results
            ]
        
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# 意图空间管理
@router.get("/intent-spaces")
async def get_intent_spaces():
    """获取所有意图空间"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM intent_spaces ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "keywords": row["keywords"].split(",") if row["keywords"] else []
        }
        for row in rows
    ]


@router.post("/intent-spaces")
async def create_intent_space(intent_space: IntentSpaceCreate):
    """创建意图空间"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO intent_spaces (name, description, keywords)
            VALUES (?, ?, ?)
        """, (intent_space.name, intent_space.description, intent_space.keywords))
        
        conn.commit()
        space_id = cursor.lastrowid
        conn.close()
        
        return {"message": "意图空间创建成功", "id": space_id}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="意图空间名称已存在")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.patch("/intent-spaces/{intent_id}")
async def update_intent_space(intent_id: int, intent_space: IntentSpaceCreate):
    """更新意图空间（名称、描述、关键词）"""
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM intent_spaces WHERE id = ?", (intent_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="意图空间不存在")
        cursor.execute("""
            UPDATE intent_spaces
            SET name = ?, description = ?, keywords = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (intent_space.name, intent_space.description, intent_space.keywords, intent_id))
        conn.commit()
        conn.close()
        return {"message": "意图空间已更新", "id": intent_id}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="意图空间名称已存在")
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


# 文档管理
@router.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    """获取单个文档信息及内容预览"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, file_path, file_format, file_size, upload_date, status, intent_space_id FROM documents WHERE id = ?",
        (doc_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    try:
        parse_result = document_parser.parse_document(row["file_path"], row["filename"])
        raw = parse_result.get("raw_content", "") or ""
        content_preview = raw[:5000] if len(raw) > 5000 else raw
    except Exception:
        content_preview = ""
    return {
        "id": row["id"],
        "filename": row["filename"],
        "file_format": row["file_format"],
        "file_size": row["file_size"],
        "upload_date": row["upload_date"],
        "status": row["status"],
        "intent_space_id": row["intent_space_id"],
        "content_preview": content_preview,
    }


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: int, body: DocumentUpdate):
    """更新文档（意图空间、可选重新解析）"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, file_path, intent_space_id FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="文档不存在")
    intent_space_id = body.intent_space_id if body.intent_space_id else None
    if body.reparse:
        try:
            parse_result = document_parser.parse_document(row["file_path"], row["filename"])
            import json
            cursor.execute(
                """UPDATE documents SET intent_space_id = ?, processed_content = ?, metadata = ?, status = 'processed' WHERE id = ?""",
                (intent_space_id, json.dumps(parse_result["structured_content"], ensure_ascii=False), json.dumps(parse_result["metadata"], ensure_ascii=False), doc_id)
            )
            conn.commit()
            kb.delete_document(doc_id)
            raw_content = parse_result["raw_content"]
            metadata = parse_result["metadata"]
            kb.add_document(doc_id, raw_content, metadata, intent_space_id)
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=500, detail=f"重新解析失败: {str(e)}")
    else:
        cursor.execute("UPDATE documents SET intent_space_id = ? WHERE id = ?", (intent_space_id, doc_id))
        conn.commit()
    conn.close()
    return {"message": "文档已更新", "doc_id": doc_id}


@router.get("/documents")
async def get_documents(
    intent_space_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None)
):
    """获取文档列表"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM documents WHERE 1=1"
    params = []
    
    if intent_space_id:
        query += " AND intent_space_id = ?"
        params.append(intent_space_id)
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    query += " ORDER BY upload_date DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row["id"],
            "filename": row["filename"],
            "file_path": row["file_path"],
            "file_format": row["file_format"],
            "file_size": row["file_size"],
            "upload_date": row["upload_date"],
            "status": row["status"],
            "intent_space_id": row["intent_space_id"]
        }
        for row in rows
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """删除文档"""
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 获取文档信息
        cursor.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="文档不存在")
        
        file_path = row["file_path"]
        
        # 从知识库删除
        kb.delete_document(doc_id)
        
        # 删除文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass  # 文件删除失败不影响数据库删除
        
        # 从数据库删除
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        
        return {"message": "文档删除成功", "doc_id": doc_id}
    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


# 前端集成
@router.get("/frontend-integrations")
async def get_frontend_integrations():
    """获取前端集成列表"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM frontend_integrations")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row["id"],
            "frontend_type": row["frontend_type"],
            "status": row["status"],
            "api_key_hash": row["api_key_hash"],
            "last_tested": row["last_tested"]
        }
        for row in rows
    ]


# 分析
@router.get("/analytics/query-history")
async def get_query_history(limit: int = Query(100)):
    """获取查询历史"""
    return analytics.get_query_history(limit)


@router.get("/analytics/accuracy")
async def get_classification_accuracy(hours: int = Query(24)):
    """获取分类准确率统计（按小时）"""
    return analytics.get_classification_accuracy(hours)


@router.get("/analytics/kb-usage")
async def get_kb_usage():
    """获取知识库使用统计"""
    return analytics.get_kb_usage()


# Webhook URL（供前端同步显示 Tunnel 启动后写入的最新地址）
@router.get("/webhook-url")
async def get_webhook_url():
    """返回当前数据库中保存的 Teams Webhook URL，供管理界面复制与刷新"""
    from app.utils.tunnel_url_saver import get_webhook_url as _get_webhook_url
    url = _get_webhook_url()
    return {"webhook_url": url or ""}


# Teams Bot消息端点
@router.post("/teams/messages")
async def teams_messages(request: Request):
    """处理Microsoft Teams Bot消息"""
    try:
        from app.integrations.teams_bot import get_teams_bot
        from botbuilder.schema import Activity
        
        teams_bot = get_teams_bot()
        if not teams_bot or not teams_bot.adapter:
            return JSONResponse(
                content={
                    "error": "Teams Bot未配置",
                    "message": "请在管理界面配置Teams Bot"
                },
                status_code=503
            )
        
        # 获取认证头
        auth_header = request.headers.get("Authorization", "")
        
        # 获取请求体
        try:
            body = await request.json()
        except Exception as e:
            return JSONResponse(
                content={"error": "无效的请求体", "message": str(e)},
                status_code=400
            )
        
        # 创建Activity对象
        try:
            activity = Activity().deserialize(body)
        except Exception as e:
            return JSONResponse(
                content={"error": "无效的Activity格式", "message": str(e)},
                status_code=400
            )
        
        # 处理消息并生成响应
        async def process_turn(turn_context):
            try:
                # 先发送“正在思考”状态
                try:
                    await turn_context.send_activity(Activity(type="typing"))
                except Exception:
                    pass
                response_activity = await teams_bot.handle_message(activity)
                if response_activity:
                    await turn_context.send_activity(response_activity)
            except Exception as e:
                logger.exception("处理Teams消息失败")
                # 发送错误消息给用户
                try:
                    await turn_context.send_activity(
                        Activity(
                            type="message",
                            text=f"抱歉，处理您的请求时出现错误：{str(e)}"
                        )
                    )
                except Exception as send_error:
                    pass  # 无法发送错误消息，忽略
        
        # Bot Framework适配器的process_activity方法签名：
        # process_activity(req, auth_header: str, logic: Callable)
        # 根据方法签名检查，参数顺序是：req, auth_header, logic
        # 但FastAPI的Request对象可能不兼容，尝试两种方式
        try:
            # 方式1：按照官方签名 (req, auth_header, logic)
            await teams_bot.adapter.process_activity(
                request,      # FastAPI Request对象
                auth_header,  # 认证头字符串
                process_turn  # 处理函数
            )
        except TypeError:
            # 如果方式1失败（可能是Request对象类型不兼容），尝试方式2
            try:
                # 方式2：按照Medium文章示例 (activity, auth_header, logic)
                # 某些版本可能接受Activity作为第一个参数
                await teams_bot.adapter.process_activity(
                    activity,      # Activity对象
                    auth_header,   # 认证头字符串
                    process_turn   # 处理函数
                )
            except Exception as e2:
                logger.exception("process_activity 方式2 失败")
                raise e2
        except Exception as e:
            logger.exception("process_activity 失败")
            # 如果process_activity失败，返回错误响应
            return JSONResponse(
                content={
                    "error": "处理Activity失败",
                    "message": str(e)
                },
                status_code=500
            )
        
        # Bot Framework适配器会自动处理响应
        # 返回200状态码
        return Response(status_code=200)
        
    except ImportError as e:
        return JSONResponse(
            content={
                "error": "Bot Framework未安装",
                "message": "请运行: pip install botbuilder-core botbuilder-schema",
                "details": str(e)
            },
            status_code=500
        )
    except Exception as e:
        logger.exception("处理Teams消息失败")
        return JSONResponse(
            content={"error": "处理Teams消息失败", "message": str(e)},
            status_code=500
        )
