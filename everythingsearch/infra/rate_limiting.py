import time
from collections import defaultdict
from functools import wraps
from flask import request, jsonify
from typing import Callable

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key: str, limit: int, period_sec: int = 60) -> bool:
        now = time.time()
        # Clean up old requests
        self.requests[key] = [t for t in self.requests[key] if now - t < period_sec]
        if len(self.requests[key]) >= limit:
            return False
        self.requests[key].append(now)
        return True

_rate_limiter = RateLimiter()

def rate_limit(limit_func: Callable[[], int], period_sec: int = 60):
    """
    基于 IP 的限制器装饰器。
    limit_func 是一个无参函数，返回 limit 数量（用于动态从 settings 获取最新的限流值）。
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limit = limit_func()
            # 如果配置 0 或负数，则可能为禁用限流
            if limit <= 0:
                return f(*args, **kwargs)
                
            # Get client IP
            ip = request.remote_addr or "unknown"
            from .settings import get_settings
            if get_settings().trust_proxy:
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    ip_list = [i.strip() for i in forwarded.split(",")]
                    ip = ip_list[0] if ip_list else ip
                
            key = f"{f.__name__}:{ip}"
            
            if not _rate_limiter.is_allowed(key, limit, period_sec):
                return jsonify({
                    "code": "RATE_LIMIT",
                    "error": "请求频率超限，请稍后再试",
                    "detail": f"Limit matched: {limit} per {period_sec}s"
                }), 429
                
            return f(*args, **kwargs)
        return wrapped
    return decorator
