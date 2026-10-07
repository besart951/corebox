from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXAMPLE_", env_file=".env", extra="ignore")
    database_url: SecretStr
    jwt_secret: SecretStr = Field(min_length=32)
    encryption_key: SecretStr
    public_url: str = "http://localhost:8000"
    sender_email: str = "noreply@example.com"
    cors_origins: tuple[str, ...] = ()
    smtp_host: str | None = None
    smtp_port: int = 587
    google_enabled: bool = False
    stripe_enabled: bool = False
    billing_price_ids: frozenset[str] = frozenset()
    jobs_enabled: bool = True
