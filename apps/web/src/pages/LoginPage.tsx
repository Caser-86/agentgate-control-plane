import { type FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export function LoginPage() {
  const { authenticated, setupRequired, sessionExpired, loading, login, refresh, setup } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [failed, setFailed] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailed(null);
    try {
      if (setupRequired) await setup(bootstrapToken, password);
      else await login(password);
      navigate("/", { replace: true });
    } catch (error) {
      setFailed(error instanceof Error && error.message ? error.message : "登录失败，请检查输入后重试。");
    }
  };

  if (!loading && authenticated) return <Navigate to="/" replace />;

  return (
    <main className="auth-page" aria-busy={loading}>
      <section className="panel auth-panel">
        <span className="eyebrow">AgentGate / 本地控制台</span>
        <h1>{setupRequired ? "初始化管理员密码" : "登录"}</h1>
        <p className="auth-intro">{setupRequired ? "使用一次性引导令牌创建唯一管理员。" : "请输入管理员密码以继续。"}</p>
        {sessionExpired && <p className="inline-error" role="alert">会话已过期，请重新登录后重试。</p>}
        {failed && <p className="inline-error" role="alert">{failed}</p>}
        {sessionExpired && <button className="button button-secondary" type="button" onClick={() => void refresh()}>重试</button>}
        <form onSubmit={(event) => void submit(event)}>
          {setupRequired && <label htmlFor="bootstrap-token">引导令牌<input id="bootstrap-token" name="bootstrap_token" value={bootstrapToken} onChange={(event) => setBootstrapToken(event.target.value)} autoComplete="off" required /></label>}
          <label htmlFor="admin-password">管理员密码</label>
          <input
            id="admin-password"
            name="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={setupRequired ? "new-password" : "current-password"}
            minLength={setupRequired ? 6 : undefined}
            required
          />
          {setupRequired && <small className="field-hint">管理员密码至少 6 位</small>}
          <button className="button button-primary" type="submit" disabled={loading}>{setupRequired ? "完成初始化" : "登录"}<span aria-hidden="true">↗</span></button>
        </form>
      </section>
    </main>
  );
}
