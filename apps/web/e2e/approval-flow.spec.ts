import { expect, test } from "@playwright/test";
import fs from "node:fs";

async function login(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/login");
  const token = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
  const bootstrapToken = token ?? fs.readFileSync(process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN_FILE ?? "", "utf8");
  await page.getByRole("textbox", { name: "引导令牌" }).fill(bootstrapToken);
  await page.getByLabel("管理员密码").fill("fake-e2e-password");
  await page.getByRole("button", { name: "完成初始化", exact: true }).click();
}

test("拒绝降级服务恢复并保留可审计记录", async ({ page, browser }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  await page.getByTestId("start-run").click();

  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect(page.getByTestId("approval-card")).toBeVisible();
  const approval = page.getByTestId("approval-card");
  await expect(approval).toBeVisible();
  await expect(approval.locator(".status-medium")).toBeVisible();
  await expect(approval.locator("pre")).toContainText('"service": "payments-api"');
  if (process.env.AGENTGATE_CAPTURE_SCREENSHOT === "1") {
    await page.screenshot({ path: "../../docs/assets/local-demo.png", fullPage: true });
  }

  const waitingBody = await page.locator("body").innerText();
  expect(waitingBody).not.toContain("api_key");

  await approval.getByTestId("approval-deny").click();
  await expect(page.locator('[data-testid="action-status"].status-denied')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.goto("/audit");
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
