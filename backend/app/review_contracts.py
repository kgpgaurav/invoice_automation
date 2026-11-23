from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    po_id: UUID | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation: int = Field(ge=1, strict=True)
    action: Literal["SELECT_PO", "PASS", "REJECT", "REQUEST_INFO"]
    payload: ReviewPayload
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def closed_action(self):
        if not self.reason.strip() or (
            (self.action == "SELECT_PO") != (self.payload.po_id is not None)
        ):
            raise ValueError("SELECT_PO requires po_id; other actions require an empty payload")
        if self.action != "SELECT_PO" and self.payload.model_fields_set:
            raise ValueError("PASS, REJECT and REQUEST_INFO require payload:{}")
        return self


def allowed_review_actions(kind):
    return (
        (["SELECT_PO"] if kind == "PO_SELECTION" else [])
        + (["PASS"] if kind in ("PO_SELECTION", "EVIDENCE_OR_POLICY") else [])
        + ["REJECT", "REQUEST_INFO"]
    )


class ReviewCandidate(BaseModel):
    po_id: UUID
    po_number: str | None
    currency: str | None
    status: str
    remaining_gross: str | None


class ReviewView(BaseModel):
    review_request_id: UUID
    run_id: UUID
    generation: int
    kind: str
    question: str
    options: list[ReviewCandidate]
    allowed_actions: list[str]
    status: str


class ReviewAccepted(BaseModel):
    run_id: UUID
    review_request_id: UUID
    job_state: Literal["QUEUED"] = "QUEUED"
