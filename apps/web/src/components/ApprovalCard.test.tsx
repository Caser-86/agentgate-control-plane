import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { ToolAction } from "../types";
import { ApprovalCard } from "./ApprovalCard";

const action: ToolAction = {
  id: "action-1",
  run_id: "run-1",
  tool_call_id: "call-1",
  tool_name: "restart_service",
  risk_level: "medium",
  policy_decision: "require_approval",
  status: "pending_approval",
  arguments: { service: "payments-api", reason: "recover the degraded service" },
  result: null,
  reason: "Medium-risk actions require explicit human approval.",
  created_at: "2026-08-31T00:00:00Z",
  decided_at: null,
  executed_at: null,
};

describe("ApprovalCard", () => {
  it("shows the action context and disables both controls while deciding", async () => {
    const user = userEvent.setup();
    let resolveDecision: (() => void) | undefined;
    const onApprove = vi.fn(
      () => new Promise<void>((resolve) => (resolveDecision = resolve)),
    );

    render(<ApprovalCard action={action} onApprove={onApprove} onDeny={vi.fn()} />);
    expect(screen.getByText("restart_service")).toBeInTheDocument();
    expect(screen.getAllByText("中风险")).not.toHaveLength(0);
    expect(screen.getByText(/等待明确的人工作出批准/)).toBeInTheDocument();
    expect(screen.getByText("payments-api", { selector: "strong" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "批准" }));
    expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeDisabled();
    await act(async () => { resolveDecision?.(); });
  });

  it("explains a duplicate decision and refreshes the detail", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    const onApprove = vi.fn().mockRejectedValue(new ApiError("approval_conflict", "already decided", 409));

    render(
      <ApprovalCard
        action={action}
        onApprove={onApprove}
        onDeny={vi.fn()}
        onRefresh={onRefresh}
      />,
    );
    await user.click(screen.getByRole("button", { name: "批准" }));

    expect(await screen.findByText("该操作已经处理过")).toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("does not render an exception message that contains secret-like values", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalCard
        action={{ ...action, arguments: { "api-key": "fake-secret" } }}
        onApprove={vi.fn().mockRejectedValue(new Error("api-key=fake-secret"))}
        onDeny={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "批准" }));

    expect(await screen.findByText("无法保存审批决定")).toBeInTheDocument();
    expect(screen.queryByText("fake-secret")).not.toBeInTheDocument();
  });

  it("redacts camelCase and compound sensitive keys in the approval payload", () => {
    render(
      <ApprovalCard
        action={{
          ...action,
          arguments: {
            clientSecret: "fake-client-secret",
            accessToken: "fake-access-token",
            passwordHash: "fake-password-hash",
            "api-key": "fake-api-key",
          },
        }}
        onApprove={vi.fn()}
        onDeny={vi.fn()}
      />,
    );

    expect(screen.getByText(/clientSecret/)).toBeInTheDocument();
    expect(screen.queryByText("fake-client-secret")).not.toBeInTheDocument();
    expect(screen.queryByText("fake-access-token")).not.toBeInTheDocument();
    expect(screen.queryByText("fake-password-hash")).not.toBeInTheDocument();
    expect(screen.queryByText("fake-api-key")).not.toBeInTheDocument();
  });
});
