import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditEvent, AuditFilters } from "../types";
import { EmptyState } from "../components/EmptyState";

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const load = () => { setLoading(true); void api.listAudit(filters).then(setEvents).finally(() => setLoading(false)); };
  useEffect(load, []);
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">03 / 核验</span><h1>审计</h1><p>每个提案、决定、执行和结果都会留下只追加的证据。</p></div><a className="button button-secondary" href={api.auditExportUrl(filters)}>导出 JSON ↗</a></div><section className="panel audit-panel"><form className="filter-bar" onSubmit={(event) => { event.preventDefault(); load(); }}><label>运行 ID<input value={filters.run_id ?? ""} onChange={(event) => setFilters({ ...filters, run_id: event.target.value })} placeholder="可选 UUID" /></label><label>执行者<input value={filters.actor ?? ""} onChange={(event) => setFilters({ ...filters, actor: event.target.value })} placeholder="用户 / Agent / 策略" /></label><label>事件类型<input value={filters.event_type ?? ""} onChange={(event) => setFilters({ ...filters, event_type: event.target.value })} placeholder="run.completed" /></label><button className="button button-primary" type="submit">应用筛选</button></form>{loading ? <div className="loading-row">正在加载审计时间线…</div> : events.length === 0 ? <EmptyState title="没有匹配的事件" description="尝试清除筛选，或运行一个确定性的演示。" /> : <div className="audit-list">{events.map((event) => <details className="audit-event" key={event.id}><summary><span className="audit-type">{event.event_type}</span><span className="audit-actor">{event.actor}</span><time>{new Date(event.created_at).toLocaleString()}</time></summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details>)}</div>}</section></div>;
}
