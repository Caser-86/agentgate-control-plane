import { afterEach, describe, expect, it, vi } from "vitest";
import { api, eventStreamUrl, resolveApiBaseUrl } from "./client";

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
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/runs/missing",
      expect.anything(),
    );
  });

  it("builds a cursor-based event stream URL without relying on EventSource headers", () => {
    expect(eventStreamUrl("run/a", 42)).toBe(
      "http://localhost:8000/api/runs/run%2Fa/events?after=42",
    );
  });

  it("uses the configured alternate API port rather than a stale default", () => {
    const runtimeConfig = { apiBaseUrl: "http://localhost:18000" };
    expect(resolveApiBaseUrl(runtimeConfig)).toBe("http://localhost:18000");
    expect(resolveApiBaseUrl(runtimeConfig)).not.toBe("http://localhost:8000");
  });

  it("treats whitespace-only runtime API configuration as same-origin", () => {
    expect(resolveApiBaseUrl({ apiBaseUrl: "   \t\n" })).toBe("");
  });

  it.each([
    "https://example.com",
    "http://user:pass@localhost:8000",
    "http://localhost:8000/api",
    "http://localhost:8000/?debug=1",
  ])("rejects unsafe API base URL %s", (apiBaseUrl) => {
    expect(() => resolveApiBaseUrl({ apiBaseUrl })).toThrow();
  });

  it.each([
    ["http://localhost:18000", "http://localhost:18000"],
    ["https://127.0.0.1:18443", "https://127.0.0.1:18443"],
    ["http://[::1]:8000/", "http://[::1]:8000"],
  ])(
    "accepts loopback root URL %s",
    (apiBaseUrl, normalizedApiBaseUrl) => {
      expect(resolveApiBaseUrl({ apiBaseUrl })).toBe(normalizedApiBaseUrl);
    },
  );
});
