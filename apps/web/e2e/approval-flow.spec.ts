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
  const deadline = Date.now() + 15_000;
  let cursor = 0;
  const diagnostics: string[] = [];
  while (Date.now() < deadline) {
    const timeout = Math.max(1, Math.min(1_000, deadline - Date.now()));
    let response: Awaited<ReturnType<typeof page.request.get>>;
    try {
      response = await page.request.get(`http://127.0.0.1:${apiPort}/api/runs/${runId}/events?after=${cursor}&limit=1`, { timeout });
    } catch (error) {
      diagnostics.push(`request: ${error instanceof Error ? error.message : String(error)}`);
      await new Promise((resolve) => setTimeout(resolve, Math.min(100, Math.max(1, deadline - Date.now()))));
      continue;
    }
    if (!response.ok()) {
      diagnostics.push(`HTTP ${response.status()}`);
      await new Promise((resolve) => setTimeout(resolve, Math.min(100, Math.max(1, deadline - Date.now()))));
      continue;
    }
    const frame = await response.text();
    const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
    if (frame.includes("event: run.updated") && dataLine) {
      try {
        if ((JSON.parse(dataLine.slice(6)) as { status?: string }).status === status) return true;
      } catch (error) {
        diagnostics.push(`invalid event JSON: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    const nextCursor = Number(frame.match(/^id: (\d+)$/m)?.[1]);
    if (Number.isSafeInteger(nextCursor) && nextCursor > cursor) cursor = nextCursor;
    else diagnostics.push(frame.trim() ? "empty or non-advancing event frame" : "empty SSE response");
    await new Promise((resolve) => setTimeout(resolve, Math.min(100, Math.max(1, deadline - Date.now()))));
  }
  throw new Error(`timed out waiting for recorded run status ${status} for ${runId}; cursor=${cursor}; diagnostics=${diagnostics.slice(-5).join(" | ") || "none"}`);
}

test("拒绝降级服务恢复并保留可审计记录", async ({ page }, testInfo) => {
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
  await expect(page.getByTestId("run-status")).toContainText("等待审批");
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
  const denialResponse = page.waitForResponse((response) => response.url().includes("/api/approvals/") && response.url().endsWith("/deny") && response.request().method() === "POST");
  await approval.getByTestId("approval-deny").click();
  expect((await denialResponse).status()).toBe(200);
  await expect(page.locator('[data-testid="action-status"] .status-denied')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.locator(".action-row").filter({ hasText: "restart_service" }).locator("pre").last()).toContainText('"denied": true');

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

  const mobilePage = await page.context().newPage({ viewport: { width: 390, height: 844 } });
  await mobilePage.goto(new URL("/", page.url()).toString());
  await expect(mobilePage.getByRole("heading", { name: "运行", exact: true })).toBeVisible();
  const dimensions = await mobilePage.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  await mobilePage.close();
});
