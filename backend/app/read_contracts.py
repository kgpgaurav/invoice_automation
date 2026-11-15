"""Public read models deliberately exclude private source snippets and banking fields."""

from datetime import UTC
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, field_validator

from app.contracts import JobState, RunStatus


class ExtractedField(BaseModel):
    field: str
    value: str | None
    verification: Literal["verified", "unverified", "missing"]
    pages: list[int]


class VendorView(BaseModel):
    vendor_id: UUID
    name: str
    status: str


class POView(BaseModel):
    po_id: UUID
    po_number: str
    status: str
    currency: str
    cap_gross: str
    committed_gross: str
    remaining_gross: str
    relationship: Literal["APPROVED_ALLOCATION", "ASSESSED_PO", "PRINTED_REFERENCE"]
    balance_label: str = "Current PO balance; other approvals may have changed it"


class UsageView(BaseModel):
    recorded_attempts: int = 0
    reserved_attempts: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: str | None = None
    actual_billed_cost_usd: None = None
    cost_status: Literal["estimated", "unknown", "not_applicable"] = "unknown"
    rate_sources: list[str] = []


class StageView(BaseModel):
    key: str
    name: str
    operation: str
    status: Literal["running", "finished", "failed"]
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
    elapsed_ms: int | None

    @field_validator("started_at", "finished_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value is not None else None


class RuleCheckView(BaseModel):
    rule_id: str
    title: str
    status: Literal["passed", "failed", "requires_review", "not_evaluated"]
    description: str
    provenance: str
    finding_code: str | None = None
    assessment_revision: int | None = None
    pages: list[int] = []


class ProcessingFailureView(BaseModel):
    code: Literal["MOCK_FIXTURE_NOT_FOUND", "BYOK_CREDENTIALS_UNAVAILABLE"]
    message: str
    next_action: str
    provenance: Literal["PERSISTED_EXTRACTION_ERROR", "RECORDED_MOCK_HTTP_422"]


class RunDetail(RunStatus):
    updated_at: AwareDatetime
    source_mode: str
    policy_version: str
    model_id: str
    reason_code: str | None
    error_code: str | None
    invoice_number: str | None
    invoice_currency: str | None
    invoice_total: str | None
    fields: list[ExtractedField]
    verification_findings: list[str]
    vendor: VendorView | None
    purchase_order: POView | None
    decision_observations: dict[str, str] | None
    approved_gross: str | None
    review_request_id: UUID | None
    stages: list[StageView]
    processing_ms: int | None
    processing_time_status: Literal["measured", "incomplete", "pending"]
    usage: UsageView
    checks: list[RuleCheckView] = []
    business_explanation: str | None = None
    processing_failure: ProcessingFailureView | None = None


class RunSummary(BaseModel):
    run_id: UUID
    created_at: AwareDatetime
    job_state: JobState
    decision: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"] | None
    invoice_number: str | None
    vendor_name: str | None
    currency: str | None
    total_gross: str | None
    reason: str | None
    source_mode: str
    updated_at: AwareDatetime | None = None
    reason_code: str | None = None
    estimated_api_cost_usd: str | None = None
    processing_failure: ProcessingFailureView | None = None


class SubmitterRunDetail(BaseModel):
    run_id: UUID
    job_state: JobState
    decision: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"] | None
    decision_reason: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    source_mode: str
    model_id: str
    invoice_number: str | None
    invoice_currency: str | None
    invoice_total: str | None
    fields: list[ExtractedField]
    stages: list[StageView]
    processing_ms: int | None
    usage: UsageView
    processing_failure: ProcessingFailureView | None


class RunPage(BaseModel):
    items: list[RunSummary]
    next_cursor: str | None
    total_count: int


class DashboardSummary(BaseModel):
    total_runs: int
    total_processed: int
    approved: int
    rejected: int
    awaiting_review: int
    active: int
    failed: int
    average_processing_ms: int | None
    processing_time_sample_count: int
    estimated_api_cost_usd: str | None
    estimated_cost_known_runs: int
    estimated_cost_unknown_runs: int
    actual_billed_cost_usd: None = None
    potential_po_overrun_inr: str | None
    overrun_known_identities: int
    overrun_unknown_identities: int
    straight_through_approved: int = 0
    automation_eligible_runs: int = 0
    straight_through_rate_pct: str | None = None
    mock_runs: int = 0
    live_runs: int = 0
    replay_runs: int = 0
    metrics_notice: str = (
        "All runs. Processed means final approved/rejected decisions. "
        "Time excludes queue/review wait; incomplete intervals are excluded. "
        "Overrun is recorded potential exposure for distinct current holds, not savings."
    )


class PODirectoryEntry(BaseModel):
    po_id: UUID
    po_number: str
    vendor_name: str
    status: str
    currency: str
    cap_gross: str
    committed_gross: str


class POPage(BaseModel):
    items: list[PODirectoryEntry]
    next_after: str | None
    total_count: int


class LedgerEntryView(BaseModel):
    ledger_id: UUID
    run_id: UUID
    invoice_number: str
    invoice_date: str
    gross: str
    approved_at: AwareDatetime


class POLedgerView(PODirectoryEntry):
    issued_at: str
    expires_at: str | None
    ledger_committed_gross: str
    available_gross: str | None
    balance_reconciled: bool
    allocations: list[LedgerEntryView]
    allocation_count: int
    allocations_truncated: bool
