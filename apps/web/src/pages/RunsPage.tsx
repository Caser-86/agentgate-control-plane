import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AgentRun } from "../types";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { SignalTrack } from "../components/SignalTrack";
import { useRuntime } from "../components/AppShell";
import { formatDateTime } from "../i18n/zh-CN";

const examples = [
  { label: "恢复降级服务 → 需审批", prompt: "检查 payments-api 并安全恢复，不要轮换凭据。" },
  { label: "轮换 API 密钥 → 直接拒绝", prompt: "请轮换 payments-api 的 API 密钥。" },
];

export function RunsPage() {
  const { provider, model } = useRuntime();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.listRuns().then((loaded) => {
      if (!active) return;
      setRuns((current) => [
        ...current,
        ...loaded.filter((run) => !current.some((existing) => existing.id === run.id)),
      ]);
    }).catch(() => { if (active) setError("无法加载运行记录。"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (prompt.trim().length < 5) return;
    setSubmitting(true);
    setError(null);
    try {
      const run = await api.createRun({ user_request: prompt.trim() });
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setPrompt("");
      navigate(`/runs/${run.id}`);
    } catch {
      setError("无法启动运行。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div><span className="eyebrow">操作</span><h1>运行</h1><p>在 Agent 意图变成外部动作前，先看清它要做什么。</p></div>
        <div className="heading-stat"><strong>{runs.length.toString().padStart(2, "0")}</strong><span>条运行记录</span></div>
      </div>
      <SignalTrack />
      <section className="composer panel">
        <div className="section-heading"><div><span className="eyebrow">新建控制运行</span><h2>你希望 Agent 调查什么？</h2></div><span className="mono-note"><span>提供方：</span><code translate="no">{provider}</code><span> · 模型：</span><code translate="no">{model}</code></span></div>
        <form onSubmit={submit}>
          <label htmlFor="task-request">任务请求</label>
          <textarea id="task-request" name="task-request" data-testid="run-request" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="描述操作目标，以及允许的安全边界…" rows={3} />
          <div className="composer-footer"><div className="example-chips" aria-label="演示示例">{examples.map((example) => <button type="button" key={example.prompt} onClick={() => setPrompt(example.prompt)}>{example.label}</button>)}</div><button className="button button-primary" data-testid="start-run" type="submit" disabled={submitting || prompt.trim().length < 5}>{submitting ? "正在启动…" : "启动运行"}<span aria-hidden="true">↗</span></button></div>
        </form>
      </section>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <section className="runs-section panel">
        <div className="section-heading"><div><span className="eyebrow">活动记录</span><h2>最近运行</h2></div><span className="mono-note">按时间倒序</span></div>
        {loading ? <div className="loading-row" aria-live="polite">正在加载运行记录…</div> : runs.length === 0 ? <EmptyState title="暂无运行记录" description="从上面的任务请求开始，查看策略和审批事件。" /> : <div className="table-wrap"><table><thead><tr><th>运行</th><th>请求</th><th>状态</th><th>模型提供方</th><th>步骤</th><th>更新时间</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td><Link className="run-link" to={`/runs/${run.id}`} translate="no">#{run.id.slice(0, 8)}</Link></td><td className="request-cell">{run.user_request}</td><td data-testid="run-status"><StatusBadge value={run.status} /></td><td><code translate="no">{run.provider}</code></td><td>{run.step_count.toString().padStart(2, "0")}</td><td className="muted-cell">{formatDateTime(run.updated_at)}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  );
}
