"""
Bot连接状态监控服务
定期检测所有Bot的连接状态并更新数据库
"""
import asyncio
import json
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

from app.models.database import db
from app.integrations.telegram_bot import TelegramBotIntegration
from app.integrations.teams_bot import TeamsBotIntegration


class BotMonitor:
    """Bot连接状态监控器"""
    
    def __init__(self, check_interval: int = 300):  # 默认5分钟
        self.check_interval = check_interval
        self.is_running = False
        self._task = None
    
    async def check_all_bots(self):
        """检测所有Bot的连接状态"""
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # 获取所有Bot配置
            cursor.execute("""
                SELECT id, frontend_type, name, status, config_data
                FROM frontend_integrations
            """)
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return
            
            updated_count = 0
            for row in rows:
                bot_id = row["id"]
                frontend_type = row["frontend_type"]
                old_status = row["status"]
                config_data = json.loads(row["config_data"]) if row["config_data"] else {}
                
                # 根据类型创建对应的集成实例
                if frontend_type == "telegram":
                    integration = TelegramBotIntegration()
                elif frontend_type == "teams":
                    integration = TeamsBotIntegration()
                else:
                    continue
                
                # 验证连接状态（在事件循环中运行同步函数）
                is_connected = False
                try:
                    # 使用run_in_executor在线程池中运行同步的验证函数，避免阻塞事件循环
                    loop = asyncio.get_event_loop()
                    is_connected = await loop.run_in_executor(
                        None, 
                        integration._verify_bot_connection, 
                        config_data
                    )
                except Exception as e:
                    is_connected = False
                
                actual_status = "connected" if is_connected else "disconnected"
                
                # 更新数据库状态
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE frontend_integrations 
                    SET status = ?, last_tested = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (actual_status, bot_id))
                conn.commit()
                conn.close()
                
                if old_status != actual_status:
                    updated_count += 1
            
        except Exception:
            logger.exception("检测Bot连接状态失败")

    async def run_periodic_check(self):
        """定期执行检测任务"""
        self.is_running = True
        
        # 启动时立即执行一次检测
        try:
            await self.check_all_bots()
        except Exception:
            logger.exception("启动时检测Bot失败")
        # 然后定期执行检测
        while self.is_running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_all_bots()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("定期检测Bot失败")

    def start(self):
        """启动监控服务"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_periodic_check())
    
    def stop(self):
        """停止监控服务"""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()


# 全局监控器实例
bot_monitor = BotMonitor(check_interval=300)  # 5分钟
