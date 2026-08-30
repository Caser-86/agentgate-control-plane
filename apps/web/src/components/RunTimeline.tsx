import type { AuditEvent } from "../types";

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function payloadSummary(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "No additional payload";
  const record = payload as Record<string, unknown>;
  const tool = record.tool_name ?? record.action_id ?? record.final_text ?? record.error;
  return tool ? String(tool) : "State recorded";
}

export function RunTimeline({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <p className="muted-copy">Events will appear as the run advances.</p>;
  }
  return (
    <ol className="timeline">
      {[...events].sort((a, b) => a.created_at.localeCompare(b.created_at)).map((event) => (
        <li className="timeline-item" key={event.id}>
          <span className="timeline-marker" aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-meta">
              <strong>{event.event_type}</strong>
              <span>{formatTime(event.created_at)}</span>
            </div>
            <p>{payloadSummary(event.payload)}</p>
            <span className="actor-label">actor · {event.actor}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
