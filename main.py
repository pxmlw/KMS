from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel
import uvicorn

# 创建FastAPI应用实例
app = FastAPI(
    title="FastAPI Web应用",
    description="包含upload、query和intents路由的简单Web应用",
    version="1.0.0"
)


# 数据模型定义
class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str
    filters: Optional[dict] = None


class IntentRequest(BaseModel):
    """意图请求模型"""
    text: str
    context: Optional[dict] = None


class IntentResponse(BaseModel):
    """意图响应模型"""
    intent: str
    confidence: float
    entities: Optional[List[dict]] = None


# 路由端点

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "欢迎使用FastAPI Web应用",
        "endpoints": {
            "upload": "/upload",
            "query": "/query",
            "intents": "/intents"
        }
    }


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    文件上传端点
    接收文件并返回上传信息
    """
    try:
        # 读取文件内容
        contents = await file.read()
        
        # 返回文件信息
        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(contents),
            "message": "文件上传成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@app.post("/query")
async def query(request: QueryRequest):
    """
    查询端点
    接收查询请求并返回结果
    """
    try:
        # 这里可以添加实际的查询逻辑
        query_text = request.query
        filters = request.filters or {}
        
        # 模拟查询结果
        result = {
            "query": query_text,
            "filters": filters,
            "results": [
                {"id": 1, "title": "结果1", "content": f"这是关于'{query_text}'的查询结果"},
                {"id": 2, "title": "结果2", "content": f"另一个关于'{query_text}'的结果"}
            ],
            "total": 2
        }
        
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@app.post("/intents", response_model=IntentResponse)
async def get_intents(request: IntentRequest):
    """
    意图识别端点
    接收文本并返回识别的意图
    """
    try:
        text = request.text
        context = request.context or {}
        
        # 简单的意图识别逻辑（示例）
        # 实际应用中可以使用NLP模型进行意图识别
        intent = "unknown"
        confidence = 0.5
        
        text_lower = text.lower()
        if "查询" in text or "搜索" in text or "find" in text_lower:
            intent = "query"
            confidence = 0.9
        elif "上传" in text or "upload" in text_lower:
            intent = "upload"
            confidence = 0.85
        elif "帮助" in text or "help" in text_lower:
            intent = "help"
            confidence = 0.8
        else:
            intent = "general"
            confidence = 0.6
        
        # 模拟实体提取
        entities = [
            {"type": "text", "value": text, "start": 0, "end": len(text)}
        ]
        
        return IntentResponse(
            intent=intent,
            confidence=confidence,
            entities=entities
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"意图识别失败: {str(e)}")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "FastAPI Web应用"}


# 运行应用
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
