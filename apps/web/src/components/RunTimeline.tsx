import type { AuditEvent } from "../types";
import { actorLabel, decisionLabel, eventLabel, formatTime, statusLabel, toolLabel } from "../i18n/zh-CN";

function payloadSummary(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "暂无更多信息";
  const record = payload as Record<string, unknown>;
  if (typeof record.tool_name === "string") return toolLabel(record.tool_name);
  if (typeof record.final_text === "string" && record.final_text) return record.final_text;
  if (typeof record.error === "string" && record.error) return `错误：${record.error}`;
  if (typeof record.decision === "string") return `策略决定：${decisionLabel(record.decision)}`;
  if (typeof record.status === "string") return `状态：${statusLabel(record.status)}`;
  if (typeof record.action_id === "string") return `动作 ID：${record.action_id.slice(0, 8)}`;
  return "已记录当前状态";
}

export function RunTimeline({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <p className="muted-copy">运行推进后，事件会显示在这里。</p>;
  }
  return (
    <ol className="timeline">
      {[...events].sort((a, b) => a.created_at.localeCompare(b.created_at)).map((event) => (
        <li className="timeline-item" key={event.id}>
          <span className="timeline-marker" aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-meta">
              <strong className="event-type">{eventLabel(event.event_type)} <code className="event-code" translate="no">{event.event_type}</code></strong>
              <span className="event-time">{formatTime(event.created_at)}</span>
            </div>
            <p>{payloadSummary(event.payload)}</p>
            <span className="actor-label">执行者 · {actorLabel(event.actor)} <code translate="no">{event.actor}</code></span>
          </div>
        </li>
      ))}
    </ol>
  );
}
