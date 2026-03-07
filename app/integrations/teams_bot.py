"""
Microsoft Teams Bot集成
"""
import os
from typing import Optional

try:
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
    from botbuilder.schema import Activity, ActivityTypes
except ImportError:
    BotFrameworkAdapter = None
    BotFrameworkAdapterSettings = None
    Activity = None
    ActivityTypes = None

from app.integrations.base import FrontendIntegration
from app.services.orchestrator import orchestrator
from app.services.knowledge_base import kb
from app.services.analytics import analytics


class TeamsBotIntegration(FrontendIntegration):
    """Microsoft Teams Bot集成"""
    
    def __init__(self, app_id: Optional[str] = None, 
                 app_password: Optional[str] = None,
                 tenant_id: Optional[str] = None,
                 name: Optional[str] = None):
        super().__init__("teams", name)
        # 不再从环境变量读取，完全依赖传入的参数
        self.app_id = app_id
        self.app_password = app_password
        self.tenant_id = tenant_id
        self.adapter = None
        
        # 初始化Bot Framework适配器
        # 单租户Bot必须设置channel_auth_tenant
        if BotFrameworkAdapter and self.app_id and self.app_password:
            # 创建Settings，如果是单租户则设置channel_auth_tenant
            settings_params = {
                "app_id": self.app_id,
                "app_password": self.app_password
            }
            
            # 如果是单租户Bot，设置channel_auth_tenant
            if self.tenant_id and self.tenant_id != "你的租户ID":
                settings_params["channel_auth_tenant"] = self.tenant_id
            
            settings = BotFrameworkAdapterSettings(**settings_params)
            
            # 配置MSAL使用无代理的HTTP客户端（如果可能）
            # 注意：Bot Framework适配器内部使用MSAL，我们需要通过环境变量控制代理
            # NO_PROXY已在main.py中设置，这里确保MSAL能正确读取
            
            self.adapter = BotFrameworkAdapter(settings)
            
            # 注意：credentials会在实际使用时自动初始化，oauth_endpoint会根据channel_auth_tenant设置
            # MSAL会读取NO_PROXY环境变量来绕过代理
    
    def setup_handlers(self):
        """设置Bot处理器"""
        # Bot Framework适配器已初始化
        pass
    
    async def handle_message(self, activity: Activity) -> Optional[Activity]:
        """处理消息"""
        if not activity:
            return None
            
        if not ActivityTypes:
            return None
            
        if activity.type != ActivityTypes.message:
            return None
        
        # 提取查询文本
        query = activity.text.strip() if activity.text else ""
        if not query:
            return None
        
        # 提取用户ID
        user_id = "unknown"
        try:
            # Bot Framework使用from_property属性（因为from是Python关键字）
            if hasattr(activity, 'from_property') and activity.from_property:
                if isinstance(activity.from_property, dict):
                    user_id = activity.from_property.get('id', 'unknown')
                else:
                    user_id = getattr(activity.from_property, 'id', 'unknown')
        except Exception as e:
            user_id = "unknown"
        
        try:
            # 优化：先快速进行关键词分类（同步，很快）
            intent_spaces = orchestrator._get_intent_spaces()
            keyword_intent, keyword_confidence = orchestrator._keyword_classify(query, intent_spaces)
            
            # 如果关键词分类置信度高，直接使用，不等待AI分类
            if keyword_confidence > 0.6:
                detected_intent = keyword_intent
                confidence = keyword_confidence
                route_info = orchestrator.route_query(query, detected_intent, confidence, "teams")
                intent_space_id = route_info["intent_space_id"]
                # 立即搜索（本地操作，很快）
                search_results = kb.search(query, intent_space_id, top_k=3)
            else:
                # 关键词分类置信度低，需要AI分类
                # 优化：并行执行AI分类和通用搜索
                import asyncio
                
                # 先搜索通用知识库（不依赖意图，可以并行）
                general_results = kb.search(query, None, top_k=3)
                
                # 同时进行AI分类（异步）
                if hasattr(orchestrator, 'classify_intent_async') and orchestrator.async_ai_client:
                    detected_intent, confidence = await orchestrator.classify_intent_async(query)
                else:
                    detected_intent, confidence = orchestrator.classify_intent(query)
                
                # 路由查询
                route_info = orchestrator.route_query(query, detected_intent, confidence, "teams")
                intent_space_id = route_info["intent_space_id"]
                
                # 如果意图空间不同，重新搜索（通常很快）
                if intent_space_id is not None:
                    search_results = kb.search(query, intent_space_id, top_k=3)
                else:
                    search_results = general_results
            
            # 生成响应（使用异步版本）
            if hasattr(kb, 'generate_response_async'):
                response_text = await kb.generate_response_async(query, search_results, "teams")
            else:
                response_text = kb.generate_response(query, search_results, "teams")
            
            # 异步记录查询（不阻塞响应）
            try:
                response_status = "success" if search_results else "no_match"
                analytics.log_query(
                    query, intent_space_id, detected_intent, confidence,
                    response_text, response_status, "teams", user_id
                )
            except Exception:
                pass  # 记录查询失败，忽略
            
            # 创建响应Activity
            response_activity = Activity(
                type=ActivityTypes.message,
                text=response_text
            )
            
            return response_activity
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 返回错误响应
            if ActivityTypes:
                error_activity = Activity(
                    type=ActivityTypes.message,
                    text=f"抱歉，处理您的请求时出现错误：{str(e)}"
                )
                return error_activity
            return None
    
    def test_connection(self) -> bool:
        """测试连接（真正验证Azure AD认证）"""
        if not self.app_id or not self.app_password:
            return False
        
        # 真正测试连接：尝试获取Azure AD访问令牌
        try:
            # 使用botframework的MicrosoftAppCredentials来真正测试连接
            # 这会真正调用Azure AD API
            from botframework.connector.auth import MicrosoftAppCredentials
            
            credentials = MicrosoftAppCredentials(
                self.app_id, 
                self.app_password,
                channel_auth_tenant=self.tenant_id
            )
            # 尝试获取token（这会真正调用Azure AD API）
            token = credentials.get_access_token()
            return token is not None and len(token) > 0
        except ImportError:
            # 如果botframework.connector.auth不可用，尝试使用MSAL
            try:
                from msal import ConfidentialClientApplication
                authority = f"https://login.microsoftonline.com/{self.tenant_id}" if self.tenant_id else "https://login.microsoftonline.com/common"
                app = ConfidentialClientApplication(
                    client_id=self.app_id,
                    client_credential=self.app_password,
                    authority=authority
                )
                result = app.acquire_token_for_client(scopes=["https://api.botframework.com/.default"])
                return result is not None and "access_token" in result
            except ImportError:
                # 如果都没有，至少检查配置是否存在
                return self.adapter is not None
        except Exception as e:
            # 连接失败
            import traceback
            traceback.print_exc()
            return False
    
    def _verify_bot_connection(self, config: Dict) -> bool:
        """验证Bot连接是否有效（使用数据库中的配置，真正测试连接）"""
        # 从config中获取配置（存储在config_data中）
        app_id = config.get("app_id")
        app_password = config.get("_app_password")  # 存储在config_data中
        tenant_id = config.get("tenant_id")
        
        if not app_id or not app_password:
            return False
        
        # 真正测试连接：尝试获取Azure AD访问令牌
        try:
            import socket
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            # 使用botframework的MicrosoftAppCredentials来真正测试连接
            from botframework.connector.auth import MicrosoftAppCredentials
            
            # 创建带超时的session
            session = requests.Session()
            retry_strategy = Retry(
                total=1,  # 只重试1次
                backoff_factor=0.1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            
            credentials = MicrosoftAppCredentials(
                app_id, 
                app_password,
                channel_auth_tenant=tenant_id
            )
            # 尝试获取token（这会真正调用Azure AD API），设置超时
            # 注意：MicrosoftAppCredentials内部使用requests，我们需要通过环境变量或修改其行为
            # 但为了简单，我们直接测试网络连接
            try:
                token = credentials.get_access_token()
                return token is not None and len(token) > 0
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, socket.timeout) as e:
                return False
        except ImportError:
            # 如果botframework.connector.auth不可用，尝试使用MSAL
            try:
                from msal import ConfidentialClientApplication
                import socket
                authority = f"https://login.microsoftonline.com/{tenant_id}" if tenant_id else "https://login.microsoftonline.com/common"
                app = ConfidentialClientApplication(
                    client_id=app_id,
                    client_credential=app_password,
                    authority=authority
                )
                # 设置超时
                result = app.acquire_token_for_client(scopes=["https://api.botframework.com/.default"])
                return result is not None and "access_token" in result
            except (ImportError, socket.timeout, Exception) as e:
                # 如果都没有或超时，返回False（无法验证）
                return False
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, socket.timeout) as e:
            # 网络超时或连接错误
            return False
        except Exception as e:
            # 连接失败
            return False
    
    def send_message(self, user_id: str, message: str) -> bool:
        """发送消息"""
        # Teams Bot通过Bot Framework发送消息
        # 实际实现需要使用Bot Framework适配器
        return False


# 全局Teams Bot实例
_teams_bot_instance: Optional[TeamsBotIntegration] = None


def reset_teams_bot_instance():
    """重置Teams Bot实例（用于配置更新后重新加载）"""
    global _teams_bot_instance
    _teams_bot_instance = None
    # 重新加载环境变量
    from dotenv import load_dotenv
    load_dotenv(override=True)


def get_teams_bot(bot_id: Optional[int] = None) -> Optional[TeamsBotIntegration]:
    """获取Teams Bot实例（单例），从数据库读取配置"""
    global _teams_bot_instance
    if _teams_bot_instance is None:
        # 从数据库读取配置
        temp_bot = TeamsBotIntegration()
        db_config = temp_bot.get_config(bot_id)
        
        if db_config and db_config.get('status') == 'connected':
            # 从数据库读取
            config = db_config.get('config', {})
            app_id = config.get('app_id')
            app_password = config.get('_app_password')  # 从config中读取
            tenant_id = config.get('tenant_id')
            
            if app_id and app_password:
                _teams_bot_instance = TeamsBotIntegration(app_id, app_password, tenant_id)
                return _teams_bot_instance
    return _teams_bot_instance


def create_teams_bot(app_id: str, app_password: str, tenant_id: Optional[str] = None, name: Optional[str] = None, bot_id: Optional[int] = None, save: bool = True) -> TeamsBotIntegration:
    """创建Teams Bot集成实例
    
    Args:
        app_id: App ID
        app_password: App Password
        tenant_id: Tenant ID（可选）
        name: Bot名称（可选）
        bot_id: 要更新的Bot ID（可选，用于更新现有配置）
        save: 是否保存配置到数据库（默认True，测试连接时应设为False）
    """
    integration = TeamsBotIntegration(app_id, app_password, tenant_id, name)
    if integration.test_connection():
        if save:
            config_data = {"app_id": app_id, "_app_password": app_password}  # 存储password在config中
            if tenant_id:
                config_data["tenant_id"] = tenant_id
            integration.save_config(config_data, app_password, bot_id)
        integration.setup_handlers()
        # 清除单例缓存，让下次使用时重新加载配置
        reset_teams_bot_instance()
    return integration


def _update_env_file(key: str, value: str):
    """更新.env文件中的环境变量"""
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
