import { api } from "./client";
import type {
  ActionListFilters,
  ExternalActionRequest,
  ExternalActionStatus,
  ToolAction,
} from "../types";

export type FileActionKind = "inspect" | "quarantine" | "restore";

export const listActions = (filters: ActionListFilters = {}): Promise<ToolAction[]> =>
  api.listActions(filters);

export const getAction = (id: string): Promise<ToolAction> => api.getAction(id);

export const listApprovals = (): Promise<ToolAction[]> => api.listApprovals();

export const approveAction = (id: string, note?: string): Promise<ToolAction> =>
  api.approveAction(id, note ? { note } : {});

export const denyAction = (id: string, note?: string): Promise<ToolAction> =>
  api.denyAction(id, note ? { note } : {});

function idempotencyKey(label: string): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-file-action-${label}-${random}`;
}

function externalRequest(
  workspaceId: string,
  kind: FileActionKind,
  relativePath?: string,
  quarantineEntryId?: string,
  reason?: string,
): ExternalActionRequest {
  const action = `file.${kind}.v1` as ExternalActionRequest["action"];
  return {
    action,
    workspace_id: workspaceId,
    ...(relativePath ? { relative_path: relativePath } : {}),
    ...(quarantineEntryId ? { quarantine_entry_id: quarantineEntryId } : {}),
    ...(reason ? { reason } : {}),
  };
}

export async function submitFileAction(
  workspaceId: string,
  kind: FileActionKind,
  relativePath?: string,
  quarantineEntryId?: string,
  reason?: string,
): Promise<ExternalActionStatus> {
  const client = await api.createClientToken({
    name: "文件治理临时令牌",
    scopes: ["propose:actions"],
    expires_in_seconds: 600,
  });
  try {
    const submitted = await api.submitExternalAction(
      client.token,
      externalRequest(workspaceId, kind, relativePath, quarantineEntryId, reason),
      idempotencyKey(kind),
    );
    return waitForAction(client.token, submitted.id);
  } finally {
    await api.revokeClientToken(client.id).catch(() => undefined);
  }
}

export async function waitForAction(
  token: string,
  actionId: string,
  timeoutMs = 15_000,
): Promise<ExternalActionStatus> {
  const deadline = Date.now() + timeoutMs;
  let latest = await api.getExternalActionStatus(token, actionId);
  while (["queued", "approved", "running", "auto_approved"].includes(latest.status) && Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    latest = await api.getExternalActionStatus(token, actionId);
  }
  return latest;
}
