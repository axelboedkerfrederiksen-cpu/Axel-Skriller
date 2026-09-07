from enum import StrEnum


class FetchMode(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"


class ResultStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    INVALID = "invalid"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class FailureKind(StrEnum):
    TRANSPORT = "transport"
    RATE_LIMITED = "rate_limited"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    ANTI_BOT = "anti_bot"
    EXTRACTION = "extraction"
    SCHEMA = "schema"
    PLAUSIBILITY = "plausibility"
    IDENTITY = "identity"
    INTERNAL = "internal"

    @property
    def is_repairable(self) -> bool:
        return self in {
            FailureKind.EXTRACTION,
            FailureKind.SCHEMA,
            FailureKind.PLAUSIBILITY,
            FailureKind.IDENTITY,
        }


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BROKEN = "broken"
    REPAIR_QUEUED = "repair_queued"
    REPAIRING = "repairing"
    DISABLED = "disabled"


class RepairStatus(StrEnum):
    QUEUED = "queued"
    DIAGNOSING = "diagnosing"
    CANDIDATE_READY = "candidate_ready"
    TESTING = "testing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MatchMethod(StrEnum):
    MANUAL = "manual"
    IDENTIFIER = "identifier"
    HEURISTIC = "heuristic"
    AI = "ai"


class ChangeKind(StrEnum):
    INITIAL = "initial"
    UNCHANGED = "unchanged"
    INCREASE = "increase"
    DECREASE = "decrease"
    CURRENCY_CHANGED = "currency_changed"
