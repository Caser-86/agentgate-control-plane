import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { type FileActionKind, submitFileAction } from "../api/actions";
import { listQuarantineEntries, listWorkspaces } from "../api/workspaces";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime, statusLabel, toolLabel } from "../i18n/zh-CN";
import type { ExternalActionStatus, ManagedWorkspace, QuarantineEntry } from "../types";

const actionOptions: Array<{ value: FileActionKind; label: string; description: string }> = [
  { value: "inspect", label: "检查文件", description: "只读计算文件元数据和摘要，不改变磁盘。" },
  { value: "quarantine", label: "隔离文件", description: "审批通过后移动到同卷隔离区，不覆盖目标文件。" },
  { value: "restore", label: "恢复文件", description: "审批通过后恢复到原相对路径，目标冲突时停止。" },
];

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "文件动作提交失败，请检查 API、Worker 和工作区状态。";
}

function digestPrefix(result: ExternalActionStatus["result"]): string {
  const digest = result?.content_sha256;
  return typeof digest === "string" ? `${digest.slice(0, 12)}…` : "未返回摘要";
}

export function FileGovernancePage() {
  const [workspaces, setWorkspaces] = useState<ManagedWorkspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [entries, setEntries] = useState<QuarantineEntry[]>([]);
  const [kind, setKind] = useState<FileActionKind>("inspect");
  const [relativePath, setRelativePath] = useState("");
  const [entryId, setEntryId] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [result, setResult] = useState<ExternalActionStatus | null>(null);

  useEffect(() => {
    let active = true;
    void listWorkspaces().then((items) => {
      if (!active) return;
      setWorkspaces(items);
      setWorkspaceId((current) => current || items.find((item) => item.enabled)?.id || "");
    }).catch((error) => {
      if (active) setFeedback({ kind: "error", message: errorMessage(error) });
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!workspaceId) { setEntries([]); return; }
    void listQuarantineEntries(workspaceId, "quarantined")
      .then((response) => setEntries(response.items))
      .catch(() => setEntries([]));
  }, [workspaceId, result]);

  const selectedWorkspace = useMemo(() => workspaces.find((item) => item.id === workspaceId), [workspaces, workspaceId]);
  const enabledWorkspaces = useMemo(() => workspaces.filter((item) => item.enabled), [workspaces]);
  const selectedAction = actionOptions.find((option) => option.value === kind) ?? actionOptions[0];
  const canSubmit = Boolean(selectedWorkspace?.enabled)
    && (kind === "restore" ? Boolean(entryId) : Boolean(relativePath.trim()));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || (kind !== "restore" && !relativePath.trim()) || (kind === "restore" && !entryId)) return;
    setSubmitting(true);
    setFeedback(null);
    setResult(null);
    try {
      const action = await submitFileAction(
        workspaceId,
        kind,
        kind === "restore" ? undefined : relativePath.trim(),
        kind === "restore" ? entryId : undefined,
        `${selectedAction.label}：${kind === "restore" ? "恢复已隔离文件" : relativePath.trim()}`,
      );
      setResult(action);
      setFeedback({ kind: "success", message: "动作已提交" });
    } catch (error) {
      setFeedback({ kind: "error", message: errorMessage(error) });
    } finally {
      setSubmitting(false);
    }
  }

  return <div className="page-shell">
    <div className="page-heading"><div><span className="eyebrow">治理 / 文件动作</span><h1>文件治理</h1><p>提交受控文件动作，统一经过路径校验、策略判断、审批和 Native Worker 执行。</p></div><div className="heading-stat"><strong>{enabledWorkspaces.length.toString().padStart(2, "0")}</strong><span>个可用工作区</span></div></div>

    {!loading && enabledWorkspaces.length === 0 ? <section className="panel file-governance-panel"><EmptyState title="还没有可用工作区" description="先登记并启用一个本机工作区，文件动作才有明确的操作边界。" /><Link className="button button-primary" to="/workspaces">去登记工作区 ↗</Link></section> : <section className="panel file-governance-panel">
      <div className="section-heading"><div><span className="eyebrow">受控操作</span><h2>提交文件动作</h2></div><span className="mono-note">只传相对路径 / 不显示令牌</span></div>
      <form className="file-governance-form" onSubmit={(event) => void submit(event)}>
        <label htmlFor="file-workspace">工作区<select id="file-workspace" value={workspaceId} onChange={(event) => { setWorkspaceId(event.target.value); setEntryId(""); setResult(null); setFeedback(null); }} disabled={loading || submitting}><option value="">请选择工作区</option>{enabledWorkspaces.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label htmlFor="file-action">动作类型<select id="file-action" value={kind} onChange={(event) => { setKind(event.target.value as FileActionKind); setResult(null); setFeedback(null); }} disabled={submitting}><option value="inspect">检查文件</option><option value="quarantine">隔离文件</option><option value="restore">恢复文件</option></select></label>
        {kind !== "restore" ? <label htmlFor="file-relative-path">相对路径<input id="file-relative-path" value={relativePath} onChange={(event) => setRelativePath(event.target.value)} placeholder="例如：src/config.json" disabled={submitting} autoComplete="off" /></label> : <label htmlFor="file-quarantine-entry">待恢复文件<select id="file-quarantine-entry" value={entryId} onChange={(event) => setEntryId(event.target.value)} disabled={submitting || entries.length === 0}><option value="">{entries.length ? "请选择隔离记录" : "没有可恢复的隔离文件"}</option>{entries.map((entry) => <option value={entry.id} key={entry.id}>{entry.original_relative_path} · {entry.content_sha256.slice(0, 12)}…</option>)}</select></label>}
        <p className="file-governance-note">{selectedAction.description}{selectedWorkspace && <> 当前工作区：<strong>{selectedWorkspace.name}</strong>{selectedWorkspace.enabled ? "。" : "（已停用，不能提交动作）。"}</>}</p>
        {feedback && <p className={feedback.kind === "error" ? "inline-error" : "inline-success"} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</p>}
        <div className="file-governance-form-footer"><span className="mono-note">审批动作会进入“审批”；所有结果会进入“动作”和“审计”。</span><button className="button button-primary" type="submit" disabled={submitting || !canSubmit}>{submitting ? "正在提交…" : "提交文件动作"}<span aria-hidden="true">↗</span></button></div>
      </form>
    </section>}

    {result && <section className="file-governance-result" aria-label="动作结果"><article className="panel file-governance-result-card"><div className="result-card-top"><span className="eyebrow">最近提交</span><StatusBadge value={result.status} /></div><h2>{toolLabel(result.action)}</h2><p>{result.reason}</p><dl className="result-facts"><div><dt>状态</dt><dd>{statusLabel(result.status)}</dd></div><div><dt>相对路径</dt><dd><code translate="no">{result.relative_path || "恢复动作（见隔离记录）"}</code></dd></div>{result.result && <div><dt>SHA-256</dt><dd><code translate="no">{digestPrefix(result.result)}</code></dd></div>}</dl><div className="file-governance-result-links">{result.status === "pending_approval" && <Link className="button button-approval" to="/approvals">去审批 ↗</Link>}<Link className="button button-secondary" to="/actions">查看动作 ↗</Link></div><span className="result-detail">提交时间：{formatDateTime(result.created_at)}</span></article></section>}
  </div>;
}
