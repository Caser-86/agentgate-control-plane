import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";

export function AppShell() {
  const [provider, setProvider] = useState("加载中");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let active = true;
    void api.getMeta().then((meta) => {
      if (!active) return;
      setProvider(meta.provider);
      setConnected(meta.status === "ok");
    }).catch(() => {
      if (!active) return;
      setProvider("不可用");
      setConnected(false);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
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
        <div className="environment-chip"><span className="live-dot" /> 本地演示</div>
        <nav aria-label="主导航" className="primary-nav">
          <span className="nav-label">操作</span>
          <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""}>运行 <span>01</span></NavLink>
          <NavLink to="/policies" className={({ isActive }) => isActive ? "active" : ""}>策略 <span>02</span></NavLink>
          <NavLink to="/audit" className={({ isActive }) => isActive ? "active" : ""}>审计 <span>03</span></NavLink>
          <NavLink to="/monitor" className={({ isActive }) => isActive ? "active" : ""}>监控 <span>04</span></NavLink>
        </nav>
        <div className="sidebar-footer">
          <span className="nav-label">运行环境</span>
          <div className="runtime-row"><span>模型提供方</span><code translate="no">{provider}</code></div>
          <div className="runtime-row"><span>后端</span><span className={connected ? "connectivity connected" : "connectivity"} aria-live="polite">{connected ? "已连接" : "检查中"}</span></div>
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
  );
}
