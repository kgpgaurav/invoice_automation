import hashlib

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval import approve
from app.evidence_verification import verify
from app.extraction_client import OpenAIExtractor
from app.extraction_store import APIUsage, recorder
from app.financial_models import ApprovalLedger
from tests.extraction_helpers import case, response, untrusted_extraction
from tests.financial_fixtures import POLICY, masters, run


def test_pdf_to_untrusted_extraction_to_verified_financial_assessment(database):
    engine = database[0]
    pdf, truth = case()
    masters(engine)
    run_id = run(engine, pdf)
    attempts = []
    persist = recorder(engine, run_id, hashlib.sha256(pdf).hexdigest())

    def record(attempt):
        attempts.append(attempt)
        persist(attempt)

    def handler(request):
        assert engine.pool.checkedout() == 0  # No database transaction during model call
        return response(untrusted_extraction(pdf, truth))

    client = OpenAIExtractor(
        "test-key",
        "test-model",
        httpx.Client(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)),
    )
    extraction = client.extract(pdf, record=record)
    checked = verify(extraction, pdf)
    assert not checked.needs_review
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    result = approve(engine, run_id, checked.document, POLICY.version)
    assert result.decision == "APPROVED"  # deterministic fixture assessment, not live AI approval
    persist(attempts[0])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(APIUsage)) == 1
        usage = session.scalar(select(APIUsage))
        assert usage.estimated_cost_usd is None
        assert usage.input_tokens == 100 and usage.cached_tokens == 20
    with pytest.raises(ValueError):
        persist(dict(attempts[0], model_id="conflicting"))
    client.close()
