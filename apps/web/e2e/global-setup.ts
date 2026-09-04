import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export default async function globalSetup(): Promise<void> {
  const requestedApiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000");
  const projects = [
    { name: "approval-flow", apiPort: requestedApiPort },
    { name: "auth-and-queue", apiPort: requestedApiPort + 1 },
    { name: "security-demo", apiPort: requestedApiPort + 2 },
  ];
  for (const project of projects) {
    const readyFile = path.join(
      os.tmpdir(),
      `agentgate-e2e-task8-${project.name}-${project.apiPort}`,
      "worker-ready",
    );
    const deadline = Date.now() + 30_000;
    while (!fs.existsSync(readyFile) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (!fs.existsSync(readyFile)) {
      throw new Error(`control worker readiness check timed out for ${project.name}: ${readyFile}`);
    }
  }
}
