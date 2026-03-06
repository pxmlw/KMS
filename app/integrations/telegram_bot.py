"""
Telegram Bot集成
"""
import os
from typing import Optional, Dict
import asyncio

try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
except ImportError:
    Bot = None
    Application = None

from app.integrations.base import FrontendIntegration
from app.services.orchestrator import orchestrator
from app.services.knowledge_base import kb
from app.services.analytics import analytics


class TelegramBotIntegration(FrontendIntegration):
    """Telegram Bot集成"""
    
    def __init__(self, bot_token: Optional[str] = None):
        super().__init__("telegram")
        self.bot_token = bot_token
        self.application = None
        
        if bot_token and Application:
            try:
                self.application = Application.builder().token(bot_token).build()
            except Exception as e:
                print(f"Telegram Bot初始化失败: {e}")
    
    def setup_handlers(self):
        """设置Bot处理器"""
        if not self.application:
            return
        
        # 命令处理器
        async def start_command(update: Update, context):
            await update.message.reply_text("欢迎使用IntelliKnow知识管理系统！\n\n发送查询即可获取知识库信息。")
        
        async def query_handler(update: Update, context):
            """处理查询消息"""
            query = update.message.text.strip()
            user_id = str(update.effective_user.id)
            
            # 意图分类
            detected_intent, confidence = orchestrator.classify_intent(query)
            
            # 路由查询
            route_info = orchestrator.route_query(
                query, detected_intent, confidence, "telegram"
            )
            intent_space_id = route_info["intent_space_id"]
            
            # 知识库搜索
            search_results = kb.search(query, intent_space_id, top_k=3)
            
            # 生成响应
            response_text = kb.generate_response(query, search_results, "telegram")
            
            # 记录查询
            response_status = "success" if search_results else "no_match"
            analytics.log_query(
                query, intent_space_id, detected_intent, confidence,
                response_text, response_status, "telegram", user_id
            )
            
            # 发送响应
            await update.message.reply_text(response_text)
        
        # 注册处理器
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler))
    
    async def start(self):
        """启动Bot"""
        if self.application:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
    
    async def stop(self):
        """停止Bot"""
        if self.application:
            try:
                # 先停止polling
                if self.application.updater.running:
                    await self.application.updater.stop()
                # 然后停止application
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                print(f"停止Bot时出错: {e}")
    
    def test_connection(self) -> bool:
        """测试连接"""
        if not self.bot_token:
            return False
        try:
            bot = Bot(self.bot_token)
            bot_info = bot.get_me()
            return True
        except Exception:
            return False
    
    def get_bot_info(self) -> Optional[Dict]:
        """获取Bot详细信息"""
        if not self.bot_token:
            return None
        try:
            bot = Bot(self.bot_token)
            bot_info = bot.get_me()
            return {
                "id": bot_info.id,
                "username": bot_info.username,
                "first_name": bot_info.first_name,
                "can_join_groups": bot_info.can_join_groups,
                "can_read_all_group_messages": bot_info.can_read_all_group_messages,
                "supports_inline_queries": bot_info.supports_inline_queries
            }
        except Exception as e:
            print(f"获取Bot信息失败: {e}")
            return None
    
    def send_message(self, user_id: str, message: str) -> bool:
        """发送消息"""
        if not self.application:
            return False
        try:
            # 这里需要实现发送逻辑
            # Telegram Bot通常通过webhook或polling接收消息
            return True
        except Exception:
            return False


def create_telegram_bot(bot_token: str) -> TelegramBotIntegration:
    """创建Telegram Bot集成实例"""
    integration = TelegramBotIntegration(bot_token)
    if integration.test_connection():
        # 获取Bot信息并保存
        bot_info = integration.get_bot_info()
        config_data = bot_info if bot_info else {}
        integration.save_config(config_data, bot_token)
        integration.setup_handlers()
        # 更新.env文件
        _update_env_file("TELEGRAM_BOT_TOKEN", bot_token)
        # 重新加载环境变量（Telegram Bot没有单例，但需要更新环境变量）
        from dotenv import load_dotenv
        load_dotenv(override=True)
    return integration


def get_telegram_bot() -> Optional[TelegramBotIntegration]:
    """获取已配置的Telegram Bot实例（从数据库或环境变量）"""
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    # 优先从数据库读取配置
    integration = TelegramBotIntegration()
    config = integration.get_config()
    
    if config and config.get('status') == 'connected':
        # 从环境变量获取token（数据库不存储完整token）
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if bot_token:
            return TelegramBotIntegration(bot_token)
    
    # 如果数据库没有配置，尝试从环境变量读取
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if bot_token:
        return TelegramBotIntegration(bot_token)
    
    return None


def start_telegram_bot_polling():
    """启动Telegram Bot polling服务"""
    bot = get_telegram_bot()
    if not bot or not bot.application:
        print("❌ Telegram Bot未配置或初始化失败")
        print("提示：请在管理界面配置Telegram Bot Token")
        return
    
    bot.setup_handlers()
    
    # 显示Bot信息
    bot_info = bot.get_bot_info()
    if bot_info:
        print(f"✅ Telegram Bot配置成功！")
        print(f"   Bot用户名: @{bot_info.get('username', 'N/A')}")
        print(f"   Bot名称: {bot_info.get('first_name', 'N/A')}")
    
    print("正在启动Telegram Bot polling服务...")
    print("正在监听消息...（按 Ctrl+C 停止）")
    
    try:
        # 使用application.run_polling()方法，这是v20+推荐的方式
        bot.application.run_polling(
            drop_pending_updates=True,
            allowed_updates=None  # 接收所有类型的更新
        )
    except KeyboardInterrupt:
        print("\n正在停止Telegram Bot...")
        print("Telegram Bot已停止")
    except Exception as e:
        print(f"❌ Telegram Bot运行错误: {e}")
        import traceback
        traceback.print_exc()


def _update_env_file(key: str, value: str):
    """更新.env文件中的环境变量"""
    import os
    try:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if not os.path.exists(env_file):
            return
        
        # 读取现有内容
        with open(env_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 查找并更新或添加
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        
        if not found:
            lines.append(f"{key}={value}\n")
        
        # 写回文件
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"警告：更新.env文件失败: {e}")
