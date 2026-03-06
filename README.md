# IntelliKnow KMS - 智能知识管理系统

基于 Gen AI 驱动的企业知识管理系统，支持多平台集成（Microsoft Teams、Telegram），提供智能文档检索和自然语言问答功能。

## ✨ 主要特性

- 📚 **智能文档管理**：支持 PDF、Word 文档上传和解析
- 🔍 **语义搜索**：基于 FAISS 和 Sentence Transformers 的向量检索
- 🎯 **意图分类**：自动识别查询意图（HR、法律、财务等）
- 💬 **多平台集成**：
  - Microsoft Teams Bot（Webhook 模式）
  - Telegram Bot（Polling 模式）
- 📊 **管理仪表板**：Streamlit 驱动的可视化管理界面
- 🤖 **AI 驱动**：集成 OpenRouter API，支持多种 LLM 模型

## 🏗️ 技术架构

- **后端框架**：FastAPI
- **数据库**：SQLite
- **向量数据库**：FAISS
- **嵌入模型**：Sentence Transformers (paraphrase-multilang-MiniLM-L12-v2)
- **AI 服务**：OpenRouter API（默认使用 DeepSeek Chat）
- **前端集成**：
  - Microsoft Teams Bot Framework
  - Python Telegram Bot
- **管理界面**：Streamlit

## 📋 系统要求

- Python 3.8+
- pip 或 pip3
- **部署 Teams Bot 时需要**：Cloudflare Tunnel 或 ngrok（用于暴露本地服务到公网）

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/pxmlw/KMS.git
cd KMS
```

### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

创建 `.env` 文件（参考 `.env.example`）：

```env
# OpenRouter API配置
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=deepseek/deepseek-chat

# Telegram Bot配置（可选）
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Teams Bot配置（可选）
TEAMS_APP_ID=your_teams_app_id
TEAMS_APP_PASSWORD=your_teams_app_password
TEAMS_TENANT_ID=your_tenant_id
```

### 5. 启动服务

#### 启动 API 服务

```bash
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000
```

API 服务将在 `http://localhost:8000` 启动。

#### 启动管理界面

```bash
python run_admin.py
# 或
streamlit run app/admin/dashboard.py
```

管理界面将在 `http://localhost:8501` 启动。

#### 启动 Telegram Bot（如已配置）

```bash
./start_telegram.sh
# 或
python start_telegram_bot.py
```

## 📖 使用指南

### 管理界面功能

访问 `http://localhost:8501` 进入管理界面：

1. **仪表板**：查看系统统计和查询历史
2. **前端集成**：配置 Teams Bot 和 Telegram Bot
3. **知识库管理**：上传和管理文档
4. **意图配置**：创建和管理意图空间（HR、法律、财务等）
5. **分析报告**：查看查询统计和准确率

### 上传文档

1. 在管理界面选择"知识库管理"
2. 选择文档文件（支持 PDF、Word）
3. 选择关联的意图空间（可选）
4. 点击"上传"

### 配置 Teams Bot

1. 在 Azure Portal 创建 Bot 应用注册
2. 获取 App ID、App Password 和 Tenant ID
3. 在管理界面"前端集成"页面配置
4. **暴露 API 服务**（使用 Cloudflare Tunnel 或 ngrok）：
   
   **使用 Cloudflare Tunnel（推荐）**：
   ```bash
   # 安装 cloudflared（如果未安装）
   # macOS: brew install cloudflared
   # Linux: 从 https://github.com/cloudflare/cloudflared/releases 下载
   
   # 创建隧道（首次使用）
   cloudflared tunnel create kms-tunnel
   
   # 运行隧道（将本地8000端口暴露到公网）
   cloudflared tunnel --url http://localhost:8000
   ```
   
   运行后会显示一个公网URL，例如：`https://xxxxx.trycloudflare.com`
   
   **或使用 ngrok**：
   ```bash
   # 安装 ngrok（如果未安装）
   # 从 https://ngrok.com/download 下载
   
   # 设置 authtoken（首次使用）
   ngrok config add-authtoken YOUR_AUTHTOKEN
   
   # 暴露本地8000端口
   ngrok http 8000
   ```
   
   运行后会显示一个公网URL，例如：`https://xxxxx.ngrok.io`

5. 设置 Teams Bot 的 Messaging Endpoint：
   - Cloudflare Tunnel: `https://xxxxx.trycloudflare.com/api/teams/messages`
   - ngrok: `https://xxxxx.ngrok.io/api/teams/messages`

6. 确保 API 服务正在运行（`python main.py`）

### 配置 Telegram Bot

1. 在 Telegram 中联系 @BotFather 创建 Bot
2. 获取 Bot Token
3. 在管理界面"前端集成"页面配置 Token
4. 运行 `./start_telegram.sh` 启动 Bot 服务

### API 使用示例

#### 查询知识库

```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "年假有多少天？",
    "frontend_type": "api"
  }'
```

#### 上传文档

```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -F "file=@document.pdf" \
  -F "intent_space_id=1"
```

## 📁 项目结构

```
fastapi-webapp/
├── app/
│   ├── admin/              # Streamlit 管理界面
│   │   └── dashboard.py
│   ├── api/                # FastAPI 路由
│   │   └── routes.py
│   ├── integrations/       # 前端集成
│   │   ├── base.py         # 集成基类
│   │   ├── telegram_bot.py # Telegram Bot
│   │   └── teams_bot.py    # Teams Bot
│   ├── models/             # 数据模型
│   │   └── database.py
│   ├── services/           # 业务逻辑
│   │   ├── analytics.py    # 分析服务
│   │   ├── document_parser.py # 文档解析
│   │   ├── knowledge_base.py  # 知识库
│   │   └── orchestrator.py   # 意图分类
│   └── config.py           # 配置
├── data/                   # 数据目录
│   ├── documents/         # 上传的文档
│   └── kb/                # 知识库索引
├── main.py                 # FastAPI 应用入口
├── run_admin.py           # 管理界面启动脚本
├── start_telegram_bot.py  # Telegram Bot 启动脚本
├── start_telegram.sh      # Telegram Bot 便捷启动脚本
├── requirements.txt       # Python 依赖
└── README.md             # 本文件
```

## 🔧 配置说明

### OpenRouter API

系统使用 OpenRouter API 作为 LLM 服务，默认模型为 `deepseek/deepseek-chat`。

如需更换模型，修改 `.env` 文件中的 `OPENROUTER_MODEL`。

### 意图空间

系统支持多个意图空间，用于分类不同类型的查询：

- **HR**：人力资源相关问题
- **Legal**：法律合规问题
- **Finance**：财务相关问题
- **General**：通用问题

可以在管理界面创建和管理意图空间。

## 🐛 故障排查

### Telegram Bot 无法启动

- 检查 Token 是否正确配置
- 确保虚拟环境已激活
- 检查网络连接

### Teams Bot 连接失败

- 检查 Azure 配置是否正确
- 确认 Messaging Endpoint URL 可访问
- 检查 Tenant ID 是否正确（单租户 Bot）
- **确保 Cloudflare Tunnel 或 ngrok 正在运行**
- 验证隧道URL是否正确配置到 Azure Bot Service
- 检查本地 API 服务是否在运行（`http://localhost:8000`）

### 文档无法搜索

- 确认文档已成功上传
- 检查文档是否关联了正确的意图空间
- 查看 API 日志了解错误信息

## 📝 开发说明

### 添加新的前端集成

1. 继承 `FrontendIntegration` 基类
2. 实现 `setup_handlers()` 和 `handle_message()` 方法
3. 在 `app/api/routes.py` 添加对应的 webhook 端点（如适用）

### 扩展意图分类

修改 `app/services/orchestrator.py` 中的分类逻辑和关键词配置。

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题或建议，请通过 GitHub Issues 联系。
