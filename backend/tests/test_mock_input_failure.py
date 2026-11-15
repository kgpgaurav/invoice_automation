import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extraction_client import ExtractionError
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger
from app.main import create_app
from app.models import Run, RunEvent
from app.product_reads import processing_failure
from app.worker import Worker, WorkerPolicy
from app.workflow import WorkflowProcessor
from app.workflow_models import WorkflowRun
from scripts.demo import extractor_for
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.workflow_helpers import intake


@pytest.fixture
def fixture_adapter():
    base = Path(__file__).resolve().parents[2] / ".local" / "mock-input-tests"
    base.mkdir(parents=True, exist_ok=True)
    pdf, expected = case()
    with TemporaryDirectory(dir=base) as name:
        path = Path(name).resolve()
        assert path.is_relative_to(base.resolve())
        (path / "fixtures.json").write_text(
            json.dumps([dict(sha256=hashlib.sha256(pdf).hexdigest(), expected=expected)]),
            encoding="utf-8",
        )
        adapter = extractor_for(path, {"mode": "mock"}, None)
        try:
            yield adapter, pdf
        finally:
            adapter.close()


def test_unknown_mock_pdf_has_no_request_or_attempt_reservation(fixture_adapter, pdf, monkeypatch):
    adapter, _ = fixture_adapter
    recorded, reserved = [], []

    def no_request(*args, **kwargs):
        pytest.fail("Unknown mock input must never reach transport")

    monkeypatch.setattr(adapter.client, "post", no_request)
    with pytest.raises(ExtractionError, match="MOCK_FIXTURE_NOT_FOUND"):
        adapter.extract(pdf, route="pdf", record=recorded.append, before_attempt=reserved.append)
    assert recorded == [] and reserved == []


def test_registered_fixture_keeps_real_verification_boundary(fixture_adapter):
    adapter, pdf = fixture_adapter
    recorded, reserved = [], []
    wire = adapter.extract(pdf, route="pdf", record=recorded.append, before_attempt=reserved.append)
    assert wire.invoice_number == "INV-001"
    assert len(recorded) == len(reserved) == 1
    assert recorded[0]["usage"] is None
    assert "verified" not in wire.model_dump_json()


def test_failed_mock_input_cause_persists_and_projects_without_financial_decision(
    workflow_db, settings, fixture_adapter, pdf
):
    engine = workflow_db
    masters(engine)
    adapter, _ = fixture_adapter
    processor = WorkflowProcessor(engine, adapter, "policy-1.1-demo", source_mode="MOCK_OPENAI")
    processor.check_ready()
    run_id = intake(engine, pdf)  # synthetic non-fixture PDF, never the user's personal document
    worker = Worker(engine, processor, WorkerPolicy(retry_seconds=0))
    for _ in range(3):
        assert worker.run_once()
    with Session(engine) as s:
        run, work = s.get(Run, run_id), s.get(WorkflowRun, run_id)
        assert run.job_state == "FAILED" and run.decision is None
        assert run.error_code == "WORKER_ATTEMPTS_EXHAUSTED"
        assert work.extraction_error == "MOCK_FIXTURE_NOT_FOUND" and work.extraction_attempts == 0
        assert s.scalar(select(func.count()).select_from(APIUsage)) == 0
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        events = s.scalars(select(RunEvent).where(RunEvent.run_id == run_id)).all()
        before = len(events)
        assert not any(e.payload_json.get("operation") == "OPENAI_REQUEST" for e in events)
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        detail = client.get(f"/api/v1/runs/{run_id}").json()
        failure = detail["processing_failure"]
        assert failure["code"] == "MOCK_FIXTURE_NOT_FOUND"
        assert failure["provenance"] == "PERSISTED_EXTRACTION_ERROR"
        assert "not analyzed" in failure["message"]
        assert detail["usage"]["recorded_attempts"] == detail["usage"]["reserved_attempts"] == 0
        assert detail["decision"] is None and detail["approved_gross"] is None
        assert client.get("/api/v1/runs").json()["items"][0]["processing_failure"] == failure
        assert "resume" not in failure["message"].lower()
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(RunEvent)) == before


@pytest.mark.parametrize(
    "mode,model,code,expected",
    [
        ("MOCK_OPENAI", "fixture-extraction", "OPENAI_HTTP_422", True),
        ("LIVE_OPENAI", "fixture-extraction", "OPENAI_HTTP_422", False),
        ("MOCK_OPENAI", "test-model", "OPENAI_HTTP_422", False),
        ("MOCK_OPENAI", "fixture-extraction", "OPENAI_HTTP_500", False),
    ],
)
def test_legacy_error_projection_is_specific_and_read_only(mode, model, code, expected):
    run = SimpleNamespace(job_state="FAILED")
    work = SimpleNamespace(source_mode=mode, model_id=model, extraction_error=code)
    usage = [SimpleNamespace(error_code=code, requested_model=model)]
    result = processing_failure(run, work, usage)
    assert bool(result) is expected
    if result:
        assert result.provenance == "RECORDED_MOCK_HTTP_422"
        assert code == work.extraction_error  # original cause is preserved
        usage.append(SimpleNamespace(error_code="OPENAI_HTTP_500", requested_model=model))
        assert processing_failure(run, work, usage) is None
    run.job_state = "COMPLETED"
    assert processing_failure(run, work, usage) is None
