import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AgentRun } from "../types";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";

const examples = [
  "Investigate payments-api and restore it safely. Do not rotate credentials.",
  "Rotate the API key for payments-api.",
];

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function RunsPage() {
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
    }).catch(() => { if (active) setError("Runs could not be loaded."); }).finally(() => { if (active) setLoading(false); });
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
      setError("The run could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div><span className="eyebrow">01 / 操作</span><h1>运行</h1><p>在意图成为外部操作前先观察它。</p></div>
        <div className="heading-stat"><strong>{runs.length.toString().padStart(2, "0")}</strong><span>tracked runs</span></div>
      </div>
      <section className="composer panel">
        <div className="section-heading"><div><span className="eyebrow">新建控制运行</span><h2>希望 Agent 调查什么？</h2></div><span className="mono-note">mock / deterministic</span></div>
        <form onSubmit={submit}>
          <label htmlFor="task-request">任务请求</label>
          <textarea id="task-request" data-testid="run-request" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="描述操作目标和安全边界…" rows={3} />
          <div className="composer-footer"><div className="example-chips" aria-label="示例">{examples.map((example) => <button type="button" key={example} onClick={() => setPrompt(example)}>{example.startsWith("Rotate") ? "轮换密钥 → 拒绝" : "恢复降级 API → 批准"}</button>)}</div><button className="button button-primary" data-testid="start-run" type="submit" disabled={submitting || prompt.trim().length < 5}>{submitting ? "启动中…" : "开始运行"}<span aria-hidden="true">↗</span></button></div>
        </form>
      </section>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <section className="runs-section panel">
        <div className="section-heading"><div><span className="eyebrow">活动账本</span><h2>最近运行</h2></div><span className="mono-note">newest first</span></div>
        {loading ? <div className="loading-row">Loading run history…</div> : runs.length === 0 ? <EmptyState title="No runs in the ledger" description="Start with one of the deterministic demos above to see policy and approval events appear." /> : <div className="table-wrap"><table><thead><tr><th>Run</th><th>Request</th><th>Status</th><th>Provider</th><th>Steps</th><th>Updated</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td><Link className="run-link" to={`/runs/${run.id}`}>#{run.id.slice(0, 8)}</Link></td><td className="request-cell">{run.user_request}</td><td data-testid="run-status"><StatusBadge value={run.status} /></td><td><code>{run.provider}</code></td><td>{run.step_count.toString().padStart(2, "0")}</td><td className="muted-cell">{formatTime(run.updated_at)}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  );
}
