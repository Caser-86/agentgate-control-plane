from functools import lru_cache
from typing import Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTGATE_",
        env_file=(".env", "../../.env"),
        extra="ignore",
    )

    app_name: str = "agentgate-api"
    llm_provider: str = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "mock-operations-agent"
    database_url: str = "postgresql+psycopg://agentgate:agentgate@postgres:5432/agentgate"
    database_migration_required: bool = True
    worker_lease_seconds: int = 30
    worker_ready_file: str | None = None
    e2e_reset_database: bool = False
    outbox_batch_size: int = 100
    auth_bootstrap_token_file: str = "/app/data/bootstrap-token"
    auth_bootstrap_ttl_seconds: int = 900
    auth_session_ttl_seconds: int = 28800
    auth_cookie_secure: bool = False
    auth_enabled: bool = True
    api_port: int = Field(default=8000, ge=1, le=65535)
    web_port: int = Field(default=5173, ge=1, le=65535)
    environment: str = Field(default="production", validation_alias="AGENTGATE_ENV")
    seed_example: bool = Field(
        default=False,
        validation_alias=AliasChoices("AGENTGATE_SEED_EXAMPLE", "AGENTGATE_SEED_DEMO"),
    )
    max_steps: int = 8
    tool_timeout_seconds: int = 10
    run_timeout_seconds: int = 120
    workspace_allowed_root: str = Field(
        default=r"C:\AgentGate\workspaces",
        validation_alias="AGENTGATE_WORKSPACE_ALLOWED_ROOT",
    )

    @model_validator(mode="after")
    def validate_auth_boundary(self) -> Self:
        if not self.auth_enabled and self.environment != "development":
            raise ValueError(
                "AGENTGATE_AUTH_ENABLED=false 仅允许在 AGENTGATE_ENV=development 时使用"
            )
        return self

    @property
    def api_base_url(self) -> str:
        return f"http://localhost:{self.api_port}"

    @property
    def web_origin(self) -> str:
        return f"http://localhost:{self.web_port}"

    @property
    def web_origins(self) -> list[str]:
        return [self.web_origin, f"http://127.0.0.1:{self.web_port}"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
