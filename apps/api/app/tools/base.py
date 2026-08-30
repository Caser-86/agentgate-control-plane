from dataclasses import dataclass

from app.models import PolicyDecision, RiskLevel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, object]
    risk_level: RiskLevel
    read_only: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        if not isinstance(self.parameters_schema, dict):
            raise TypeError("tool parameters_schema must be a dictionary")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("tool risk_level must be a RiskLevel")
        if not isinstance(self.read_only, bool):
            raise TypeError("tool read_only must be a bool")


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    risk_level: RiskLevel
    reason: str
