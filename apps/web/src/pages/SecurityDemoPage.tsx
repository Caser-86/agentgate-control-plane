import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import {
  approveAndWait,
  getAction,
  restoreAndWait,
  runSecurityDemo,
  type SecurityDemoSession,
} from "../api/actions";
import { listWorkspaces } from "../api/workspaces";
import { SignalTrack } from "../components/SignalTrack";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../i18n/zh-CN";
import type { ManagedWorkspace } from "../types";

type DemoState = "idle" | "loading" | "ready" | "approving" | "restoring" | "error";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "演示未完成，请确认 API、Worker 和演示文件已经准备好。";
}

function digestPrefix(result: SecurityDemoSession["ordinary"]["result"]): string {
  const digest = result?.content_sha256;
  return typeof digest === "string" ? `${digest.slice(0, 12)}…` : "等待 Worker 返回摘要";
}

export function SecurityDemoPage() {
  const [workspaces, setWorkspaces] = useState<ManagedWorkspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [ordinaryPath, setOrdinaryPath] = useState("demo.txt");
  const [session, setSession] = useState<SecurityDemoSession | null>(null);
  const [state, setState] = useState<DemoState>("idle");
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<SecurityDemoSession | null>(null);

  useEffect(() => {
    let active = true;
    void listWorkspaces().then((items) => {
      if (!active) return;
      setWorkspaces(items);
      setWorkspaceId((current) => current || items.find((item) => item.enabled)?.id || "");
    }).catch((reason) => {
      if (active) setError(errorMessage(reason));
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  useEffect(() => () => {
    const current = sessionRef.current;
    if (current?.clientTokenId) void api.revokeClientToken(current.clientTokenId).catch(() => undefined);
  }, []);

  const workspace = useMemo(
    () => workspaces.find((item) => item.id === workspaceId),
    [workspaceId, workspaces],
  );

  async function startDemo() {
    if (!workspaceId || !ordinaryPath.trim()) return;
    setState("loading");
    setError(null);
    try {
      setSession(await runSecurityDemo(workspaceId, ordinaryPath.trim()));
      setState("ready");
    } catch (reason) {
      setState("error");
      setError(errorMessage(reason));
    }
  }

  async function approveOrdinaryFile() {
    if (!session || !workspace) return;
    setState("approving");
    setError(null);
    try {
      const adminAction = await getAction(session.ordinary.id);
      const ordinary = await approveAndWait(session.clientToken, adminAction);
      setSession((current) => current ? { ...current, ordinary } : current);
      setState("ready");
    } catch (reason) {
      setState("error");
      setError(errorMessage(reason));
    }
  }

  async function restoreOrdinaryFile() {
    const entryId = session?.ordinary.result?.quarantine_entry_id;
    if (!session || !workspace || typeof entryId !== "string") return;
    setState("restoring");
    setError(null);
    try {
      const restored = await restoreAndWait(session.clientToken, workspace.id, entryId);
      setSession((current) => current ? { ...current, ordinary: restored } : current);
      setState("ready");
    } catch (reason) {
      setState("error");
      setError(errorMessage(reason));
    }
  }

  const ordinarySucceeded = session?.ordinary.status === "succeeded" && session.ordinary.result?.side_effect === "quarantined";
  const restored = session?.ordinary.status === "succeeded" && session.ordinary.result?.side_effect === "restored";

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="eyebrow">面试演示 / 文件治理</span>
          <h1>安全演示</h1>
          <p>用一个真实工作区走完“受保护文件拒绝、普通文件审批、隔离、恢复”四个结论，直接看到策略、审批和 Worker 是否一致。</p>
        </div>
        <div className="heading-stat"><strong>{restored ? "04" : ordinarySucceeded ? "03" : session ? "02" : "01"}</strong><span>个安全结论</span></div>
      </div>

      <SignalTrack activeStage={restored ? 4 : ordinarySucceeded ? 3 : session ? 2 : 1} />

      {!workspace && <section className="panel demo-setup-panel"><span className="eyebrow">开始前准备</span><h2>先登记一个受管工作区</h2><p>工作区是唯一允许 Worker 操作的本机目录。请在工作区中准备一个普通文件，例如 <code translate="no">demo.txt</code>，再回来开始演示。</p><Link className="button button-primary" to="/workspaces">去登记工作区 ↗</Link></section>}

      {workspace && <section className="panel demo-setup-panel">
        <div className="section-heading"><div><span className="eyebrow">真实动作链</span><h2>开始一次可复核的演示</h2></div><span className="mono-note">不显示令牌 / 只传相对路径</span></div>
        <div className="demo-form-grid">
          <label htmlFor="demo-workspace">工作区<select id="demo-workspace" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} disabled={state === "loading"}><option value="">请选择工作区</option>{workspaces.map((item) => <option value={item.id} key={item.id}>{item.name}{item.enabled ? "" : "（已停用）"}</option>)}</select></label>
          <label htmlFor="demo-path">普通文件相对路径<input id="demo-path" value={ordinaryPath} onChange={(event) => setOrdinaryPath(event.target.value)} placeholder="例如：demo.txt" disabled={state === "loading"} /></label>
        </div>
        <p className="demo-safety-note">受保护样例固定为 <code translate="no">.env</code>；普通文件必须已经存在于工作区内。演示令牌只在内存中短暂使用，结束后撤销。</p>
        <button className="button button-primary" type="button" aria-label="开始安全演示" onClick={() => void startDemo()} disabled={!workspaceId || !ordinaryPath.trim() || ["loading", "approving", "restoring"].includes(state)}>{state === "loading" ? "正在提交真实动作…" : "开始安全演示 ↗"}</button>
      </section>}

      {error && <p className="inline-error" role="alert">{error}</p>}

      {session && <section className="demo-result-grid" aria-label="安全演示结果">
        <article className="demo-result-card result-denied">
          <div className="result-card-top"><span className="result-index">01</span><StatusBadge value={session.protected.status} /></div>
          <span className="eyebrow">真实策略结论 / 受保护文件</span><h2><code translate="no">.env</code> 已拒绝</h2>
          <p>已拒绝，文件未执行任何变化</p><span className="result-detail">{session.protected.reason}</span>
        </article>
        <article className={`demo-result-card ${ordinarySucceeded || restored ? "result-success" : "result-pending"}`}>
          <div className="result-card-top"><span className="result-index">02</span><StatusBadge value={session.ordinary.status} /></div>
          <span className="eyebrow">普通文件</span><h2><code translate="no">{session.ordinary.relative_path || ordinaryPath}</code></h2>
          <p>{restored ? "已恢复，目标文件没有被覆盖" : ordinarySucceeded ? "已隔离，文件已经离开原路径" : "待审批，Worker 尚未执行文件变化"}</p>
          <span className="result-detail">策略：{session.ordinary.reason}</span>
          {session.ordinary.result && <div className="result-facts"><span>SHA-256 <code translate="no">{digestPrefix(session.ordinary.result)}</code></span><span>结果：{String(session.ordinary.result.side_effect || "无")}</span></div>}
          {!ordinarySucceeded && session.ordinary.status === "pending_approval" && <button className="button button-approval" type="button" onClick={() => void approveOrdinaryFile()} disabled={state === "approving"}>{state === "approving" ? "正在审批并等待 Worker…" : "批准并隔离 ↗"}</button>}
          {ordinarySucceeded && !restored && <button className="button button-primary" type="button" onClick={() => void restoreOrdinaryFile()} disabled={state === "restoring"}>{state === "restoring" ? "正在恢复并校验…" : "恢复文件 ↗"}</button>}
          {restored && <span className="result-confirmed">已完成闭环 · {formatDateTime(session.ordinary.created_at)}</span>}
        </article>
      </section>}

      <section className="demo-explain"><span className="eyebrow">你要展示什么</span><p><strong>拒绝不是提示语。</strong> 它意味着没有任务进入 Worker；批准也不是直接移动文件，而是先生成受控任务，再由 Native Worker 在工作区边界内执行，并把摘要、相对路径和最终状态回传。</p><Link to="/audit">查看完整审计轨迹 ↗</Link></section>
    </div>
  );
}
