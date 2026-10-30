from typing import Optional
from urllib.parse import quote
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_URL: str = "http://localhost:8000"
    
    # Token expiration times (in minutes)
    TOKEN_EXPIRE_TIME: int = 30
    MAIL_VAL_EXPIRE_TIME: int = 30
    RESET_PW_CODE_EXPIRE_TIME: int = 5
    
    # MySQL Database
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "laravel"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    
    @property
    def REDIS_URL(self) -> str:
        auth = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CELERY_BROKER_URL = self.REDIS_URL
        self.CELERY_RESULT_BACKEND = self.REDIS_URL
    
    # Google SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # Storage
    STORAGE_BASE_PATH: str = "storage/app/private/files"
    STORAGE_RECALCULATION_PERIOD: int = 604800  # 7 days in seconds
    DOWNLOAD_TOKEN_EXPIRE_SECONDS: int = 30  # seconds

    # Collaboration snapshots
    SNAPSHOT_INTERVAL: int = 900  # 15 minutes in seconds

    # Collaboration WebSocket auth (short-lived single-use ticket via Sec-WebSocket-Protocol)
    WS_SUBPROTOCOL: str = "meowcloud-collab.v1"
    WS_TICKET_TTL_SECONDS: int = 60
    MAX_COLLAB_CONTENT_BYTES: int = 2 * 1024 * 1024   # 2MB, aligned with MAX_EDIT_BYTES
    MAX_Y_UPDATE_BYTES: int = 2 * 1024 * 1024        # per y_update payload
    MAX_ROOM_CONNECTIONS: int = 50                   # concurrent sockets per file room
    WS_MSG_PER_MIN: int = 1200                       # per-connection message rate (burst-tolerant)
    COLLAB_STATE_TTL_SECONDS: int = 7 * 24 * 3600    # expire abandoned collab keys
    COLLAB_UPDATE_BUDGET_BYTES: int = 16 * 1024 * 1024  # per-file y-update log budget
    MAX_Y_INCREMENTAL_BYTES: int = 2 * 1024 * 1024    # single incremental y_update cap

    # Allowed browser origins for CORS / Origin checks / WS
    ALLOWED_ORIGINS: str = "https://meowcloud.jun.org.uk,https://meowcloud-api.jun.org.uk"

    # Session cookie SameSite. "lax" is correct for a same-site SPA+API split
    # (both under one registrable domain). Set to "none" ONLY for a genuine
    # cross-site deployment (different eTLD+1 for SPA and API); browsers then
    # also require Secure, which the app always sets.
    COOKIE_SAMESITE: str = "lax"

    # Behind a non-Cloudflare reverse proxy (own domain / VPS), CF-Connecting-IP
    # is absent and every request would collapse to the proxy's loopback IP.
    # When true, fall back to X-Real-IP but ONLY if the direct peer is a
    # loopback/trusted proxy address (never a client-supplied XFF).
    TRUST_REAL_IP: bool = False
    TRUSTED_PROXY_IPS: str = "127.0.0.1,::1"

    @property
    def trusted_proxy_ips(self) -> set[str]:
        return {p.strip() for p in self.TRUSTED_PROXY_IPS.split(",") if p.strip()}

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # API docs are off by default. When enabled they are served ONLY for direct
    # loopback access (no proxy headers) — i.e. local development, never the tunnel.
    ENABLE_API_DOCS: bool = False

    # TUS temporary uploads older than this are garbage-collected.
    TUS_TEMP_MAX_AGE_SECONDS: int = 24 * 3600

    # Trash cleanup (celery beat)
    TRASH_RETENTION_DAYS: int = 30
    TRASH_CLEANUP_INTERVAL_SECONDS: int = 604800  # 7 days

    # Password-protected share links
    SHARE_TICKET_SECRET: str = ""  # empty = per-process ephemeral key (tickets die on restart)
    SHARE_TICKET_TTL_SECONDS: int = 900  # 15 minutes

    # Security monitoring & auto-throttling
    SECURITY_ALERT_ENABLED: bool = True
    SECURITY_ALERT_EMAIL: str = ""              # empty -> send to SMTP_FROM (self)
    SEC_GLOBAL_HOURLY_LIMIT: int = 5000         # flood guard per IP
    SEC_SCORE_SLOW_THRESHOLD: int = 20          # violation score/h -> transfer throttle
    SEC_SCORE_BLOCK_THRESHOLD: int = 15         # auth-probe score/h -> direct site block
    SEC_UPLOAD_HOURLY_LIMIT: int = 600          # upload starts per user-hour
    SEC_DOWNLOAD_HOURLY_LIMIT: int = 300        # downloads per user-hour
    SEC_ANON_DOWNLOAD_HOURLY_LIMIT: int = 150   # anonymous share downloads per IP-hour
    SEC_DEFAULT_UPLOAD_DELAY_MS: int = 2000
    SEC_DEFAULT_DOWNLOAD_DELAY_MS: int = 0
    SEC_DEFAULT_UPLOAD_KBPS: int = 256
    SEC_DEFAULT_DOWNLOAD_KBPS: int = 512

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
