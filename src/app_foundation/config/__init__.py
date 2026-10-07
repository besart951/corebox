"""Typed settings are read only by adapters and application composition."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_DATABASE_", extra="ignore")
    url: SecretStr
    pool_size: int = Field(default=5, ge=1)


class JwtSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_JWT_", extra="ignore")
    secret: SecretStr = Field(min_length=32)
    issuer: str = "app-foundation"
    audience: str = "app-foundation"
    access_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_seconds: int = Field(default=2592000, ge=3600)


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_EMAIL_", extra="ignore")
    host: str
    port: int = 587
    username: str | None = None
    password: SecretStr | None = None
    start_tls: bool = True
    use_tls: bool = False


class GoogleOAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_GOOGLE_", extra="ignore")
    client_id: str
    client_secret: SecretStr
    redirect_uri: str


class StripeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_STRIPE_", extra="ignore")
    secret_key: SecretStr
    webhook_secret: SecretStr


class WhatsAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_WHATSAPP_", extra="ignore")
    access_token: SecretStr
    phone_number_id: str
    api_version: str


__all__ = (
    "DatabaseSettings",
    "EmailSettings",
    "GoogleOAuthSettings",
    "JwtSettings",
    "StripeSettings",
    "WhatsAppSettings",
)
