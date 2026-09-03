import type { ActionStatus, RiskLevel, RunStatus } from "../types";
import { decisionLabel, riskLabel, statusLabel } from "../i18n/zh-CN";

type BadgeValue = RunStatus | ActionStatus | RiskLevel | string;

export function StatusBadge({ value }: { value: BadgeValue }) {
  const label = ["low", "medium", "high", "critical"].includes(value)
    ? riskLabel(value)
    : ["auto_approve", "require_approval", "deny"].includes(value)
      ? decisionLabel(value)
      : statusLabel(value);
  return (
    <span className={`status-badge status-${value.replaceAll("_", "-")}`}>
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
