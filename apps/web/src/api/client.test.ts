import { afterEach, describe, expect, it, vi } from "vitest";
import { api, eventStreamUrl } from "./client";

describe("api client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("turns an API error envelope into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "not_found", message: "run was not found" } }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.getRun("missing")).rejects.toEqual(
      expect.objectContaining({ code: "not_found", message: "Request failed", status: 404 }),
    );
  });

  it("builds a cursor-based event stream URL without relying on EventSource headers", () => {
    expect(eventStreamUrl("run/a", 42)).toBe(
      "http://localhost:8000/api/runs/run%2Fa/events?after=42",
    );
  });
});
