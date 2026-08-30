import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { RunDetail } from "../types";
import { ApprovalCard } from "../components/ApprovalCard";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import { useRunEvents } from "../hooks/useRunEvents";

function formatArguments(value: unknown): string {
  const secretKeys = new Set(["api_key", "authorization", "token", "secret", "password"]);
  const safe = (item: unknown): unknown => Array.isArray(item) ? item.map(safe) : item && typeof item === "object" ? Object.fromEntries(Object.entries(item).map(([key, child]) => [key, secretKeys.has(key.toLowerCase()) ? "***REDACTED***" : safe(child)])) : item;
  return JSON.stringify(safe(value), null, 2);
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!runId) return Promise.resolve();
    return api.getRun(runId).then(setDetail).catch(() => setError("This run could not be loaded."));
  }, [runId]);
  useEffect(() => { void load(); }, [load]);
  const connection = useRunEvents(runId, useCallback(() => { void load(); }, [load]));

  if (error) return <div className="page-shell"><Link className="back-link" to="/">← Back to runs</Link><div className="error-panel"><span className="eyebrow">Safe error</span><h1>Run unavailable</h1><p>{error}</p></div></div>;
  if (!detail) return <div className="page-shell"><div className="loading-row">Loading run detail…</div></div>;
  const pending = detail.actions.find((action) => action.status === "pending_approval");

  return (
    <div className="page-shell detail-page">
      <Link className="back-link" to="/">← Back to runs</Link>
      <div className="page-heading detail-heading"><div><span className="eyebrow">Run detail / {detail.id.slice(0, 8)}</span><h1>Operational trace</h1><p>{detail.user_request}</p></div><div className="detail-status"><StatusBadge value={detail.status} /><span className={connection === "reconnecting" ? "reconnecting" : "live-status"}>{connection === "reconnecting" ? "Reconnecting to events" : "Live event stream"}</span></div></div>
      {pending && <ApprovalCard action={pending} onApprove={async () => { await api.approveAction(pending.id, { actor: "local-user" }); await load(); }} onDeny={async () => { await api.denyAction(pending.id, { actor: "local-user" }); await load(); }} onRefresh={() => void load()} />}
      <div className="detail-grid">
        <section className="panel timeline-panel"><div className="section-heading"><div><span className="eyebrow">Trace / chronological</span><h2>Decision timeline</h2></div><span className="mono-note">{detail.audit_events.length.toString().padStart(2, "0")} events</span></div><RunTimeline events={detail.audit_events} /></section>
        <aside className="panel side-panel"><div className="section-heading"><div><span className="eyebrow">Run metadata</span><h2>Control facts</h2></div></div><dl className="facts-list"><div><dt>Status</dt><dd><StatusBadge value={detail.status} /></dd></div><div><dt>Provider</dt><dd><code>{detail.provider}</code></dd></div><div><dt>Model</dt><dd><code>{detail.model}</code></dd></div><div><dt>Steps</dt><dd>{detail.step_count.toString().padStart(2, "0")}</dd></div></dl></aside>
      </div>
      {detail.final_text && <section className="panel final-panel"><span className="eyebrow">Agent conclusion</span><h2>Safe outcome</h2><p>{detail.final_text}</p></section>}
      {detail.status === "failed" && <section className="error-panel"><span className="eyebrow">Safe error</span><h2>Run stopped before completion</h2><p>{detail.error_message ?? "The run reached a protected failure boundary."}</p></section>}
      <section className="panel actions-panel"><div className="section-heading"><div><span className="eyebrow">Tool actions</span><h2>Action ledger</h2></div></div><div className="action-list">{detail.actions.map((action) => <div className="action-row" key={action.id}><div><strong>{action.tool_name}</strong><span>{action.reason}</span></div><div className="action-meta"><StatusBadge value={action.risk_level} /><StatusBadge value={action.status} /></div><details><summary>Args</summary><pre>{formatArguments(action.arguments)}</pre></details></div>)}</div></section>
    </div>
  );
}
