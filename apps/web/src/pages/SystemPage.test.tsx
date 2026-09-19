import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SystemPage } from "./SystemPage";

vi.mock("../api/client", () => ({
  api: {
    getPlatformHealth: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <SystemPage />
    </MemoryRouter>,
  );
}

describe("SystemPage", () => {
  beforeEach(() => {
    vi.mocked(api.getPlatformHealth).mockResolvedValue({
      status: "ok",
      checks: {
        api: {
          status: "ok",
          code: "api_ready",
          message_zh: "API 正常",
          observed_at: "2026-09-12T00:00:00Z",
          details: {},
        },
        database: {
          status: "ok",
          code: "database_ready",
          message_zh: "数据库正常",
          observed_at: "2026-09-12T00:00:00Z",
          details: {},
        },
        worker: {
          status: "ok",
          code: "worker_heartbeat_recent",
          message_zh: "Worker 心跳正常",
          observed_at: "2026-09-12T00:00:00Z",
          details: {
            age_seconds: 3,
            execution_status: "ready",
            pending_report_count: 0,
          },
        },
      },
    });
  });

  it("shows platform checks and safe Worker details", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "系统" })).toBeInTheDocument();
    expect(await screen.findByText("API 正常")).toBeInTheDocument();
    expect(screen.getByText("数据库正常")).toBeInTheDocument();
    expect(screen.getByText("Worker 心跳正常")).toBeInTheDocument();
    expect(screen.getAllByText("运行正常")).toHaveLength(3);
    expect(screen.getByText("待上报 0 条")).toBeInTheDocument();
    expect(screen.getByText("最近心跳 3 秒前")).toBeInTheDocument();
  });

  it("makes reconciliation and blocked execution visible", async () => {
    vi.mocked(api.getPlatformHealth).mockResolvedValueOnce({
      status: "degraded",
      checks: {
        worker: {
          status: "degraded",
          code: "worker_reconciliation_required",
          message_zh: "Worker 需要对账后才能继续执行",
          observed_at: "2026-09-12T00:00:00Z",
          details: {
            age_seconds: 12,
            execution_status: "reconciliation_required",
            pending_report_count: 2,
            last_error_code: "result_replay_conflict",
          },
        },
      },
    });
    renderPage();

    expect(await screen.findByText("Worker 需要对账后才能继续执行")).toBeInTheDocument();
    expect(screen.getByText("待上报 2 条")).toBeInTheDocument();
    expect(screen.getByText("需要对账")).toBeInTheDocument();
    expect(screen.getByText("result_replay_conflict")).toBeInTheDocument();
  });

  it("reports a readable error when health cannot be loaded", async () => {
    vi.mocked(api.getPlatformHealth).mockRejectedValueOnce(new Error("service unavailable"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("运行状态读取失败：请确认本地 API 已启动。");
  });
});
