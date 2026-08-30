import { useEffect, useState } from "react";
import { apiBaseUrl } from "../api/client";
import type { RunEvent } from "../types";

export function useRunEvents(runId: string | undefined, onEvent: (event: RunEvent) => void) {
  const [connection, setConnection] = useState<"connecting" | "live" | "reconnecting">("connecting");

  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let source: EventSource | null = null;
    let retry: number | undefined;

    const connect = () => {
      if (disposed) return;
      setConnection(retry ? "reconnecting" : "connecting");
      source = new EventSource(`${apiBaseUrl}/api/runs/${encodeURIComponent(runId)}/events`);
      const handleEvent = (raw: MessageEvent<string>) => {
        setConnection("live");
        try {
          onEvent({ id: Number(raw.lastEventId || 0), event_type: raw.type, payload: JSON.parse(raw.data) as Record<string, unknown> });
        } catch {
          // Ignore malformed optional event payloads; the next persisted event will refresh the detail.
        }
      };
      source.addEventListener("run.updated", handleEvent);
      source.addEventListener("action.updated", handleEvent);
      source.onerror = () => {
        source?.close();
        if (disposed) return;
        setConnection("reconnecting");
        retry = window.setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retry !== undefined) window.clearTimeout(retry);
      source?.close();
    };
  }, [runId, onEvent]);

  return connection;
}
