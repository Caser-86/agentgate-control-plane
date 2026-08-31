from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import require_operator
from app.auth.models import Operator
from app.config import get_settings
from app.db import get_session
from app.services.platform_checks import platform_health, platform_self_check

router = APIRouter(prefix="/api/platform", tags=["platform"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]


@router.get("/health")
def health(session: SessionDep, _: OperatorDep) -> dict[str, object]:
    checks = platform_health(session)
    status = "ok" if all(item["status"] == "ok" for item in checks.values()) else "degraded"
    return {"status": status, "checks": checks}


@router.get("/self-check")
def self_check(session: SessionDep, _: OperatorDep) -> dict[str, object]:
    return platform_self_check(session, get_settings())
