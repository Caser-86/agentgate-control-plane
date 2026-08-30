export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type ActionStatus =
  | "proposed"
  | "auto_approved"
  | "pending_approval"
  | "approved"
  | "denied"
  | "running"
  | "succeeded"
  | "failed"
  | "expired";

export type RiskLevel = "low" | "medium" | "high";
export type PolicyDecision = "auto_approve" | "require_approval" | "deny";
export type JsonObject = Record<string, unknown>;

export interface AgentRun {
  id: string;
  user_request: string;
  status: RunStatus;
  provider: string;
  model: string;
  step_count: number;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

export interface ToolAction {
  id: string;
  run_id: string;
  tool_call_id: string;
  tool_name: string;
  risk_level: RiskLevel;
  policy_decision: PolicyDecision;
  status: ActionStatus;
  arguments: JsonObject;
  result: unknown;
  reason: string;
  created_at: string;
  decided_at: string | null;
  executed_at: string | null;
}

export interface AuditEvent {
  id: string;
  run_id: string;
  action_id: string | null;
  event_type: string;
  actor: string;
  payload: unknown;
  created_at: string;
}

export interface RunDetail extends AgentRun {
  actions: ToolAction[];
  audit_events: AuditEvent[];
  final_text: string | null;
}

export interface PolicyView {
  name: string;
  description: string;
  risk_level: RiskLevel;
  read_only: boolean;
  decision: PolicyDecision;
  reason: string;
}

export interface RunEvent {
  id: number;
  event_type: string;
  payload: JsonObject;
}

export interface CreateRunRequest {
  user_request: string;
}

export interface ApprovalRequest {
  actor?: string;
  note?: string;
}

export interface AuditFilters {
  run_id?: string;
  event_type?: string;
  actor?: string;
}

export interface ApiMeta {
  provider: string;
  model: string;
  status: string;
}
