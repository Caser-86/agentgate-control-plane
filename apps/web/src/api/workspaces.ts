import { api } from "./client";
import type { ManagedWorkspace, QuarantineEntry } from "../types";

export const listWorkspaces = (): Promise<ManagedWorkspace[]> => api.listWorkspaces();

export const createWorkspace = (input: {
  name: string;
  root_path: string;
  protected_patterns?: string[];
}): Promise<ManagedWorkspace> => api.createWorkspace(input);

export const updateWorkspace = (
  id: string,
  input: { name?: string; root_path?: string; protected_patterns?: string[]; enabled?: boolean },
): Promise<ManagedWorkspace> => api.updateWorkspace(id, input);

export const listQuarantineEntries = (
  id: string,
  status?: string,
): Promise<{ items: QuarantineEntry[] }> => api.listQuarantineEntries(id, status);
