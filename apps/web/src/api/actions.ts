import { api } from "./client";
import type {
  ActionListFilters,
  ExternalActionStatus,
  ToolAction,
} from "../types";

export interface SecurityDemoSession {
  clientTokenId: string;
  clientToken: string;
  protected: ExternalActionStatus;
  ordinary: ExternalActionStatus;
}

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
  return `web-demo-${label}-${random}`;
}

export async function runSecurityDemo(
  workspaceId: string,
  ordinaryPath = "demo.txt",
): Promise<SecurityDemoSession> {
  const client = await api.createClientToken({
    name: "安全演示临时令牌",
    scopes: ["propose:actions"],
    expires_in_seconds: 600,
  });
  try {
    const protectedAction = await api.submitExternalAction(
      client.token,
      {
        action: "file.quarantine.v1",
        workspace_id: workspaceId,
        relative_path: ".env",
        reason: "验证受保护文件不会被误删或移动",
      },
      idempotencyKey("protected"),
    );
    const ordinaryAction = await api.submitExternalAction(
      client.token,
      {
        action: "file.quarantine.v1",
        workspace_id: workspaceId,
        relative_path: ordinaryPath,
        reason: "演示审批后隔离普通文件",
      },
      idempotencyKey("ordinary"),
    );
    return {
      clientTokenId: client.id,
      clientToken: client.token,
      protected: protectedAction,
      ordinary: ordinaryAction,
    };
  } catch (error) {
    await api.revokeClientToken(client.id).catch(() => undefined);
    throw error;
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

export async function approveAndWait(
  token: string,
  action: ToolAction,
): Promise<ExternalActionStatus> {
  await approveAction(action.id);
  return waitForAction(token, action.id);
}

export async function restoreAndWait(
  token: string,
  workspaceId: string,
  quarantineEntryId: string,
): Promise<ExternalActionStatus> {
  const restore = await api.submitExternalAction(
    token,
    {
      action: "file.restore.v1",
      workspace_id: workspaceId,
      quarantine_entry_id: quarantineEntryId,
    },
    idempotencyKey("restore"),
  );
  if (restore.status === "pending_approval") await approveAction(restore.id);
  return waitForAction(token, restore.id);
}
