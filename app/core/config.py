import hashlib
import logging
from functools import lru_cache
from typing import List, Literal

from pydantic import AnyHttpUrl, EmailStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ───────────────────────────────────────────────
    APP_NAME: str = "MyApp API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ─── Security ─────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Secret Encryption (Fernet) ───────────────────────
    # Used to encrypt BotEnvVar.value when is_secret=True.
    #
    # Must be a URL-safe base64-encoded 32-byte key, exactly as produced by:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    #
    # In production:  REQUIRED — startup fails if absent.
    # In development: auto-generated as a deterministic fallback derived from
    #                 SECRET_KEY so the dev environment always boots without
    #                 extra setup.  A warning is logged so developers know
    #                 they are using the fallback.
    #
    # ⚠  Never commit a real production key to version control.
    SECRET_ENCRYPTION_KEY: str = ""  # empty → trigger fallback logic below

    # ─── Database ─────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "myapp_db"
    POSTGRES_USER: str = "myapp_user"
    POSTGRES_PASSWORD: str

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Used by Alembic (sync driver)."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ─── Redis ────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ─── CORS ─────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    # ─── Rate Limiting ────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ─── First Superuser ──────────────────────────────────
    FIRST_SUPERUSER_EMAIL: EmailStr = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "changeme123"

    # ─── Helpers ──────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    # ─── Encryption key validation / fallback ─────────────
    @model_validator(mode="after")
    def validate_encryption_key(self) -> "Settings":
        """
        Enforce SECRET_ENCRYPTION_KEY policy:

          production  → key MUST be set; raise ValueError if absent/empty.
          dev/staging → if absent, derive a deterministic fallback from
                        SECRET_KEY so the app boots without extra config.
                        Log a prominent warning so developers notice.

        The fallback key is derived via HKDF-like logic using SHA-256 so it
        is stable across restarts (same SECRET_KEY → same fallback), while
        being completely isolated from the JWT secret in terms of usage.

        The derived key is valid Fernet (URL-safe base64, 32 bytes) because
        we take the first 32 bytes of SHA-256(SECRET_KEY + salt) and
        base64url-encode them.
        """
        import base64 as _b64

        if self.SECRET_ENCRYPTION_KEY.strip():
            # Key was explicitly provided — validate length/format later in
            # crypto.py when Fernet() is actually constructed.  No action here.
            return self

        # Key is absent or blank.
        if self.is_production:
            raise ValueError(
                "\n\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  ERRO DE CONFIGURAÇÃO — SECRET_ENCRYPTION_KEY ausente        ║\n"
                "║                                                              ║\n"
                "║  Em produção, SECRET_ENCRYPTION_KEY é OBRIGATÓRIA.          ║\n"
                "║                                                              ║\n"
                "║  Gere uma chave segura com:                                  ║\n"
                "║    python -c \"from cryptography.fernet import Fernet;       ║\n"
                "║              print(Fernet.generate_key().decode())\"         ║\n"
                "║                                                              ║\n"
                "║  Adicione ao .env (ou variável de ambiente):                 ║\n"
                "║    SECRET_ENCRYPTION_KEY=<chave gerada acima>               ║\n"
                "╚══════════════════════════════════════════════════════════════╝\n"
            )

        # Development / staging fallback: derive from SECRET_KEY.
        # We use a fixed salt so the derivation is domain-separated from
        # other uses of SECRET_KEY.
        _SALT = b"serverdronics:encryption-key-derivation:v1"
        digest = hashlib.sha256(
            self.SECRET_KEY.encode("utf-8") + _SALT
        ).digest()  # 32 bytes
        derived_key = _b64.urlsafe_b64encode(digest).decode("ascii")

        object.__setattr__(self, "SECRET_ENCRYPTION_KEY", derived_key)

        _logger.warning(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║  AVISO DE SEGURANÇA — usando chave de criptografia de        ║\n"
            "║  desenvolvimento (derivada de SECRET_KEY).                   ║\n"
            "║                                                              ║\n"
            "║  Defina SECRET_ENCRYPTION_KEY no .env para remover este      ║\n"
            "║  aviso e usar uma chave dedicada e segura.                   ║\n"
            "║                                                              ║\n"
            "║  Esta chave derivada NÃO deve ser usada em produção.         ║\n"
            "╚══════════════════════════════════════════════════════════════╝"
        )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
