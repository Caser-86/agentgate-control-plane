import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
    expect(screen.getByText("Local Demo")).toBeInTheDocument();
  });
});
