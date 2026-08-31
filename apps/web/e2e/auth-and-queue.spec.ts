import { expect, test } from "@playwright/test";
import fs from "node:fs";

test("中文首次登录、排队审批拒绝并在刷新后保留审计游标", async ({ page }) => {
  await page.goto("/login");
  const setup = page.getByRole("heading", { name: "初始化管理员密码", exact: true });
  const loginHeading = page.getByRole("heading", { name: "登录", exact: true });
  await expect(setup.or(loginHeading)).toBeVisible();

  if (await page.getByRole("textbox", { name: "引导令牌" }).count() > 0) {
    const bootstrapToken = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN
      ?? fs.readFileSync(process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN_FILE ?? "", "utf8");
    await page.getByRole("textbox", { name: "引导令牌" }).fill(bootstrapToken);
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "完成初始化", exact: true }).click();
  } else {
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "登录", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  await page.getByTestId("start-run").click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect(page.locator('[data-testid="run-status"]').first()).toBeVisible();
  await expect(page.getByTestId("approval-card")).toBeVisible({ timeout: 15_000 });

  const approval = page.getByTestId("approval-card");
  await approval.getByTestId("approval-deny").click();
  await expect(page.locator('[data-testid="action-status"].status-denied')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("api_key");

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.goto("/audit");
  await page.locator(".filter-bar input").first().fill(runId ?? "");
  await page.locator(".filter-bar button").click();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
});
