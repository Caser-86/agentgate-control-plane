import pytest

from app.models import PolicyDecision, RiskLevel
from app.policy import PolicyEngine
from app.tools.base import ToolSpec


def make_spec(risk: RiskLevel, read_only: bool) -> ToolSpec:
    return ToolSpec(
        name="demo_tool",
        description="A demo tool",
        parameters_schema={"type": "object"},
        risk_level=risk,
        read_only=read_only,
    )


@pytest.mark.parametrize(
    ("risk", "read_only", "expected"),
    [
        (RiskLevel.LOW, True, PolicyDecision.AUTO_APPROVE),
        (RiskLevel.LOW, False, PolicyDecision.DENY),
        (RiskLevel.MEDIUM, False, PolicyDecision.REQUIRE_APPROVAL),
        (RiskLevel.HIGH, False, PolicyDecision.DENY),
    ],
)
def test_policy_matrix(
    risk: RiskLevel, read_only: bool, expected: PolicyDecision
) -> None:
    result = PolicyEngine().evaluate(make_spec(risk, read_only), {})

    assert result.decision == expected
    assert result.risk_level == risk
    assert result.reason


def test_invalid_tool_metadata_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        ToolSpec(
            name="",
            description="demo",
            parameters_schema={},
            risk_level=RiskLevel.LOW,
            read_only=True,
        )

    with pytest.raises(TypeError):
        ToolSpec(
            name="demo",
            description="demo",
            parameters_schema={},
            risk_level="low",  # type: ignore[arg-type]
            read_only=True,
        )
