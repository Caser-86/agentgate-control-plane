import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { RunsPage } from "./RunsPage";

vi.mock("../api/client", () => ({
  api: { listRuns: vi.fn(), createRun: vi.fn() },
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

describe("RunsPage", () => {
  beforeEach(() => {
    vi.mocked(api.listRuns).mockResolvedValue([]);
    vi.mocked(api.createRun).mockResolvedValue({
      id: "run-new",
      user_request: "Inspect payments-api",
      status: "queued",
      provider: "mock",
      model: "mock-operations-agent",
      step_count: 0,
      created_at: "2026-08-31T00:00:00Z",
      updated_at: "2026-08-31T00:00:00Z",
      error_message: null,
    });
  });

  it("submits a task and displays the created run", async () => {
    render(
      <MemoryRouter>
        <RunsPage />
      </MemoryRouter>,
    );
    const input = screen.getByTestId("run-request");
    fireEvent.change(input, { target: { value: "Inspect payments-api" } });
    fireEvent.click(screen.getByTestId("start-run"));

    await waitFor(() => expect(api.createRun).toHaveBeenCalledWith({ user_request: "Inspect payments-api" }));
    expect(await screen.findByRole("link", { name: /run-new/ })).toBeInTheDocument();
  });
});
