import type { ActionStatus, RiskLevel, RunStatus } from "../types";

type BadgeValue = RunStatus | ActionStatus | RiskLevel | string;

const labels: Record<string, string> = {
  auto_approve: "Auto approve",
  auto_approved: "Auto approved",
  require_approval: "Requires approval",
  waiting_approval: "Waiting approval",
  pending_approval: "Pending approval",
  succeeded: "Succeeded",
  failed: "Failed",
  denied: "Denied",
  running: "Running",
  queued: "Queued",
  completed: "Completed",
  cancelled: "Cancelled",
  proposed: "Proposed",
  approved: "Approved",
  expired: "Expired",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export function StatusBadge({ value }: { value: BadgeValue }) {
  return (
    <span className={`status-badge status-${value.replaceAll("_", "-")}`}>
      <span className="status-dot" aria-hidden="true" />
      {labels[value] ?? value}
    </span>
  );
}
