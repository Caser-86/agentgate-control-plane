import { expect, test } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

function bootstrapToken(projectName: string): string {
  const configured = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
  if (configured) return configured.trim();
  const apiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000") + 1;
  const tokenFile = path.join(os.tmpdir(), `agentgate-e2e-task8-${projectName}-${apiPort}`, "bootstrap-token");
  if (!fs.existsSync(tokenFile)) {
    throw new Error(`E2E bootstrap token is missing: set AGENTGATE_E2E_BOOTSTRAP_TOKEN or provide ${tokenFile}`);
  }
  return fs.readFileSync(tokenFile, "utf8").trim();
}

test("中文首次登录、排队审批拒绝并在刷新后保留审计游标", async ({ page }, testInfo) => {
  await page.goto("/login");
  const setup = page.getByRole("heading", { name: "初始化管理员密码", exact: true });
  await expect(setup).toBeVisible();
  await page.getByRole("textbox", { name: "引导令牌" }).fill(bootstrapToken(testInfo.project.name));
  await page.getByLabel("管理员密码").fill("fake-e2e-password");
  await page.getByRole("button", { name: "完成初始化", exact: true }).click();
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  const runCreated = page.waitForResponse((response) => response.url().endsWith("/api/runs") && response.request().method() === "POST");
  await page.getByTestId("start-run").click();
  await expect((await runCreated).json()).resolves.toMatchObject({ status: "queued" });
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect(page.locator('[data-testid="run-status"]').first()).toBeVisible();
  await expect(page.locator('[data-testid="run-status"]').first()).toContainText(/Queued|Running|Waiting approval/);
  await expect.poll(async () => { await page.reload(); return page.getByTestId("approval-card").count(); }, { timeout: 15_000 }).toBe(1);
  await expect(page.getByTestId("approval-card")).toContainText("需要人工审批");

  const approval = page.getByTestId("approval-card");
  await expect(approval.getByRole("button", { name: "拒绝", exact: true })).toBeVisible();
  await approval.getByTestId("approval-deny").click();
  await expect(page.locator('[data-testid="action-status"].status-denied')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("api_key");

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "审计", exact: true })).toBeVisible();
  await page.locator(".filter-bar input").first().fill(runId ?? "");
  await page.locator(".filter-bar button").click();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
});
