import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalsPage } from "./ApprovalsPage";

vi.mock("../api/actions", () => ({
  listApprovals: vi.fn().mockResolvedValue([
    {
      id: "action-1",
      run_id: null,
      tool_call_id: "external:1",
      tool_name: "file.quarantine.v1",
      risk_level: "medium",
      policy_decision: "require_approval",
      status: "pending_approval",
      arguments: { relative_path: "notes.txt" },
      result: null,
      reason: "该文件动作需要人工审批",
      created_at: "2026-09-04T01:00:00Z",
      decided_at: null,
      executed_at: null,
    },
  ]),
  approveAction: vi.fn(),
  denyAction: vi.fn(),
}));

describe("ApprovalsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("keeps approve disabled while Worker is not online", async () => {
    render(<ApprovalsPage />);

    const approve = await screen.findByRole("button", { name: "批准并执行 ↗" });
    expect(approve).toBeDisabled();
    expect(screen.getByText("Worker 正在检查，批准不会执行文件操作；请先启动本机 Worker。")).toBeVisible();
  });
});
