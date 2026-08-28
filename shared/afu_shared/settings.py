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

    backend_cors_origins: str = "https://rtm.afu.uz"
    storage_root: str = "/app/storage"

    # --- HEMIS OAuth2 (per-user employee login) ---
    # Field names intentionally mirror the EMPLOYEE_* env var names supplied by HEMIS,
    # so the credentials block can be pasted into .env verbatim.
    # NOTE: model_config uses extra="ignore" — an env var with no field here is silently dropped.
    employee_client_id: str = ""
    employee_client_secret: str = ""
    employee_redirect_uri: str = "https://rtm.afu.uz/oauth/callback"
    employee_url_authorize: str = "https://hemis.alfraganusuniversity.uz/oauth/authorize"
    employee_url_access_token: str = "https://hemis.alfraganusuniversity.uz/oauth/access-token"
    employee_url_resource_owner_details: str = (
        "https://hemis.alfraganusuniversity.uz/oauth/api/user"
        "?fields=id,uuid,type,name,login,picture,email,university_id,phone,specialty"
    )
    # Empty means the scope param is omitted entirely — Yii2 providers often reject unknown scopes.
    employee_oauth_scope: str = ""
    #: How long a login state stays redeemable. Generous on purpose: the bot mints the
    #: state when it renders its login screen, so the clock is already running before the
    #: user taps the button and starts typing their HEMIS password.
    oauth_state_ttl_seconds: int = 3600
    oauth_debug_log_userinfo: bool = True
    oauth_allowed_user_types: str = "employee"

    # --- Outgoing mail (password reset only) ---
    #: Empty smtp_host disables sending. The reset flow then tells the user to contact RTM
    #: rather than pretending a mail went out — a silent no-op is the one behaviour that
    #: leaves somebody waiting for an email forever.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "RTM Murojaatlar <no-reply@afu.uz>"
    #: STARTTLS on the standard submission port. Set false for an implicit-TLS server on 465.
    smtp_starttls: bool = True
    #: How long a reset link stays usable.
    password_reset_ttl_minutes: int = 60

    # --- deployment ---
    public_base_url: str = "https://rtm.afu.uz"
    cookie_secure: bool = True


settings = Settings()
