"""律问 · 配置加载"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "laws.db"
INDEX_PATH = DATA_DIR / "bm25.pkl"
WEB_DIR = PROJECT_ROOT / "web"

PORT = int(os.getenv("LAWQ_PORT", "8790"))

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-5.3-flash")

ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "").strip()
TOKEN_SECRET = os.getenv("TOKEN_SECRET") or (ZHIPU_API_KEY + "lawq-secret") or "lawq-dev-secret"
TOKEN_TTL_DAYS = 7

TOP_K = 6
ASK_RATE_LIMIT = (10, 60)  # 每 IP 每 60 秒最多 10 次问答
