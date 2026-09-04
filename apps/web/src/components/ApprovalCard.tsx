import { useState } from "react";
import { ApiError } from "../api/client";
import type { ToolAction } from "../types";
import { reasonLabel, riskLabel, toolLabel } from "../i18n/zh-CN";
import { StatusBadge } from "./StatusBadge";

const secretKeys = new Set([
  "api_key", "apikey", "authorization", "access_token", "refresh_token",
  "client_secret", "private_key", "token", "secret", "password",
]);

function normalizedKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function safeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        secretKeys.has(normalizedKey(key)) ? "***REDACTED***" : safeValue(item),
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
        ? "该操作已经处理过"
        : "无法保存审批决定";
      setError(message);
      if (reason instanceof ApiError && reason.status === 409) onRefresh?.();
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="approval-card" aria-labelledby={`approval-${action.id}`} data-testid="approval-card">
      <div className={`decision-rail rail-${action.risk_level}`} aria-hidden="true">
        <span>审批</span>
        <strong>{riskLabel(action.risk_level)}</strong>
      </div>
      <div className="approval-content">
        <div className="approval-heading">
          <div>
            <span className="eyebrow">需要人工审批</span>
            <h2 id={`approval-${action.id}`}><span>{toolLabel(action.tool_name)}</span> <code translate="no">{action.tool_name}</code></h2>
          </div>
          <StatusBadge value={action.risk_level} />
        </div>
        <p className="approval-reason">{reasonLabel(action.reason)}</p>
        <div className="approval-impact">
          <span>影响目标</span>
          <strong translate="no">{String(action.arguments.service ?? "本地服务")}</strong>
        </div>
        <details className="arguments-panel" open>
          <summary>参数</summary>
          <pre>{formattedArguments(action.arguments)}</pre>
        </details>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="approval-actions">
          <button
            className="button button-primary"
            type="button"
            aria-label="批准"
            data-testid="approval-approve"
            onClick={() => void decide("approve")}
            disabled={pending !== null}
          >
            {pending === "approve" ? "正在批准…" : "批准"}
          </button>
          <button
            className="button button-secondary"
            type="button"
            aria-label="拒绝"
            data-testid="approval-deny"
            onClick={() => void decide("deny")}
            disabled={pending !== null}
          >
            {pending === "deny" ? "正在拒绝…" : "拒绝"}
          </button>
        </div>
      </div>
    </section>
  );
}
