import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PolicyView } from "../types";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { modeLabel, reasonLabel, toolDescription, toolLabel } from "../i18n/zh-CN";

export function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyView[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { void api.listPolicies().then(setPolicies).finally(() => setLoading(false)); }, []);
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">02 / 治理</span><h1>策略</h1><p>只读策略契约定义 Agent 可以自动执行的范围。</p></div><div className="heading-stat"><strong>04</strong><span>已注册工具</span></div></div><section className="panel policy-panel"><div className="section-heading"><div><span className="eyebrow">执行矩阵</span><h2>工具风险边界</h2></div><span className="mono-note">代码注册 / 只读</span></div>{loading ? <div className="loading-row" aria-live="polite">正在加载策略注册表…</div> : policies.length === 0 ? <EmptyState title="策略注册表为空" description="后端没有返回已注册的工具契约。" /> : <div className="table-wrap"><table><thead><tr><th>工具</th><th>风险</th><th>模式</th><th>决定</th><th>理由</th></tr></thead><tbody>{policies.map((policy) => <tr key={policy.name}><td><strong className="tool-display"><span>{toolLabel(policy.name)}</span> <code translate="no">{policy.name}</code></strong><span className="table-subtext">{toolDescription(policy.name, policy.description)}</span></td><td><StatusBadge value={policy.risk_level} /></td><td>{modeLabel(policy.read_only)}</td><td><StatusBadge value={policy.decision} /></td><td className="reason-cell">{reasonLabel(policy.reason)}</td></tr>)}</tbody></table></div>}</section></div>;
}
