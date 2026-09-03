import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { RunDetail } from "../types";
import { ApprovalCard } from "../components/ApprovalCard";
import { RunTimeline } from "../components/RunTimeline";
import { StatusBadge } from "../components/StatusBadge";
import { useRunEvents } from "../hooks/useRunEvents";
import { reasonLabel, toolLabel } from "../i18n/zh-CN";

function formatArguments(value: unknown): string {
  const secretKeys = new Set(["apikey", "authorization", "accesstoken", "refreshtoken", "clientsecret", "privatekey", "token", "secret", "password", "passwordhash"]);
  const normalize = (key: string): string => key.toLowerCase().replace(/[^a-z0-9]/g, "");
  const safe = (item: unknown): unknown => Array.isArray(item) ? item.map(safe) : item && typeof item === "object" ? Object.fromEntries(Object.entries(item).map(([key, child]) => [key, secretKeys.has(normalize(key)) ? "***REDACTED***" : safe(child)])) : item;
  return JSON.stringify(safe(value), null, 2);
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!runId) return Promise.resolve();
    return api.getRun(runId).then(setDetail).catch(() => setError("运行详情无法加载。"));
  }, [runId]);
  useEffect(() => { void load(); }, [load]);
  const reload = useCallback(() => { void load(); }, [load]);
  const connection = useRunEvents(runId, reload, reload);

  if (error) return <div className="page-shell"><Link className="back-link" to="/">← 返回运行列表</Link><div className="error-panel"><span className="eyebrow">安全错误</span><h1>运行暂时不可用</h1><p>无法加载该运行详情，请稍后重试。</p></div></div>;
  if (!detail) return <div className="page-shell"><div className="loading-row" aria-live="polite">正在加载运行详情…</div></div>;
  const pending = detail.actions.find((action) => action.status === "pending_approval");

  return (
    <div className="page-shell detail-page">
      <Link className="back-link" to="/">← 返回运行列表</Link>
      <div className="page-heading detail-heading"><div><span className="eyebrow">运行详情 / <span translate="no">{detail.id.slice(0, 8)}</span></span><h1>操作轨迹</h1><p>{detail.user_request}</p></div><div className="detail-status" data-testid="run-status"><StatusBadge value={detail.status} /><span className={connection === "reconnecting" ? "reconnecting" : "live-status"} aria-live="polite">{connection === "reconnecting" ? "正在重连事件流" : "事件流已连接"}</span></div></div>
      {pending && <ApprovalCard action={pending} onApprove={async () => { const updated = await api.approveAction(pending.id, {}); setDetail((current) => current ? { ...current, actions: current.actions.map((item) => item.id === updated.id ? updated : item) } : current); await load(); }} onDeny={async () => { const updated = await api.denyAction(pending.id, {}); setDetail((current) => current ? { ...current, actions: current.actions.map((item) => item.id === updated.id ? updated : item) } : current); await load(); }} onRefresh={() => void load()} />}
      <div className="detail-grid">
        <section className="panel timeline-panel"><div className="section-heading"><div><span className="eyebrow">时间线 / 按时间排序</span><h2>决策时间线</h2></div><span className="mono-note">{detail.audit_events.length.toString().padStart(2, "0")} 个事件</span></div><RunTimeline events={detail.audit_events} /></section>
        <aside className="panel side-panel"><div className="section-heading"><div><span className="eyebrow">运行元数据</span><h2>控制信息</h2></div></div><dl className="facts-list"><div><dt>状态</dt><dd><StatusBadge value={detail.status} /></dd></div><div><dt>模型提供方</dt><dd><code translate="no">{detail.provider}</code></dd></div><div><dt>模型</dt><dd><code translate="no">{detail.model}</code></dd></div><div><dt>步骤</dt><dd>{detail.step_count.toString().padStart(2, "0")}</dd></div></dl></aside>
      </div>
      {detail.final_text && <section className="panel final-panel"><span className="eyebrow">Agent 结论</span><h2>安全结果</h2><p>{detail.final_text}</p></section>}
      {detail.status === "failed" && <section className="error-panel"><span className="eyebrow">安全错误</span><h2>运行在完成前停止</h2><p>运行触及受保护的失败边界。</p></section>}
      <section className="panel actions-panel"><div className="section-heading"><div><span className="eyebrow">工具动作</span><h2>动作记录</h2></div></div><div className="action-list">{detail.actions.map((action) => <div className="action-row" key={action.id}><div><strong><span>{toolLabel(action.tool_name)}</span> <code translate="no">{action.tool_name}</code></strong><span>{reasonLabel(action.reason)}</span></div><div className="action-meta"><StatusBadge value={action.risk_level} /><span data-testid="action-status"><StatusBadge value={action.status} /></span></div><details><summary>参数</summary><pre>{formatArguments(action.arguments)}</pre></details>{action.result !== null && <details><summary>结果</summary><pre>{formatArguments(action.result)}</pre></details>}</div>)}</div></section>
    </div>
  );
}
