import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { TargetsPage } from "./TargetsPage";

vi.mock("../api/client", () => ({
  api: {
    listMonitorTargets: vi.fn(),
    createMonitorTarget: vi.fn(),
    probeMonitorTarget: vi.fn(),
  },
}));

const target = {
  id: "target-1",
  name: "本地 API",
  kind: "http" as const,
  endpoint: "http://127.0.0.1:8000/health",
  enabled: true,
  interval_seconds: 60,
  timeout_seconds: 5,
  failure_threshold: 3,
  recovery_threshold: 2,
  health: "unknown" as const,
  consecutive_failures: 0,
  consecutive_successes: 0,
  last_probe_status: null,
  last_probe_detail: null,
  last_latency_ms: null,
  last_probe_at: null,
  next_probe_at: "2026-09-03T00:00:00Z",
  created_at: "2026-09-03T00:00:00Z",
  updated_at: "2026-09-03T00:00:00Z",
  active_event: null,
};

describe("TargetsPage", () => {
  beforeEach(() => {
    vi.mocked(api.listMonitorTargets).mockResolvedValue([target]);
    vi.mocked(api.createMonitorTarget).mockResolvedValue(target);
    vi.mocked(api.probeMonitorTarget).mockResolvedValue({
      task_id: "task-1",
      target_id: target.id,
      status: "queued",
    });
  });

  it("shows a Chinese monitoring view and queues a manual probe", async () => {
    render(
      <MemoryRouter>
        <TargetsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "监控" })).toBeInTheDocument();
    expect(screen.getByText("本地 API")).toBeInTheDocument();
    expect(screen.getByText("未知")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "立即探测" }));
    await waitFor(() => expect(api.probeMonitorTarget).toHaveBeenCalledWith("target-1"));
  });
});
