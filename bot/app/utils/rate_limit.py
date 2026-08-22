from redis.asyncio import Redis

MAX_EMPLOYEE_ID_ATTEMPTS = 5
EMPLOYEE_ID_ATTEMPTS_WINDOW_SECONDS = 600


async def register_employee_id_attempt(redis: Redis, telegram_user_id: int) -> bool:
    """Returns True if this attempt is allowed, False if the caller should be rate-limited."""
    key = f"bot:id_guess_attempts:{telegram_user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, EMPLOYEE_ID_ATTEMPTS_WINDOW_SECONDS)
    return count <= MAX_EMPLOYEE_ID_ATTEMPTS
