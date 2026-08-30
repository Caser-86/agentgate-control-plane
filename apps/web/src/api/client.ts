import type {
  AgentRun,
  ApiMeta,
  ApprovalRequest,
  AuditEvent,
  AuditFilters,
  CreateRunRequest,
  PolicyView,
  RunDetail,
  ToolAction,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const apiBaseUrl = API_BASE_URL;

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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      body?.error?.code ?? "http_error",
      body?.error?.message ?? "Request failed",
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
};
