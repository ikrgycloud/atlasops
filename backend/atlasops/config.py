from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, model_validator
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
    # Explicit alias bypasses ATLAS_ for the standard local OpenAI variable.
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY", repr=False)
    ai_provider: Literal["compatible", "openai"] = "compatible"
    ai_allowed_hosts: str = "api.openai.com"
    ai_response_format: Literal["json_schema", "json_object", "text_json"] = "json_schema"
    ai_token_parameter: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    ai_max_output_tokens: int = Field(default=2500, ge=128, le=8000)
    ai_max_iterations: int = Field(default=4, ge=1, le=8)
    ai_max_tool_calls: int = Field(default=8, ge=3, le=16)
    ai_max_query_window_seconds: int = Field(default=7200, ge=60, le=7200)
    ai_max_evidence: int = Field(default=100, ge=3, le=200)
    ai_max_context_bytes: int = Field(default=60000, ge=4096, le=128000)
    ai_max_output_bytes: int = Field(default=32768, ge=1024, le=65536)
    ai_request_timeout_seconds: float = Field(default=15, ge=1, le=20)
    ai_max_elapsed_seconds: float = Field(default=60, ge=1, le=75)
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
