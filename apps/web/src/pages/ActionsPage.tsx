import { useEffect, useMemo, useState } from "react";
import { listActions } from "../api/actions";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { actionLabel, formatDateTime, reasonLabel, statusLabel } from "../i18n/zh-CN";
import type { ActionListFilters, ToolAction } from "../types";

function relativePath(action: ToolAction): string {
  const value = action.arguments.relative_path;
  return typeof value === "string" ? value : "恢复动作（见隔离记录）";
}

export function ActionsPage() {
  const [actions, setActions] = useState<ToolAction[]>([]);
  const [filters, setFilters] = useState<ActionListFilters>({});
  const [source, setSource] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load(next = filters) {
    setLoading(true);
    setError(null);
    void listActions(next).then(setActions).catch(() => setError("无法加载动作记录，请稍后重试。")).finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const visibleActions = useMemo(() => actions.filter((action) => source === "all" || (source === "external" ? action.run_id === null : action.run_id !== null)), [actions, source]);

  return <div className="page-shell">
    <div className="page-heading"><div><span className="eyebrow">治理 / 动作记录</span><h1>动作</h1><p>所有动作先经过策略判断；这里只显示可审查的参数摘要，不显示文件内容、根路径或凭据。</p></div><div className="heading-stat"><strong>{visibleActions.length.toString().padStart(2, "0")}</strong><span>条可审查动作</span></div></div>
    <section className="panel filter-panel"><form className="action-filter-bar" onSubmit={(event) => { event.preventDefault(); load(filters); }}>
      <label htmlFor="action-source">来源<select id="action-source" value={source} onChange={(event) => setSource(event.target.value)}><option value="all">全部来源</option><option value="external">外部 Agent</option><option value="runner">内置 Agent</option></select></label>
      <label htmlFor="action-status">状态<select id="action-status" value={filters.status ?? ""} onChange={(event) => setFilters({ ...filters, status: event.target.value || undefined })}><option value="">全部状态</option><option value="pending_approval">待审批</option><option value="succeeded">执行成功</option><option value="denied">已拒绝</option><option value="failed">执行失败</option></select></label>
      <label htmlFor="action-risk">风险<select id="action-risk" value={filters.risk_level ?? ""} onChange={(event) => setFilters({ ...filters, risk_level: event.target.value || undefined })}><option value="">全部风险</option><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option></select></label>
      <button className="button button-primary" type="submit">应用筛选</button>
    </form>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {loading ? <div className="loading-row" role="status">正在加载动作记录…</div> : visibleActions.length === 0 ? <EmptyState title="还没有动作记录" description="从内置 Agent 或外部 Agent 提交一个动作后，这里会出现完整的策略和执行状态。" /> : <div className="action-board">{visibleActions.map((action) => <article className="action-card" key={action.id}><div className="action-card-main"><div><span className="eyebrow">{action.run_id ? "内置 Agent" : "外部 Agent"}</span><h2>{actionLabel(action.tool_name)} <code translate="no">{action.tool_name}</code></h2><p>{reasonLabel(action.reason)}</p></div><div className="action-card-badges"><StatusBadge value={action.risk_level} /><StatusBadge value={action.status} /></div></div><div className="action-card-facts"><span>目标相对路径<strong translate="no">{relativePath(action)}</strong></span><span>创建时间<strong>{formatDateTime(action.created_at)}</strong></span><span>策略决定<strong>{statusLabel(action.policy_decision)}</strong></span></div><details><summary>查看安全参数摘要</summary><pre>{JSON.stringify(action.arguments, null, 2)}</pre></details></article>)}</div>}
    </section>
  </div>;
}
