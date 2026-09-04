import { expect, test } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

function bootstrapToken(projectName: string): string {
  const configured = process.env.AGENTGATE_E2E_BOOTSTRAP_TOKEN;
  if (configured) return configured.trim();
  const apiPort = Number(process.env.AGENTGATE_E2E_API_PORT ?? "8000") + 2;
  const tokenFile = path.join(os.tmpdir(), `agentgate-e2e-task8-${projectName}-${apiPort}`, "bootstrap-token");
  if (!fs.existsSync(tokenFile)) {
    throw new Error(`E2E bootstrap token is missing: set AGENTGATE_E2E_BOOTSTRAP_TOKEN or provide ${tokenFile}`);
  }
  return fs.readFileSync(tokenFile, "utf8").trim();
}

function timestamp(): string {
  return "2026-09-04T00:00:00Z";
}

function inspectStatus(status: "succeeded" | "failed" = "succeeded") {
  return {
    id: "inspect-1",
    action: "file.inspect.v1",
    workspace_id: "workspace-1",
    relative_path: "README.md",
    quarantine_entry_id: null,
    decision: "auto_approve",
    status,
    reason: status === "succeeded" ? "只读检查可以自动执行" : "文件动作执行失败",
    action_version: "file.inspect.v1",
    task_id: status === "succeeded" ? "task-1" : null,
    approval_expires_at: null,
    created_at: timestamp(),
    result: status === "succeeded" ? { content_sha256: "a".repeat(64), side_effect: "none" } : null,
  };
}

test("文件治理可以提交只读检查并显示真实状态", async ({ page }, testInfo) => {
  await page.goto("/login");
  await expect(page.locator("main[aria-busy='false']")).toBeVisible({ timeout: 15_000 });
  const bootstrapField = page.getByRole("textbox", { name: "引导令牌" });
  const loginButton = page.getByRole("button", { name: "登录", exact: true });
  await expect(bootstrapField.or(loginButton)).toBeVisible({ timeout: 15_000 });
  if (await bootstrapField.isVisible()) {
    await bootstrapField.fill(bootstrapToken(testInfo.project.name));
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "完成初始化", exact: true }).click();
  } else {
    await page.getByLabel("管理员密码").fill("fake-e2e-password");
    await page.getByRole("button", { name: "登录", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "运行", exact: true })).toBeVisible({ timeout: 15_000 });

  await page.route("**/api/v1/workspaces", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [{ id: "workspace-1", name: "源码工作区", root_path: "C:\\AgentGate\\workspaces\\source", quarantine_root_path: "C:\\AgentGate\\quarantine\\workspace-1", protected_patterns: [".env", "*.key"], enabled: true, version: 1 }] });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/v1/workspaces/workspace-1/quarantine*", async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/auth/tokens", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { id: "client-1", name: "文件治理临时令牌", scopes: ["propose:actions"], expires_at: timestamp(), token: "e2e-token" } });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/auth/tokens/client-1", async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/v1/actions", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: inspectStatus() });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/v1/actions/inspect-1", async (route) => {
    await route.fulfill({ json: inspectStatus() });
  });

  await page.goto("/files");
  await expect(page.getByRole("heading", { name: "文件治理", exact: true })).toBeVisible();
  await page.getByLabel("相对路径").fill("README.md");
  await page.getByRole("button", { name: "提交文件动作", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("动作已提交");
  await expect(page.getByRole("heading", { name: "检查文件", exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toMatch(/安全演示|面试演示|Mock/);
});
