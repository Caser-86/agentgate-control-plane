import { describe, expect, it } from "vitest";
import {
  actorLabel,
  decisionLabel,
  eventLabel,
  modeLabel,
  riskLabel,
  statusLabel,
  toolLabel,
} from "./zh-CN";

describe("zh-CN interface vocabulary", () => {
  it("translates system enums while preserving unknown identifiers", () => {
    expect(statusLabel("waiting_approval")).toBe("等待审批");
    expect(riskLabel("medium")).toBe("中风险");
    expect(decisionLabel("require_approval")).toBe("需要审批");
    expect(toolLabel("restart_service")).toBe("重启服务");
  expect(eventLabel("approval.approved")).toBe("审批已通过");
  expect(eventLabel("run.waiting_approval")).toBe("运行等待审批");
    expect(actorLabel("policy")).toBe("策略引擎");
    expect(modeLabel(false)).toBe("会改变状态");
    expect(toolLabel("vendor_specific_tool")).toBe("vendor_specific_tool");
  });
});
