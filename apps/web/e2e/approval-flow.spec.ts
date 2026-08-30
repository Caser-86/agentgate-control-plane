import { expect, test } from "@playwright/test";

test("approves a degraded-service restart and preserves an auditable trace", async ({ page, browser }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();

  await page.getByRole("textbox", { name: "Task request" }).fill(
    "Investigate payments-api and restore it safely. Do not rotate credentials.",
  );
  await page.getByRole("button", { name: "Start run", exact: true }).click();

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

  await approval.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("approval.approved", { exact: true })).toBeVisible();
  await expect(page.getByText("tool.succeeded", { exact: true }).first()).toBeVisible();

  const runId = page.url().split("/").pop();
  expect(runId).toBeTruthy();
  await page.getByRole("link", { name: /^Audit/ }).click();
  await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Run ID" }).fill(runId ?? "");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page.getByText("approval.approved", { exact: true })).toBeVisible();

  const auditBody = await page.locator("body").innerText();
  expect(auditBody).not.toContain("api_key");
  expect(auditBody).not.toContain("Bearer ");

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobilePage.goto("http://127.0.0.1:5173/");
  await expect(mobilePage.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  const dimensions = await mobilePage.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  await mobilePage.close();
});
