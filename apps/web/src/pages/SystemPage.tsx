import { Link } from "react-router-dom";

export function SystemPage() {
  return <div className="page-shell"><div className="page-heading"><div><span className="eyebrow">本机设置 / 运行状态</span><h1>系统</h1><p>系统页放运行状态和可解释的配置入口。它不会代替安全动作，也不会自动获得文件权限。</p></div><div className="heading-stat"><strong>02</strong><span>个系统入口</span></div></div><section className="system-link-grid"><Link className="panel system-link-card" to="/monitor"><span className="eyebrow">运行状态</span><h2>本机监控 ↗</h2><p>检查 API、Worker 和本机 HTTP / Windows 服务的健康状态。</p></Link><Link className="panel system-link-card" to="/policies"><span className="eyebrow">规则注册</span><h2>策略注册表 ↗</h2><p>查看哪些动作只读、哪些需要审批，以及为什么会被拒绝。</p></Link></section></div>;
}
