import { expect, test } from "@playwright/test";

test("approves a degraded-service restart and preserves an auditable trace", async ({ page }) => {
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
});
