from enum import StrEnum


class TargetKind(StrEnum):
    HTTP = "http"
    WINDOWS_SERVICE = "windows_service"


class ProbeStatus(StrEnum):
    HEALTHY = "healthy"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TargetHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class EventStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


HTTP_MONITOR_CAPABILITY = "monitor.http"
WINDOWS_SERVICE_MONITOR_CAPABILITY = "monitor.windows_service"
