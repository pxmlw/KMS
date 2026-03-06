"""
分析和历史服务
记录查询历史、跟踪指标、知识库使用统计
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import Counter

from app.models.database import db


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
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]
    
    def get_classification_accuracy(self, days: int = 7) -> Dict:
        """
        获取分类准确率统计
        
        Returns:
            包含准确率指标的字典
        """
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 获取最近N天的查询
        since_date = datetime.now() - timedelta(days=days)
        cursor.execute("""
            SELECT detected_intent, intent_space_id, confidence
            FROM query_history
            WHERE timestamp >= ?
        """, (since_date,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {
                "total_queries": 0,
                "average_confidence": 0.0,
                "accuracy_rate": 0.0,
                "intent_distribution": {}
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
            "period_days": days
        }
    
    def get_kb_usage(self) -> Dict:
        """获取知识库使用统计"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 文档统计
        cursor.execute("SELECT COUNT(*) AS total, COUNT(CASE WHEN status = 'processed' THEN 1 END) AS processed FROM documents")
        doc_stats = cursor.fetchone()
        
        # 最常访问的文档（通过查询历史）
        cursor.execute("""
            SELECT d.id, d.filename, COUNT(qh.id) AS access_count
            FROM documents d
            LEFT JOIN query_history qh ON qh.intent_space_id = d.intent_space_id
            GROUP BY d.id, d.filename
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
        accuracy = self.get_classification_accuracy()
        
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
