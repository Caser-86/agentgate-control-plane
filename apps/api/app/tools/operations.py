from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.models import ServiceState


class ServiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["payments-api", "orders-api"]


class SearchLogsArgs(ServiceArgs):
    severity: Literal["info", "warning", "error"] = "error"
    limit: int = Field(default=20, ge=1, le=100)


class RestartServiceArgs(ServiceArgs):
    reason: str = Field(min_length=5, max_length=240)


def _service_or_raise(session: Session, service: str) -> ServiceState:
    state = session.get(ServiceState, service)
    if state is None:
        raise ValueError("service state is unavailable")
    return state


async def get_service_health(args: ServiceArgs, session: Session) -> dict[str, object]:
    state = _service_or_raise(session, args.service)
    return {
        "service": state.service,
        "health": state.health,
        "restart_count": state.restart_count,
    }


async def search_logs(args: SearchLogsArgs, session: Session) -> dict[str, object]:
    state = _service_or_raise(session, args.service)
    if state.health == "degraded":
        records: list[dict[str, object]] = [
            {
                "timestamp": "2026-08-31T00:00:00Z",
                "severity": "error",
                "message": "upstream dependency connection pool is exhausted",
            },
            {
                "timestamp": "2026-08-31T00:01:00Z",
                "severity": "warning",
                "message": "health check latency exceeded the local threshold",
            },
        ]
    else:
        records = [
            {
                "timestamp": "2026-08-31T00:00:00Z",
                "severity": "info",
                "message": "service health checks are nominal",
            }
        ]
    filtered = [record for record in records if record["severity"] == args.severity]
    return {"service": state.service, "records": filtered[: args.limit]}


async def restart_service(args: RestartServiceArgs, session: Session) -> dict[str, object]:
    state = _service_or_raise(session, args.service)
    state.health = "healthy"
    state.restart_count += 1
    state.last_restart_at = datetime.now(UTC)
    session.add(state)
    session.commit()
    session.refresh(state)
    return {
        "service": state.service,
        "health": state.health,
        "restart_count": state.restart_count,
        "reason": args.reason,
    }
