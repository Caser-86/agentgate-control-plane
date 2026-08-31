from fastapi import BackgroundTasks
from sqlmodel import Session

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.models import AgentRun
from app.services.agent_loop import AgentRunner


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "openai_compatible":
        if not settings.llm_base_url or not settings.llm_api_key:
            raise RuntimeError("OpenAI-compatible provider requires base URL and API key")
        return OpenAICompatibleProvider(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
        )
    raise RuntimeError(f"unknown LLM provider: {settings.llm_provider}")


class RunService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create(self, user_request: str, background_tasks: BackgroundTasks) -> AgentRun:
        provider = build_provider(self.settings)
        runner = AgentRunner(
            self.session,
            provider=provider,
            provider_name=self.settings.llm_provider,
            model=self.settings.llm_model,
            max_steps=self.settings.max_steps,
            run_timeout_seconds=self.settings.run_timeout_seconds,
        )
        run = runner.create_run(user_request)
        background_tasks.add_task(runner.resume_run, run.id)
        return run
