"""
前端集成基类
"""
import json
import hashlib
from typing import Dict, Optional
from datetime import datetime

from app.models.database import db


class FrontendIntegration:
    """前端集成基类"""
    
    def __init__(self, frontend_type: str):
        self.frontend_type = frontend_type
    
    def save_config(self, config_data: Dict, api_key: Optional[str] = None):
        """保存集成配置"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 哈希API Key（只存储后4位）
        api_key_hash = None
        if api_key:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[-4:]
        
        config_json = json.dumps(config_data, ensure_ascii=False)
        
        cursor.execute("""
            INSERT OR REPLACE INTO frontend_integrations 
            (frontend_type, status, config_data, api_key_hash, updated_at)
            VALUES (?, 'connected', ?, ?, CURRENT_TIMESTAMP)
        """, (
            self.frontend_type,
            config_json,
            api_key_hash
        ))
        
        conn.commit()
        conn.close()
    
    def get_config(self) -> Optional[Dict]:
        """获取集成配置"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, config_data, api_key_hash, last_tested
            FROM frontend_integrations
            WHERE frontend_type = ?
        """, (self.frontend_type,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        config = json.loads(row["config_data"]) if row["config_data"] else {}
        return {
            "status": row["status"],
            "config": config,
            "api_key_hash": row["api_key_hash"],
            "last_tested": row["last_tested"]
        }
    
    def test_connection(self) -> bool:
        """测试连接"""
        # 子类实现
        raise NotImplementedError("子类必须实现test_connection方法")
    
    def send_message(self, user_id: str, message: str) -> bool:
        """发送消息"""
        # 子类实现
        raise NotImplementedError("子类必须实现send_message方法")
