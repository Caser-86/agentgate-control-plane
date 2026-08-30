import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PolicyView } from "../types";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";

export function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyView[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { void api.listPolicies().then(setPolicies).finally(() => setLoading(false)); }, []);
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">02 / Govern</span><h1>Policies</h1><p>Read-only policy contracts define what the agent can do automatically.</p></div><div className="heading-stat"><strong>04</strong><span>registered tools</span></div></div><section className="panel policy-panel"><div className="section-heading"><div><span className="eyebrow">Enforcement matrix</span><h2>Tool risk boundaries</h2></div><span className="mono-note">code-registered / read only</span></div>{loading ? <div className="loading-row">Loading policy registry…</div> : policies.length === 0 ? <EmptyState title="Policy registry is empty" description="The backend did not return a registered tool contract." /> : <div className="table-wrap"><table><thead><tr><th>Tool</th><th>Risk</th><th>Mode</th><th>Decision</th><th>Rationale</th></tr></thead><tbody>{policies.map((policy) => <tr key={policy.name}><td><strong>{policy.name}</strong><span className="table-subtext">{policy.description}</span></td><td><StatusBadge value={policy.risk_level} /></td><td>{policy.read_only ? "Read only" : "State changing"}</td><td><StatusBadge value={policy.decision} /></td><td className="reason-cell">{policy.reason}</td></tr>)}</tbody></table></div>}</section></div>;
}
