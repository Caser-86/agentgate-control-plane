import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const apiPort = process.env.AGENTGATE_E2E_API_PORT ?? "8000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const pythonCommand = process.env.AGENTGATE_E2E_PYTHON ?? "python";
const pythonExecutable = pythonCommand.includes(" ") ? `"${pythonCommand}"` : pythonCommand;
const e2eState = path.join(os.tmpdir(), `agentgate-e2e-task8-${apiPort}`);
fs.mkdirSync(e2eState, { recursive: true });
const e2eDatabase = path.join(e2eState, "agentgate.sqlite").replaceAll("\\", "/");
const e2eBootstrapToken = path.join(e2eState, "bootstrap-token");
process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN_FILE = e2eBootstrapToken;
const e2eApiEnv = {
  ...process.env,
  AGENTGATE_LLM_PROVIDER: "mock",
  AGENTGATE_ENV: "test",
  AGENTGATE_DATABASE_URL: `sqlite:///${e2eDatabase}`,
  AGENTGATE_AUTH_BOOTSTRAP_TOKEN_FILE: e2eBootstrapToken,
  AGENTGATE_WEB_ORIGIN: "http://127.0.0.1:5173",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
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
      env: e2eApiEnv,
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `${pythonExecutable} -m app.processes.control_worker`,
      cwd: "../api",
      env: e2eApiEnv,
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
