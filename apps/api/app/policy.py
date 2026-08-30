from app.models import PolicyDecision, RiskLevel
from app.tools.base import PolicyResult, ToolSpec


class PolicyEngine:
    def evaluate(self, tool: ToolSpec, arguments: dict[str, object]) -> PolicyResult:
        del arguments
        if tool.risk_level is RiskLevel.HIGH:
            return PolicyResult(
                PolicyDecision.DENY,
                tool.risk_level,
                "High-risk actions are denied by the local demo policy.",
            )
        if tool.risk_level is RiskLevel.MEDIUM:
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                tool.risk_level,
                "Medium-risk actions require explicit human approval.",
            )
        if tool.read_only:
            return PolicyResult(
                PolicyDecision.AUTO_APPROVE,
                tool.risk_level,
                "Low-risk read-only actions are automatically approved.",
            )
        return PolicyResult(
            PolicyDecision.DENY,
            tool.risk_level,
            "Low-risk write actions are denied because only read-only automation is allowed.",
        )
