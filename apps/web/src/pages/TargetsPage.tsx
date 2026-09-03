import { type FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../i18n/zh-CN";
import type { CreateMonitorTargetRequest, MonitorTarget, MonitorTargetKind } from "../types";

const initialForm: CreateMonitorTargetRequest = {
  name: "",
  kind: "http",
  endpoint: "http://127.0.0.1:8000/health",
  interval_seconds: 60,
  timeout_seconds: 5,
  failure_threshold: 3,
  recovery_threshold: 2,
};

function kindLabel(kind: MonitorTargetKind): string {
  return kind === "http" ? "HTTP 地址" : "Windows 服务";
}

export function TargetsPage() {
  const [targets, setTargets] = useState<MonitorTarget[]>([]);
  const [form, setForm] = useState<CreateMonitorTargetRequest>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTargets = () => {
    setLoading(true);
    void api.listMonitorTargets()
      .then(setTargets)
      .catch(() => setError("无法加载监控目标。"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadTargets();
  }, []);

  const updateForm = <K extends keyof CreateMonitorTargetRequest>(
    key: K,
    value: CreateMonitorTargetRequest[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  async function createTarget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.name.trim() || !form.endpoint?.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.createMonitorTarget({ ...form, name: form.name.trim(), endpoint: form.endpoint.trim() });
      setTargets((current) => [created, ...current.filter((target) => target.id !== created.id)]);
      setForm(initialForm);
    } catch {
      setError("无法创建目标，请检查名称、地址和参数。只允许监控本机回环地址。 ");
    } finally {
      setSaving(false);
    }
  }

  async function probeTarget(target: MonitorTarget) {
    setProbing(target.id);
    setError(null);
    try {
      await api.probeMonitorTarget(target.id);
      setError("探测任务已排队，完成后请刷新查看结果。 ");
    } catch {
      setError("无法排队探测任务。 ");
    } finally {
      setProbing(null);
    }
  }

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="eyebrow">04 / 观测</span>
          <h1>监控</h1>
          <p>只读检查本机 HTTP 地址和 Windows 服务，让故障、降级与恢复都有可追溯证据。</p>
        </div>
        <div className="heading-stat"><strong>{targets.length.toString().padStart(2, "0")}</strong><span>个监控目标</span></div>
      </div>

      <section className="panel composer monitor-form-panel">
        <div className="section-heading">
          <div><span className="eyebrow">登记本机目标</span><h2>添加只读监控</h2></div>
          <span className="mono-note">loopback / read-only</span>
        </div>
        <form className="monitor-form" onSubmit={(event) => void createTarget(event)}>
          <label htmlFor="monitor-name">目标名称<input id="monitor-name" value={form.name} onChange={(event) => updateForm("name", event.target.value)} placeholder="例如：本地 API" required /></label>
          <label htmlFor="monitor-kind">目标类型
            <select id="monitor-kind" value={form.kind} onChange={(event) => {
              const kind = event.target.value as MonitorTargetKind;
              updateForm("kind", kind);
              updateForm("endpoint", kind === "http" ? "http://127.0.0.1:8000/health" : "AgentGateWorker");
            }}>
              <option value="http">HTTP 地址</option>
              <option value="windows_service">Windows 服务</option>
            </select>
          </label>
          <label htmlFor="monitor-endpoint">{form.kind === "http" ? "本机 HTTP 地址" : "Windows 服务名"}<input id="monitor-endpoint" value={form.endpoint} onChange={(event) => updateForm("endpoint", event.target.value)} placeholder={form.kind === "http" ? "http://127.0.0.1:8000/health" : "AgentGateWorker"} required /></label>
          <div className="monitor-form-grid">
            <label htmlFor="monitor-interval">间隔（秒）<input id="monitor-interval" type="number" min={5} max={86400} value={form.interval_seconds} onChange={(event) => updateForm("interval_seconds", Number(event.target.value))} /></label>
            <label htmlFor="monitor-timeout">超时（秒）<input id="monitor-timeout" type="number" min={1} max={30} value={form.timeout_seconds} onChange={(event) => updateForm("timeout_seconds", Number(event.target.value))} /></label>
            <label htmlFor="monitor-failure-threshold">失败阈值<input id="monitor-failure-threshold" type="number" min={1} max={10} value={form.failure_threshold} onChange={(event) => updateForm("failure_threshold", Number(event.target.value))} /></label>
            <label htmlFor="monitor-recovery-threshold">恢复阈值<input id="monitor-recovery-threshold" type="number" min={1} max={10} value={form.recovery_threshold} onChange={(event) => updateForm("recovery_threshold", Number(event.target.value))} /></label>
          </div>
          <div className="monitor-form-footer"><p className="mono-note">只允许 localhost / 127.0.0.1 / ::1；不会发送或保存响应正文。</p><button className="button button-primary" type="submit" disabled={saving}>{saving ? "正在保存…" : "添加监控"}<span aria-hidden="true">↗</span></button></div>
        </form>
      </section>

      {error && <p className="inline-error" role="status">{error}</p>}
      <section className="panel runs-section">
        <div className="section-heading"><div><span className="eyebrow">实时观测</span><h2>监控目标</h2></div><button className="button button-secondary" type="button" onClick={loadTargets}>刷新</button></div>
        {loading ? <div className="loading-row" aria-live="polite">正在加载监控目标…</div> : targets.length === 0 ? <EmptyState title="还没有监控目标" description="先登记一个本机 HTTP 地址或 Windows 服务，系统才会开始排队只读探测。" /> : <div className="monitor-grid">{targets.map((target) => <article className="monitor-card" key={target.id}>
          <div className="monitor-card-heading"><div><span className="eyebrow">{kindLabel(target.kind)}</span><h3>{target.name}</h3></div><StatusBadge value={target.health} /></div>
          <code className="monitor-endpoint" translate="no">{target.endpoint}</code>
          <dl className="monitor-facts"><div><dt>最近探测</dt><dd>{target.last_probe_at ? formatDateTime(target.last_probe_at) : "尚未探测"}</dd></div><div><dt>最近结果</dt><dd>{target.last_probe_detail || "等待 Worker 返回"}{target.last_latency_ms !== null && <span className="table-subtext">{target.last_latency_ms} ms</span>}</dd></div><div><dt>连续计数</dt><dd>失败 {target.consecutive_failures} / 恢复 {target.consecutive_successes}</dd></div></dl>
          {target.active_event && <p className="monitor-event"><span className="status-dot" aria-hidden="true" />活动事件：{target.active_event.reason}</p>}
          <div className="monitor-card-footer"><span className="mono-note">每 {target.interval_seconds} 秒</span><button className="button button-secondary" type="button" onClick={() => void probeTarget(target)} disabled={probing === target.id}>{probing === target.id ? "正在排队…" : "立即探测"}</button></div>
        </article>)}</div>}
      </section>
    </div>
  );
}
