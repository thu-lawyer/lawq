"""律问 · 访问口令 → HMAC token（7 天）"""
import base64
import hashlib
import hmac
import time

from .config import ACCESS_PASSWORD, TOKEN_SECRET, TOKEN_TTL_DAYS


def issue_token() -> str:
    exp = int(time.time()) + TOKEN_TTL_DAYS * 86400
    sig = hmac.new(TOKEN_SECRET.encode(), f"lawq|{exp}".encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{exp}|{sig}".encode()).decode()


def verify_token(token: str | None) -> bool:
    if not ACCESS_PASSWORD:
        return True  # 未设口令 = 开放模式
    if not token:
        return False
    try:
        exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
        good = hmac.new(TOKEN_SECRET.encode(), f"lawq|{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > time.time()
    except Exception:
        return False


def check_password(password: str) -> bool:
    return not ACCESS_PASSWORD or hmac.compare_digest(password, ACCESS_PASSWORD)
