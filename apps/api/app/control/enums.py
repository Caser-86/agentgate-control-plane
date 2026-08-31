from enum import StrEnum


class TaskKind(StrEnum):
    AGENT_RUN = "agent_run_resume"
    ACTION_EXECUTION = "action_execution"
    CONTROL = "control"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class TaskOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class SideEffectCertainty(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    POSSIBLE = "possible"


class WorkerStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
