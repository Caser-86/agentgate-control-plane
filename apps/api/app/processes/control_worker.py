"""Durable local dispatcher for control-plane run continuation tasks."""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.config import Settings, get_settings
from app.control.enums import TaskKind, TaskOutcome, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import append_outbox_event, claim_next_task, complete_task
from app.db import get_engine
from app.models import RunStatus
from app.repositories import AuditRepository, RunRepository
from app.services.agent_loop import AgentRunner
from app.services.audit import AuditService
from app.services.runs import build_provider

logger = logging.getLogger(__name__)
CONTROL_RUN_CAPABILITY = "control.run"


class ControlWorker:
    """Claim and process only durable agent-run continuation tasks.

    This dispatcher is intentionally not a Task 4 remote Worker.  Remote Workers
    remain restricted to the self-check protocol; this process never exposes its
    local session or tool handlers through that protocol.
    """

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        settings: Settings | None = None,
        worker_id: UUID | None = None,
        runner_factory: Callable[[Session], AgentRunner] | None = None,
        poll_seconds: float = 0.25,
    ) -> None:
        self.engine = engine or get_engine()
        self.settings = settings or get_settings()
        self.worker_id = worker_id or uuid4()
        self.runner_factory = runner_factory
        self.poll_seconds = poll_seconds

    def run_once(self) -> int:
        """Claim and execute at most one task using sessions owned by this process."""
        with Session(self.engine) as claim_session:
            task = claim_next_task(
                claim_session,
                worker_id=self.worker_id,
                capabilities={CONTROL_RUN_CAPABILITY},
                now=self._now(),
            )
            claim_session.commit()
            task_id = task.id if task is not None else None
        if task_id is None:
            return 0

        with Session(self.engine) as session:
            task = session.get(ControlTask, task_id)
            if task is None:
                return 0
            if not self._is_agent_run_task(task):
                self._finish_invalid_task(session, task)
                return 1
            task.status = TaskStatus.RUNNING
            session.add(task)
            session.commit()

        self._execute_run_task(task_id)
        return 1

    def run_forever(self) -> None:
        """Run until interrupted; fail fast when provider configuration is invalid."""
        try:
            build_provider(self.settings)
        except RuntimeError as error:
            logger.error("control_worker_configuration_error", exc_info=False)
            raise SystemExit(2) from error
        while True:
            if self.run_once() == 0:
                time.sleep(self.poll_seconds)

    @staticmethod
    def _now() -> datetime:
        from app.models import utc_now

        return utc_now()

    @staticmethod
    def _is_agent_run_task(task: ControlTask) -> bool:
        return (
            task.kind is TaskKind.AGENT_RUN
            and task.capability == CONTROL_RUN_CAPABILITY
            and task.run_id is not None
            and task.payload == {"run_id": str(task.run_id)}
        )

    def _runner(self, session: Session) -> AgentRunner:
        if self.runner_factory is not None:
            return self.runner_factory(session)
        return AgentRunner(
            session,
            provider=build_provider(self.settings),
            provider_name=self.settings.llm_provider,
            model=self.settings.llm_model,
            max_steps=self.settings.max_steps,
            run_timeout_seconds=self.settings.run_timeout_seconds,
        )

    def _execute_run_task(self, task_id: UUID) -> None:
        with Session(self.engine) as session:
            task = session.get(ControlTask, task_id)
            if task is None or task.run_id is None:
                return
            try:
                asyncio.run(self._runner(session).resume_run(task.run_id))
                run = RunRepository(session).get(task.run_id)
                if run is None:
                    self._finish_invalid_task(session, task)
                    return
                outcome = (
                    TaskOutcome.FAILED if run.status is RunStatus.FAILED else TaskOutcome.SUCCEEDED
                )
                result: dict[str, object] = {"run_status": run.status.value}
                completed = complete_task(
                    session,
                    task_id=task.id,
                    worker_id=self.worker_id,
                    outcome=outcome,
                    result=result,
                )
                append_outbox_event(
                    session,
                    event_type="task.updated",
                    resource_type="run",
                    resource_id=run.id,
                    payload={"task_id": str(completed.id), "status": completed.status.value},
                )
                AuditService(AuditRepository(session)).append(
                    run.id,
                    "control.task.completed",
                    f"control-worker:{self.worker_id}",
                    {"task_id": str(completed.id), "status": completed.status.value},
                    commit=False,
                )
                session.commit()
            except ValueError:
                # A lease may have elapsed while a run was in progress.  The queue's
                # existing recovery path will requeue read-only work or require manual
                # review for possible side effects; never execute it a second time here.
                session.rollback()
            except Exception:
                session.rollback()
                logger.exception("control_worker_task_failed")

    def _finish_invalid_task(self, session: Session, task: ControlTask) -> None:
        task.status = TaskStatus.MANUAL_REVIEW
        task.error_class = "invalid_control_task"
        task.result = {"error": "invalid control task payload"}
        task.completed_at = self._now()
        task.lease_owner_id = None
        task.lease_expires_at = None
        session.add(task)
        append_outbox_event(
            session,
            event_type="task.updated",
            resource_type="task",
            resource_id=task.id,
            payload={"status": task.status.value, "error": task.error_class},
        )
        AuditService(AuditRepository(session)).append(
            event_type="control.task.rejected",
            actor=f"control-worker:{self.worker_id}",
            payload={"task_id": str(task.id), "error": task.error_class},
            resource_type="task",
            resource_id=task.id,
            commit=False,
        )
        session.commit()


if __name__ == "__main__":
    ControlWorker().run_forever()
