import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  setCsrfToken: vi.fn(),
  api: {
    authStatus: vi.fn().mockResolvedValue({ authenticated: true, setup_required: false }),
    csrf: vi.fn().mockResolvedValue({ csrf_token: "csrf-placeholder" }),
    setCsrfToken: vi.fn(),
    getMeta: vi.fn().mockResolvedValue({ provider: "mock", model: "mock-operations-agent", status: "ok" }),
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
    expect(screen.getByText("本地演示")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /运行/ })).toBeInTheDocument();
    expect(await screen.findByText("mock")).toBeInTheDocument();
  });
});
