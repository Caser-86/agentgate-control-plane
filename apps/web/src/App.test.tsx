import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  setCsrfToken: vi.fn(),
  api: {
    authStatus: vi.fn().mockResolvedValue({ authenticated: true, setup_required: false }),
    csrf: vi.fn().mockResolvedValue({ csrf_token: "csrf-placeholder" }),
    setCsrfToken: vi.fn(),
    getMeta: vi.fn().mockResolvedValue({
      provider: "openai_compatible",
      model: "ark-code-latest",
      api_base_url: "http://localhost:18230",
      status: "ok",
    }),
    getPlatformHealth: vi.fn().mockResolvedValue({
      status: "ok",
      checks: {
        worker: {
          status: "ok",
          code: "worker_heartbeat_recent",
          message_zh: "Worker 心跳正常",
          observed_at: "2026-09-04T00:00:00+00:00",
          details: {},
        },
      },
    }),
    listRuns: vi.fn().mockResolvedValue([]),
  },
}));

describe("App", () => {
  afterEach(() => vi.restoreAllMocks());

  it("identifies the product as a local agent control plane after authentication", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ authenticated: true, setup_required: false })))
        .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "csrf-placeholder" }))),
    );
    render(<App />);
    expect(await screen.findByRole("heading", { name: "AgentGate" })).toBeInTheDocument();
    expect(screen.getByText("本机运行中")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /安全演示/ })).toBeInTheDocument();
    expect((await screen.findAllByText("openai_compatible")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("ark-code-latest")).length).toBeGreaterThan(0);
  });
});
