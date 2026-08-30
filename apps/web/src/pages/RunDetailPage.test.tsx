import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { RunDetailPage } from "./RunDetailPage";

vi.mock("../api/client", () => ({
  apiBaseUrl: "http://localhost:8000",
  api: {
    getRun: vi.fn(),
    approveAction: vi.fn(),
    denyAction: vi.fn(),
  },
}));

describe("RunDetailPage", () => {
  it("renders the timeline and never exposes a raw API key", async () => {
    vi.mocked(api.getRun).mockResolvedValue({
      id: "run-1",
      user_request: "Inspect safely",
      status: "completed",
      provider: "mock",
      model: "mock-operations-agent",
      step_count: 1,
      created_at: "2026-08-31T00:00:00Z",
      updated_at: "2026-08-31T00:00:00Z",
      error_message: null,
      final_text: "Completed safely.",
      actions: [
        {
          id: "action-1",
          run_id: "run-1",
          tool_call_id: "call-1",
          tool_name: "get_service_health",
          risk_level: "low",
          policy_decision: "auto_approve",
          status: "succeeded",
          arguments: { api_key: "***REDACTED***", service: "payments-api" },
          result: { health: "healthy" },
          reason: "Read-only action.",
          created_at: "2026-08-31T00:00:00Z",
          decided_at: null,
          executed_at: "2026-08-31T00:00:01Z",
        },
      ],
      audit_events: [],
    });
    vi.stubGlobal("EventSource", class {
      close() {}
      addEventListener() {}
      onerror = null;
    });

    render(
      <MemoryRouter initialEntries={["/runs/run-1"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Completed safely.")).toBeInTheDocument();
    expect(screen.getByText("get_service_health")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});
