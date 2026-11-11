import base64
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extraction_client import OpenAIExtractor
from app.financial_models import ApprovalLedger, PurchaseOrder
from app.models import Document, QueueItem, Run
from app.pdf_input import inspect_pdf
from app.worker import Worker
from app.workflow import WorkflowProcessor
from scripts.extraction_fixtures import expected_invoice
from tests.extraction_helpers import response, untrusted_extraction
from tests.financial_fixtures import POLICY, masters
from tests.workflow_helpers import intake, invoice_pdf


def test_two_owned_graphs_share_po_without_overspending(workflow_db):
    engine = workflow_db
    _, po_id, _ = masters(engine, cap="15000")
    wires = {}
    for number in ("CONCURRENT-1", "CONCURRENT-2"):
        expected = expected_invoice(number)
        pdf = invoice_pdf(expected)
        wires[number] = untrusted_extraction(pdf, expected)
        intake(engine, pdf)

    def handle(request):
        data = json.loads(request.content)["input"][0]["content"][0]["file_data"]
        text = inspect_pdf(base64.b64decode(data.split(",", 1)[1])).text
        return response(next(wire for number, wire in wires.items() if number in text))

    extractor = OpenAIExtractor(
        "mock",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        ),
    )
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    workers = [Worker(engine, processor), Worker(engine, processor)]
    claims = [worker.claim() for worker in workers]
    assert len({claim.run_id for claim in claims}) == 2

    def execute(pair):
        worker, claim = pair
        try:
            with Session(engine) as s:
                pdf = s.get(Document, s.get(Run, claim.run_id).document_id).content
            processor(worker, claim, pdf)
        finally:
            claim.close()

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(execute, zip(workers, claims)))
    with Session(engine) as s:
        assert set(s.scalars(select(Run.decision))) == {"APPROVED", "NEEDS_REVIEW"}
        assert s.get(PurchaseOrder, po_id).committed_gross == 11800
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert set(s.scalars(select(QueueItem.status))) == {"DONE"}
