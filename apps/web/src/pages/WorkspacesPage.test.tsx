import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspacesPage } from "./WorkspacesPage";

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
  listQuarantineEntries: vi.fn().mockResolvedValue({ items: [] }),
}));

describe("WorkspacesPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("explains that only relative paths are actionable", async () => {
    render(<WorkspacesPage />);

    expect(await screen.findByRole("heading", { name: "工作区" })).toBeVisible();
    expect(screen.getAllByText("面试演示工作区").length).toBeGreaterThan(0);
    expect(screen.getByText(/只显示给本地管理员/)).toBeVisible();
    expect(screen.getAllByText(".env").length).toBeGreaterThan(0);
  });
});
