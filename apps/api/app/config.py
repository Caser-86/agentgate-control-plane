from functools import lru_cache

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
    database_url: str = "sqlite:///./data/agentgate.db"
    max_steps: int = 8
    tool_timeout_seconds: int = 10
    run_timeout_seconds: int = 120
    web_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
