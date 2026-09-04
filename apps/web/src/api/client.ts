import type {
  AgentRun,
  ApiMeta,
  ApprovalRequest,
  AuditEvent,
  AuditFilters,
  CreateMonitorTargetRequest,
  CreateRunRequest,
  ActionListFilters,
  ClientTokenCreated,
  ExternalActionRequest,
  ExternalActionStatus,
  MonitorEvent,
  MonitorTarget,
  PlatformHealth,
  PolicyView,
  RunDetail,
  ToolAction,
  ManagedWorkspace,
  QuarantineEntry,
} from "../types";
import { validateApiBaseUrl } from "./validate-api-base-url";

export type RuntimeConfig = { apiBaseUrl?: string };

export function resolveApiBaseUrl(runtimeConfig?: RuntimeConfig): string {
  const configured = (runtimeConfig?.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? "").trim();
  return configured ? validateApiBaseUrl(configured) : "";
}

const API_BASE_URL = resolveApiBaseUrl(
  typeof window === "undefined" ? undefined : window.__AGENTGATE_CONFIG__,
);
export const apiBaseUrl = API_BASE_URL;

export function localMonitorEndpoint(baseUrl: string): string {
  if (!baseUrl.trim()) return "http://127.0.0.1:8000/health";
  const parsed = new URL(validateApiBaseUrl(baseUrl));
  parsed.hostname = "127.0.0.1";
  parsed.pathname = "/health";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString();
}

export function eventStreamUrl(runId: string, after: number): string {
  const params = new URLSearchParams({ after: String(Math.max(after, 0)) });
  return `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/events?${params}`;
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const method = (init?.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(
      "service_unavailable",
      "无法连接本地 API，请确认服务已经启动。",
      0,
    );
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    const code = response.status === 401
      ? body?.error?.code ?? "authentication_required"
      : response.status === 422
        ? "validation_error"
        : response.status >= 500
          ? "server_error"
          : body?.error?.code ?? "http_error";
    const messages: Record<string, string> = {
      authentication_required: "需要登录或当前会话已失效。",
      operator_required: "该请求需要管理员身份。",
      csrf_validation_failed: "安全校验失败，请刷新页面后重试。",
      invalid_credentials: "管理员密码不正确，请检查后重试。",
      invalid_or_expired_bootstrap_token: "引导令牌无效或已过期，请重新获取。",
      setup_already_completed: "管理员初始化已经完成，请直接登录。",
      not_found: "请求的资源不存在。",
      invalid_target: "监控目标配置不合法，请检查地址和参数。",
      validation_error: "输入参数不正确，请检查后重试。",
      server_error: "本地服务处理失败，请稍后重试。",
      http_error: "请求失败，请稍后重试。",
    };
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("agentgate:session-expired"));
    }
    throw new ApiError(
      code,
      messages[code] ?? body?.error?.message ?? "请求失败，请稍后重试。",
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function queryString(filters: AuditFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function actionQueryString(filters: ActionListFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.risk_level) params.set("risk_level", filters.risk_level);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const api = {
  authStatus(): Promise<{ authenticated: boolean; setup_required: boolean }> {
    return request("/api/auth/status");
  },
  csrf(): Promise<{ csrf_token: string }> {
    return request("/api/auth/csrf");
  },
  setup(input: { bootstrap_token: string; password: string }): Promise<{ authenticated: boolean }> {
    return request("/api/auth/setup", { method: "POST", body: JSON.stringify(input) });
  },
  login(input: { password: string }): Promise<{ authenticated: boolean }> {
    return request("/api/auth/login", { method: "POST", body: JSON.stringify(input) });
  },
  logout(): Promise<void> {
    return request("/api/auth/logout", { method: "POST" });
  },
  createRun(input: CreateRunRequest): Promise<AgentRun> {
    return request<AgentRun>("/api/runs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  listRuns(): Promise<AgentRun[]> {
    return request<AgentRun[]>("/api/runs");
  },
  getRun(id: string): Promise<RunDetail> {
    return request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`);
  },
  approveAction(id: string, input: ApprovalRequest): Promise<ToolAction> {
    return request<ToolAction>(`/api/approvals/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  denyAction(id: string, input: ApprovalRequest): Promise<ToolAction> {
    return request<ToolAction>(`/api/approvals/${encodeURIComponent(id)}/deny`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  listPolicies(): Promise<PolicyView[]> {
    return request<PolicyView[]>("/api/policies");
  },
  listAudit(filters: AuditFilters): Promise<AuditEvent[]> {
    return request<AuditEvent[]>(`/api/audit${queryString(filters)}`);
  },
  auditExportUrl(filters: AuditFilters): string {
    return `${API_BASE_URL}/api/audit/export${queryString(filters)}`;
  },
  getMeta(): Promise<ApiMeta> {
    return request<ApiMeta>("/api/meta");
  },
  listActions(filters: ActionListFilters = {}): Promise<ToolAction[]> {
    return request<ToolAction[]>(`/api/actions${actionQueryString(filters)}`);
  },
  getAction(id: string): Promise<ToolAction> {
    return request<ToolAction>(`/api/actions/${encodeURIComponent(id)}`);
  },
  listApprovals(): Promise<ToolAction[]> {
    return request<ToolAction[]>("/api/approvals");
  },
  createClientToken(input: { name: string; scopes: string[]; expires_in_seconds?: number }): Promise<ClientTokenCreated> {
    return request<ClientTokenCreated>("/api/auth/tokens", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  revokeClientToken(id: string): Promise<void> {
    return request<void>(`/api/auth/tokens/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
  submitExternalAction(
    token: string,
    input: ExternalActionRequest,
    idempotencyKey: string,
  ): Promise<ExternalActionStatus> {
    return request<ExternalActionStatus>("/api/v1/actions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(input),
    });
  },
  getExternalActionStatus(token: string, id: string): Promise<ExternalActionStatus> {
    return request<ExternalActionStatus>(`/api/v1/actions/${encodeURIComponent(id)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
  getPlatformHealth(): Promise<PlatformHealth> {
    return request<PlatformHealth>("/api/platform/health");
  },
  listMonitorTargets(): Promise<MonitorTarget[]> {
    return request<MonitorTarget[]>("/api/monitor/targets");
  },
  createMonitorTarget(input: CreateMonitorTargetRequest): Promise<MonitorTarget> {
    return request<MonitorTarget>("/api/monitor/targets", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  probeMonitorTarget(id: string): Promise<{ task_id: string; target_id: string; status: string }> {
    return request(`/api/monitor/targets/${encodeURIComponent(id)}/probe`, { method: "POST" });
  },
  listMonitorEvents(): Promise<MonitorEvent[]> {
    return request<MonitorEvent[]>("/api/monitor/events");
  },
  listWorkspaces(): Promise<ManagedWorkspace[]> {
    return request<ManagedWorkspace[]>("/api/v1/workspaces");
  },
  createWorkspace(input: { name: string; root_path: string; protected_patterns?: string[] }): Promise<ManagedWorkspace> {
    return request<ManagedWorkspace>("/api/v1/workspaces", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateWorkspace(id: string, input: { name?: string; root_path?: string; protected_patterns?: string[]; enabled?: boolean }): Promise<ManagedWorkspace> {
    return request<ManagedWorkspace>(`/api/v1/workspaces/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  listQuarantineEntries(id: string, status?: string): Promise<{ items: QuarantineEntry[] }> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ items: QuarantineEntry[] }>(`/api/v1/workspaces/${encodeURIComponent(id)}/quarantine${query}`);
  },
};
