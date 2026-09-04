import { afterEach, describe, expect, it, vi } from "vitest";
import { api, eventStreamUrl, localMonitorEndpoint, resolveApiBaseUrl } from "./client";

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
      expect.objectContaining({ code: "not_found", message: "请求的资源不存在。", status: 404 }),
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

  it("derives a loopback monitoring endpoint from the configured API port", () => {
    expect(localMonitorEndpoint("http://localhost:18230")).toBe(
      "http://127.0.0.1:18230/health",
    );
    expect(localMonitorEndpoint("")).toBe("http://127.0.0.1:8000/health");
  });

  it("reports a local service error when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.getRun("missing")).rejects.toEqual(
      expect.objectContaining({
        code: "service_unavailable",
        message: "无法连接本地 API，请确认服务已经启动。",
        status: 0,
      }),
    );
  });

  it("accepts empty 204 responses for revoke and logout operations", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(new Response(null, { status: 204 }))
        .mockResolvedValueOnce(new Response(null, { status: 204 })),
    );

    await expect(api.revokeClientToken("token-1")).resolves.toBeUndefined();
    await expect(api.logout()).resolves.toBeUndefined();
  });

  it("reads the secret-free platform health endpoint", async () => {
    const responseBody = {
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
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), { status: 200 }),
    ));

    await expect(api.getPlatformHealth()).resolves.toEqual(responseBody);
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/platform/health",
      expect.anything(),
    );
  });

  it("calls the Chinese monitoring API endpoints", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
        .mockResolvedValueOnce(new Response(JSON.stringify({ id: "target-1" }), { status: 201 }))
        .mockResolvedValueOnce(new Response(JSON.stringify({ task_id: "task-1" }), { status: 202 }))
        .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 })),
    );

    await api.listMonitorTargets();
    await api.createMonitorTarget({
      name: "本地 API",
      kind: "http",
      endpoint: "http://127.0.0.1:8000/health",
    });
    await api.probeMonitorTarget("target-1");
    await api.listMonitorEvents();

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/monitor/targets",
      expect.anything(),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/monitor/targets/target-1/probe",
      expect.objectContaining({ method: "POST" }),
    );
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
