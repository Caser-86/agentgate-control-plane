from sqlmodel import Session

from app.auth.dependencies import ClientIdentity
from app.config import Settings
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import append_outbox_event, enqueue_task
from app.llm.base import LLMProvider
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.models import AgentRun
from app.repositories import AuditRepository, RunRepository
from app.services.audit import AuditService

CONTROL_RUN_CAPABILITY = "control.run"


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

    def create(self, user_request: str, source: ClientIdentity | object) -> AgentRun:
        """Persist the run and its continuation atomically without touching a provider."""
        actor = getattr(source, "actor", None)
        if not isinstance(actor, str):
            operator_id = getattr(source, "id", None)
            actor = f"operator:{operator_id}" if operator_id is not None else "system"
        runs = RunRepository(self.session)
        try:
            run = runs.create(
                user_request, self.settings.llm_provider, self.settings.llm_model, commit=False
            )
            runs.save_checkpoint(
                run.id, [{"role": "user", "content": user_request}], 0, commit=False
            )
            AuditService(AuditRepository(self.session)).append(
                run.id, "run.created", actor, {"user_request": user_request}, commit=False
            )
            task = enqueue_task(
                self.session,
                kind=TaskKind.AGENT_RUN,
                payload={"run_id": str(run.id)},
                idempotency_key=f"agent-run-resume:{run.id}:initial",
                capability=CONTROL_RUN_CAPABILITY,
                run_id=run.id,
                side_effect_certainty=SideEffectCertainty.READ_ONLY,
            )
            append_outbox_event(
                self.session,
                event_type="task.queued",
                resource_type="run",
                resource_id=run.id,
                payload={"task_id": str(task.id), "kind": task.kind.value},
            )
            self.session.commit()
            self.session.refresh(run)
            return run
        except Exception:
            self.session.rollback()
            raise
