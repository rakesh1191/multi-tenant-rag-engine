"""
Sliding window rate limiter using Redis ZSETs.

Key format: rl:{tenant_id}:{limit_key}

Usage:
    from app.common.rate_limit import RateLimit

    @router.post("/endpoint")
    async def my_endpoint(_: None = RateLimit(max_calls=60, window_seconds=60, key="query")):
        ...
"""
from __future__ import annotations

import time

from fastapi import Depends

from app.common.exceptions import RateLimitError


def RateLimit(
    max_calls: int = 60,
    window_seconds: int = 60,
    key: str = "default",
):
    """
    Dependency factory for sliding-window rate limiting.

    Returns a FastAPI Depends that:
      - Reads the current tenant via get_current_tenant dependency
      - Uses Redis ZSET to enforce max_calls per window_seconds
      - Raises RateLimitError (429) when limit is exceeded
      - Silently passes on any Redis error (fail open)
    """
    # Import here to satisfy the "lazy imports" pattern required by the project
    from app.auth.dependencies import get_current_tenant

    async def _check_rate_limit(tenant=Depends(get_current_tenant)) -> None:
        tenant_id = str(tenant.id)
        try:
            from app.cache.redis import _get_redis
            r = _get_redis()
            rl_key = f"rl:{tenant_id}:{key}"
            now = time.time()
            window_start = now - window_seconds

            pipe = r.pipeline()
            # Remove entries outside the sliding window
            await pipe.zremrangebyscore(rl_key, "-inf", window_start)
            # Count entries currently in the window
            await pipe.zcard(rl_key)
            # Record this request
            await pipe.zadd(rl_key, {str(now): now})
            # Auto-expire the key slightly after the window
            await pipe.expire(rl_key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]  # zcard result (before this request)
            if current_count >= max_calls:
                raise RateLimitError(
                    f"Rate limit exceeded: {max_calls} requests per {window_seconds}s"
                )
        except RateLimitError:
            raise
        except Exception:
            pass  # fail open — never block requests due to Redis unavailability

    return Depends(_check_rate_limit)
