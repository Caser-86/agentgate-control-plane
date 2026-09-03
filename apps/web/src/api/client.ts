import type {
  AgentRun,
  ApiMeta,
  ApprovalRequest,
  AuditEvent,
  AuditFilters,
  CreateMonitorTargetRequest,
  CreateRunRequest,
  MonitorEvent,
  MonitorTarget,
  PolicyView,
  RunDetail,
  ToolAction,
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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    const code = response.status === 401
      ? "authentication_required"
      : response.status === 422
        ? "validation_error"
        : body?.error?.code ?? "http_error";
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("agentgate:session-expired"));
    }
    throw new ApiError(
      code,
      "Request failed",
      response.status,
    );
  }
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
};
