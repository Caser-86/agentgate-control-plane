import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export function LoginPage() {
  const { setupRequired, sessionExpired, loading, login, refresh, setup } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [failed, setFailed] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailed(false);
    try {
      if (setupRequired) await setup(bootstrapToken, password);
      else await login(password);
      navigate("/", { replace: true });
    } catch {
      setFailed(true);
    }
  };

  return (
    <main className="page-shell" aria-busy={loading}>
      <section className="panel" style={{ maxWidth: 480, margin: "4rem auto" }}>
        <span className="eyebrow">AgentGate / 本地控制台</span>
        <h1>{setupRequired ? "初始化管理员密码" : "登录"}</h1>
        <p>{setupRequired ? "使用一次性引导令牌创建唯一管理员。" : "请输入管理员密码以继续。"}</p>
        {sessionExpired && <p role="alert">会话已过期，请重新登录后重试。</p>}
        {failed && <p role="alert">登录失败，请检查输入后重试。</p>}
        {sessionExpired && <button type="button" onClick={() => void refresh()}>重试</button>}
        <form onSubmit={(event) => void submit(event)}>
          {setupRequired && <label>引导令牌<input value={bootstrapToken} onChange={(event) => setBootstrapToken(event.target.value)} autoComplete="off" required /></label>}
          <label htmlFor="admin-password">管理员密码</label>
          <input
            id="admin-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            minLength={setupRequired ? 6 : undefined}
            required
          />
          {setupRequired && <small>管理员密码至少 6 位</small>}
          <button type="submit" disabled={loading}>{setupRequired ? "完成初始化" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
