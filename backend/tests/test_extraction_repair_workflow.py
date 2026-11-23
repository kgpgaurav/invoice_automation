"""Durable field repair with mocked OpenAI; no live extraction/cost claims."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extraction_client import OpenAIExtractor
from app.extraction_repair import repair_model
from app.extraction_schema import InvoiceExtractionV1, InvoiceExtractionV12
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger
from app.main import create_app
from app.models import Run, RunEvent
from app.workflow import WorkflowProcessor
from app.workflow_models import WorkflowRun
from tests.conftest import TOKEN
from tests.extraction_helpers import response
from tests.financial_fixtures import POLICY
from tests.ordinary_invoices import invoice
from tests.test_ordinary_invoices import ordinary_masters
from tests.workflow_helpers import execute, intake


@pytest.mark.parametrize("repair_ok", [True, False])
def test_targeted_second_pass_is_persisted_and_reverified(workflow_db, settings, repair_ok):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, correct = invoice()
    data = correct.model_dump()
    data["invoice_date"] = None
    initial = InvoiceExtractionV1.model_validate(data)
    targets = ["invoice_date"]
    patch = repair_model(initial, targets).model_validate(
        dict(
            values={"invoice_date": correct.invoice_date if repair_ok else None},
            evidence=[e.model_dump() for e in correct.evidence if e.field == "invoice_date"],
        )
    )
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 2:
            assert "InvoiceRepairV1" == body["text"]["format"]["name"]
            assert "invoice_date" in body["instructions"]
            return response(patch)
        return response(initial)

    extractor = OpenAIExtractor(
        "mock",
        "test-model",
        httpx.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx.MockTransport(handle),
        ),
    )
    ident = intake(engine, pdf)
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    execute(engine, processor)
    assert len(calls) == 2
    with Session(engine) as s:
        work = s.get(WorkflowRun, ident)
        assert work.extraction_attempts == 2
        assert work.extraction_history[0] == InvoiceExtractionV12.model_validate(data).model_dump()
        assert len(work.extraction_history) == 2
        assert work.extraction_json["total_gross"] == data["total_gross"]
        assert s.get(Run, ident).decision == ("APPROVED" if repair_ok else "NEEDS_REVIEW")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == int(repair_ok)
        assert s.scalar(select(func.count()).select_from(APIUsage)) == 2
        reports = [r for r in work.diagnostic_history if r["stage"] == "SOURCE_VERIFICATION"]
        assert len(reports) == 2
        first = next(f for f in reports[0]["fields"] if f["field"] == "invoice_date")
        assert first["state"] == "MISSING" and first["original_value"] is None
        last = next(f for f in reports[1]["fields"] if f["field"] == "invoice_date")
        assert last["state"] == ("EXTRACTED" if repair_ok else "MISSING")
        # Nothing from the diagnostic reports/citations enters event streams.
        assert all("raw_text" not in str(e.payload_json) for e in s.scalars(select(RunEvent)))
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        detail = client.get(f"/api/v1/runs/{ident}").json()
        field = next(f for f in detail["fields"] if f["field"] == "invoice_date")
        assert field["extraction_state"] == ("EXTRACTED" if repair_ok else "MISSING")
        assert "source_reason" in field and "raw_text" not in field
    extractor.close()


def test_schema_retry_consumes_budget_before_any_source_repair(workflow_db):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice()
    data = wire.model_dump()
    data["invoice_date"] = None
    wire = InvoiceExtractionV1.model_validate(data)
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"status": "completed", "output": []})
        return response(wire)

    extractor = OpenAIExtractor(
        "mock",
        "test-model",
        httpx.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx.MockTransport(handle),
        ),
        sleep=lambda _: None,
    )
    ident = intake(engine, pdf)
    execute(engine, WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI"))
    with Session(engine) as s:
        work = s.get(WorkflowRun, ident)
        assert work.extraction_attempts == len(calls) == 2
        assert work.diagnostic_history[0]["stage"] == "SCHEMA_VALIDATION"
        assert work.diagnostic_history[0]["issues"]
        assert s.get(Run, ident).decision == "NEEDS_REVIEW"
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    extractor.close()
