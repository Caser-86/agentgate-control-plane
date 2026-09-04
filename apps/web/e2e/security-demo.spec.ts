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

function externalStatus(id: string, action: "file.quarantine.v1" | "file.restore.v1", relativePath: string | null, status: string, result: Record<string, unknown> | null) {
  return {
    id,
    action,
    workspace_id: "workspace-demo",
    relative_path: relativePath,
    quarantine_entry_id: result?.quarantine_entry_id ?? null,
    decision: status === "denied" ? "deny" : status === "pending_approval" ? "require_approval" : "allow",
    status,
    reason: status === "denied" ? "目标路径受保护，未执行任何变化" : status === "pending_approval" ? "该文件动作需要人工审批" : "文件动作已由 Native Worker 执行并校验",
    action_version: action,
    task_id: status === "succeeded" ? "task-demo" : null,
    approval_expires_at: null,
    created_at: timestamp(),
    result,
  };
}

test("中文安全演示展示拒绝、审批、隔离与恢复闭环", async ({ page }, testInfo) => {
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

  const ordinary = externalStatus("ordinary-demo", "file.quarantine.v1", "demo.txt", "pending_approval", null);
  await page.route("**/api/v1/workspaces", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [{ id: "workspace-demo", name: "面试演示工作区", root_path: "C:\\AgentGate\\demo", quarantine_root_path: "C:\\AgentGate\\quarantine", protected_patterns: [".env", "*.key"], enabled: true, version: 1 }] });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/auth/tokens", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { id: "client-demo", name: "安全演示临时令牌", scopes: ["propose:actions"], expires_at: timestamp(), token: "e2e-demo-token" } });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/v1/actions", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const body = JSON.parse(route.request().postData() ?? "{}") as { relative_path?: string; action?: string };
    if (body.action === "file.restore.v1") {
      await route.fulfill({ json: externalStatus("restore-demo", "file.restore.v1", "demo.txt", "pending_approval", { quarantine_entry_id: "entry-demo" }) });
      return;
    }
    if (body.relative_path === ".env") {
      await route.fulfill({ json: externalStatus("protected-demo", "file.quarantine.v1", ".env", "denied", null) });
      return;
    }
    await route.fulfill({ json: ordinary });
  });
  await page.route("**/api/v1/actions/*", async (route) => {
    const id = route.request().url().split("/").pop();
    if (route.request().method() === "GET" && id === "ordinary-demo") {
      await route.fulfill({ json: externalStatus("ordinary-demo", "file.quarantine.v1", "demo.txt", "succeeded", { side_effect: "quarantined", content_sha256: "a".repeat(64), quarantine_entry_id: "entry-demo" }) });
      return;
    }
    if (route.request().method() === "GET" && id === "restore-demo") {
      await route.fulfill({ json: externalStatus("restore-demo", "file.restore.v1", "demo.txt", "succeeded", { side_effect: "restored", content_sha256: "a".repeat(64), quarantine_entry_id: "entry-demo" }) });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/actions/ordinary-demo", async (route) => {
    await route.fulfill({ json: { id: "ordinary-demo", run_id: null, tool_call_id: "demo", tool_name: "file.quarantine.v1", risk_level: "medium", policy_decision: "require_approval", status: "pending_approval", arguments: { relative_path: "demo.txt" }, result: null, reason: "该文件动作需要人工审批", created_at: timestamp(), decided_at: null, executed_at: null } });
  });
  await page.route("**/api/approvals/ordinary-demo/approve", async (route) => {
    await route.fulfill({ json: { id: "ordinary-demo", run_id: null, tool_call_id: "demo", tool_name: "file.quarantine.v1", risk_level: "medium", policy_decision: "require_approval", status: "approved", arguments: { relative_path: "demo.txt" }, result: null, reason: "已批准，等待 Native Worker 执行", created_at: timestamp(), decided_at: timestamp(), executed_at: null } });
  });
  await page.route("**/api/approvals/restore-demo/approve", async (route) => {
    await route.fulfill({ json: { id: "restore-demo", run_id: null, tool_call_id: "demo", tool_name: "file.restore.v1", risk_level: "medium", policy_decision: "require_approval", status: "approved", arguments: { relative_path: "demo.txt" }, result: null, reason: "已批准，等待 Native Worker 执行", created_at: timestamp(), decided_at: timestamp(), executed_at: null } });
  });

  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "安全演示", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "开始安全演示", exact: false }).click();
  await expect(page.getByText(".env 已拒绝", { exact: true })).toBeVisible();
  await expect(page.getByText("待审批，Worker 尚未执行文件变化", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "批准并隔离 ↗", exact: true }).click();
  await expect(page.getByText("已隔离，文件已经离开原路径", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "恢复文件 ↗", exact: true }).click();
  await expect(page.getByText("已恢复，目标文件没有被覆盖", { exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("Mock");
});
