import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.AGENTGATE_E2E_API_PORT ?? "8000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const pythonCommand = process.env.AGENTGATE_E2E_PYTHON ?? "python";
const pythonExecutable = pythonCommand.includes(" ") ? `"${pythonCommand}"` : pythonCommand;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "dot" : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    viewport: { width: 1440, height: 900 },
  },
  webServer: [
    {
      command: `${pythonExecutable} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../api",
      env: {
        ...process.env,
        AGENTGATE_LLM_PROVIDER: "mock",
        AGENTGATE_DATABASE_URL: "sqlite://",
        AGENTGATE_WEB_ORIGIN: "http://127.0.0.1:5173",
      },
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiUrl,
      },
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
