"""
Streamlit管理界面
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None


# 加载环境变量
load_dotenv()

from app.models.database import db
from app.services.analytics import analytics, utc_to_beijing
from app.services.document_parser import document_parser
from app.services.knowledge_base import kb
from app.integrations.telegram_bot import create_telegram_bot
from app.integrations.teams_bot import create_teams_bot


def init_session_state():
    """初始化session state"""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True


@st.cache_data(ttl=60)  # 缓存60秒
def _get_kb_stats():
    """获取知识库统计（带缓存）"""
    return analytics.get_kb_usage()

# 移除缓存，因为时间范围是动态的，缓存会导致数据不更新
def _get_accuracy_stats(hours=24):
    """获取准确率统计（按小时）"""
    return analytics.get_classification_accuracy(hours)

@st.cache_data(ttl=30)  # 缓存30秒
def _get_query_history(limit=10):
    """获取查询历史（带缓存）"""
    return analytics.get_query_history(limit)

def main_dashboard():
    """主仪表板"""
    st.title("📊 IntelliKnow KMS - 管理仪表板")
    
    try:
        # 获取统计数据（使用缓存）
        kb_stats = _get_kb_stats()
        accuracy_stats = _get_accuracy_stats(24)  # 默认24小时（1天）
        
        # 统计卡片
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("总文档数", kb_stats.get("total_documents", 0))
        with col2:
            st.metric("已处理文档", kb_stats.get("processed_documents", 0))
        with col3:
            st.metric("总查询数", accuracy_stats.get("total_queries", 0))
        with col4:
            accuracy_rate = accuracy_stats.get("accuracy_rate", 0)
            st.metric("分类准确率", f"{accuracy_rate*100:.1f}%")
        
        # 意图空间分布
        st.subheader("意图空间查询分布")
        intent_distribution = accuracy_stats.get("intent_distribution", {})
        if intent_distribution:
            intent_df = pd.DataFrame([
                {"意图空间": k, "查询数": v}
                for k, v in intent_distribution.items()
            ])
            fig = px.pie(intent_df, values="查询数", names="意图空间", 
                         title="查询分布")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无查询数据")
        
        # 最近查询（使用缓存）
        st.subheader("最近查询")
        query_history = _get_query_history(limit=10)
        if query_history:
            df = pd.DataFrame(query_history)
            # 确保列存在
            available_cols = [col for col in ["query_text", "detected_intent", "confidence", 
                                             "response_status", "timestamp"] if col in df.columns]
            if available_cols:
                st.dataframe(df[available_cols], use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
        else:
            st.info("暂无查询历史")
    except Exception as e:
        st.error(f"加载仪表板数据失败: {e}")


@st.cache_data(ttl=30)  # 缓存30秒
def _get_telegram_configs(verify: bool = False):
    """获取Telegram配置（verify=False 时仅读库，加载快）"""
    try:
        from app.integrations.telegram_bot import TelegramBotIntegration
        return TelegramBotIntegration().get_all_configs(verify_connection=verify)
    except Exception:
        return []

@st.cache_data(ttl=30)  # 缓存30秒
def _get_teams_configs(verify: bool = False):
    """获取Teams配置（verify=False 时仅读库，加载快）"""
    try:
        from app.integrations.teams_bot import TeamsBotIntegration
        return TeamsBotIntegration().get_all_configs(verify_connection=verify)
    except Exception:
        return []

def frontend_integration_page():
    """前端集成管理页面"""
    st.title("🔌 前端集成管理")
    
    # 快速加载：仅读库，不发起网络验证（状态由 bot_monitor 后台更新）
    col_title, col_refresh = st.columns([3, 1])
    with col_refresh:
        if st.button("🔄 刷新状态", key="refresh_bot_status"):
            # 点击时直接执行验证，结果存入 session_state 供 rerun 后使用
            with st.spinner("正在验证连接..."):
                try:
                    from app.integrations.telegram_bot import TelegramBotIntegration
                    from app.integrations.teams_bot import TeamsBotIntegration
                    tg = TelegramBotIntegration().get_all_configs(verify_connection=True)
                    tm = TeamsBotIntegration().get_all_configs(verify_connection=True)
                    st.session_state.refreshed_telegram_configs = tg
                    st.session_state.refreshed_teams_configs = tm
                except Exception as e:
                    st.session_state.refreshed_telegram_configs = []
                    st.session_state.refreshed_teams_configs = []
                    st.session_state.refresh_error = str(e)
            _get_telegram_configs.clear()
            _get_teams_configs.clear()
            st.rerun()
    
    # 优先使用刷新结果，否则用缓存（仅读库）
    if "refreshed_telegram_configs" in st.session_state:
        telegram_configs = st.session_state.pop("refreshed_telegram_configs")
        teams_configs = st.session_state.pop("refreshed_teams_configs")
        err = st.session_state.pop("refresh_error", None)
        if err:
            st.error(f"验证出错: {err}")
        _get_telegram_configs.clear()
        _get_teams_configs.clear()
        # 显示验证结果摘要
        tg_ok = sum(1 for c in telegram_configs if c.get("status") == "connected")
        tg_fail = len(telegram_configs) - tg_ok
        tm_ok = sum(1 for c in teams_configs if c.get("status") == "connected")
        tm_fail = len(teams_configs) - tm_ok
        st.info(f"✅ 验证完成 | Telegram: 🟢{tg_ok} 🟴{tg_fail} | Teams: 🟢{tm_ok} 🟴{tm_fail}")
    else:
        telegram_configs = _get_telegram_configs(verify=False)
        teams_configs = _get_teams_configs(verify=False)
    
    # 如果加载失败，显示警告
    if not telegram_configs and not teams_configs:
        st.warning("⚠️ 加载配置失败，请刷新页面重试")
    
    # Telegram Bot管理
    st.subheader("Telegram Bot 管理")
    
    # 初始化session_state
    if 'editing_telegram_id' not in st.session_state:
        st.session_state.editing_telegram_id = None
    
    # 显示当前 Telegram Bot 配置（系统仅支持一个实例在线）
    if telegram_configs:
        st.write("**当前 Telegram Bot 配置（仅支持一个实例，如需更换请编辑或删除后重新添加）：**")
        # 只显示最新一条配置
        for config in telegram_configs[:1]:
            status_icon = "🟢" if config['status'] == 'connected' else "🔴"
            bot_config = config.get('config', {})
            
            with st.expander(f"{status_icon} {config['name']} - {config['status']}"):
                # 显示配置信息
                if bot_config.get('username'):
                    st.write(f"**Bot用户名**: @{bot_config['username']}")
                if bot_config.get('first_name'):
                    st.write(f"**Bot名称**: {bot_config['first_name']}")
                if bot_config.get('id'):
                    st.write(f"**Bot ID**: {bot_config['id']}")
                if config.get('api_key_hash'):
                    st.write(f"**Token哈希**: ...{config['api_key_hash']}")
                if config.get('updated_at'):
                    updated_time = utc_to_beijing(config['updated_at']) if config['updated_at'] else "未知"
                    st.write(f"**最后更新**: {updated_time}")
                
                # 编辑/保存按钮
                col1, col2 = st.columns(2)
                with col1:
                    if st.session_state.editing_telegram_id == config['id']:
                        # 编辑模式
                        st.write("**编辑配置：**")
                        edit_name = st.text_input("Bot名称", value=config['name'], key=f"edit_telegram_name_{config['id']}")
                        edit_token = st.text_input(
                            "Telegram Bot Token", 
                            type="password",
                            value="",  # 不显示已保存的token
                            key=f"edit_telegram_token_{config['id']}",
                            help="留空则不修改Token"
                        )
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("保存", key=f"save_edit_telegram_{config['id']}"):
                                try:
                                    # 获取当前token（如果未修改）
                                    current_token = bot_config.get('_api_key')
                                    new_token = edit_token.strip() if edit_token.strip() else current_token
                                    
                                    if new_token:
                                        # 更新配置
                                        bot = create_telegram_bot(new_token, edit_name.strip() or None, config['id'])
                                        if bot.test_connection():
                                            st.success("✅ 配置已更新！")
                                            st.session_state.editing_telegram_id = None
                                            _get_telegram_configs.clear()
                                            st.rerun()
                                        else:
                                            st.error("❌ 连接测试失败，请检查Token")
                                    else:
                                        st.warning("⚠️ Token不能为空")
                                except Exception as e:
                                    st.error(f"❌ 更新失败: {e}")
                        
                        with col_cancel:
                            if st.button("取消", key=f"cancel_edit_telegram_{config['id']}"):
                                st.session_state.editing_telegram_id = None
                                st.rerun()
                    else:
                        if st.button("✏️ 编辑", key=f"edit_telegram_{config['id']}"):
                            st.session_state.editing_telegram_id = config['id']
                            st.rerun()
                
                with col2:
                    if st.button("🗑️ 删除", key=f"delete_telegram_{config['id']}"):
                        conn = db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM frontend_integrations WHERE id = ?", (config['id'],))
                        conn.commit()
                        conn.close()
                        st.success("已删除")
                        if st.session_state.editing_telegram_id == config['id']:
                            st.session_state.editing_telegram_id = None
                        _get_telegram_configs.clear()
                        st.rerun()
    else:
        st.info("暂无Telegram Bot配置")
    
    # 仅在没有配置时允许添加新的 Telegram Bot
    if not telegram_configs:
        with st.expander("➕ 添加新的Telegram Bot"):
            telegram_name = st.text_input("Bot名称（可选）", key="telegram_name", value="")
            telegram_token = st.text_input(
                "Telegram Bot Token", 
                type="password",
                key="telegram_token",
                help="输入Telegram Bot Token，可在@BotFather获取"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("保存并连接", key="save_telegram"):
                    if telegram_token:
                        try:
                            name = telegram_name.strip() if telegram_name.strip() else None
                            bot = create_telegram_bot(telegram_token, name)
                            if bot.test_connection():
                                bot_info = bot.get_bot_info()
                                if bot_info:
                                    st.success(f"✅ Telegram Bot连接成功！\nBot: @{bot_info.get('username', 'N/A')}")
                                else:
                                    st.success("✅ Telegram Bot连接成功并已保存配置！")
                                _get_telegram_configs.clear()
                                st.rerun()
                            else:
                                st.error("❌ 连接失败，请检查Token")
                        except Exception as e:
                            st.error(f"❌ 连接失败: {e}")
                    else:
                        st.warning("⚠️ 请输入Bot Token")
            
            with col2:
                if st.button("测试连接", key="test_telegram"):
                    if telegram_token:
                        try:
                            # 测试连接时不保存配置（save=False）
                            bot = create_telegram_bot(telegram_token, save=False)
                            if bot.test_connection():
                                bot_info = bot.get_bot_info()
                                if bot_info:
                                    st.success(f"✅ 连接测试成功！\nBot: @{bot_info.get('username', 'N/A')}")
                                else:
                                    st.success("✅ 连接测试成功！")
                            else:
                                st.error("❌ 连接测试失败")
                        except Exception as e:
                            st.error(f"❌ 测试失败: {e}")
                    else:
                        st.warning("⚠️ 请输入Token进行测试")
    
    st.divider()
    
    # Teams Bot管理
    st.subheader("Microsoft Teams Bot 管理")
    
    # 初始化session_state
    if 'editing_teams_id' not in st.session_state:
        st.session_state.editing_teams_id = None
    
    # 显示所有Teams Bot实例（系统仅支持一个实例在线）
    if teams_configs:
        st.write("**当前 Teams Bot 配置（仅支持一个实例，如需更换请编辑或删除后重新添加）：**")
        
        # 获取Webhook URL：优先从 API 拉取最新（与 Tunnel 启动后写入的 DB 同步），便于用户复制
        import os
        saved_webhook_url = None
        if requests:
            try:
                base_url = os.environ.get("FASTAPI_URL", "http://127.0.0.1:8000")
                r = requests.get(f"{base_url.rstrip('/')}/api/webhook-url", timeout=3)
                if r.ok:
                    data = r.json()
                    saved_webhook_url = (data.get("webhook_url") or "").strip() or None
            except Exception:
                pass
        if not saved_webhook_url:
            from app.utils.tunnel_url_saver import get_webhook_url
            saved_webhook_url = get_webhook_url() or None
        if not saved_webhook_url:
            tunnel_url = os.environ.get("TUNNEL_URL", "") or os.environ.get("CLOUDFLARE_TUNNEL_URL", "") or os.environ.get("WEBHOOK_URL", "")
            if tunnel_url:
                saved_webhook_url = f"{tunnel_url.rstrip('/')}/api/teams/messages"
        if not saved_webhook_url and teams_configs:
            first_config = teams_configs[0].get('config', {})
            base_url = first_config.get('webhook_base_url', '')
            if base_url:
                saved_webhook_url = f"{base_url.rstrip('/')}/api/teams/messages"
        
        # 显示Webhook URL（简洁版）+ 刷新按钮，便于 Tunnel 启动后同步最新地址
        if saved_webhook_url:
            col_title, col_btn = st.columns([3, 1])
            with col_title:
                st.write("**Webhook URL：**（复制到 Teams 开发者门户配置）")
            with col_btn:
                if st.button("🔄 刷新", key="refresh_webhook_url", help="启动 Tunnel 后点击可获取最新地址"):
                    st.rerun()
            st.code(saved_webhook_url, language=None)
            
            # 测试按钮
            if st.button("🔗 测试连接", key="test_webhook_url"):
                if requests:
                    try:
                        # 测试健康检查端点（使用基础URL）
                        base_url = saved_webhook_url.replace('/api/teams/messages', '')
                        test_url = f"{base_url}/health"
                        response = requests.get(test_url, timeout=5)
                        if response.status_code == 200:
                            st.success(f"✅ 连接成功！状态码: {response.status_code}")
                        else:
                            st.warning(f"⚠️ 返回状态码: {response.status_code}")
                    except requests.exceptions.RequestException as e:
                        st.error(f"❌ 连接失败: {e}")
                else:
                    st.warning("⚠️ requests库未安装，无法测试连接")
        else:
            st.info("⚠️ 未检测到Webhook URL，请启动Cloudflare Tunnel 后点击下方刷新")
            if st.button("🔄 刷新 Webhook URL", key="refresh_webhook_empty", help="启动 Tunnel 后点击获取最新地址"):
                st.rerun()
        
        st.divider()
        
        for config in teams_configs[:1]:
            status_icon = "🟢" if config['status'] == 'connected' else "🔴"
            bot_config = config.get('config', {})
            # 脱敏显示：只展示后4位
            def _mask_value(v: str) -> str:
                if not v:
                    return ""
                v = str(v)
                return ("*" * max(len(v) - 4, 0)) + v[-4:]
            
            with st.expander(f"{status_icon} {config['name']} - {config['status']}"):
                # 显示配置信息（仅展示后4位）
                if bot_config.get('app_id'):
                    masked_app_id = _mask_value(bot_config.get('app_id', ''))
                    st.write(f"**App ID**: {masked_app_id}")
                if bot_config.get('tenant_id'):
                    masked_tenant_id = _mask_value(bot_config.get('tenant_id', ''))
                    st.write(f"**Tenant ID**: {masked_tenant_id}")
                if config.get('api_key_hash'):
                    st.write(f"**Password哈希**: ...{config['api_key_hash']}")
                if config.get('updated_at'):
                    updated_time = utc_to_beijing(config['updated_at']) if config['updated_at'] else "未知"
                    st.write(f"**最后更新**: {updated_time}")
                
                # 显示Webhook URL配置状态（简化）
                if saved_webhook_url:
                    st.write(f"**Webhook URL**: `{saved_webhook_url}`")
                
                # 编辑/保存按钮
                col1, col2 = st.columns(2)
                with col1:
                    if st.session_state.editing_teams_id == config['id']:
                        # 编辑模式
                        st.write("**编辑配置：**")
                        edit_name = st.text_input("Bot名称", value=config['name'], key=f"edit_teams_name_{config['id']}")
                        edit_app_id = st.text_input(
                            "Teams App ID",
                            value=bot_config.get('app_id', ''),
                            key=f"edit_teams_app_id_{config['id']}"
                        )
                        edit_app_password = st.text_input(
                            "Teams App Password", 
                            type="password",
                            value="",  # 不显示已保存的password
                            key=f"edit_teams_app_password_{config['id']}",
                            help="留空则不修改Password"
                        )
                        edit_tenant_id = st.text_input(
                            "Tenant ID",
                            value=bot_config.get('tenant_id', ''),
                            key=f"edit_teams_tenant_id_{config['id']}"
                        )
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("保存", key=f"save_edit_teams_{config['id']}"):
                                try:
                                    # 获取当前password（如果未修改）
                                    current_password = bot_config.get('_app_password')
                                    new_password = edit_app_password.strip() if edit_app_password.strip() else current_password
                                    
                                    if edit_app_id.strip() and new_password:
                                        # 更新配置
                                        tenant_id = edit_tenant_id.strip() if edit_tenant_id.strip() else None
                                        bot = create_teams_bot(
                                            edit_app_id.strip(), 
                                            new_password, 
                                            tenant_id, 
                                            edit_name.strip() or None, 
                                            config['id']
                                        )
                                        if bot.test_connection():
                                            st.success("✅ 配置已更新！")
                                            st.session_state.editing_teams_id = None
                                            _get_teams_configs.clear()
                                            st.rerun()
                                        else:
                                            st.error("❌ 连接测试失败，请检查配置")
                                    else:
                                        st.warning("⚠️ App ID和Password不能为空")
                                except Exception as e:
                                    st.error(f"❌ 更新失败: {e}")
                        
                        with col_cancel:
                            if st.button("取消", key=f"cancel_edit_teams_{config['id']}"):
                                st.session_state.editing_teams_id = None
                                st.rerun()
                    else:
                        if st.button("✏️ 编辑", key=f"edit_teams_{config['id']}"):
                            st.session_state.editing_teams_id = config['id']
                            st.rerun()
                
                with col2:
                    if st.button("🗑️ 删除", key=f"delete_teams_{config['id']}"):
                        conn = db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM frontend_integrations WHERE id = ?", (config['id'],))
                        conn.commit()
                        conn.close()
                        st.success("已删除")
                        if st.session_state.editing_teams_id == config['id']:
                            st.session_state.editing_teams_id = None
                        _get_teams_configs.clear()
                        st.rerun()
    else:
        st.info("暂无Teams Bot配置")
    
    # 仅在没有配置时允许添加新的 Teams Bot（每次只维护一个实例）
    if not teams_configs:
        with st.expander("➕ 添加新的Teams Bot"):
            teams_name = st.text_input("Bot名称（可选）", key="teams_name", value="")
            teams_app_id = st.text_input(
                "Teams App ID",
                key="teams_app_id",
                help="从Azure Portal获取的App ID"
            )
            teams_app_password = st.text_input(
                "Teams App Password", 
                type="password",
                key="teams_app_password",
                help="从Azure Portal获取的App Password（客户端密码）"
            )
            teams_tenant_id = st.text_input(
                "Tenant ID（单租户Bot必需）",
                key="teams_tenant_id",
                help="从Azure Portal → App注册 → 概述 → Directory (tenant) ID获取"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("保存并连接", key="save_teams"):
                    if teams_app_id and teams_app_password:
                        try:
                            name = teams_name.strip() if teams_name.strip() else None
                            tenant_id = teams_tenant_id if teams_tenant_id.strip() else None
                            bot = create_teams_bot(teams_app_id, teams_app_password, tenant_id, name)
                            if bot.test_connection():
                                st.success("✅ Teams Bot连接成功并已保存配置！")
                                _get_teams_configs.clear()
                                st.rerun()
                            else:
                                st.error("❌ 连接失败，请检查配置")
                        except Exception as e:
                            st.error(f"❌ 连接失败: {e}")
                    else:
                        st.warning("⚠️ 请输入App ID和Password")
            
            with col2:
                if st.button("测试连接", key="test_teams"):
                    if teams_app_id and teams_app_password:
                        try:
                            tenant_id = teams_tenant_id if teams_tenant_id.strip() else None
                            # 测试连接时不保存配置（save=False）
                            bot = create_teams_bot(teams_app_id, teams_app_password, tenant_id, save=False)
                            if bot.test_connection():
                                st.success("✅ 连接测试成功！")
                            else:
                                st.error("❌ 连接测试失败")
                        except Exception as e:
                            st.error(f"❌ 测试失败: {e}")
                    else:
                        st.warning("⚠️ 请输入配置进行测试")
    
    st.divider()
    
    # 集成状态总览
    st.subheader("集成状态总览")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM frontend_integrations ORDER BY frontend_type, updated_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            # 按类型分组显示
            telegram_bots = [r for r in rows if r['frontend_type'] == 'telegram']
            teams_bots = [r for r in rows if r['frontend_type'] == 'teams']
            
            if telegram_bots:
                st.write("**Telegram Bot:**")
                for row in telegram_bots:
                    status_color = "🟢" if row["status"] == "connected" else "🔴"
                    name = row["name"] if row["name"] else "default"
                    updated_time = utc_to_beijing(row["updated_at"]) if row["updated_at"] else "未知"
                    st.write(f"{status_color} {name}: {row['status']} (更新于: {updated_time})")
            
            if teams_bots:
                st.write("**Teams Bot:**")
                for row in teams_bots:
                    status_color = "🟢" if row["status"] == "connected" else "🔴"
                    name = row["name"] if row["name"] else "default"
                    updated_time = utc_to_beijing(row["updated_at"]) if row["updated_at"] else "未知"
                    st.write(f"{status_color} {name}: {row['status']} (更新于: {updated_time})")
        else:
            st.info("暂无集成配置")
    except Exception as e:
        st.error(f"加载集成状态失败: {e}")


def kb_management_page():
    """知识库管理页面"""
    st.title("📚 知识库管理")
    
    # 拖拽上传与进度
    st.subheader("上传文档")
    uploaded_file = st.file_uploader(
        "拖拽文件到此处或点击上传",
        type=["pdf", "docx", "doc"],
        help="支持 PDF、Word 格式，最大 50MB"
    )
    
    # 选择意图空间
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM intent_spaces ORDER BY name")
        intent_spaces = cursor.fetchall()
        conn.close()
        
        intent_space_options = {0: "未分配"}
        if intent_spaces:
            intent_space_options.update({row["id"]: row["name"] for row in intent_spaces})
        
        selected_intent = st.selectbox("关联意图空间", 
                                       options=list(intent_space_options.keys()),
                                       format_func=lambda x: intent_space_options[x])
    except Exception as e:
        st.error(f"加载意图空间失败: {e}")
        selected_intent = 0
    
    if uploaded_file and st.button("上传"):
        try:
            with st.spinner("正在上传并解析文档..."):
                from app.config import DOCUMENTS_DIR
                file_path = DOCUMENTS_DIR / uploaded_file.name
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                intent_space_id = selected_intent if selected_intent > 0 else None
                doc_id = document_parser.save_parsed_document(
                    uploaded_file.name, str(file_path), intent_space_id
                )
                try:
                    parse_result = document_parser.parse_document(str(file_path), uploaded_file.name)
                    raw_content = parse_result["raw_content"]
                    metadata = parse_result["metadata"]
                    kb.add_document(doc_id, raw_content, metadata, intent_space_id)
                    st.success(f"✅ 文档上传成功！文档ID: {doc_id}")
                except Exception as kb_error:
                    st.warning(f"文档已保存但添加到知识库失败: {kb_error}")
            st.rerun()
            
        except Exception as e:
            st.error(f"上传失败: {e}")
    
    # 搜索与筛选
    st.subheader("搜索与筛选")
    col_kw, col_fmt, col_intent, col_date = st.columns(4)
    with col_kw:
        filter_keyword = st.text_input("文件名", key="doc_filter_keyword", placeholder="关键词")
    with col_fmt:
        filter_format = st.selectbox("格式", ["全部", ".pdf", ".docx", ".doc"], key="doc_filter_format")
    with col_intent:
        conn_i = db.get_connection()
        cursor_i = conn_i.cursor()
        cursor_i.execute("SELECT id, name FROM intent_spaces ORDER BY name")
        intent_list = cursor_i.fetchall()
        conn_i.close()
        intent_filter_opts = [None] + [r["id"] for r in intent_list]
        intent_filter_labels = ["全部"] + [r["name"] for r in intent_list]
        filter_intent_idx = st.selectbox("意图空间", range(len(intent_filter_opts)),
                                         format_func=lambda i: intent_filter_labels[i], key="doc_filter_intent")
        filter_intent = intent_filter_opts[filter_intent_idx]
    with col_date:
        filter_date = st.date_input("上传日期起", value=None, key="doc_filter_date")
    
    # 获取文档列表（API 支持筛选）
    try:
        params = {}
        if filter_keyword:
            params["keyword"] = filter_keyword
        if filter_format != "全部":
            params["file_format"] = filter_format
        if filter_intent is not None:
            params["intent_space_id"] = filter_intent
        if filter_date:
            params["date_from"] = filter_date.isoformat()
        if requests:
            r = requests.get("http://localhost:8000/api/documents", params=params, timeout=10)
            rows = r.json() if r.status_code == 200 else []
        else:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.*, intent_spaces.name AS intent_space_name
                FROM documents d
                LEFT JOIN intent_spaces ON d.intent_space_id = intent_spaces.id
                ORDER BY d.upload_date DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
    except Exception as e:
        st.error(f"加载文档列表失败: {e}")
        rows = []
    
    # 表格展示（ID 列带编辑按钮）
    st.subheader("文档列表")
    if rows:
        # 表头（ID 列即编辑按钮）
        h1, h2, h3, h4, h5, h6, h7 = st.columns([1, 3, 1, 1, 2, 1, 2])
        with h1: st.write("**ID**")
        with h2: st.write("**文件名**")
        with h3: st.write("**格式**")
        with h4: st.write("**大小**")
        with h5: st.write("**意图空间**")
        with h6: st.write("**状态**")
        with h7: st.write("**上传时间**")
        st.divider()
        
        editing_doc_id = st.session_state.get("editing_doc_id")
        for r in rows:
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 3, 1, 1, 2, 1, 2])
            with c1:
                # ID 作为编辑按钮
                if st.button(f"✏️ {r['id']}", key=f"edit_btn_{r['id']}", use_container_width=True):
                    st.session_state["editing_doc_id"] = r["id"]
                    st.rerun()
            with c2: st.write(r["filename"])
            with c3: st.write(r["file_format"])
            with c4: st.write(f"{round(r.get('file_size', 0) / 1024, 1)} KB" if r.get("file_size") else "0 KB")
            with c5: st.write(r.get("intent_space_name") or "未分配")
            with c6: st.write(r["status"])
            with c7: st.write(utc_to_beijing(r["upload_date"]) if r.get("upload_date") else "-")
        
        # 编辑弹窗（由 ID 上的编辑按钮触发）
        sel = next((r for r in rows if r["id"] == editing_doc_id), None)
        if sel:
            _edit_doc_dialog(sel)
    else:
        st.info("暂无文档")


def _on_edit_doc_dismiss():
    st.session_state.pop("editing_doc_id", None)


@st.dialog("编辑文档", width="large", on_dismiss=_on_edit_doc_dismiss)
def _edit_doc_dialog(sel):
    """文档编辑弹窗"""
    st.caption(f"{sel['filename']} · ID: {sel['id']}")
    
    # 编辑区域
    with st.container():
        st.markdown("##### 修改配置")
        intent_opts = {0: "未分配"}
        conn_u = db.get_connection()
        cursor_u = conn_u.cursor()
        cursor_u.execute("SELECT id, name FROM intent_spaces ORDER BY name")
        for r in cursor_u.fetchall():
            intent_opts[r["id"]] = r["name"]
        conn_u.close()
        keys = list(intent_opts.keys())
        cur_id = sel.get("intent_space_id") or 0
        default_idx = keys.index(cur_id) if cur_id in keys else 0
        col_a, col_b = st.columns([2, 1])
        with col_a:
            new_intent = st.selectbox("意图空间", options=keys, index=default_idx,
                                     format_func=lambda x: intent_opts[x], key=f"dlg_intent_{sel['id']}")
        with col_b:
            reparse = st.checkbox("重新解析文档", key=f"dlg_reparse_{sel['id']}")
    
    st.divider()
    
    # 查看内容
    with st.container():
        st.markdown("##### 内容预览")
        if st.button("加载预览", key=f"dlg_view_{sel['id']}", type="secondary"):
            try:
                if requests:
                    r = requests.get(f"http://localhost:8000/api/documents/{sel['id']}", timeout=10)
                    if r.status_code == 200:
                        st.session_state[f"doc_preview_{sel['id']}"] = r.json().get("content_preview", "")
            except Exception:
                pass
            st.rerun()
        if f"doc_preview_{sel['id']}" in st.session_state:
            prev = st.session_state[f"doc_preview_{sel['id']}"]
            st.text_area("预览", prev[:3000] + ("..." if len(prev) > 3000 else ""), height=160, key=f"dlg_preview_{sel['id']}", label_visibility="collapsed")
    
    st.divider()
    
    # 操作按钮
    st.markdown("##### 操作")
    btn_save, btn_del, _ = st.columns([1, 1, 4])
    with btn_save:
        if st.button("保存", key=f"dlg_save_{sel['id']}", type="primary", use_container_width=True):
            try:
                if requests:
                    with st.spinner("正在更新..."):
                        body = {"intent_space_id": new_intent if new_intent > 0 else 0, "reparse": reparse}
                        r = requests.patch(f"http://localhost:8000/api/documents/{sel['id']}", json=body, timeout=30)
                    if r.status_code == 200:
                        st.success("✅ 更新成功")
                        st.session_state.pop("editing_doc_id", None)
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "更新失败"))
            except Exception as e:
                st.error(str(e))
    with btn_del:
        if st.button("删除", key=f"dlg_del_{sel['id']}", type="secondary", use_container_width=True):
            try:
                if requests:
                    with st.spinner("正在删除..."):
                        r = requests.delete(f"http://localhost:8000/api/documents/{sel['id']}", timeout=10)
                    if r.status_code == 200:
                        st.success("✅ 已删除")
                        st.session_state.pop("editing_doc_id", None)
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "删除失败"))
            except Exception as e:
                st.error(str(e))


def intent_configuration_page():
    """意图空间配置页面"""
    st.title("🎯 意图空间配置")
    
    # 创建新意图空间
    st.subheader("创建意图空间")
    with st.form("create_intent"):
        intent_name = st.text_input("名称")
        intent_description = st.text_area("描述")
        intent_keywords = st.text_input("关键词（逗号分隔）")
        
        if st.form_submit_button("创建"):
            if intent_name:
                conn = db.get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO intent_spaces (name, description, keywords)
                        VALUES (?, ?, ?)
                    """, (intent_name, intent_description, intent_keywords))
                    conn.commit()
                    st.success("意图空间创建成功！")
                except Exception as e:
                    st.error(f"创建失败: {e}")
                finally:
                    conn.close()
            else:
                st.warning("请输入名称")
    
    # 意图空间列表
    st.subheader("意图空间列表")
    editing_intent_id = st.session_state.get("editing_intent_id")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM intent_spaces ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            for row in rows:
                with st.expander(f"📁 {row['name']}"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        if editing_intent_id == row["id"]:
                            # 编辑模式
                            st.markdown("**编辑意图空间**")
                            edit_name = st.text_input("名称", value=row["name"] or "", key=f"intent_name_{row['id']}")
                            edit_desc = st.text_area("描述", value=row["description"] or "", key=f"intent_desc_{row['id']}")
                            edit_kw = st.text_input("关键词（逗号分隔）", value=row["keywords"] or "", key=f"intent_kw_{row['id']}")
                            c1, c2, _ = st.columns([1, 1, 4])
                            with c1:
                                if st.button("保存", key=f"save_intent_{row['id']}"):
                                    if edit_name.strip():
                                        try:
                                            if requests:
                                                r = requests.patch(
                                                    f"http://localhost:8000/api/intent-spaces/{row['id']}",
                                                    json={"name": edit_name.strip(), "description": edit_desc.strip(), "keywords": edit_kw.strip()},
                                                    timeout=10
                                                )
                                                if r.status_code == 200:
                                                    st.success("✅ 已更新")
                                                    st.session_state.pop("editing_intent_id", None)
                                                    st.rerun()
                                                else:
                                                    st.error(r.json().get("detail", "更新失败"))
                                            else:
                                                conn_u = db.get_connection()
                                                cur = conn_u.cursor()
                                                cur.execute(
                                                    "UPDATE intent_spaces SET name=?, description=?, keywords=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                                    (edit_name.strip(), edit_desc.strip(), edit_kw.strip(), row["id"])
                                                )
                                                conn_u.commit()
                                                conn_u.close()
                                                st.success("✅ 已更新")
                                                st.session_state.pop("editing_intent_id", None)
                                                st.rerun()
                                        except Exception as e:
                                            st.error(str(e))
                                    else:
                                        st.warning("名称为必填")
                            with c2:
                                if st.button("取消", key=f"cancel_intent_{row['id']}"):
                                    st.session_state.pop("editing_intent_id", None)
                                    st.rerun()
                        else:
                            st.write(f"**描述**: {row['description'] or '无描述'}")
                            st.write(f"**关键词**: {row['keywords'] or '无关键词'}")
                            
                            # 查询分类日志
                            try:
                                conn_logs = db.get_connection()
                                cursor_logs = conn_logs.cursor()
                                cursor_logs.execute("""
                                    SELECT detected_intent, confidence, COUNT(*) as count
                                    FROM query_history
                                    WHERE detected_intent = ?
                                    GROUP BY detected_intent, confidence
                                """, (row['name'],))
                                logs = cursor_logs.fetchall()
                                conn_logs.close()
                                
                                if logs:
                                    st.write("**分类统计**:")
                                    for log in logs:
                                        st.write(f"- 置信度 {log['confidence']:.2f}: {log['count']} 次查询")
                                else:
                                    st.write("*暂无查询统计*")
                            except Exception as e:
                                st.write(f"*无法加载统计信息: {e}*")
                    
                    with col2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if editing_intent_id != row["id"]:
                            if st.button("✏️ 编辑", key=f"edit_intent_{row['id']}", use_container_width=True):
                                st.session_state["editing_intent_id"] = row["id"]
                                st.rerun()
                        if st.button("🗑️ 删除", key=f"delete_intent_{row['id']}", type="primary", use_container_width=True):
                            try:
                                conn = db.get_connection()
                                cursor = conn.cursor()
                                
                                # 检查是否有文档关联到此意图空间
                                cursor.execute("SELECT COUNT(*) FROM documents WHERE intent_space_id = ?", (row['id'],))
                                doc_count = cursor.fetchone()[0]
                                
                                if doc_count > 0:
                                    st.warning(f"⚠️ 该意图空间关联了 {doc_count} 个文档，删除前请先处理这些文档。")
                                else:
                                    cursor.execute("DELETE FROM intent_spaces WHERE id = ?", (row['id'],))
                                    conn.commit()
                                    st.success(f"✅ 意图空间 '{row['name']}' 已删除")
                                    st.rerun()
                                conn.close()
                            except Exception as e:
                                st.error(f"❌ 删除失败: {e}")
                                if conn:
                                    conn.close()
        else:
            st.info("暂无意图空间")
    except Exception as e:
        st.error(f"加载意图空间失败: {e}")


def analytics_page():
    """分析页面"""
    st.title("📈 分析报告")
    
    try:
        # 分类准确率
        st.subheader("分类准确率")
        
        # 时间范围选择（按小时）
        # 使用 session_state 确保值正确传递
        if "accuracy_hours_value" not in st.session_state:
            st.session_state.accuracy_hours_value = 24
        
        hours = st.slider(
            "时间范围（小时）", 
            min_value=1, 
            max_value=168,  # 7天 = 168小时
            value=st.session_state.accuracy_hours_value,  # 使用session_state的值
            step=1,
            key="accuracy_hours_slider",
            help="选择要统计的时间范围（1-168小时，即1小时到7天）"
        )
        
        # 更新session_state
        st.session_state.accuracy_hours_value = hours
        
        # 直接调用，不使用缓存，确保时间范围变化时数据更新
        # 注意：每次 slider 变化都会触发重新计算
        # 确保 hours 是整数
        try:
            hours_int = int(hours)
        except (ValueError, TypeError):
            hours_int = 24
        
        accuracy_data = analytics.get_classification_accuracy(hours_int)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总查询数", accuracy_data.get("total_queries", 0))
        with col2:
            avg_conf = accuracy_data.get("average_confidence", 0)
            st.metric("平均置信度", f"{avg_conf:.2f}")
        with col3:
            acc_rate = accuracy_data.get("accuracy_rate", 0)
            st.metric("高置信度比例", f"{acc_rate*100:.1f}%")
        
        # 查询历史
        st.subheader("查询历史")
        limit = st.slider("显示数量", 10, 100, 50)
        query_history = analytics.get_query_history(limit)
        
        if query_history:
            df = pd.DataFrame(query_history)
            st.dataframe(df, use_container_width=True)
            
            # 导出数据
            if st.button("导出数据（JSON）"):
                try:
                    export_path = analytics.export_data("json")
                    st.success(f"数据已导出到: {export_path}")
                except Exception as e:
                    st.error(f"导出失败: {e}")
        else:
            st.info("暂无查询历史")
        
        # 知识库使用统计
        st.subheader("知识库使用统计")
        kb_usage = analytics.get_kb_usage()
        
        top_docs = kb_usage.get("top_accessed_documents", [])
        if top_docs:
            st.write("**最常访问的文档**:")
            doc_df = pd.DataFrame(top_docs)
            st.dataframe(doc_df, use_container_width=True)
        else:
            st.info("暂无文档访问数据")
        
        top_intents = kb_usage.get("top_intent_spaces", [])
        if top_intents:
            st.write("**最常用的意图空间**:")
            intent_df = pd.DataFrame(top_intents)
            fig = px.bar(intent_df, x="name", y="query_count", 
                        title="意图空间查询统计")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无意图空间数据")
    except Exception as e:
        st.error(f"加载分析数据失败: {e}")


def main():
    """主函数"""
    init_session_state()
    
    # 侧边栏标题
    st.sidebar.title("IntelliKnow KMS")
    st.sidebar.markdown("---")  # 分隔线
    
    # 初始化session state中的当前页面
    if "current_page" not in st.session_state:
        st.session_state.current_page = "📊 仪表板"
    
    # 侧边栏标签导航（使用按钮组，优化性能）
    st.sidebar.markdown("### 导航菜单")
    st.sidebar.markdown("")  # 空行增加间距
    
    # 使用按钮组，每个按钮独立一行（优化：使用唯一key避免重复渲染检查）
    current = st.session_state.current_page
    
    # 定义页面列表
    pages = [
        ("📊 仪表板", "📊 仪表板"),
        ("🔌 前端集成", "🔌 前端集成"),
        ("📚 知识库管理", "📚 知识库管理"),
        ("🎯 意图配置", "🎯 意图配置"),
        ("📈 分析报告", "📈 分析报告")
    ]
    
    # 渲染按钮（优化：只在点击时更新，避免每次渲染都检查状态）
    for page_key, page_label in pages:
        is_selected = (current == page_key)
        button_type = "primary" if is_selected else "secondary"
        
        if st.sidebar.button(
            page_label, 
            use_container_width=True,
            type=button_type,
            key=f"nav_btn_{page_key}"  # 使用唯一key避免重复渲染
        ):
            if current != page_key:
                st.session_state.current_page = page_key
                st.rerun()
        
        st.sidebar.markdown("")  # 空行增加间距
    
    st.sidebar.markdown("")  # 空行增加间距
    
    st.sidebar.markdown("---")  # 底部分隔线
    
    # 根据选择的页面显示对应内容
    if st.session_state.current_page == "📊 仪表板":
        main_dashboard()
    elif st.session_state.current_page == "🔌 前端集成":
        frontend_integration_page()
    elif st.session_state.current_page == "📚 知识库管理":
        kb_management_page()
    elif st.session_state.current_page == "🎯 意图配置":
        intent_configuration_page()
    elif st.session_state.current_page == "📈 分析报告":
        analytics_page()


if __name__ == "__main__":
    main()
