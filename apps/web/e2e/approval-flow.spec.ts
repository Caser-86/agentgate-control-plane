import { expect, test } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

function bootstrapToken(projectName: string): string {
  const configured = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
  if (configured) return configured.trim();
  const apiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000");
  const tokenFile = path.join(os.tmpdir(), `agentgate-e2e-task8-${projectName}-${apiPort}`, "bootstrap-token");
  if (!fs.existsSync(tokenFile)) {
    throw new Error(`E2E bootstrap token is missing: set AGENTGATE_E2E_BOOTSTRAP_TOKEN or provide ${tokenFile}`);
  }
  return fs.readFileSync(tokenFile, "utf8").trim();
}

async function login(page: import("@playwright/test").Page, projectName: string): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: "引导令牌" }).fill(bootstrapToken(projectName));
  await page.getByLabel("管理员密码").fill("fake-e2e-password");
  await page.getByRole("button", { name: "完成初始化", exact: true }).click();
}

async function hasRecordedRunStatus(page: import("@playwright/test").Page, runId: string, status: string): Promise<boolean> {
  const apiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000");
  let cursor = 0;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    let response;
    try {
      response = await page.request.get(`http://127.0.0.1:${apiPort}/api/runs/${runId}/events?after=${cursor}&limit=1`, { timeout: 1_000 });
    } catch {
      return false;
    }
    if (!response.ok()) throw new Error(`run events request failed: ${response.status()}`);
    const frame = await response.text();
    const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
    if (frame.includes("event: run.updated") && dataLine && (JSON.parse(dataLine.slice(6)) as { status?: string }).status === status) return true;
    const nextCursor = Number(frame.match(/^id: (\d+)$/m)?.[1]);
    if (!Number.isSafeInteger(nextCursor) || nextCursor <= cursor) return false;
    cursor = nextCursor;
  }
  return false;
}

test("拒绝降级服务恢复并保留可审计记录", async ({ page, browser }, testInfo) => {
  await login(page, testInfo.project.name);
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  const runCreated = page.waitForResponse((response) => response.url().endsWith("/api/runs") && response.request().method() === "POST");
  await page.getByTestId("start-run").click();
  const createdRun = await (await runCreated).json() as { id: string; status: string };
  expect(createdRun.status).toBe("queued");

  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect.poll(() => hasRecordedRunStatus(page, createdRun.id, "running"), { timeout: 15_000, intervals: [100, 250, 500] }).toBe(true);
  await page.reload();
  await expect(page.getByTestId("run-status")).toContainText("Waiting approval");
  await expect(page.getByTestId("approval-card")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("approval-card")).toContainText("需要人工审批");
  const approval = page.getByTestId("approval-card");
  await expect(approval).toBeVisible();
  await expect(page.locator('[data-testid="action-status"] .status-pending-approval')).toBeVisible();
  await expect(approval.locator(".status-medium")).toBeVisible();
  await expect(approval.locator("pre")).toContainText('"service": "payments-api"');
  if (process.env.AGENTGATE_CAPTURE_SCREENSHOT === "1") {
    await page.screenshot({ path: "../../docs/assets/local-demo.png", fullPage: true });
  }

  const waitingBody = await page.locator("body").innerText();
  expect(waitingBody).not.toContain("api_key");

  await expect(approval.getByRole("button", { name: "拒绝", exact: true })).toBeVisible();
  await approval.getByTestId("approval-deny").click();
  await expect(page.locator('[data-testid="action-status"] .status-denied')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "审计", exact: true })).toBeVisible();
  await page.locator(".filter-bar input").first().fill(runId ?? "");
  await page.locator(".filter-bar button").click();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();

  const auditBody = await page.locator("body").innerText();
  expect(auditBody).not.toContain("api_key");
  expect(auditBody).not.toContain("Bearer ");

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobilePage.goto("http://127.0.0.1:5173/");
  await expect(mobilePage.getByRole("heading", { name: "运行", exact: true })).toBeVisible();
  const dimensions = await mobilePage.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  await mobilePage.close();
});
