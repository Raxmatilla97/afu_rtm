from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    api_hemis_token: str = ""
    api_hemis_url: str = "https://student.alfraganusuniversity.uz"

    admin_email: str = "admin@rtm.afu.uz"
    admin_password: str = ""

    jwt_secret: str = "change_me"
    session_cookie_name: str = "afu_rtm_session"
    session_ttl_days: int = 30

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    backend_cors_origins: str = "http://localhost:5173"
    storage_root: str = "/app/storage"


settings = Settings()
