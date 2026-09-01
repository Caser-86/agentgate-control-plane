import { validateApiBaseUrl } from "./validate-api-base-url";

export function resolveApiBaseUrl(apiBaseUrl: string | undefined, apiPort: string): string {
  const configuredUrl = apiBaseUrl?.trim();
  return validateApiBaseUrl(configuredUrl || `http://localhost:${apiPort}`);
}
