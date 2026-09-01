import { describe, expect, it } from "vitest";
import { resolveApiBaseUrl } from "./resolve-api-base-url";

describe("Vite API base URL", () => {
  it.each(["", "   ", "\t\n"]) (
    "uses the localhost fallback for blank build-time URL %j",
    (apiBaseUrl) => expect(resolveApiBaseUrl(apiBaseUrl, "8000")).toBe("http://localhost:8000"),
  );

  it.each(["https://example.com", "http://localhost:8000/api", "http://localhost:8000/?x=1"])(
    "rejects unsafe build-time URL %s",
    (apiBaseUrl) => expect(() => resolveApiBaseUrl(apiBaseUrl, "8000")).toThrow(),
  );
});
