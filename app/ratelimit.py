"""律问 · 轻量滑动窗口限流（进程内）"""
import collections
import threading
import time

_buckets: dict[str, collections.deque] = {}
_lock = threading.Lock()


def allow(key: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    with _lock:
        dq = _buckets.setdefault(key, collections.deque())
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True
