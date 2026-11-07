from functools import lru_cache

from redis import Redis

from app.config import get_settings


@lru_cache
def get_redis() -> Redis:
    """Process-wide sync Redis client (used for health checks and event publishing)."""
    # Short timeouts: publishing happens inside requests and must never hang one.
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
