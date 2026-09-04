const stages = [
  { label: "任务请求", detail: "接收意图" },
  { label: "策略判断", detail: "划定边界" },
  { label: "人工审批", detail: "必要时介入" },
  { label: "安全执行", detail: "一次性动作" },
  { label: "留下证据", detail: "完整审计" },
];

export function SignalTrack({ activeStage = 0 }: { activeStage?: number }) {
  return (
    <ol className="signal-track" aria-label="控制流程">
      {stages.map((stage, index) => (
        <li className={`signal-stage ${index <= activeStage ? "is-reached" : ""} ${index === activeStage ? "is-current" : ""}`} key={stage.label}>
          <span className="signal-node" aria-hidden="true">{index + 1}</span>
          <span className="signal-stage-copy">
            <strong>{stage.label}</strong>
            <small>{stage.detail}</small>
          </span>
        </li>
      ))}
    </ol>
  );
}
