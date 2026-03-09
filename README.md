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
- **部署 Teams Bot 时需要**：Cloudflare Tunnel（`brew install cloudflared`）或 ngrok（用于暴露本地服务到公网）

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/pxmlw/KMS.git
cd KMS
```

### 2. 创建虚拟环境（必需）

**重要**：macOS（特别是使用 Homebrew 安装的 Python）不允许直接安装包到系统 Python，**必须使用虚拟环境**。

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

激活虚拟环境后，命令提示符前会显示 `(venv)`。

### 3. 安装依赖

**必须在虚拟环境中安装依赖**：

```bash
# 确保虚拟环境已激活（看到 (venv) 前缀）
pip install -r requirements.txt
```

**注意**：如果遇到 `externally-managed-environment` 错误，说明你尝试在系统 Python 中安装，请先创建并激活虚拟环境。

### 4. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
# 编辑 .env，至少配置 OPENROUTER_API_KEY
```

**必需配置**（OpenRouter 用于意图分类和 AI 回复）：
- `OPENROUTER_API_KEY`：从 [OpenRouter](https://openrouter.ai/) 获取
- `OPENROUTER_MODEL`：默认 `deepseek/deepseek-chat`

**可选配置**（也可在管理界面「前端集成」中配置 Bot）：
- `TELEGRAM_BOT_TOKEN`、`TEAMS_APP_ID`、`TEAMS_APP_PASSWORD`、`TEAMS_TENANT_ID`

### 5. 启动服务

**重要**：**必须使用虚拟环境**（macOS 系统 Python 不允许直接安装包）

#### 方式1：一键启动所有服务（推荐）

**macOS / Linux：**

```bash
# 1. 确保虚拟环境已激活
source venv/bin/activate

# 2. 一键启动所有服务
./start_all.sh
```

**Windows（PowerShell）：**

```powershell
# 1. 激活虚拟环境
.\venv\Scripts\activate

# 2. 一键启动所有服务
powershell -ExecutionPolicy Bypass -File .\start_all.ps1
```

启动脚本会按顺序启动：
1. FastAPI 主服务（`http://localhost:8000`）
2. Streamlit 管理界面（`http://localhost:8501`）
3. Telegram Bot 服务（如已配置）
4. Cloudflare Tunnel（**启动前会询问**是否启动，用于 Teams Bot）

**单独管理服务（macOS / Linux）：**

```bash
./start_all.sh fastapi          # 仅启动 FastAPI
./start_all.sh streamlit        # 仅启动 Streamlit
./start_all.sh telegram         # 仅启动 Telegram Bot
./start_all.sh tunnel           # 仅启动 Cloudflare Tunnel

./start_all.sh restart fastapi  # 重启 FastAPI
./start_all.sh restart telegram # 重启 Telegram Bot
./start_all.sh restart tunnel   # 重启 Cloudflare Tunnel
```

首次使用需赋予执行权限：`chmod +x start_all.sh`

#### 方式2：分别启动各个服务

**启动 API 服务**：
```bash
# 1. 确保虚拟环境已激活（看到 (venv) 前缀）
source venv/bin/activate

# 2. 启动服务
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000
```

如果未激活虚拟环境，会提示 `ModuleNotFoundError`。

API 服务将在 `http://localhost:8000` 启动。

**启动管理界面**：
```bash
# 1. 确保虚拟环境已激活
source venv/bin/activate

# 2. 启动管理界面
python run_admin.py
# 或
streamlit run app/admin/dashboard.py
```

管理界面将在 `http://localhost:8501` 启动。

**启动 Telegram Bot**（如已配置）：
```bash
# 1. 激活虚拟环境（如果使用虚拟环境）
source venv/bin/activate

# 2. 启动Bot
python3 start_telegram_bot.py
```

## 📖 使用指南

### 管理界面功能

访问 `http://localhost:8501` 进入管理界面：

1. **仪表板**：查看系统统计和查询历史
2. **前端集成**：配置 Teams Bot 和 Telegram Bot
   - 每种前端仅支持一个在线 Bot 配置（可编辑/删除/更换）
   - 实时连接状态检测（调用 Telegram / Teams 平台接口）
   - Webhook URL 自动保存和显示（Cloudflare Tunnel）
   - Bot 配置的增删改查
3. **知识库管理**：上传、删除文档，关联意图空间
4. **意图配置**：创建、删除意图空间（HR、法律、财务等），配置描述和关键词
5. **分析报告**：查看查询统计、分类准确率、知识库使用情况

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
   
   **使用 Cloudflare Tunnel（推荐，支持自动保存 URL）**：
   ```bash
   # 安装 cloudflared（如果未安装）
   # macOS: brew install cloudflared
   # Linux: 从 https://github.com/cloudflare/cloudflared/releases 下载
   
   # 方式1：使用自动保存 URL 的启动脚本（推荐）
   python3 start_tunnel_with_save.py
   
   # 方式2：手动启动（需要手动复制 URL）
   cloudflared tunnel --url http://localhost:8000
   ```
   
   运行后会显示一个公网URL，例如：`https://xxxxx.trycloudflare.com`
   
   **注意**：使用 `start_tunnel_with_save.py` 启动时，URL 会自动保存到数据库，并在管理界面显示。
   
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
   
   **提示**：如果使用 `start_tunnel_with_save.py` 启动 Tunnel，完整 Webhook URL 会自动显示在管理界面的"前端集成"页面，可以直接复制使用。

6. 确保 API 服务正在运行（`python main.py` 或使用一键启动脚本）

### 配置 Telegram Bot

1. 在 Telegram 中联系 @BotFather 创建 Bot
2. 获取 Bot Token
3. 在管理界面"前端集成"页面配置 Token
4. 运行 `python3 start_telegram_bot.py` 启动 Bot 服务

### API 使用示例

#### 健康检查

```bash
curl http://localhost:8000/health
```

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
KMS/                    # 或 fastapi-webapp/（项目根目录）
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
│   │   ├── bot_monitor.py  # Bot 连接监控
│   │   ├── document_parser.py # 文档解析
│   │   ├── knowledge_base.py  # 知识库
│   │   └── orchestrator.py   # 意图分类
│   ├── utils/              # 工具函数
│   │   └── tunnel_url_saver.py # Tunnel URL 保存工具
│   └── config.py           # 应用配置
├── data/                   # 数据目录
│   ├── documents/         # 上传的文档
│   └── kb/                # 知识库索引
├── logs/                   # 日志目录（自动创建，含 fastapi.log、streamlit.log 等）
├── main.py                 # FastAPI 应用入口
├── run_admin.py           # 管理界面启动脚本
├── start_all.sh           # 一键启动所有服务（Shell脚本）
├── start_telegram_bot.py  # Telegram Bot 启动脚本
├── start_tunnel_with_save.py # Cloudflare Tunnel 启动脚本（自动保存URL）
├── .env.example           # 环境变量示例（复制为 .env 并填写）
├── requirements.txt       # Python 依赖
└── README.md              # 本文件
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

### 服务无法启动 / ModuleNotFoundError / externally-managed-environment

**问题1**：运行 `python3 main.py` 时提示 `ModuleNotFoundError: No module named 'fastapi'`

**解决方案**：必须使用虚拟环境：
```bash
# 1. 创建虚拟环境（如果还没有）
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python main.py
```

**问题2**：运行 `pip3 install -r requirements.txt` 时提示 `externally-managed-environment`

**原因**：macOS（Homebrew Python）不允许直接安装包到系统 Python。

**解决方案**：必须使用虚拟环境（同上）。

**检查虚拟环境是否激活**：
- 命令提示符前应该显示 `(venv)`
- 或运行：`which python` 应该显示 `.../venv/bin/python`

**检查依赖安装情况**：
```bash
# 在虚拟环境中运行
source venv/bin/activate
python -c "import fastapi, uvicorn, streamlit; print('核心依赖已安装')"
```

### Telegram Bot 无法启动

- 检查 Token 是否正确配置（管理界面或 .env）
- 确保 `start_telegram_bot.py` 或 `start_all.sh` 已启动 Telegram 服务
- 确保依赖已安装（虚拟环境）
- 检查网络连接（Telegram API 需可访问）

### Teams Bot 连接失败

- 检查 Azure 配置是否正确
- 确认 Messaging Endpoint URL 可访问
- 检查 Tenant ID 是否正确（单租户 Bot）
- **确保 Cloudflare Tunnel 或 ngrok 正在运行**
- 验证隧道URL是否正确配置到 Azure Bot Service
- 检查本地 API 服务是否在运行（`http://localhost:8000`）
- **使用 `start_tunnel_with_save.py` 启动 Tunnel 时，URL 会自动保存并在管理界面显示**
- 如果 Tunnel URL 变化，需要重新在 Azure Portal 中配置 Messaging Endpoint

### 文档无法搜索

- 确认文档已成功上传且状态为「已处理」
- 检查文档是否关联了正确的意图空间（未关联则匹配所有查询）
- 查询内容需与意图空间描述/关键词或文档内容相关
- 查看 API 日志：`tail -f logs/fastapi.log`

## 📝 开发说明

### 添加新的前端集成

1. 继承 `FrontendIntegration` 基类
2. 实现 `setup_handlers()` 和 `handle_message()` 方法
3. 在 `app/api/routes.py` 添加对应的 webhook 端点（如适用）

### 扩展意图分类

意图空间和关键词在管理界面「意图配置」中维护，系统会动态加载，**无需修改代码**。如需自定义分类逻辑，可修改 `app/services/orchestrator.py`。

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题或建议，请通过 GitHub Issues 联系。
