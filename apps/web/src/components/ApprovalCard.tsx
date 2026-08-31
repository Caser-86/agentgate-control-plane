import { useState } from "react";
import { ApiError } from "../api/client";
import type { ToolAction } from "../types";
import { StatusBadge } from "./StatusBadge";

const secretKeys = new Set([
  "api_key", "apikey", "authorization", "access_token", "refresh_token",
  "client_secret", "private_key", "token", "secret", "password",
]);

function safeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        secretKeys.has(key.toLowerCase()) ? "***REDACTED***" : safeValue(item),
      ]),
    );
  }
  return value;
}

function formattedArguments(argumentsValue: Record<string, unknown>): string {
  return JSON.stringify(safeValue(argumentsValue), null, 2);
}

interface ApprovalCardProps {
  action: ToolAction;
  onApprove: () => Promise<void>;
  onDeny: () => Promise<void>;
  onRefresh?: () => void;
}

export function ApprovalCard({ action, onApprove, onDeny, onRefresh }: ApprovalCardProps) {
  const [pending, setPending] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "deny") {
    setPending(decision);
    setError(null);
    try {
      if (decision === "approve") await onApprove();
      else await onDeny();
    } catch (reason) {
      const message = reason instanceof ApiError && reason.status === 409
        ? "This action was already decided"
        : reason instanceof Error
          ? reason.message
          : "The decision could not be saved";
      setError(message);
      if (reason instanceof ApiError && reason.status === 409) onRefresh?.();
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="approval-card" aria-labelledby={`approval-${action.id}`}>
      <div className={`decision-rail rail-${action.risk_level}`} aria-hidden="true">
        <span>DECISION</span>
        <strong>{action.risk_level.toUpperCase()}</strong>
      </div>
      <div className="approval-content">
        <div className="approval-heading">
          <div>
            <span className="eyebrow">Human approval required</span>
            <h2 id={`approval-${action.id}`}>{action.tool_name}</h2>
          </div>
          <StatusBadge value={action.risk_level} />
        </div>
        <p className="approval-reason">{action.reason}</p>
        <div className="approval-impact">
          <span>Impact target</span>
          <strong>{String(action.arguments.service ?? "Local demo service")}</strong>
        </div>
        <details className="arguments-panel" open>
          <summary>Arguments</summary>
          <pre>{formattedArguments(action.arguments)}</pre>
        </details>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="approval-actions">
          <button
            className="button button-primary"
            type="button"
            aria-label="Approve"
            onClick={() => void decide("approve")}
            disabled={pending !== null}
          >
            {pending === "approve" ? "Approving…" : "Approve"}
          </button>
          <button
            className="button button-secondary"
            type="button"
            aria-label="Deny"
            onClick={() => void decide("deny")}
            disabled={pending !== null}
          >
            {pending === "deny" ? "Denying…" : "Deny"}
          </button>
        </div>
      </div>
    </section>
  );
}
