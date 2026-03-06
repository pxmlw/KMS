"""
Streamlit管理界面
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from app.models.database import db
from app.services.analytics import analytics
from app.services.document_parser import document_parser
from app.services.knowledge_base import kb
from app.integrations.telegram_bot import create_telegram_bot
from app.integrations.teams_bot import create_teams_bot


def init_session_state():
    """初始化session state"""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True


def main_dashboard():
    """主仪表板"""
    st.title("📊 IntelliKnow KMS - 管理仪表板")
    
    try:
        # 获取统计数据
        kb_stats = analytics.get_kb_usage()
        accuracy_stats = analytics.get_classification_accuracy(7)
        
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
        
        # 最近查询
        st.subheader("最近查询")
        query_history = analytics.get_query_history(limit=10)
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
        import traceback
        st.code(traceback.format_exc())


def frontend_integration_page():
    """前端集成管理页面"""
    st.title("🔌 前端集成管理")
    
    # 加载已保存的配置
    telegram_config = None
    teams_config = None
    try:
        from app.integrations.telegram_bot import TelegramBotIntegration
        from app.integrations.teams_bot import TeamsBotIntegration
        
        telegram_bot = TelegramBotIntegration()
        telegram_config = telegram_bot.get_config()
        
        teams_bot = TeamsBotIntegration()
        teams_config = teams_bot.get_config()
    except Exception as e:
        st.warning(f"加载配置失败: {e}")
    
    # Telegram集成
    st.subheader("Telegram Bot")
    
    # 显示当前配置
    if telegram_config:
        st.info(f"✅ 当前已配置（状态: {telegram_config['status']}）")
        config = telegram_config.get('config', {})
        if config.get('username'):
            st.caption(f"Bot用户名: @{config['username']}")
        if config.get('first_name'):
            st.caption(f"Bot名称: {config['first_name']}")
        if config.get('id'):
            st.caption(f"Bot ID: {config['id']}")
        if telegram_config.get('api_key_hash'):
            st.caption(f"Token哈希: ...{telegram_config['api_key_hash']}")
        if telegram_config.get('updated_at'):
            st.caption(f"最后更新: {telegram_config['updated_at']}")
    
    telegram_token = st.text_input(
        "Telegram Bot Token", 
        type="password",
        value="",  # 不显示已保存的token
        help="输入Telegram Bot Token，可在@BotFather获取"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("保存并连接Telegram", type="primary"):
            if telegram_token:
                try:
                    bot = create_telegram_bot(telegram_token)
                    if bot.test_connection():
                        bot_info = bot.get_bot_info()
                        if bot_info:
                            st.success(f"✅ Telegram Bot连接成功！\nBot: @{bot_info.get('username', 'N/A')} ({bot_info.get('first_name', 'N/A')})")
                        else:
                            st.success("✅ Telegram Bot连接成功并已保存配置！")
                        st.rerun()  # 刷新页面显示新配置
                    else:
                        st.error("❌ 连接失败，请检查Token")
                except Exception as e:
                    st.error(f"❌ 连接失败: {e}")
                    import traceback
                    st.code(traceback.format_exc())
            else:
                st.warning("⚠️ 请输入Bot Token")
    
    with col2:
        if st.button("测试Telegram连接"):
            if telegram_token:
                try:
                    bot = create_telegram_bot(telegram_token)
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
                    import traceback
                    st.code(traceback.format_exc())
            else:
                st.warning("⚠️ 请输入Token进行测试")
    
    st.divider()
    
    # Teams集成
    st.subheader("Microsoft Teams Bot")
    
    # 显示当前配置
    if teams_config:
        st.info(f"✅ 当前已配置（状态: {teams_config['status']}）")
        config = teams_config.get('config', {})
        if config.get('app_id'):
            st.caption(f"App ID: {config['app_id']}")
        if teams_config.get('api_key_hash'):
            st.caption(f"Password哈希: ...{teams_config['api_key_hash']}")
    
    teams_app_id = st.text_input(
        "Teams App ID",
        value=teams_config.get('config', {}).get('app_id', '') if teams_config else '',
        help="从Azure Portal获取的App ID"
    )
    teams_app_password = st.text_input(
        "Teams App Password", 
        type="password",
        value="",  # 不显示已保存的password
        help="从Azure Portal获取的App Password（客户端密码）"
    )
    teams_tenant_id = st.text_input(
        "Tenant ID（单租户Bot必需）",
        value=teams_config.get('config', {}).get('tenant_id', '') if teams_config else '',
        help="从Azure Portal → App注册 → 概述 → Directory (tenant) ID获取"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("保存并连接Teams"):
            if teams_app_id and teams_app_password:
                try:
                    tenant_id = teams_tenant_id if teams_tenant_id else None
                    bot = create_teams_bot(teams_app_id, teams_app_password, tenant_id)
                    if bot.test_connection():
                        st.success("✅ Teams Bot连接成功并已保存配置！")
                        st.rerun()  # 刷新页面显示新配置
                    else:
                        st.error("❌ 连接失败，请检查配置")
                except Exception as e:
                    st.error(f"❌ 连接失败: {e}")
            else:
                st.warning("⚠️ 请输入App ID和Password")
    
    with col2:
        if st.button("测试Teams连接"):
            if teams_app_id and teams_app_password:
                try:
                    tenant_id = teams_tenant_id if teams_tenant_id else None
                    bot = create_teams_bot(teams_app_id, teams_app_password, tenant_id)
                    if bot.test_connection():
                        st.success("✅ 连接测试成功！")
                    else:
                        st.error("❌ 连接测试失败")
                except Exception as e:
                    st.error(f"❌ 测试失败: {e}")
            else:
                st.warning("⚠️ 请输入配置进行测试")
    
    st.divider()
    
    # 集成状态
    st.subheader("集成状态")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM frontend_integrations ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            for row in rows:
                status_color = "🟢" if row["status"] == "connected" else "🔴"
                updated_time = row["updated_at"] if row["updated_at"] else "未知"
                st.write(f"{status_color} **{row['frontend_type']}**: {row['status']} (更新于: {updated_time})")
        else:
            st.info("暂无集成配置")
    except Exception as e:
        st.error(f"加载集成状态失败: {e}")
        import traceback
        st.code(traceback.format_exc())


def kb_management_page():
    """知识库管理页面"""
    st.title("📚 知识库管理")
    
    # 文档上传
    st.subheader("上传文档")
    uploaded_file = st.file_uploader("选择文档", type=["pdf", "docx", "doc"])
    
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
            # 保存文件
            from app.config import DOCUMENTS_DIR
            file_path = DOCUMENTS_DIR / uploaded_file.name
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 解析文档
            intent_space_id = selected_intent if selected_intent > 0 else None
            doc_id = document_parser.save_parsed_document(
                uploaded_file.name, str(file_path), intent_space_id
            )
            
            # 添加到知识库
            try:
                parse_result = document_parser.parse_document(str(file_path), uploaded_file.name)
                raw_content = parse_result["raw_content"]
                metadata = parse_result["metadata"]
                
                kb.add_document(doc_id, raw_content, metadata, intent_space_id)
                st.success(f"文档上传成功并已添加到知识库！文档ID: {doc_id}")
            except Exception as kb_error:
                st.warning(f"文档已保存但添加到知识库失败: {kb_error}")
                st.info("文档已保存到数据库，但可能需要重新上传以添加到知识库")
            
        except Exception as e:
            st.error(f"上传失败: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    # 文档列表
    st.subheader("文档列表")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, intent_spaces.name AS intent_space_name
            FROM documents d
            LEFT JOIN intent_spaces ON d.intent_space_id = intent_spaces.id
            ORDER BY d.upload_date DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            df = pd.DataFrame([
                {
                    "ID": row["id"],
                    "文件名": row["filename"],
                    "格式": row["file_format"],
                    "大小": f"{row['file_size']/1024:.1f} KB" if row['file_size'] else "0 KB",
                    "状态": row["status"],
                    "意图空间": row["intent_space_name"] if row["intent_space_name"] else "未分配",
                    "上传时间": row["upload_date"]
                }
                for row in rows
            ])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("暂无文档")
    except Exception as e:
        st.error(f"加载文档列表失败: {e}")
        st.info("暂无文档")


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
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM intent_spaces ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            for row in rows:
                with st.expander(f"📁 {row['name']}"):
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
        days = st.slider("时间范围（天）", 1, 30, 7)
        accuracy_data = analytics.get_classification_accuracy(days)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("总查询数", accuracy_data.get("total_queries", 0))
            avg_conf = accuracy_data.get("average_confidence", 0)
            st.metric("平均置信度", f"{avg_conf:.2f}")
        with col2:
            acc_rate = accuracy_data.get("accuracy_rate", 0)
            st.metric("准确率", f"{acc_rate*100:.1f}%")
        
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
        import traceback
        st.code(traceback.format_exc())


def main():
    """主函数"""
    init_session_state()
    
    # 侧边栏导航
    st.sidebar.title("IntelliKnow KMS")
    page = st.sidebar.selectbox(
        "选择页面",
        ["仪表板", "前端集成", "知识库管理", "意图配置", "分析报告"]
    )
    
    if page == "仪表板":
        main_dashboard()
    elif page == "前端集成":
        frontend_integration_page()
    elif page == "知识库管理":
        kb_management_page()
    elif page == "意图配置":
        intent_configuration_page()
    elif page == "分析报告":
        analytics_page()


if __name__ == "__main__":
    main()
