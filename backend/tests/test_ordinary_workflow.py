import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction_client import OpenAIExtractor
from app.main import create_app
from app.models import Run
from app.review_contracts import ReviewResponse
from app.reviews import respond
from app.workflow import WorkflowProcessor
from app.workflow_models import ReviewRequest, WorkflowRun
from tests.conftest import TOKEN
from tests.extraction_helpers import response
from tests.financial_fixtures import POLICY
from tests.ordinary_invoices import invoice
from tests.test_ordinary_invoices import ordinary_masters
from tests.workflow_helpers import execute, intake


def processor(engine, wire):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return response(wire)

    extractor = OpenAIExtractor(
        "mock-only",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        ),
    )
    return WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI"), calls


def test_arbitrary_layout_uses_openai_contract_and_persists_individual_checks(
    workflow_db, settings
):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice(numbered=False)
    ident = intake(engine, pdf)
    handler, calls = processor(engine, wire)
    execute(engine, handler)
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        detail = client.get(f"/api/v1/runs/{ident}").json()
    assert detail["decision"] == "APPROVED"
    assert len(calls) == 1 and calls[0]["text"]["format"]["strict"]
    assert "ordinary invoice" in calls[0]["instructions"]
    assert calls[0]["input"][0]["content"][0]["type"] == "input_file"
    fields = {f["field"]: f for f in detail["fields"]}
    assert fields["tax_total"]["value"] == "1350.00"
    assert (
        fields["tax_total"]["origin"] == "derived" and fields["tax_total"]["original_value"] is None
    )
    assert fields["lines.1.sku"]["required_for_approval"] is False
    assert fields["lines.1.description"]["verification"] == "verified"
    assert len(detail["checks"]) == 13
    assert next(c for c in detail["checks"] if c["rule_id"] == "PO_PRICE")["status"] == "passed"
    with Session(engine) as session:
        assert session.get(WorkflowRun, ident).extraction_json["tax_total"] is None


def test_missing_po_directly_interrupts_and_selection_revalidates_same_thread(workflow_db):
    engine = workflow_db
    _, po_id, _ = ordinary_masters(engine)
    pdf, wire = invoice(po=None)
    ident = intake(engine, pdf)
    handler, calls = processor(engine, wire)
    execute(engine, handler)
    with Session(engine) as session:
        run = session.get(Run, ident)
        thread = run.thread_id
        assert run.job_state == "WAITING_REVIEW"
        review = session.scalar(select(ReviewRequest).where(ReviewRequest.run_id == ident))
        assert review.kind == "PO_SELECTION" and review.options_json == [str(po_id)]
        review_id, generation = review.id, review.generation
    assert len(calls) == 1
    respond(
        engine,
        review_id,
        ReviewResponse(
            generation=generation,
            action="SELECT_PO",
            payload={"po_id": str(po_id)},
            reason="Confirmed the intended order in this synthetic procurement case.",
        ),
        "ordinary-select",
        "configured-reviewer",
    )
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "APPROVED"
        assert session.get(Run, ident).thread_id == thread
    assert len(calls) == 1


def test_no_po_with_missing_tax_still_goes_to_review_without_paid_repair(workflow_db):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice(po=None, tax=False, rate="0")
    ident = intake(engine, pdf)
    handler, calls = processor(engine, wire)
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "NEEDS_REVIEW"
        request = session.scalar(select(ReviewRequest).where(ReviewRequest.run_id == ident))
        assert request.kind == "EVIDENCE_OR_POLICY"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "prompt,verifier",
    [
        ("invoice-extract-1", "labelled-fields-3"),
        ("invoice-extract-2", "layout-grounding-4"),
        ("invoice-extract-3", "layout-diagnostics-5"),
        ("invoice-extract-3", "semantic-diagnostics-6"),
        ("invoice-extract-4", "extended-diagnostics-7"),
    ],
)
def test_frozen_legacy_review_survives_new_prompt_and_verifier(
    workflow_db, monkeypatch, prompt, verifier
):
    from app import workflow
    from tests.test_workflow_reviews import ambiguous, selection

    engine = workflow_db
    with monkeypatch.context() as old:
        old.setattr(workflow, "PROMPT_VERSION", prompt)
        old.setattr(workflow, "VERIFIER_VERSION", verifier)
        ident, po_id, review_id, handler, calls = ambiguous(engine)
    respond(
        engine, review_id, selection(po_id), "legacy-normal-layout-upgrade", "configured-reviewer"
    )
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "APPROVED"
        work = session.get(WorkflowRun, ident)
        assert work.prompt_version == prompt and work.verifier_version == verifier
    assert len(calls) == 1
