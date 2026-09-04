import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FileGovernancePage } from "./FileGovernancePage";

vi.mock("../api/workspaces", () => ({
  listWorkspaces: vi.fn().mockResolvedValue([
    {
      id: "workspace-1",
      name: "源码工作区",
      root_path: "C:\\AgentGate\\workspaces\\source",
      quarantine_root_path: "C:\\AgentGate\\quarantine\\workspace-1",
      protected_patterns: [".env", "*.pem"],
      enabled: true,
      version: 1,
    },
  ]),
  listQuarantineEntries: vi.fn().mockResolvedValue({ items: [] }),
}));

vi.mock("../api/actions", () => ({
  submitFileAction: vi.fn().mockResolvedValue({
    id: "action-1",
    action: "file.inspect.v1",
    workspace_id: "workspace-1",
    relative_path: "README.md",
    quarantine_entry_id: null,
    decision: "auto_approve",
    status: "succeeded",
    reason: "只读检查可以自动执行",
    action_version: "file.inspect.v1",
    task_id: "task-1",
    approval_expires_at: null,
    created_at: "2026-09-04T01:00:00Z",
    result: { content_sha256: "a".repeat(64), side_effect: "none" },
  }),
}));

describe("FileGovernancePage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits an explicitly selected file action without demo copy", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><FileGovernancePage /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "文件治理" })).toBeVisible();
    expect(screen.queryByText(/演示|面试/)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("相对路径"), "README.md");
    await user.click(screen.getByRole("button", { name: "提交文件动作" }));

    expect(await screen.findByText("动作已提交")).toBeVisible();
    expect(screen.getByRole("heading", { name: "检查文件" })).toBeVisible();
  });
});
