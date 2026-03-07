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
USE_AI_RESPONSE = True  # 是否使用AI生成响应（False则总是使用简化响应）
FAST_RESPONSE_THRESHOLD = 0.95  # 快速响应阈值（score > 此值才使用简化响应，提高阈值确保大部分使用AI）


# 创建必要的目录
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
KB_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
