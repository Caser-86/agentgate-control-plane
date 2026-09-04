import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditEvent, AuditFilters } from "../types";
import { EmptyState } from "../components/EmptyState";
import { actorLabel, eventLabel, formatDateTime } from "../i18n/zh-CN";

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setLoading(true);
    setError(null);
    void api.listAudit(filters)
      .then(setEvents)
      .catch(() => setError("无法加载审计记录，请稍后重试。"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">证据 / 追加式记录</span><h1>审计</h1><p>为每次提议、决定、执行和结果记录追加式证据；敏感字段由服务端脱敏后才会到达页面。</p></div><a className="button button-secondary" href={api.auditExportUrl(filters)}>导出 JSON ↗</a></div><section className="panel audit-panel"><form className="filter-bar" onSubmit={(event) => { event.preventDefault(); load(); }}><label htmlFor="audit-run-id">运行 ID<input id="audit-run-id" name="run-id" autoComplete="off" value={filters.run_id ?? ""} onChange={(event) => setFilters({ ...filters, run_id: event.target.value })} placeholder="可选 UUID…" /></label><label htmlFor="audit-actor">执行者<input id="audit-actor" name="actor" autoComplete="off" value={filters.actor ?? ""} onChange={(event) => setFilters({ ...filters, actor: event.target.value })} placeholder="例如：用户、Agent、策略" /></label><label htmlFor="audit-event-type">事件类型<input id="audit-event-type" name="event-type" autoComplete="off" value={filters.event_type ?? ""} onChange={(event) => setFilters({ ...filters, event_type: event.target.value })} placeholder="例如：审批已通过" /></label><button className="button button-primary" type="submit">应用筛选</button></form>{error && <p className="inline-error" role="alert">{error}</p>}{loading ? <div className="loading-row" aria-live="polite">正在加载审计时间线…</div> : events.length === 0 ? <EmptyState title="没有符合条件的事件" description="尝试清除筛选条件，或先运行安全演示生成审计证据。" /> : <div className="audit-list">{events.map((event) => <details className="audit-event" key={event.id}><summary><span className="audit-type"><span>{eventLabel(event.event_type)}</span> <code translate="no">{event.event_type}</code></span><span className="audit-actor"><span>{actorLabel(event.actor)}</span> <code translate="no">{event.actor}</code></span><time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time></summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details>)}</div>}</section></div>;
}
