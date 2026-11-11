import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.checkpoints import checkpoint_store
from app.extraction_client import OpenAIExtractor
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger
from app.models import QueueItem, Run
from app.review_contracts import ReviewResponse
from app.reviews import respond
from app.worker import Claim, LostLease, Worker
from app.workflow import WorkflowProcessor
from app.workflow_models import ReviewRequest
from tests.extraction_helpers import case
from tests.financial_fixtures import POLICY, masters
from tests.test_owned_finalizer import prepared
from tests.workflow_helpers import execute, intake


def test_malformed_extraction_has_bounded_calls_and_can_be_rejected(workflow_db):
    engine = workflow_db
    masters(engine)
    pdf, _ = case()
    run_id = intake(engine, pdf)
    calls = []

    def invalid(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
            },
        )

    extractor = OpenAIExtractor(
        "mock",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(invalid)
        ),
        sleep=lambda _: None,
    )
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    execute(engine, processor)
    with Session(engine) as s:
        request = s.scalar(select(ReviewRequest).where(ReviewRequest.status == "OPEN"))
        review_id = request.id
        assert s.get(Run, run_id).decision == "NEEDS_REVIEW"
        assert s.scalar(select(func.count()).select_from(APIUsage)) == 2
    assert len(calls) == 2
    body = ReviewResponse(
        generation=1, action="REJECT", payload={}, reason="No usable invoice evidence"
    )
    respond(engine, review_id, body, "reject", "configured-reviewer")
    execute(engine, processor)
    with Session(engine) as s:
        assert (s.get(Run, run_id).job_state, s.get(Run, run_id).decision) == (
            "COMPLETED",
            "REJECTED",
        )
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("UPDATE review_actions SET reason='rewritten'"))
    assert len(calls) == 2


def test_checkpoint_writes_require_real_owner_connection(database):
    from tests.workflow_helpers import setup, teardown

    engine = database[0]
    setup(engine)
    worker, claim, _, _ = prepared(engine)
    connection = engine.connect()
    fake = Claim(claim.job_id, claim.run_id, claim.owner, claim.attempt, connection)
    try:
        with checkpoint_store(engine, worker, fake) as saver, pytest.raises(LostLease):
            saver.put({}, {}, {}, {})
    finally:
        fake.close()
        claim.close()
        teardown(engine)


def test_openai_call_never_spans_claim_transaction(workflow_db):
    from tests.extraction_helpers import response, untrusted_extraction

    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    intake(engine, pdf)
    holder = {}

    def handle(request):
        assert not holder["claim"].connection.in_transaction()
        return response(untrusted_extraction(pdf, expected))

    extractor = OpenAIExtractor(
        "mock",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        ),
    )
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    worker = Worker(engine, processor)
    holder["claim"] = claim = worker.claim()
    try:
        processor(worker, claim, pdf)
        with Session(engine) as s:
            job = s.get(QueueItem, claim.job_id)
            assert job.status == "DONE" and job.claimed_by is None and job.lease_until is None
    finally:
        claim.close()
