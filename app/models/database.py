"""
数据库模型和配置
使用SQLite作为轻量级数据库
"""
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path
import json


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path: str = "data/kms.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 文档表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_format TEXT NOT NULL,
                file_size INTEGER,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                intent_space_id INTEGER,
                processed_content TEXT,
                metadata TEXT,
                FOREIGN KEY (intent_space_id) REFERENCES intent_spaces(id)
            )
        """)
        
        # 意图空间表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS intent_spaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 查询历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                intent_space_id INTEGER,
                detected_intent TEXT,
                confidence REAL,
                response_text TEXT,
                response_status TEXT,
                frontend_type TEXT,
                frontend_user_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (intent_space_id) REFERENCES intent_spaces(id)
            )
        """)
        
        # 前端集成配置表（支持多个Bot实例）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS frontend_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frontend_type TEXT NOT NULL,
                name TEXT,
                status TEXT DEFAULT 'disconnected',
                config_data TEXT,
                api_key_hash TEXT,
                last_tested TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 添加name字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE frontend_integrations ADD COLUMN name TEXT")
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        # 分析指标表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 全局配置表（用于存储webhook URL等全局配置）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 初始化默认意图空间
        self._init_default_intent_spaces(cursor)
        
        conn.commit()
        conn.close()
    
    def _init_default_intent_spaces(self, cursor):
        """初始化默认意图空间（HR, Legal, Finance）"""
        default_spaces = [
            ("HR", "人力资源相关问题，包括招聘、员工政策、福利等", "招聘,员工,福利,政策,薪资,假期,培训"),
            ("Legal", "法律相关问题，包括合同、合规、法规等", "合同,法律,合规,法规,诉讼,知识产权"),
            ("Finance", "财务相关问题，包括预算、报销、财务报告等", "预算,报销,财务,会计,发票,成本")
        ]
        
        for name, description, keywords in default_spaces:
            cursor.execute("""
                INSERT OR IGNORE INTO intent_spaces (name, description, keywords)
                VALUES (?, ?, ?)
            """, (name, description, keywords))
    
    def close(self):
        """关闭数据库连接"""
        pass  # SQLite会自动管理连接


# 数据库实例
db = Database()
