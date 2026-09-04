import { useEffect, useState } from "react";
import { approveAction, denyAction, listApprovals } from "../api/actions";
import { useRuntime } from "../components/AppShell";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { actionLabel, formatDateTime, reasonLabel } from "../i18n/zh-CN";
import type { ToolAction } from "../types";

function target(action: ToolAction): string {
  const value = action.arguments.relative_path;
  return typeof value === "string" ? value : "恢复隔离文件";
}

export function ApprovalsPage() {
  const { workerStatus } = useRuntime();
  const [items, setItems] = useState<ToolAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  function load() {
    setLoading(true);
    void listApprovals().then(setItems).catch(() => setFeedback("无法加载审批队列，请稍后重试。")).finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  async function decide(action: ToolAction, approved: boolean) {
    if (approved && workerStatus !== "online") return;
    setPending(action.id);
    setFeedback(null);
    try {
      if (approved) await approveAction(action.id, "本地管理员确认安全边界");
      else await denyAction(action.id, "本地管理员拒绝该动作");
      setItems((current) => current.filter((item) => item.id !== action.id));
      setFeedback(approved ? "已批准，任务已交给 Worker；请到动作页查看最终结果。" : "已拒绝，未创建文件执行任务。");
    } catch {
      setFeedback("审批未保存，可能已被其他操作处理；请刷新队列确认。 ");
    } finally {
      setPending(null);
    }
  }

  const offline = workerStatus !== "online";
  return <div className="page-shell">
    <div className="page-heading"><div><span className="eyebrow">人工介入 / 安全闸门</span><h1>审批</h1><p>审批只改变动作状态，不在浏览器请求里直接操作文件。真正的文件变化必须由已注册 Worker 执行并回报。</p></div><div className="heading-stat"><strong>{items.length.toString().padStart(2, "0")}</strong><span>个待处理动作</span></div></div>
    {offline && <div className="notice-bar notice-warning" role="status"><span className="notice-icon">!</span><span>Worker {workerStatus === "checking" ? "正在检查" : "离线或不可用"}，批准不会执行文件操作；请先启动本机 Worker。</span></div>}
    {feedback && <p className="inline-success" role="status">{feedback}</p>}
    <section className="approval-list">{loading ? <div className="panel loading-row" role="status">正在加载审批队列…</div> : items.length === 0 ? <div className="panel"><EmptyState title="审批队列为空" description="受保护路径会直接拒绝；普通文件动作在这里等待你的明确决定。" /></div> : items.map((action) => <article className="approval-card approval-card-wide" key={action.id}><div className="decision-rail rail-medium" aria-hidden="true" /><div className="approval-content"><div className="approval-heading"><div><span className="eyebrow">外部 Agent 请求</span><h2>{actionLabel(action.tool_name)}</h2></div><StatusBadge value={action.risk_level} /></div><div className="approval-target"><span>目标相对路径</span><code translate="no">{target(action)}</code></div><p className="approval-reason">{reasonLabel(action.reason)}</p><div className="approval-impact"><span>提交时间<strong>{formatDateTime(action.created_at)}</strong></span><span>预期结果<strong>审批后由 Worker 执行</strong></span></div><div className="approval-actions"><button className="button button-primary" type="button" onClick={() => void decide(action, true)} disabled={pending !== null || offline}>{pending === action.id ? "正在提交…" : "批准并执行 ↗"}</button><button className="button button-secondary" type="button" onClick={() => void decide(action, false)} disabled={pending !== null}>{pending === action.id ? "正在提交…" : "拒绝动作"}</button></div></div></article>)}</section>
  </div>;
}
