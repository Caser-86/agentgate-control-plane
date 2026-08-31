import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, setCsrfToken } from "../api/client";

type AuthState = {
  authenticated: boolean;
  setupRequired: boolean;
  loading: boolean;
  sessionExpired: boolean;
  refresh(): Promise<void>;
  setup(bootstrapToken: string, password: string): Promise<void>;
  login(password: string): Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

async function loadCsrfToken(): Promise<void> {
  const response = await api.csrf();
  setCsrfToken(response.csrf_token);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await api.authStatus();
      setAuthenticated(status.authenticated);
      setSetupRequired(status.setup_required);
      setSessionExpired(false);
      if (status.authenticated) await loadCsrfToken();
      else setCsrfToken(null);
    } catch {
      setAuthenticated(false);
      setCsrfToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const markExpired = () => {
      setAuthenticated(false);
      setSessionExpired(true);
      setCsrfToken(null);
    };
    window.addEventListener("agentgate:session-expired", markExpired);
    return () => window.removeEventListener("agentgate:session-expired", markExpired);
  }, []);

  const value = useMemo<AuthState>(() => ({
    authenticated,
    setupRequired,
    loading,
    sessionExpired,
    refresh,
    async setup(bootstrapToken, password) {
      await api.setup({ bootstrap_token: bootstrapToken, password });
      await refresh();
    },
    async login(password) {
      await api.login({ password });
      await refresh();
    },
  }), [authenticated, loading, refresh, sessionExpired, setupRequired]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { authenticated, loading } = useAuth();
  if (loading) return <div role="status">正在验证会话…</div>;
  return authenticated ? <>{children}</> : <Navigate to="/login" replace />;
}
