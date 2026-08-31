import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { parseRunEvent } from "../hooks/useRunEvents";
import { RunDetailPage } from "./RunDetailPage";

vi.mock("../api/client", () => ({
  apiBaseUrl: "http://localhost:8000",
  eventStreamUrl: (runId: string, after: number) =>
    `http://localhost:8000/api/runs/${runId}/events?after=${after}`,
  api: {
    getRun: vi.fn(),
    approveAction: vi.fn(),
    denyAction: vi.fn(),
  },
}));

describe("RunDetailPage", () => {
  it("shows safe Chinese loading and error copy without the underlying exception", async () => {
    vi.mocked(api.getRun).mockRejectedValue(new Error("secret backend token"));
    vi.stubGlobal("EventSource", class {
      close() {}
      addEventListener() {}
      onerror = null;
    });

    render(
      <MemoryRouter initialEntries={["/runs/run-error"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("正在加载运行详情…")).toBeInTheDocument();
    expect(await screen.findByText("运行暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("无法加载该运行详情，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByText("secret backend token")).not.toBeInTheDocument();
    expect(screen.queryByText("Run unavailable")).not.toBeInTheDocument();
  });

  it("ignores stale and malformed SSE frames before they can replace REST state", () => {
    expect(
      parseRunEvent({ lastEventId: "11", type: "run.updated", data: '{"status":"completed"}' } as MessageEvent<string>, 10),
    ).toEqual({ id: 11, event_type: "run.updated", payload: { status: "completed" } });
    expect(
      parseRunEvent({ lastEventId: "10", type: "run.updated", data: '{"status":"running"}' } as MessageEvent<string>, 10),
    ).toBeNull();
    expect(
      parseRunEvent({ lastEventId: "12", type: "run.updated", data: "not-json" } as MessageEvent<string>, 10),
    ).toBeNull();
  });

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
