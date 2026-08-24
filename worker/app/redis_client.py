"""One Redis connection for the worker, shared the way ``bot_client`` shares the Bot.

Every notification now writes a message→request link, and opening a fresh connection per
job would spend more time on the handshake than on the write.
"""

from redis.asyncio import Redis

from afu_shared.settings import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        # decode_responses matches what the bot uses, so both sides read back the same
        # strings from the same keys.
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis
