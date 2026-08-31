import { expect, test } from "@playwright/test";

async function login(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/login");
  const setup = page.getByRole("heading", { name: "初始化管理员密码", exact: true });
  if (await setup.isVisible().catch(() => false)) {
    const token = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
    if (!token) throw new Error("AGENTGATE_E2E_BOOTSTRAP_TOKEN is required for first-run setup");
    await page.getByRole("textbox", { name: "引导令牌" }).fill(token);
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "完成初始化", exact: true }).click();
  } else {
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "登录", exact: true }).click();
  }
}

test("rejects a degraded-service restart and preserves an auditable trace", async ({ page, browser }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible();

  await page.getByTestId("run-request").fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  await page.getByTestId("start-run").click();

  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+/);
  await expect(page.getByText("Waiting approval", { exact: true }).first()).toBeVisible();
  const approval = page.getByRole("region", { name: "restart_service" });
  await expect(approval).toBeVisible();
  await expect(approval.getByText("Medium risk", { exact: true })).toBeVisible();
  await expect(approval.getByText("Medium-risk actions require explicit human approval.", { exact: true })).toBeVisible();
  await expect(approval.locator("pre")).toContainText('"service": "payments-api"');
  if (process.env.AGENTGATE_CAPTURE_SCREENSHOT === "1") {
    await page.screenshot({ path: "../../docs/assets/local-demo.png", fullPage: true });
  }

  const waitingBody = await page.locator("body").innerText();
  expect(waitingBody).not.toContain("api_key");

  await approval.getByTestId("approval-deny").click();
  await expect(page.getByText("Denied", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText("approval.denied", { exact: true })).toBeVisible();
  await expect(page.getByText('"denied": true', { exact: true })).toBeVisible();

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.getByRole("link", { name: /^Audit/ }).click();
  await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Run ID" }).fill(runId ?? "");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
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
