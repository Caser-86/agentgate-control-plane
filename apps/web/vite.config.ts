import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { configDefaults } from "vitest/config";
import { resolveApiBaseUrl } from "./src/api/resolve-api-base-url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiPort = env.AGENTGATE_API_PORT ?? "8000";
  const apiBaseUrl = resolveApiBaseUrl(env.VITE_API_BASE_URL, apiPort);
  return {
  plugins: [react()],
  define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify(apiBaseUrl) },
  server: {
    port: Number(env.AGENTGATE_WEB_PORT ?? "5173"),
    proxy: {
      "/api": `http://127.0.0.1:${apiPort}`,
      "/health": `http://127.0.0.1:${apiPort}`,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
  };
});
