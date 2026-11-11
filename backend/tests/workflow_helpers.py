"""Synthetic PDFs and explicitly mocked OpenAI transport; no trusted-flag injection."""

import httpx
import pymupdf
from sqlalchemy import text

from app.checkpoints import checkpoint_schema, setup_checkpoints
from app.extraction_client import OpenAIExtractor
from app.intake import create_intake
from app.worker import Worker, WorkerPolicy
from app.workflow import WorkflowProcessor
from scripts.extraction_fixtures import FIELDS
from tests.extraction_helpers import case, response, untrusted_extraction
from tests.financial_fixtures import POLICY


def invoice_pdf(data):
    rows = [
        (FIELDS[key], value)
        for key, value in data.items()
        if key != "line_items" and value is not None
    ]
    for line in data["line_items"]:
        rows.append((f"Line {line['line_no']} Number", str(line["line_no"])))
        rows.extend(
            (f"Line {line['line_no']} {FIELDS[key]}", value)
            for key, value in line.items()
            if key != "line_no" and value is not None
        )
    with pymupdf.open() as doc:
        page = doc.new_page()
        for i, (label, value) in enumerate(rows):
            page.insert_text((40, 50 + i * 24), f"{label}: {value}", fontsize=10)
        return doc.tobytes()


def missing_po():
    _, expected = case()
    expected = dict(expected, po_reference=None)
    return invoice_pdf(expected), expected


def mock_processor(engine, pdf, expected, *, crash_hook=lambda _: None):
    calls = []
    wire = untrusted_extraction(pdf, expected)

    def handle(request):
        calls.append(request)
        return response(wire)

    extractor = OpenAIExtractor(
        "test-only",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        ),
    )
    processor = WorkflowProcessor(
        engine, extractor, POLICY.version, source_mode="MOCK_OPENAI", crash_hook=crash_hook
    )
    return processor, calls


def execute(engine, processor):
    worker = Worker(engine, processor, WorkerPolicy(retry_seconds=0))
    claim = worker.claim()
    assert claim is not None
    try:
        from sqlalchemy.orm import Session

        from app.models import Document, Run

        with Session(engine) as s:
            pdf = s.get(Document, s.get(Run, claim.run_id).document_id).content
        processor(worker, claim, pdf)
    finally:
        claim.close()


def intake(engine, pdf):
    return create_intake(engine, pdf, None, None).run_id


def setup(engine):
    setup_checkpoints(engine)


def teardown(engine):
    with engine.begin() as c:
        c.execute(text(f'DROP SCHEMA "{checkpoint_schema(engine)}" CASCADE'))
