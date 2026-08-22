from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from afu_shared.settings import settings

JWT_ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, subject: str, scope: str, expires_days: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "scope": scope,
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
