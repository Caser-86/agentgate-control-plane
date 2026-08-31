from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_operator
from app.auth.models import Operator
from app.config import get_settings

router = APIRouter()
OperatorDep = Annotated[Operator, Depends(require_operator)]


@router.get("/health")
def health() -> dict[str, str]:
    """Anonymous infrastructure liveness probe, outside browser and adapter APIs."""
    return {"status": "ok", "service": "agentgate-api"}


@router.get("/api/meta")
def meta(_: OperatorDep) -> dict[str, str]:
    settings = get_settings()
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "status": "ok",
    }
