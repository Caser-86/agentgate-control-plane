import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const pythonCommand = process.env.AGENTGATE_E2E_PYTHON ?? "python";
const pythonExecutable = pythonCommand.includes(" ") ? `"${pythonCommand}"` : pythonCommand;
const requestedApiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000");
const requestedWebPort = Number(process.env.AGENTGATE_E2E_WEB_PORT ?? "5173");
const projects = [
  {
    name: "approval-flow",
    spec: "approval-flow.spec.ts",
    apiPort: requestedApiPort,
    webPort: requestedWebPort,
  },
  {
    name: "auth-and-queue",
    spec: "auth-and-queue.spec.ts",
    apiPort: requestedApiPort + 1,
    webPort: requestedWebPort + 1,
  },
  {
    name: "security-demo",
    spec: "security-demo.spec.ts",
    apiPort: requestedApiPort + 2,
    webPort: requestedWebPort + 2,
  },
];

const serverState = projects.map((project) => {
  const directory = path.join(os.tmpdir(), `agentgate-e2e-task8-${project.name}-${project.apiPort}`);
  fs.mkdirSync(directory, { recursive: true });
  return {
    ...project,
    directory,
    database: path.join(directory, "agentgate.sqlite").replaceAll("\\", "/"),
    bootstrapToken: path.join(directory, "bootstrap-token"),
    workerReady: path.join(directory, "worker-ready"),
  };
});

const webServers = serverState.flatMap((project) => {
  const apiUrl = `http://127.0.0.1:${project.apiPort}`;
  const apiEnv = {
    ...process.env,
    AGENTGATE_LLM_PROVIDER: "mock",
    AGENTGATE_ENV: "test",
    AGENTGATE_AUTH_ENABLED: "true",
    AGENTGATE_DATABASE_URL: `sqlite:///${project.database}`,
    AGENTGATE_AUTH_BOOTSTRAP_TOKEN_FILE: project.bootstrapToken,
    AGENTGATE_WORKER_READY_FILE: project.workerReady,
    AGENTGATE_E2E_RESET_DATABASE: "true",
    AGENTGATE_API_PORT: String(project.apiPort),
    AGENTGATE_WEB_PORT: String(project.webPort),
  };
  return [
    {
      command: `${pythonExecutable} -m uvicorn app.main:app --host 127.0.0.1 --port ${project.apiPort}`,
      cwd: "../api",
      env: apiEnv,
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `${pythonExecutable} -m app.processes.control_worker`,
      cwd: "../api",
      env: apiEnv,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${project.webPort}`,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiUrl,
      },
      url: `http://127.0.0.1:${project.webPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ];
});

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "dot" : "list",
  globalSetup: "./e2e/global-setup.ts",
  projects: serverState.map((project) => ({
    name: project.name,
    testMatch: project.spec,
    use: {
      ...devices["Desktop Chrome"],
      baseURL: `http://127.0.0.1:${project.webPort}`,
      trace: "on-first-retry" as const,
      viewport: { width: 1440, height: 900 },
    },
  })),
  webServer: webServers,
});
