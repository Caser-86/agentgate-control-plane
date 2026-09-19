import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { PlatformHealth, PlatformHealthCheck } from "../types";

const checkLabels: Record<string, string> = {
  api: "控制平面 API",
  database: "数据库",
  queue: "任务队列",
  outbox: "待投递事件箱",
  worker: "本机 Worker",
};

function checkLabel(key: string): string {
  return checkLabels[key] ?? key;
}

function checkTone(check: PlatformHealthCheck | undefined): "healthy" | "degraded" | "down" | "unknown" {
  if (!check) return "unknown";
  if (check.status === "ok") return "healthy";
  return check.status === "degraded" ? "degraded" : "down";
}

function checkStatusLabel(key: string, check: PlatformHealthCheck | undefined): string {
  if (!check) return "未返回";
  if (key === "worker") {
    const executionStatus = check.details.execution_status;
    if (executionStatus === "reconciliation_required") return "需要对账";
    if (executionStatus === "blocked") return "执行受阻";
  }
  if (check.status === "ok") return "运行正常";
  return check.status === "degraded" ? "需要检查" : "不可用";
}

function numberDetail(check: PlatformHealthCheck, key: string): number | null {
  const value = check.details[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function workerDetails(check: PlatformHealthCheck): string[] {
  const details: string[] = [];
  const pending = numberDetail(check, "pending_report_count");
  const age = numberDetail(check, "age_seconds");
  if (pending !== null) details.push(`待上报 ${pending} 条`);
  if (age !== null) details.push(`最近心跳 ${Math.max(0, Math.round(age))} 秒前`);
  if (typeof check.details.last_error_code === "string") {
    details.push(`最近错误 ${check.details.last_error_code}`);
  }
  return details;
}

export function SystemPage() {
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadHealth = useCallback(() => {
    setLoading(true);
    setError(false);
    void api.getPlatformHealth().then((result) => {
      setHealth(result);
    }).catch(() => {
      setHealth(null);
      setError(true);
    }).finally(() => {
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  const checks = health ? Object.entries(health.checks) : [];

  return <div className="page-shell">
    <div className="page-heading">
      <div><span className="eyebrow">本机设置 / 运行状态</span><h1>系统</h1><p>查看控制平面和本机 Worker 的真实运行状态。这里不会显示密钥，也不会授予额外文件权限。</p></div>
      <div className="heading-stat"><strong>{checks.length.toString().padStart(2, "0")}</strong><span>项平台检查</span></div>
    </div>
    {error && <div className="inline-error" role="alert">运行状态读取失败：请确认本地 API 已启动。</div>}
    <section className="panel system-health-panel" aria-labelledby="system-health-title">
      <div className="section-heading"><div><span className="eyebrow">运行诊断</span><h2 id="system-health-title">服务状态</h2></div><button className="button button-secondary" type="button" onClick={loadHealth} disabled={loading}>{loading ? "正在刷新…" : "刷新状态"}</button></div>
      {loading && !health ? <div className="loading-row" role="status">正在读取本机运行状态…</div> : checks.length === 0 ? <p className="muted-copy">暂时没有可显示的状态检查。</p> : <div className="system-health-grid">{checks.map(([key, check]) => <article className={`system-health-card system-health-${checkTone(check)}`} key={key}><div className="system-health-card-top"><div><span className="eyebrow">{key.toUpperCase()}</span><h3>{checkLabel(key)}</h3></div><span className={`status-badge status-${checkTone(check)}`}><span className="status-dot" aria-hidden="true" />{checkStatusLabel(key, check)}</span></div><p>{check.message_zh}</p>{key === "worker" && workerDetails(check).length > 0 && <div className="system-health-facts">{workerDetails(check).map((detail) => <span key={detail}>{detail.startsWith("最近错误 ") ? <><span>最近错误</span><code translate="no">{detail.slice(5)}</code></> : detail}</span>)}</div>}<span className="system-health-time">检查时间：{new Date(check.observed_at).toLocaleString("zh-CN")}</span></article>)}</div>}
    </section>
    <section className="system-link-grid"><Link className="panel system-link-card" to="/monitor"><span className="eyebrow">运行状态</span><h2>本机监控 ↗</h2><p>检查 API、Worker 和本机 HTTP / Windows 服务的健康状态。</p></Link><Link className="panel system-link-card" to="/policies"><span className="eyebrow">规则注册</span><h2>策略注册表 ↗</h2><p>查看哪些动作只读、哪些需要审批，以及为什么会被拒绝。</p></Link></section>
  </div>;
}
