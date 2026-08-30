import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";

export function AppShell() {
  const [provider, setProvider] = useState("loading");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let active = true;
    void api.getMeta().then((meta) => {
      if (!active) return;
      setProvider(meta.provider);
      setConnected(meta.status === "ok");
    }).catch(() => {
      if (!active) return;
      setProvider("unavailable");
      setConnected(false);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">AG</span>
          <div>
            <h1>AgentGate</h1>
            <span>control plane</span>
          </div>
        </div>
        <div className="environment-chip"><span className="live-dot" /> Local Demo</div>
        <nav aria-label="Primary navigation" className="primary-nav">
          <span className="nav-label">Operate</span>
          <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""}>Runs <span>01</span></NavLink>
          <NavLink to="/policies" className={({ isActive }) => isActive ? "active" : ""}>Policies <span>02</span></NavLink>
          <NavLink to="/audit" className={({ isActive }) => isActive ? "active" : ""}>Audit <span>03</span></NavLink>
        </nav>
        <div className="sidebar-footer">
          <span className="nav-label">Runtime</span>
          <div className="runtime-row"><span>Provider</span><code>{provider}</code></div>
          <div className="runtime-row"><span>Backend</span><span className={connected ? "connectivity connected" : "connectivity"}>{connected ? "Connected" : "Checking"}</span></div>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <span className="topbar-path">Agent operations / <strong>Local environment</strong></span>
          <span className="topbar-note">Every action leaves a trace</span>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
