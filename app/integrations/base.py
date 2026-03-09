"""
前端集成基类
"""
import json
import hashlib
import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

from app.models.database import db


class FrontendIntegration:
    """前端集成基类"""
    
    def __init__(self, frontend_type: str, name: Optional[str] = None):
        self.frontend_type = frontend_type
        self.name = name or "default"  # 默认名称
    
    def save_config(self, config_data: Dict, api_key: Optional[str] = None, bot_id: Optional[int] = None):
        """保存集成配置。

        现在的约束：每种 frontend_type 只保留一个“当前配置”。
        - 如指定 bot_id，则更新该记录；
        - 如未指定 bot_id，则优先覆盖该 frontend_type 最新的一条记录，没有则插入新记录。
        """
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 哈希API Key（只存储后4位）
        api_key_hash = None
        if api_key:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[-4:]
        
        # 将api_key也存储在config_data中（加密存储）
        if api_key:
            config_data["_api_key"] = api_key  # 存储完整key用于验证
        
        config_json = json.dumps(config_data, ensure_ascii=False)
        
        if bot_id:
            # 更新指定实例
            cursor.execute("""
                UPDATE frontend_integrations 
                SET name = ?, status = 'connected', config_data = ?, api_key_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (self.name, config_json, api_key_hash, bot_id))
        else:
            # 未指定 ID：每种 frontend_type 仅保留一个配置，如已存在则覆盖最新一条
            cursor.execute("""
                SELECT id FROM frontend_integrations
                WHERE frontend_type = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (self.frontend_type,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE frontend_integrations
                    SET name = ?, status = 'connected', config_data = ?, api_key_hash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (self.name, config_json, api_key_hash, row["id"]))
            else:
                cursor.execute("""
                    INSERT INTO frontend_integrations 
                    (frontend_type, name, status, config_data, api_key_hash, updated_at)
                    VALUES (?, ?, 'connected', ?, ?, CURRENT_TIMESTAMP)
                """, (
                    self.frontend_type,
                    self.name,
                    config_json,
                    api_key_hash
                ))
        
        conn.commit()
        conn.close()
    
    def get_all_configs(self, verify_connection: bool = True) -> List[Dict]:
        """获取所有配置实例。verify_connection=True 时真正测试连接并更新状态；False 时仅读库，加载更快。"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, status, config_data, api_key_hash, last_tested, updated_at
            FROM frontend_integrations
            WHERE frontend_type = ?
            ORDER BY updated_at DESC
        """, (self.frontend_type,))
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            config = json.loads(row["config_data"]) if row["config_data"] else {}
            if verify_connection:
                # 真正验证连接状态（调用API测试）
                is_connected = False
                try:
                    is_connected = self._verify_bot_connection(config)
                except Exception:
                    logger.exception("验证Bot连接失败")
                actual_status = "connected" if is_connected else "disconnected"
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE frontend_integrations 
                    SET status = ?, last_tested = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (actual_status, row["id"]))
                conn.commit()
                conn.close()
            else:
                actual_status = row["status"] or "disconnected"
            
            result.append({
                "id": row["id"],
                "name": row["name"] or "default",
                "status": actual_status,
                "config": config,
                "api_key_hash": row["api_key_hash"],
                "last_tested": datetime.now().isoformat(),
                "updated_at": row["updated_at"]
            })
        
        return result
    
    def get_config(self, bot_id: Optional[int] = None) -> Optional[Dict]:
        """获取指定Bot实例的配置（兼容旧代码，返回第一个）"""
        configs = self.get_all_configs()
        if not configs:
            return None
        
        if bot_id:
            # 返回指定ID的配置
            for config in configs:
                if config["id"] == bot_id:
                    return config
            return None
        else:
            # 返回第一个配置（兼容旧代码）
            return configs[0] if configs else None
    
    def _verify_bot_connection(self, config: Dict) -> bool:
        """验证Bot连接是否有效（使用数据库中的配置）"""
        # 子类实现，使用config中的配置而不是环境变量
        raise NotImplementedError("子类必须实现_verify_bot_connection方法")
    
    def test_connection(self) -> bool:
        """测试连接"""
        # 子类实现
        raise NotImplementedError("子类必须实现test_connection方法")
    
    def send_message(self, user_id: str, message: str) -> bool:
        """发送消息"""
        # 子类实现
        raise NotImplementedError("子类必须实现send_message方法")
