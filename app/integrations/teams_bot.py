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
                 tenant_id: Optional[str] = None):
        super().__init__("teams")
        self.app_id = app_id or os.getenv("TEAMS_APP_ID")
        self.app_password = app_password or os.getenv("TEAMS_APP_PASSWORD")
        self.tenant_id = tenant_id or os.getenv("TEAMS_TENANT_ID")
        self.adapter = None
        
        # 初始化Bot Framework适配器
        # 单租户Bot必须设置channel_auth_tenant
        if BotFrameworkAdapter and self.app_id and self.app_password:
            print(f"DEBUG: 初始化Bot Framework适配器")
            print(f"DEBUG: App ID: {self.app_id}")
            print(f"DEBUG: App Password: {'已设置（长度: ' + str(len(self.app_password)) + '）' if self.app_password else '未设置'}")
            print(f"DEBUG: Tenant ID: {self.tenant_id or '未设置（多租户模式）'}")
            
            # 创建Settings，如果是单租户则设置channel_auth_tenant
            settings_params = {
                "app_id": self.app_id,
                "app_password": self.app_password
            }
            
            # 如果是单租户Bot，设置channel_auth_tenant
            if self.tenant_id and self.tenant_id != "你的租户ID":
                settings_params["channel_auth_tenant"] = self.tenant_id
                print(f"DEBUG: 使用单租户模式，channel_auth_tenant: {self.tenant_id}")
            else:
                print(f"DEBUG: 使用多租户模式（未设置tenant_id）")
            
            settings = BotFrameworkAdapterSettings(**settings_params)
            
            print(f"DEBUG: BotFrameworkAdapterSettings创建成功")
            print(f"DEBUG: Settings.app_id: {settings.app_id}")
            if hasattr(settings, 'channel_auth_tenant'):
                print(f"DEBUG: Settings.channel_auth_tenant: {getattr(settings, 'channel_auth_tenant', 'N/A')}")
            
            # 配置MSAL使用无代理的HTTP客户端（如果可能）
            # 注意：Bot Framework适配器内部使用MSAL，我们需要通过环境变量控制代理
            # NO_PROXY已在main.py中设置，这里确保MSAL能正确读取
            
            self.adapter = BotFrameworkAdapter(settings)
            print(f"DEBUG: Bot Framework适配器已初始化")
            print(f"DEBUG: 当前NO_PROXY: {os.environ.get('NO_PROXY', '未设置')}")
            
            # 注意：credentials会在实际使用时自动初始化，oauth_endpoint会根据channel_auth_tenant设置
            # MSAL会读取NO_PROXY环境变量来绕过代理
    
    def setup_handlers(self):
        """设置Bot处理器"""
        # Bot Framework适配器已初始化
        pass
    
    async def handle_message(self, activity: Activity) -> Optional[Activity]:
        """处理消息"""
        if not activity:
            print("ERROR: Activity为空")
            return None
            
        if not ActivityTypes:
            print("ERROR: ActivityTypes未导入")
            return None
            
        if activity.type != ActivityTypes.message:
            print(f"DEBUG: 忽略非消息类型的Activity: {activity.type}")
            return None
        
        # 提取查询文本
        query = activity.text.strip() if activity.text else ""
        if not query:
            print("DEBUG: 查询文本为空")
            return None
        
        print(f"DEBUG: 收到Teams消息: {query}")
        
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
            print(f"WARNING: 无法提取用户ID: {e}")
            user_id = "unknown"
        
        try:
            # 意图分类
            detected_intent, confidence = orchestrator.classify_intent(query)
            
            # 路由查询
            route_info = orchestrator.route_query(
                query, detected_intent, confidence, "teams"
            )
            intent_space_id = route_info["intent_space_id"]
            
            # 知识库搜索
            search_results = kb.search(query, intent_space_id, top_k=3)
            
            # 生成响应
            response_text = kb.generate_response(query, search_results, "teams")
            
            # 记录查询
            response_status = "success" if search_results else "no_match"
            analytics.log_query(
                query, intent_space_id, detected_intent, confidence,
                response_text, response_status, "teams", user_id
            )
            
            # 创建响应Activity
            response_activity = Activity(
                type=ActivityTypes.message,
                text=response_text
            )
            
            return response_activity
            
        except Exception as e:
            import traceback
            print(f"处理Teams消息时出错: {e}")
            print(traceback.format_exc())
            # 返回错误响应
            if ActivityTypes:
                error_activity = Activity(
                    type=ActivityTypes.message,
                    text=f"抱歉，处理您的请求时出现错误：{str(e)}"
                )
                return error_activity
            return None
    
    def test_connection(self) -> bool:
        """测试连接"""
        return self.app_id is not None and self.app_password is not None
    
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


def get_teams_bot() -> Optional[TeamsBotIntegration]:
    """获取Teams Bot实例（单例），优先从数据库读取配置"""
    global _teams_bot_instance
    if _teams_bot_instance is None:
        # 确保加载环境变量
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        # 优先从数据库读取配置
        temp_bot = TeamsBotIntegration()
        db_config = temp_bot.get_config()
        
        if db_config and db_config.get('status') == 'connected':
            # 从数据库读取
            config = db_config.get('config', {})
            app_id = config.get('app_id')
            tenant_id = config.get('tenant_id')
            # Password需要从.env读取（数据库只存储哈希）
            app_password = os.getenv("TEAMS_APP_PASSWORD")
            
            if app_id and app_password:
                _teams_bot_instance = TeamsBotIntegration(app_id, app_password, tenant_id)
                print(f"DEBUG: Teams Bot实例已创建（从数据库配置），App ID: {app_id}, Tenant ID: {tenant_id or '未设置（多租户）'}")
            else:
                print("DEBUG: 数据库有配置但缺少App ID或Password")
        else:
            # 从环境变量读取
            app_id = os.getenv("TEAMS_APP_ID")
            app_password = os.getenv("TEAMS_APP_PASSWORD")
            tenant_id = os.getenv("TEAMS_TENANT_ID")
            
            if app_id and app_password:
                _teams_bot_instance = TeamsBotIntegration(app_id, app_password, tenant_id)
                print(f"DEBUG: Teams Bot实例已创建（从环境变量），App ID: {app_id}, Tenant ID: {tenant_id or '未设置（多租户）'}")
            else:
                print("DEBUG: Teams Bot未创建，因为环境变量未设置")
    return _teams_bot_instance


def create_teams_bot(app_id: str, app_password: str, tenant_id: Optional[str] = None) -> TeamsBotIntegration:
    """创建Teams Bot集成实例（用于dashboard测试）"""
    integration = TeamsBotIntegration(app_id, app_password, tenant_id)
    if integration.test_connection():
        config_data = {"app_id": app_id}
        if tenant_id:
            config_data["tenant_id"] = tenant_id
        integration.save_config(config_data, app_password)
        integration.setup_handlers()
        # 更新.env文件
        _update_env_file("TEAMS_APP_ID", app_id)
        _update_env_file("TEAMS_APP_PASSWORD", app_password)
        if tenant_id:
            _update_env_file("TEAMS_TENANT_ID", tenant_id)
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
        print(f"警告：更新.env文件失败: {e}")
