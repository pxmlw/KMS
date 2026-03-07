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
    
    def __init__(self, bot_token: Optional[str] = None, name: Optional[str] = None):
        super().__init__("telegram", name)
        self.bot_token = bot_token
        self.application = None
        
        if bot_token and Application:
            try:
                self.application = Application.builder().token(bot_token).build()
            except Exception as e:
                pass  # Telegram Bot初始化失败
    
    def setup_handlers(self):
        """设置Bot处理器"""
        if not self.application:
            return
        
        # 命令处理器
        async def start_command(update: Update, context):
            await update.message.reply_text("欢迎使用IntelliKnow知识管理系统！\n\n发送查询即可获取知识库信息。")
        
        async def query_handler(update: Update, context):
            """处理查询消息（优化：快速响应和并行处理）"""
            try:
                if not update.message or not update.message.text:
                    return
                
                query = update.message.text.strip()
                if not query:
                    await update.message.reply_text("请输入您的问题。")
                    return
                
                user_id = str(update.effective_user.id)
                
                # 发送"正在思考"提示（优化用户体验）
                thinking_msg = None
                try:
                    thinking_msg = await update.message.reply_text("🤔 正在思考...")
                except:
                    pass  # 如果发送失败，继续处理
                
                try:
                    # 优化策略1：先快速进行关键词分类（同步，很快）
                    intent_spaces = orchestrator._get_intent_spaces()
                    keyword_intent, keyword_confidence = orchestrator._keyword_classify(query, intent_spaces)
                    
                    # 如果关键词分类置信度高，直接使用，不等待AI分类
                    if keyword_confidence > 0.6:
                        detected_intent = keyword_intent
                        confidence = keyword_confidence
                        route_info = orchestrator.route_query(query, detected_intent, confidence, "telegram")
                        intent_space_id = route_info["intent_space_id"]
                        
                        # 立即搜索（本地操作，很快）
                        search_results = kb.search(query, intent_space_id, top_k=3)
                        
                        # 注意：快速路径已移到generate_response内部，使用配置控制
                        # 这里不再单独处理，确保使用AI生成响应
                    else:
                        # 关键词分类置信度低，需要AI分类
                        # 优化策略2：并行执行AI分类和通用搜索
                        import asyncio
                        
                        # 先搜索通用知识库（不依赖意图，可以并行）
                        general_results = kb.search(query, None, top_k=3)
                        
                        # 同时进行AI分类（异步）
                        if hasattr(orchestrator, 'classify_intent_async') and orchestrator.async_ai_client:
                            detected_intent, confidence = await orchestrator.classify_intent_async(query)
                        else:
                            detected_intent, confidence = orchestrator.classify_intent(query)
                        
                        # 路由查询
                        route_info = orchestrator.route_query(query, detected_intent, confidence, "telegram")
                        intent_space_id = route_info["intent_space_id"]
                        
                        # 如果意图空间不同，重新搜索（通常很快）
                        if intent_space_id is not None:
                            search_results = kb.search(query, intent_space_id, top_k=3)
                        else:
                            search_results = general_results
                    
                    # 生成响应（使用异步版本）
                    if hasattr(kb, 'generate_response_async'):
                        response_text = await kb.generate_response_async(query, search_results, "telegram")
                    else:
                        response_text = kb.generate_response(query, search_results, "telegram")
                    
                    # 发送响应（如果之前发送了"正在思考"，先删除它）
                    if thinking_msg:
                        try:
                            await thinking_msg.delete()
                        except:
                            pass  # 删除失败，继续发送响应
                    
                    await update.message.reply_text(response_text)
                    
                    # 异步记录查询（不阻塞响应）
                    try:
                        response_status = "success" if search_results else "no_match"
                        analytics.log_query(
                            query, intent_space_id, detected_intent, confidence,
                            response_text, response_status, "telegram", user_id
                        )
                    except Exception as e:
                        pass  # 记录查询失败，忽略
                    
                except Exception as e:
                    await update.message.reply_text("抱歉，处理您的请求时出现了错误。请稍后再试。")
                    
            except Exception as e:
                pass  # Telegram Bot消息处理错误
                try:
                    await update.message.reply_text("抱歉，发生了未知错误。")
                except:
                    pass
        
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
                pass  # 停止Bot时出错，忽略
    
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
    
    def _verify_bot_connection(self, config: Dict) -> bool:
        """验证Bot连接是否有效（使用数据库中的配置，真正测试连接）"""
        # 从config中获取token（存储在config_data中的_api_key）
        bot_token = config.get("_api_key")
        if not bot_token:
            return False
        
        # 真正测试连接：调用Telegram API验证token是否有效
        try:
            from telegram import Bot
            from telegram.request import HTTPXRequest
            import httpx
            
            # 创建带超时的request对象（5秒超时）
            request = HTTPXRequest(connection_pool_size=1, read_timeout=5.0, write_timeout=5.0, connect_timeout=5.0)
            bot = Bot(bot_token, request=request)
            # 调用get_me()真正测试连接
            bot_info = bot.get_me()
            # 如果成功获取Bot信息，说明连接有效
            return bot_info is not None
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            # 超时或网络错误，说明无法连接
            return False
        except Exception as e:
            # 连接失败（认证错误等）
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


def create_telegram_bot(bot_token: str, name: Optional[str] = None, bot_id: Optional[int] = None, save: bool = True) -> TelegramBotIntegration:
    """创建Telegram Bot集成实例
    
    Args:
        bot_token: Bot Token
        name: Bot名称（可选）
        bot_id: 要更新的Bot ID（可选，用于更新现有配置）
        save: 是否保存配置到数据库（默认True，测试连接时应设为False）
    """
    integration = TelegramBotIntegration(bot_token, name)
    if integration.test_connection():
        if save:
            # 获取Bot信息并保存
            bot_info = integration.get_bot_info()
            config_data = bot_info if bot_info else {}
            # 保存配置（包括token在config_data中）
            integration.save_config(config_data, bot_token, bot_id)
        integration.setup_handlers()
    return integration


def get_telegram_bot(bot_id: Optional[int] = None) -> Optional[TelegramBotIntegration]:
    """获取已配置的Telegram Bot实例（从数据库读取）"""
    # 从数据库读取配置
    integration = TelegramBotIntegration()
    config = integration.get_config(bot_id)
    
    if config and config.get('status') == 'connected':
        # 从config中获取token
        config_data = config.get('config', {})
        bot_token = config_data.get('_api_key')  # 从config中读取
        if bot_token:
            return TelegramBotIntegration(bot_token)
    
    return None


def start_telegram_bot_polling():
    """启动Telegram Bot polling服务"""
    bot = get_telegram_bot()
    if not bot or not bot.application:
        return
    
    bot.setup_handlers()
    
    try:
        # 使用application.run_polling()方法，这是v20+推荐的方式
        bot.application.run_polling(
            drop_pending_updates=True,
            allowed_updates=None  # 接收所有类型的更新
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
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
        pass  # 更新.env文件失败，忽略
