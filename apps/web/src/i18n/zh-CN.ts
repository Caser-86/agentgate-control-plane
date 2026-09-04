import type { ActionStatus, PolicyDecision, RiskLevel, RunStatus } from "../types";

const statusLabels: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  waiting_approval: "等待审批",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  proposed: "已提议",
  auto_approved: "已自动批准",
  pending_approval: "待审批",
  approved: "已批准",
  denied: "已拒绝",
  succeeded: "执行成功",
  expired: "已过期",
  healthy: "健康",
  degraded: "降级",
  down: "故障",
  unknown: "未知",
};

const riskLabels: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "高风险",
};

const decisionLabels: Record<string, string> = {
  auto_approve: "自动批准",
  require_approval: "需要审批",
  deny: "拒绝",
};

const toolLabels: Record<string, string> = {
  get_service_health: "读取服务健康状态",
  search_logs: "查询服务日志",
  restart_service: "重启服务",
  rotate_api_key: "轮换 API 密钥",
  "file.inspect.v1": "检查文件",
  "file.quarantine.v1": "隔离文件",
  "file.restore.v1": "恢复文件",
};

const toolDescriptions: Record<string, string> = {
  get_service_health: "读取服务健康状态，不会改变运行中的资源。",
  search_logs: "查询服务日志，不会改变运行中的资源。",
  restart_service: "重启服务，会改变运行中的资源状态。",
  rotate_api_key: "轮换 API 密钥，会立即影响凭据。",
  "file.inspect.v1": "只读取文件元数据和 SHA-256 摘要，不读取文件内容。",
  "file.quarantine.v1": "获批后把普通文件移动到隔离区，不覆盖同名目标。",
  "file.restore.v1": "获批后把已隔离文件恢复到原相对路径，目标冲突时停止。",
};

const eventLabels: Record<string, string> = {
  "run.created": "运行已创建",
  "run.updated": "运行状态更新",
  "run.completed": "运行已完成",
  "run.failed": "运行失败",
  "run.waiting_approval": "运行等待审批",
  "action.updated": "动作状态更新",
  "action.proposed": "动作已提议",
  "policy.decision": "策略已决策",
  "approval.requested": "等待人工审批",
  "approval.approved": "审批已通过",
  "approval.denied": "审批已拒绝",
  "tool.started": "工具开始执行",
  "tool.succeeded": "工具执行成功",
  "tool.denied": "工具执行已拒绝",
  "tool.failed": "工具执行失败",
  "monitor.target.created": "监控目标已创建",
  "monitor.probe.recorded": "监控探测已记录",
  "monitor.event.opened": "监控故障已打开",
  "monitor.event.closed": "监控故障已恢复",
  "file.action.pending_approval": "文件动作等待审批",
  "file.action.denied": "文件动作已拒绝",
  "file.action.queued": "文件动作已排队",
  "file.action.updated": "文件动作状态更新",
  "file.action.completed": "文件动作已完成",
  "file.action.manual_review_required": "文件动作需要人工复核",
};

const actorLabels: Record<string, string> = {
  user: "用户",
  agent: "Agent",
  policy: "策略引擎",
  tool: "工具执行器",
  system: "系统",
  monitoring: "监控服务",
};

const reasonLabels: Record<string, string> = {
  "High-risk actions are denied by the local demo policy.": "本地演示策略会直接拒绝高风险操作。",
  "Medium-risk actions require explicit human approval.": "中风险操作会暂停，等待明确的人工作出批准。",
  "Low-risk actions are automatically approved.": "低风险操作会自动批准。",
  "Low-risk read-only actions are automatically approved.": "低风险只读操作会自动批准。",
  "Low-risk write actions are denied because only read-only automation is allowed.": "低风险写操作仍会被拒绝，因为自动化仅允许只读行为。",
  "Unknown tools are denied by the allowlist.": "未注册工具不在允许列表中，已安全拒绝。",
  "Tool arguments failed schema validation.": "工具参数未通过结构校验，已安全拒绝。",
  "Read-only action.": "只读操作。",
  "recover the degraded payments service safely": "安全恢复已降级的 payments 服务",
};

export function statusLabel(value: RunStatus | ActionStatus | string): string {
  return statusLabels[value] ?? value;
}

export function riskLabel(value: RiskLevel | string): string {
  return riskLabels[value] ?? value;
}

export function decisionLabel(value: PolicyDecision | string): string {
  return decisionLabels[value] ?? value;
}

export function toolLabel(value: string): string {
  return toolLabels[value] ?? value;
}

export function toolDescription(value: string, fallback: string): string {
  return toolDescriptions[value] ?? fallback;
}

export function eventLabel(value: string): string {
  return eventLabels[value] ?? value;
}

export function actorLabel(value: string): string {
  if (value === "operator:00000000-0000-0000-0000-000000000001") return "本地操作员";
  if (value.startsWith("operator:")) return "管理员";
  if (value.startsWith("client:")) return "外部 Agent";
  if (value.startsWith("control-worker:")) return "控制 Worker";
  if (value.startsWith("worker:")) return "原生 Worker";
  return actorLabels[value] ?? value;
}

export function actionLabel(value: string): string {
  return toolLabel(value);
}

export function reasonLabel(value: string): string {
  return reasonLabels[value] ?? value;
}

export function modeLabel(readOnly: boolean): string {
  return readOnly ? "只读 · 自动执行" : "会改变状态";
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
