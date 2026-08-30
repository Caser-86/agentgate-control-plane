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
    expect(screen.getByText("Medium risk")).toBeInTheDocument();
    expect(screen.getByText(/explicit human approval/)).toBeInTheDocument();
    expect(screen.getByText("payments-api", { selector: "strong" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    await act(async () => { resolveDecision?.(); });
  });

  it("explains a duplicate decision and refreshes the detail", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    const onApprove = vi
      .fn()
      .mockRejectedValue(new ApiError("approval_conflict", "This action was already decided", 409));

    render(
      <ApprovalCard
        action={action}
        onApprove={onApprove}
        onDeny={vi.fn()}
        onRefresh={onRefresh}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("This action was already decided")).toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
