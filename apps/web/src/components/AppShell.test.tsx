import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api/client";
import { AppShell } from "./AppShell";

vi.mock("../api/client", () => ({
  api: {
    getMeta: vi.fn(),
    getPlatformHealth: vi.fn(),
  },
}));

const meta = {
  provider: "mock",
  model: "mock-model",
  api_base_url: "http://127.0.0.1:8000",
  status: "ok",
};

function health(status: "ok" | "degraded") {
  return {
    status,
    checks: {
      worker: {
        status,
        code: status === "ok" ? "worker_heartbeat_recent" : "worker_heartbeat_missing_or_stale",
        message_zh: status === "ok" ? "Worker 心跳正常" : "Worker 心跳缺失或过期",
        observed_at: "2026-09-04T00:00:00+00:00",
        details: {},
      },
    },
  };
}

describe("AppShell Worker 状态", () => {
  beforeEach(() => {
    vi.mocked(api.getMeta).mockResolvedValue(meta);
    vi.mocked(api.getPlatformHealth).mockResolvedValue(health("ok"));
  });

  it("displays an online Worker when its heartbeat is recent", async () => {
    render(<MemoryRouter><AppShell /></MemoryRouter>);

    expect(await screen.findByTestId("worker-health")).toHaveTextContent("在线");
  });

  it("displays a degraded Worker when its heartbeat is missing or stale", async () => {
    vi.mocked(api.getPlatformHealth).mockResolvedValue(health("degraded"));
    render(<MemoryRouter><AppShell /></MemoryRouter>);

    expect(await screen.findByTestId("worker-health")).toHaveTextContent("需要检查");
  });

  it("displays an unavailable Worker when the health request fails", async () => {
    vi.mocked(api.getPlatformHealth).mockRejectedValue(new Error("offline"));
    render(<MemoryRouter><AppShell /></MemoryRouter>);

    expect(await screen.findByTestId("worker-health")).toHaveTextContent("不可用");
  });
});
