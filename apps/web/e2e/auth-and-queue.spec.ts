import { expect, test } from "@playwright/test";

test("中文首次登录、排队审批拒绝并在刷新后保留审计游标", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "初始化管理员密码", exact: true })).toBeVisible();

  const bootstrapToken = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
  if (!bootstrapToken) {
    throw new Error("AGENTGATE_E2E_BOOTSTRAP_TOKEN is required for the first-run E2E flow");
  }
  await page.getByRole("textbox", { name: "引导令牌" }).fill(bootstrapToken);
  await page.getByLabel("管理员密码").fill("fake-e2e-password");
  await page.getByRole("button", { name: "完成初始化", exact: true }).click();
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  await page.getByTestId("start-run").click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect(page.getByText(/Queued|Running/, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Waiting approval", { exact: true }).first()).toBeVisible({ timeout: 15_000 });

  const approval = page.getByRole("region", { name: "restart_service" });
  await approval.getByTestId("approval-deny").click();
  await expect(page.getByText("Denied", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("api_key");

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.getByRole("link", { name: /^Audit/ }).click();
  await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Run ID" }).fill(runId ?? "");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
});
