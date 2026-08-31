import { useEffect, useRef, useState } from "react";
import { eventStreamUrl } from "../api/client";
import type { RunEvent } from "../types";

const MAX_RETRY_DELAY_MS = 30_000;

export function parseRunEvent(raw: MessageEvent<string>, lastEventId: number): RunEvent | null {
  const id = Number(raw.lastEventId);
  if (!Number.isSafeInteger(id) || id <= lastEventId) return null;
  try {
    const payload: unknown = JSON.parse(raw.data);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    return { id, event_type: raw.type, payload: payload as Record<string, unknown> };
  } catch {
    return null;
  }
}

export function useRunEvents(
  runId: string | undefined,
  onEvent: (event: RunEvent) => void,
  onReconnect?: () => void,
) {
  const [connection, setConnection] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const lastEventId = useRef(0);

  useEffect(() => {
    if (!runId) return;
    lastEventId.current = 0;
    let disposed = false;
    let source: EventSource | null = null;
    let retry: number | undefined;
    let retryDelay = 1000;
    let hasConnected = false;

    const connect = () => {
      if (disposed) return;
      setConnection(hasConnected ? "reconnecting" : "connecting");
      source = new EventSource(eventStreamUrl(runId, lastEventId.current));
      source.onopen = () => {
        const reconnected = hasConnected;
        hasConnected = true;
        retryDelay = 1000;
        setConnection("live");
        if (reconnected) onReconnect?.();
      };
      const handleEvent = (raw: MessageEvent<string>) => {
        setConnection("live");
        const event = parseRunEvent(raw, lastEventId.current);
        if (!event) return;
        lastEventId.current = event.id;
        onEvent(event);
      };
      source.addEventListener("run.updated", handleEvent);
      source.addEventListener("action.updated", handleEvent);
      source.onerror = () => {
        source?.close();
        if (disposed) return;
        setConnection("reconnecting");
        retry = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS);
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
