from fastapi import APIRouter

from app.policy import PolicyEngine
from app.schemas import PolicyView
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=list[PolicyView])
def list_policies() -> list[PolicyView]:
    engine = PolicyEngine()
    policies: list[PolicyView] = []
    for registered in ToolRegistry().registered():
        result = engine.evaluate(registered.spec, {})
        policies.append(
            PolicyView(
                name=registered.spec.name,
                description=registered.spec.description,
                risk_level=registered.spec.risk_level.value,
                read_only=registered.spec.read_only,
                decision=result.decision.value,
                reason=result.reason,
            )
        )
    return policies
