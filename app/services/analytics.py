"""
分析和历史服务
记录查询历史、跟踪指标、知识库使用统计
"""
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from collections import Counter

from app.models.database import db


def utc_to_beijing(utc_time_str: str) -> str:
    """将UTC时间字符串转换为北京时间（UTC+8）"""
    try:
        # 解析UTC时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        if isinstance(utc_time_str, str) and ' ' in utc_time_str:
            dt = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M:%S")
        else:
            return utc_time_str  # 如果格式不对，直接返回
        
        # UTC时区
        utc_dt = dt.replace(tzinfo=timezone.utc)
        # 转换为北京时间（UTC+8）
        beijing_tz = timezone(timedelta(hours=8))
        beijing_dt = utc_dt.astimezone(beijing_tz)
        
        # 返回格式化字符串
        return beijing_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return utc_time_str  # 转换失败时返回原值


class Analytics:
    """分析服务"""
    
    def log_query(self, query: str, intent_space_id: Optional[int], 
                  detected_intent: str, confidence: float,
                  response_text: str, response_status: str,
                  frontend_type: str, frontend_user_id: Optional[str] = None):
        """
        记录查询历史
        """
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO query_history 
            (query_text, intent_space_id, detected_intent, confidence, response_text, 
             response_status, frontend_type, frontend_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            query,
            intent_space_id,
            detected_intent,
            confidence,
            response_text[:1000],  # 限制长度
            response_status,
            frontend_type,
            frontend_user_id
        ))
        
        conn.commit()
        conn.close()
    
    def get_query_history(self, limit: int = 100) -> List[Dict]:
        """获取查询历史"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT qh.*, intent_spaces.name AS intent_space_name
            FROM query_history qh
            LEFT JOIN intent_spaces ON qh.intent_space_id = intent_spaces.id
            ORDER BY qh.timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row["id"],
                "query_text": row["query_text"],
                "intent_space_name": row["intent_space_name"] if row["intent_space_name"] else None,
                "detected_intent": row["detected_intent"],
                "confidence": row["confidence"],
                "response_status": row["response_status"],
                "frontend_type": row["frontend_type"],
                "timestamp": utc_to_beijing(row["timestamp"])  # 转换为北京时间
            }
            for row in rows
        ]
    
    def get_classification_accuracy(self, hours: int = 24) -> Dict:
        """
        获取分类准确率统计（按小时计算）
        
        注意：这里的"准确率"实际上是"高置信度查询的比例"（置信度 >= 阈值的查询数 / 总查询数）
        不是真正的准确率（因为没有真实标签来对比）
        
        Args:
            hours: 时间范围（小时数），默认24小时（1天）
        
        Returns:
            包含准确率指标的字典
        """
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 获取最近N小时的查询（修复时间比较问题）
        # 确保 hours 是整数，防止类型错误
        try:
            hours_int = int(hours) if hours else 24
            # 验证范围：1-720小时（30天）
            if hours_int < 1 or hours_int > 720:
                hours_int = 24  # 默认值
        except (ValueError, TypeError):
            hours_int = 24  # 默认值
        
        # 计算起始时间
        # 使用UTC时间进行计算（数据库存储的是UTC时间）
        now_utc = datetime.now(timezone.utc)
        since_date_utc = now_utc - timedelta(hours=hours_int)
        # SQLite TIMESTAMP 比较：转换为字符串格式进行比较（UTC时间）
        since_date_str = since_date_utc.strftime("%Y-%m-%d %H:%M:%S")
        
        # SQLite时间比较：使用julianday进行精确比较
        cursor.execute("""
            SELECT detected_intent, intent_space_id, confidence, timestamp
            FROM query_history
            WHERE julianday(timestamp) >= julianday(?)
            ORDER BY timestamp DESC
        """, (since_date_str,))
        rows = cursor.fetchall()
        
        # 注意：ORDER BY timestamp DESC，所以第一条是最新的，最后一条是最旧的
        if rows:
            # 将UTC时间转换为北京时间（UTC+8）
            first_timestamp = utc_to_beijing(rows[0]["timestamp"])  # 最新的时间戳
            last_timestamp = utc_to_beijing(rows[-1]["timestamp"])  # 最旧的时间戳
        else:
            first_timestamp = None
            last_timestamp = None
        
        conn.close()
        
        if not rows:
            return {
                "total_queries": 0,
                "average_confidence": 0.0,
                "accuracy_rate": 0.0,
                "intent_distribution": {},
                "period_hours": hours_int,
                "date_range": {
                    "since": since_date_str,
                    "first_query": None,
                    "last_query": None
                }
            }
        
        total = len(rows)
        confidences = [r["confidence"] or 0.0 for r in rows]  # 处理None值
        average_confidence = sum(confidences) / total if total > 0 else 0.0
        
        # 计算准确率（置信度>=阈值的比例）
        from app.config import AI_CONFIDENCE_THRESHOLD
        accurate_count = sum(1 for c in confidences if c and c >= AI_CONFIDENCE_THRESHOLD)
        accuracy_rate = accurate_count / total if total > 0 else 0.0
        
        # 意图分布（处理None值）
        intent_distribution = Counter(
            r["detected_intent"] or "Unknown" for r in rows
        )
        
        return {
            "total_queries": total,
            "average_confidence": average_confidence,
            "accuracy_rate": accuracy_rate,
            "intent_distribution": dict(intent_distribution),
            "period_hours": hours_int,
            "date_range": {
                "since": since_date_str,
                "first_query": first_timestamp,
                "last_query": last_timestamp
            },
            "confidence_stats": {
                "min": min(confidences) if confidences else 0.0,
                "max": max(confidences) if confidences else 0.0,
                "threshold": AI_CONFIDENCE_THRESHOLD,
                "above_threshold": accurate_count,
                "below_threshold": total - accurate_count
            }
        }
    
    def get_kb_usage(self) -> Dict:
        """获取知识库使用统计"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 文档统计
        cursor.execute("SELECT COUNT(*) AS total, COUNT(CASE WHEN status = 'processed' THEN 1 END) AS processed FROM documents")
        doc_stats = cursor.fetchone()
        
        # 最常访问的文档（通过查询历史）
        # 统计逻辑：
        # 1. 如果文档有意图空间，匹配相同意图空间的查询
        # 2. 如果文档是通用文档（intent_space_id为NULL），匹配所有查询
        cursor.execute("""
            SELECT d.id, d.filename, d.upload_date, 
                   COUNT(qh.id) AS access_count,
                   MAX(qh.timestamp) AS last_access_date
            FROM documents d
            INNER JOIN query_history qh ON (
                (d.intent_space_id IS NOT NULL AND qh.intent_space_id = d.intent_space_id)
                OR (d.intent_space_id IS NULL)
            )
            WHERE qh.response_status = 'success'
            GROUP BY d.id, d.filename, d.upload_date
            HAVING access_count > 0
            ORDER BY access_count DESC
            LIMIT 10
        """)
        top_docs = cursor.fetchall()
        
        # 最常用的意图空间
        cursor.execute("""
            SELECT intent_spaces.name, COUNT(qh.id) AS query_count
            FROM intent_spaces
            LEFT JOIN query_history qh ON intent_spaces.id = qh.intent_space_id
            GROUP BY intent_spaces.name
            ORDER BY query_count DESC
        """)
        top_intents = cursor.fetchall()
        
        conn.close()
        
        return {
            "total_documents": doc_stats["total"] or 0,
            "processed_documents": doc_stats["processed"] or 0,
            "top_accessed_documents": [
                {
                    "doc_id": row["id"],
                    "filename": row["filename"],
                    "upload_date": utc_to_beijing(row["upload_date"]) if row["upload_date"] else None,
                    "last_access_date": utc_to_beijing(row["last_access_date"]) if row["last_access_date"] else None,
                    "access_count": row["access_count"] or 0
                }
                for row in top_docs
            ],
            "top_intent_spaces": [
                {
                    "name": row["name"],
                    "query_count": row["query_count"] or 0
                }
                for row in top_intents
            ]
        }
    
    def export_data(self, format: str = "json") -> str:
        """
        导出分析数据
        
        Args:
            format: 导出格式（json/csv）
            
        Returns:
            导出文件路径
        """
        from pathlib import Path
        from app.config import DATA_DIR
        
        # 获取所有数据
        query_history = self.get_query_history(limit=10000)
        kb_usage = self.get_kb_usage()
        accuracy = self.get_classification_accuracy(24)  # 默认24小时
        
        data = {
            "query_history": query_history,
            "kb_usage": kb_usage,
            "accuracy": accuracy
        }
        
        # 导出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format == "json":
            export_path = DATA_DIR / f"analytics_export_{timestamp}.json"
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif format == "csv":
            import csv
            export_path = DATA_DIR / f"analytics_export_{timestamp}.csv"
            with open(export_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f)
                writer.writeheader(["query", "intent", "confidence", "status", "timestamp"])
                for qh in query_history:
                    writer.writerow({
                        "query": qh["query_text"],
                        "intent": qh.get("intent_space_name") or qh["detected_intent"],
                        "confidence": qh["confidence"],
                        "status": qh["response_status"],
                        "timestamp": qh["timestamp"]
                    })
        
        return str(export_path)


# 分析服务实例
analytics = Analytics()
