import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ActionsPage } from "./ActionsPage";

vi.mock("../api/actions", () => ({
  listActions: vi.fn().mockResolvedValue([
    {
      id: "action-1",
      run_id: null,
      tool_call_id: "external:1",
      tool_name: "file.quarantine.v1",
      risk_level: "medium",
      policy_decision: "require_approval",
      status: "pending_approval",
      arguments: { workspace_id: "workspace-1", relative_path: "notes.txt" },
      result: null,
      reason: "该文件动作需要人工审批",
      created_at: "2026-09-04T01:00:00Z",
      decided_at: null,
      executed_at: null,
    },
  ]),
}));

describe("ActionsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a Chinese action record with its relative target", async () => {
    render(<ActionsPage />);

    expect(await screen.findByRole("heading", { name: "动作" })).toBeVisible();
    expect(screen.getByText("隔离文件")).toBeVisible();
    expect(screen.getByText("notes.txt")).toBeVisible();
    expect(screen.getAllByText("待审批").some((element) => element.classList.contains("status-badge"))).toBe(true);
  });
});
