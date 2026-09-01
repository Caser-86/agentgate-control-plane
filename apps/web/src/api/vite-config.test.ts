import { describe, expect, it } from "vitest";
import { validateApiBaseUrl } from "./validate-api-base-url";

describe("Vite API base URL", () => {
  it.each(["https://example.com", "http://localhost:8000/api", "http://localhost:8000/?x=1"])(
    "rejects unsafe build-time URL %s",
    (apiBaseUrl) => expect(() => validateApiBaseUrl(apiBaseUrl)).toThrow(),
  );
});
