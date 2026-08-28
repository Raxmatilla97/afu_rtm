"""A small fixed-window rate limiter for the endpoints that guard identity.

The quick login answers two questions that are worth abusing: "does this employee id
exist, and whose is it?" and "is this the password?". The per-account lockout in
``afu_shared.quick_login`` covers the second one for a single account, but neither covers
somebody walking a list of id numbers from one machine — ten-digit numbers are guessable in
blocks, and the lookup returns a name.

So: a counter per caller per endpoint, in Redis, expiring with its window. Fixed-window
rather than a sliding log because the failure mode of the simple version is that somebody
gets 2× the limit across a window boundary, which is irrelevant at these sizes, while the
failure mode of a clever version is a bug in the thing standing between users and login.

Redis being unreachable must never lock people out of the system it protects, so a failure
here allows the request and logs it.
"""

import logging

from fastapi import HTTPException, Request, status

from app.arq_pool import get_arq_pool

logger = logging.getLogger(__name__)

#: Written by our own nginx from ``$remote_addr`` (deploy/frontend-nginx.conf), so unlike
#: X-Forwarded-For it cannot be set by the caller.
_REAL_IP_HEADER = "x-real-ip"


def client_key(request: Request) -> str:
    real_ip = request.headers.get(_REAL_IP_HEADER)
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


async def enforce(
    request: Request, *, bucket: str, limit: int, window_seconds: int, message: str
) -> None:
    """Count one attempt; raise 429 once the caller is over the limit for this window."""
    key = f"ratelimit:{bucket}:{client_key(request)}"
    try:
        redis = await get_arq_pool()
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, window_seconds)
    except Exception as exc:  # noqa: BLE001 - any Redis fault must not become a lockout
        logger.warning("Rate limit check failed for %s, allowing through: %r", bucket, exc)
        return

    if used > limit:
        logger.warning("Rate limit hit: bucket=%s key=%s used=%s", bucket, key, used)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(window_seconds)},
        )
