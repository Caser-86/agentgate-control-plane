import { FormEvent, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { createWorkspace, listQuarantineEntries, listWorkspaces } from "../api/workspaces";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../i18n/zh-CN";
import type { ManagedWorkspace, QuarantineEntry } from "../types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "工作区操作失败，请检查路径和本地服务。";
}

export function WorkspacesPage() {
  const [items, setItems] = useState<ManagedWorkspace[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<QuarantineEntry[]>([]);
  const [form, setForm] = useState({ name: "", root_path: "C:\\AgentGate\\workspaces\\面试演示", patterns: ".env,*.pem,*.key" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string } | null>(null);

  function load() {
    setLoading(true);
    void listWorkspaces().then((loaded) => {
      setItems(loaded);
      setSelected((current) => current || loaded[0]?.id || null);
    }).catch((error) => setFeedback({ kind: "error", message: errorMessage(error) })).finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!selected) { setEntries([]); return; }
    void listQuarantineEntries(selected).then((response) => setEntries(response.items)).catch(() => setEntries([]));
  }, [selected]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.name.trim() || !form.root_path.trim()) return;
    setSaving(true);
    setFeedback(null);
    try {
      const created = await createWorkspace({ name: form.name.trim(), root_path: form.root_path.trim(), protected_patterns: form.patterns.split(",").map((value) => value.trim()).filter(Boolean) });
      setItems((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setSelected(created.id);
      setForm({ name: "", root_path: form.root_path, patterns: form.patterns });
      setFeedback({ kind: "success", message: "工作区已登记。请在该目录内准备一个普通文件后开始安全演示。" });
    } catch (error) {
      setFeedback({ kind: "error", message: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  const selectedWorkspace = items.find((item) => item.id === selected);
  return <div className="page-shell">
    <div className="page-heading"><div><span className="eyebrow">边界 / 本机目录</span><h1>工作区</h1><p>工作区把 Agent 的相对路径约束到一个明确的 Windows 根目录，并保存保护规则和隔离记录。</p></div><div className="heading-stat"><strong>{items.length.toString().padStart(2, "0")}</strong><span>个受管目录</span></div></div>
    <section className="panel workspace-create-panel"><div className="section-heading"><div><span className="eyebrow">登记边界</span><h2>添加本机工作区</h2></div><span className="mono-note">路径会经过 API 校验</span></div><form className="workspace-form" onSubmit={(event) => void submit(event)}><label htmlFor="workspace-name">名称<input id="workspace-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="例如：面试演示工作区" required /></label><label htmlFor="workspace-root">Windows 根目录<input id="workspace-root" value={form.root_path} onChange={(event) => setForm({ ...form, root_path: event.target.value })} placeholder="C:\\AgentGate\\workspaces\\demo" required /></label><label htmlFor="workspace-patterns">保护规则<input id="workspace-patterns" value={form.patterns} onChange={(event) => setForm({ ...form, patterns: event.target.value })} placeholder=".env,*.pem,*.key" /></label><div className="workspace-form-footer"><span>建议保留 <code translate="no">.env</code>、<code translate="no">*.pem</code>、<code translate="no">*.key</code>。</span><button className="button button-primary" type="submit" disabled={saving}>{saving ? "正在登记…" : "登记工作区 ↗"}</button></div></form></section>
    {feedback && <p className={feedback.kind === "error" ? "inline-error" : "inline-success"} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</p>}
    <section className="workspace-grid"><div className="panel workspace-list-panel"><div className="section-heading"><div><span className="eyebrow">本地管理员</span><h2>已登记目录</h2></div><button className="button button-secondary" type="button" onClick={load}>刷新</button></div>{loading ? <div className="loading-row">正在加载工作区…</div> : items.length === 0 ? <EmptyState title="还没有工作区" description="登记一个位于允许根目录内的 Windows 文件夹，Worker 才能获得最小操作边界。" /> : <div className="workspace-list">{items.map((item) => <button className={`workspace-list-item ${selected === item.id ? "selected" : ""}`} type="button" key={item.id} onClick={() => setSelected(item.id)}><span><strong>{item.name}</strong><code translate="no">{item.root_path}</code></span><StatusBadge value={item.enabled ? "healthy" : "down"} /></button>)}</div>}<p className="privacy-note">工作区根路径只显示给本地管理员；发送给外部 Agent 的始终是相对路径。</p></div><div className="panel workspace-detail-panel">{selectedWorkspace ? <><div className="section-heading"><div><span className="eyebrow">边界详情</span><h2>{selectedWorkspace.name}</h2></div><StatusBadge value={selectedWorkspace.enabled ? "healthy" : "down"} /></div><dl className="workspace-facts"><div><dt>根目录（本机）</dt><dd><code translate="no">{selectedWorkspace.root_path}</code></dd></div><div><dt>保护规则</dt><dd className="pattern-list">{selectedWorkspace.protected_patterns.map((pattern) => <code translate="no" key={pattern}>{pattern}</code>)}</dd></div><div><dt>配置版本</dt><dd>v{selectedWorkspace.version}</dd></div></dl><div className="quarantine-heading"><span className="eyebrow">证据</span><h3>隔离记录</h3></div>{entries.length === 0 ? <p className="muted-copy">当前没有隔离记录。</p> : <div className="quarantine-list">{entries.map((entry) => <div className="quarantine-row" key={entry.id}><div><strong translate="no">{entry.original_relative_path}</strong><span>{entry.status === "restored" ? "已恢复" : "已隔离"} · {formatDateTime(entry.created_at)}</span></div><code translate="no">{entry.content_sha256.slice(0, 12)}…</code></div>)}</div>}</> : <EmptyState title="选择一个工作区" description="左侧选择后查看保护规则和隔离证据。" />}</div></section>
  </div>;
}
