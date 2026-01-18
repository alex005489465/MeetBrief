import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 基礎路徑
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "meetbrief.db"

# 確保目錄存在
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# DeepSeek API 設定
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Whisper 設定
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

# Redis 設定
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 上傳設定
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 524288000))  # 500MB
ALLOWED_EXTENSIONS = ["mp3", "wav", "m4a", "ogg", "webm", "aac", "flac", "wma"]
