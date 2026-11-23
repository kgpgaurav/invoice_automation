from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, field_validator

API_PREFIX = "/api/v1"
MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = 5


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class Health(BaseModel):
    status: Literal["ok", "ready", "not_ready"]
    database: Literal["ready", "unavailable"] | None = None
    extraction_schema_version: str | None = None
    prompt_version: str | None = None
    verifier_version: str | None = None
    scan_review_required: bool | None = None


class IntakeResponse(BaseModel):
    run_id: UUID
    job_state: Literal["QUEUED"] = "QUEUED"
    links: dict[str, str]


class RunStatus(BaseModel):
    run_id: UUID
    job_state: JobState
    decision: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"] | None
    decision_reason: str | None
    thread_id: UUID
    created_at: AwareDatetime
    replay_mode: bool
    implementation_notice: str

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class RunEventResponse(BaseModel):
    run_id: UUID
    seq: int
    type: str
    stage: str
    occurred_at: AwareDatetime
    payload: dict

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
