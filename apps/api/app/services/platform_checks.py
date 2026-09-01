"""Bounded, secret-free checks used by the operator-facing platform endpoints."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlmodel import Session

from app.config import Settings
from app.control.enums import TaskStatus, WorkerStatus
from app.control.models import ControlTask, OutboxEvent, WorkerRegistration
from app.db import database_schema_is_ready
from app.models import utc_now

MAX_DETAILS = 10


def _observed_at() -> str:
    return utc_now().isoformat()


def check(
    *, status: str, code: str, message_zh: str, details: dict[str, Any] | None = None
) -> dict[str, object]:
    bounded = dict(list((details or {}).items())[:MAX_DETAILS])
    return {
        "status": status,
        "code": code,
        "message_zh": message_zh,
        "observed_at": _observed_at(),
        "details": bounded,
    }


def platform_health(session: Session) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {
        "api": check(status="ok", code="api_healthy", message_zh="API 正常")
    }
    try:
        ready = database_schema_is_ready(cast(Any, session.get_bind()))
        checks["database"] = check(
            status="ok" if ready else "error",
            code="database_ready" if ready else "database_schema_not_ready",
            message_zh="数据库迁移已就绪" if ready else "数据库迁移未就绪",
        )
        session.exec(cast(Any, select(func.count()).select_from(ControlTask))).one()
        checks["queue"] = check(status="ok", code="queue_ready", message_zh="持久化队列可读")
        session.exec(cast(Any, select(func.count()).select_from(OutboxEvent))).one()
        checks["outbox"] = check(status="ok", code="outbox_ready", message_zh="Outbox 可读")
    except Exception:
        checks["database"] = check(
            status="error", code="database_unavailable", message_zh="数据库不可用"
        )
        checks["queue"] = check(
            status="error", code="queue_unavailable", message_zh="持久化队列不可用"
        )
        checks["outbox"] = check(
            status="error", code="outbox_unavailable", message_zh="Outbox 不可用"
        )

    worker = session.exec(
        cast(
            Any,
            select(cast(Any, WorkerRegistration.last_heartbeat_at))
            .where(cast(Any, WorkerRegistration.status) == WorkerStatus.ACTIVE)
            .order_by(cast(Any, WorkerRegistration.last_heartbeat_at).desc().nullslast()),
        )
    ).scalar()
    heartbeat_age = _heartbeat_age_seconds(worker)
    checks["worker"] = check(
        status="ok" if heartbeat_age is not None and heartbeat_age <= 90 else "degraded",
        code=(
            "worker_heartbeat_recent"
            if heartbeat_age is not None and heartbeat_age <= 90
            else "worker_heartbeat_missing_or_stale"
        ),
        message_zh=(
            "Worker 心跳正常"
            if heartbeat_age is not None and heartbeat_age <= 90
            else "Worker 心跳缺失或过期"
        ),
        details={"age_seconds": heartbeat_age} if heartbeat_age is not None else {},
    )
    return checks


def _heartbeat_age_seconds(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0.0, (utc_now() - value).total_seconds())


def platform_self_check(session: Session, settings: Settings) -> dict[str, object]:
    migration_head: str | None = None
    code_migration_head: str | None = None
    applied_migration_revision: str | None = None
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        code_migration_head = ScriptDirectory.from_config(config).get_current_head()
        with cast(Any, session.get_bind()).connect() as connection:
            applied_migration_revision = MigrationContext.configure(
                connection
            ).get_current_revision()
        migration_head = applied_migration_revision
    except Exception:
        pass

    if code_migration_head is None:
        migration_check = check(
            status="error",
            code="database_migration_head_unavailable",
            message_zh="无法读取代码迁移头",
        )
    elif applied_migration_revision is None:
        migration_check = check(
            status="error",
            code="database_migration_missing",
            message_zh="数据库没有已应用的迁移",
            details={"code_head": code_migration_head},
        )
    elif applied_migration_revision != code_migration_head:
        migration_check = check(
            status="error",
            code="database_migration_mismatch",
            message_zh="数据库迁移版本与代码不一致",
            details={
                "applied_revision": applied_migration_revision,
                "code_head": code_migration_head,
            },
        )
    else:
        migration_check = check(
            status="ok",
            code="database_migration_current",
            message_zh="数据库迁移版本正确",
            details={"applied_revision": applied_migration_revision},
        )

    queued_available_at = session.exec(
        cast(
            Any,
            select(cast(Any, ControlTask.available_at))
            .where(cast(Any, ControlTask.status) == TaskStatus.QUEUED)
            .order_by(cast(Any, ControlTask.available_at)),
        )
    ).scalar()
    queue_latency_ms = None
    if queued_available_at is not None:
        available_at = (
            queued_available_at.replace(tzinfo=UTC)
            if queued_available_at.tzinfo is None
            else queued_available_at
        )
        queue_latency_ms = max(0, int((utc_now() - available_at).total_seconds() * 1000))
    worker = session.exec(
        cast(
            Any,
            select(cast(Any, WorkerRegistration.last_heartbeat_at))
            .where(cast(Any, WorkerRegistration.status) == WorkerStatus.ACTIVE)
            .order_by(cast(Any, WorkerRegistration.last_heartbeat_at).desc().nullslast()),
        )
    ).scalar()
    stale_leases = session.exec(
        cast(
            Any,
            select(ControlTask).where(
                cast(Any, ControlTask.status).in_([TaskStatus.LEASED, TaskStatus.RUNNING]),
                cast(Any, ControlTask.lease_expires_at) < utc_now(),
            ),
        )
    ).all()
    return {
        "migration_head": migration_head,
        "migration_check": migration_check,
        "queue_latency_ms": queue_latency_ms,
        "stale_lease_count": len(stale_leases),
        "worker_heartbeat_age_seconds": _heartbeat_age_seconds(worker),
        "provider": {
            "name": settings.llm_provider,
            "model": settings.llm_model,
            "configured": True,
        },
    }
