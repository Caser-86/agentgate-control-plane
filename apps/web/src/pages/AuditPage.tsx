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
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">03 / Verify</span><h1>Audit</h1><p>Append-only evidence for every proposal, decision, execution and outcome.</p></div><a className="button button-secondary" href={api.auditExportUrl(filters)}>Export JSON ↗</a></div><section className="panel audit-panel"><form className="filter-bar" onSubmit={(event) => { event.preventDefault(); load(); }}><label>Run ID<input value={filters.run_id ?? ""} onChange={(event) => setFilters({ ...filters, run_id: event.target.value })} placeholder="optional UUID" /></label><label>Actor<input value={filters.actor ?? ""} onChange={(event) => setFilters({ ...filters, actor: event.target.value })} placeholder="user / agent / policy" /></label><label>Event type<input value={filters.event_type ?? ""} onChange={(event) => setFilters({ ...filters, event_type: event.target.value })} placeholder="run.completed" /></label><button className="button button-primary" type="submit">Apply filters</button></form>{loading ? <div className="loading-row">Loading audit timeline…</div> : events.length === 0 ? <EmptyState title="No events match these filters" description="Try clearing a filter or run one of the deterministic demos." /> : <div className="audit-list">{events.map((event) => <details className="audit-event" key={event.id}><summary><span className="audit-type">{event.event_type}</span><span className="audit-actor">{event.actor}</span><time>{new Date(event.created_at).toLocaleString()}</time></summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details>)}</div>}</section></div>;
}
