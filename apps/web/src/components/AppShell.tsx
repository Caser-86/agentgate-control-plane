import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";

export type WorkerStatus = "checking" | "online" | "degraded" | "unavailable";

export type RuntimeState = {
  provider: string;
  model: string;
  apiBaseUrl: string;
  connected: boolean;
  workerStatus: WorkerStatus;
};

const defaultRuntime: RuntimeState = {
  provider: "加载中",
  model: "加载中",
  apiBaseUrl: "",
  connected: false,
  workerStatus: "checking",
};

const RuntimeContext = createContext<RuntimeState>(defaultRuntime);

export function useRuntime(): RuntimeState {
  return useContext(RuntimeContext);
}

export function AppShell() {
  const [runtime, setRuntime] = useState<RuntimeState>(defaultRuntime);

  useEffect(() => {
    let active = true;
    void api.getMeta().then((meta) => {
      if (!active) return;
      setRuntime((current) => ({
        ...current,
        provider: meta.provider,
        model: meta.model,
        apiBaseUrl: meta.api_base_url,
        connected: meta.status === "ok",
      }));
    }).catch(() => {
      if (!active) return;
      setRuntime((current) => ({
        ...current,
        provider: "不可用",
        model: "不可用",
        apiBaseUrl: "",
        connected: false,
      }));
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const loadWorkerHealth = () => {
      void api.getPlatformHealth().then((health) => {
        if (!active) return;
        const workerHealth = health.checks.worker;
        setRuntime((current) => ({
          ...current,
          workerStatus: workerHealth?.status === "ok" ? "online" : "degraded",
        }));
      }).catch(() => {
        if (!active) return;
        setRuntime((current) => ({ ...current, workerStatus: "unavailable" }));
      });
    };
    loadWorkerHealth();
    const interval = window.setInterval(loadWorkerHealth, 10_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const workerStatusLabel: Record<WorkerStatus, string> = {
    checking: "检查中",
    online: "在线",
    degraded: "需要检查",
    unavailable: "不可用",
  };
  const workerStatusClass: Record<WorkerStatus, string> = {
    checking: "worker-health checking",
    online: "worker-health online",
    degraded: "worker-health degraded",
    unavailable: "worker-health unavailable",
  };

  return (
    <RuntimeContext.Provider value={runtime}>
      <div className="app-frame">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">AG</span>
          <div>
            <h1>AgentGate</h1>
            <span>控制平面</span>
          </div>
        </div>
        <div className="environment-chip"><span className="live-dot" /> 本机运行中</div>
        <nav aria-label="主导航" className="primary-nav">
          <span className="nav-label">安全控制台</span>
          <NavLink to="/demo" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">✦</span><span>安全演示</span></span><span className="nav-count">01</span></NavLink>
          <NavLink to="/actions" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">↗</span><span>动作</span></span><span className="nav-count">02</span></NavLink>
          <NavLink to="/approvals" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">!</span><span>审批</span></span><span className="nav-count">03</span></NavLink>
          <NavLink to="/workspaces" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">□</span><span>工作区</span></span><span className="nav-count">04</span></NavLink>
          <NavLink to="/audit" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">≡</span><span>审计</span></span><span className="nav-count">05</span></NavLink>
          <NavLink to="/system" className={({ isActive }) => isActive ? "active" : ""}><span className="nav-leading"><span className="nav-symbol" aria-hidden="true">⚙</span><span>系统</span></span><span className="nav-count">06</span></NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-footer-heading"><span className="nav-label">当前连接</span><span className={runtime.connected ? "connectivity connected" : "connectivity"} aria-live="polite">{runtime.connected ? "在线" : "检查中"}</span></div>
          <div className="runtime-row"><span>模型提供方</span><code translate="no">{runtime.provider}</code></div>
          <div className="runtime-row"><span>模型</span><code translate="no">{runtime.model}</code></div>
          <div className="runtime-row"><span>后端</span><code translate="no">{runtime.apiBaseUrl || "等待地址"}</code></div>
          <div className="runtime-row"><span>本机 Worker</span><span
            className={workerStatusClass[runtime.workerStatus]}
            data-testid="worker-health"
            aria-live="polite"
          >{workerStatusLabel[runtime.workerStatus]}</span></div>
          <p className="runtime-note">只显示运行时元数据，不会显示密钥。</p>
        </div>
      </aside>
      <main id="main-content" className="main-content">
        <header className="topbar">
          <span className="topbar-path">Agent 操作 / <strong>本地环境</strong></span>
          <span className="topbar-note">每个操作都会留下审计轨迹</span>
        </header>
        <Outlet />
      </main>
      </div>
    </RuntimeContext.Provider>
  );
}
