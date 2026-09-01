export function validateApiBaseUrl(apiBaseUrl: string): string {
  const parsed = new URL(apiBaseUrl);
  if (!["http:", "https:"].includes(parsed.protocol) ||
      !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname) ||
      parsed.username || parsed.password || parsed.search || parsed.hash ||
      !["", "/"].includes(parsed.pathname)) {
    throw new Error("API base URL must be a loopback HTTP(S) root URL without credentials or query parameters.");
  }
  return apiBaseUrl.replace(/\/+$/, "");
}
