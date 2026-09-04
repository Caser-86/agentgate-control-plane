import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SecurityDemoPage } from "./SecurityDemoPage";

vi.mock("../api/workspaces", () => ({
  listWorkspaces: vi.fn().mockResolvedValue([
    {
      id: "workspace-1",
      name: "面试演示工作区",
      root_path: "C:\\AgentGate\\workspaces\\demo",
      quarantine_root_path: "C:\\AgentGate\\.agentgate-quarantine\\workspace-1",
      protected_patterns: [".env", "*.pem"],
      enabled: true,
      version: 1,
    },
  ]),
}));

vi.mock("../api/actions", () => ({
  runSecurityDemo: vi.fn().mockResolvedValue({
    protected: { status: "denied", reason: "目标路径受保护，文件未执行任何变化" },
    ordinary: { status: "pending_approval", id: "action-1" },
  }),
}));

describe("SecurityDemoPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the protected-file denial as a visible no-side-effect conclusion", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SecurityDemoPage /></MemoryRouter>);

    await user.click(await screen.findByRole("button", { name: "开始安全演示" }));

    expect(await screen.findByText("已拒绝，文件未执行任何变化")).toBeVisible();
    expect(screen.getByText(/真实策略结论/)).toBeVisible();
    expect(screen.getByText("待审批")).toBeVisible();
  });
});
