"""
应用配置
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
KB_DIR = DATA_DIR / "kb"

# 数据库路径
DB_PATH = DATA_DIR / "kms.db"

# 文件上传配置
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

# AI配置
AI_CONFIDENCE_THRESHOLD = 0.7  # 意图分类置信度阈值
DEFAULT_INTENT_SPACE = "General"

# 前端集成配置
TELEGRAM_API_URL = "https://api.telegram.org/bot"
TEAMS_API_URL = "https://graph.microsoft.com/v1.0"

# 响应配置
MAX_RESPONSE_LENGTH = 2000  # Telegram消息最大长度
RESPONSE_TIMEOUT = 3  # 响应超时时间（秒）

# 创建必要的目录
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
KB_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
