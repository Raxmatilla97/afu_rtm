import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from afu_shared.settings import settings
from app.api.oauth import router as oauth_router
from app.api.router import api_router

logger = logging.getLogger(__name__)

# Settings uses extra="ignore", so a misspelled env var silently becomes an empty default
# rather than an error. Surface that at boot instead of at the first login attempt.
for _name in ("employee_client_id", "employee_client_secret", "public_base_url"):
    if not getattr(settings, _name):
        logger.warning("Setting %s is empty — HEMIS OAuth login will not work", _name.upper())

# Refusing to start is the correct response to this one. Every session in the system — the
# panel admin's included — is a JWT signed with this value, so leaving the shipped default
# in place means anyone who has read this repository can mint an admin cookie. A warning in
# a log nobody reads is not a defence; the service simply must not run.
if settings.jwt_secret in ("", "change_me"):
    raise RuntimeError(
        "JWT_SECRET is unset or still the default. Set a long random value in .env before "
        "starting: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
if len(settings.jwt_secret) < 32:
    logger.warning(
        "JWT_SECRET is only %s characters. Use at least 32 — it signs every session cookie.",
        len(settings.jwt_secret),
    )

app = FastAPI(title="AFU RTM Helpdesk API")

origins = [o.strip() for o in settings.backend_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/media/employees",
    StaticFiles(directory=f"{settings.storage_root}/employees", check_dir=False),
    name="employee-media",
)

app.include_router(api_router, prefix="/api")

# Mounted WITHOUT a prefix: the HEMIS redirect URI is https://rtm.afu.uz/oauth/callback,
# a root path. Deliberately not part of api_router, which lives under /api.
app.include_router(oauth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
