import time
import redis
from fastapi import HTTPException, Request
from app.settings import settings

r = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

def rate_limit(_request: Request, key: str, limit: int, window_seconds: int):
    now = int(time.time())
    window = now // window_seconds
    rk = f"rl:{key}:{window}"

    count = r.incr(rk)
    if count == 1:
        r.expire(rk, window_seconds)

    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests")
