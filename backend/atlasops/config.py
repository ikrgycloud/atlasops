from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ATLAS_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    mode: Literal["development", "production"] = "production"
    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    dev_auth_enabled: bool = False
    dev_auth_secret: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,testserver,host.docker.internal,api"
    integration_hosts: str = ""
    allow_insecure_integrations: bool = False
    report_timezone: str = "Asia/Kolkata"
    report_hour: int = 8
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_username: str = ""
    smtp_password_ref: str = ""
    smtp_sender: str = "atlasops@localhost"
    report_recipient: str = ""
    ai_url: str = ""
    ai_model: str = ""
    ai_secret_ref: str = ""
    telemetry_ttl_seconds: int = 900

    @model_validator(mode="after")
    def validate_runtime(self):
        ZoneInfo(self.report_timezone)
        if not 0 <= self.report_hour <= 23:
            raise ValueError("report_hour must be between 0 and 23")
        if self.dev_auth_enabled and (self.mode != "development" or len(self.dev_auth_secret) < 32):
            raise ValueError(
                "Development authentication requires development mode and a 32+ character secret"
            )
        if self.mode == "production" and not all((self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)):
            raise ValueError("Production requires OIDC issuer, audience and JWKS URL")
        if self.allow_insecure_integrations and self.mode != "development":
            raise ValueError("Insecure integration HTTP is restricted to development")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
