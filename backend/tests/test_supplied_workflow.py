"""Opt-in private-PDF workflow replay in disposable PostgreSQL schemas; zero model calls."""

import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval import register_policy
from app.extraction_client import OpenAIExtractor
from app.extraction_schema import InvoiceExtractionV12
from app.financial_models import ApprovalLedger, POLine, PurchaseOrder, Vendor
from app.models import Run
from app.review_contracts import ReviewResponse
from app.reviews import respond
from app.worker import Worker
from app.workflow import WorkflowProcessor
from app.workflow_models import ReviewRequest, WorkflowRun
from tests.extraction_helpers import response
from tests.financial_fixtures import POLICY
from tests.test_scan_review import raster_overlay
from tests.workflow_helpers import execute, intake

MANIFEST = os.environ.get("PS1_SUPPLIED_INVOICE_LABELS")
REPORT = os.environ.get("PS1_SUPPLIED_INVOICE_REPORT")
CASES = json.loads(Path(MANIFEST).read_text(encoding="utf-8")) if MANIFEST else [{}]


@pytest.mark.skipif(not MANIFEST or not REPORT, reason="Private supplied-invoice replay is opt-in")
@pytest.mark.parametrize("label", CASES, ids=[f"private-case-{i + 1}" for i in range(len(CASES))])
@pytest.mark.parametrize("scan", ["digital", "ocr_overlay", "image_only"])
def test_private_invoice_full_workflow_keeps_financial_and_scan_safeguards(
    workflow_db, label, scan
):
    engine = workflow_db
    source = (Path(MANIFEST).resolve().parent / label["source_pdf"]).read_bytes()
    report = json.loads(Path(REPORT).read_text(encoding="utf-8"))
    case = next(c for c in report["cases"] if c["fixture"] == label["fixture_id"])
    artifact = json.loads(Path(case["private_extraction_artifact"]).read_text(encoding="utf-8"))
    assert artifact["mode"] == "LIVE_OPENAI"
    assert artifact["document_sha256"] == hashlib.sha256(source).hexdigest()
    # Optional V1.2 fields default to null in a labelled compatibility replay of
    # an older extraction. This never claims the new prompt ran live.
    wire = InvoiceExtractionV12.model_validate(artifact["extraction"])
    expected = label["expected_financial_fields"]
    register_policy(engine, POLICY, "fixture-private-replay")
    with Session(engine) as session, session.begin():
        vendor = Vendor(
            id=uuid4(),
            legal_name=expected["vendor_name"],
            jurisdiction="IN",
            tax_id_original=expected["vendor_tax_id"],
            normalized_tax_id=expected["vendor_tax_id"],
        )
        session.add(vendor)
        session.flush()
        po = PurchaseOrder(
            id=uuid4(),
            po_number=expected["po_reference"] or "EXPLICIT-REPLAY-CANDIDATE",
            vendor_id=vendor.id,
            issued_at=date(2023, 1, 1),
            approved_cap_gross=Decimal(label["workflow_test_po_cap"]),
        )
        session.add(po)
        session.flush()
        po_id = po.id
        for i, line in enumerate(expected["line_items"], 1):
            session.add(
                POLine(
                    id=uuid4(),
                    po_id=po.id,
                    line_no=i,
                    sku=line["sku"],
                    description=line["description"],
                    quantity=Decimal(line["quantity"]),
                    unit_price=Decimal(line["unit_price"]),
                    tax_rate=Decimal(line["tax_rate"]),
                )
            )
    if scan == "ocr_overlay":
        source = raster_overlay(source)
    elif scan == "image_only":
        with pymupdf.open(stream=source, filetype="pdf") as old, pymupdf.open() as new:
            for page in old:
                output = new.new_page(width=page.rect.width, height=page.rect.height)
                output.insert_image(output.rect, stream=page.get_pixmap().tobytes("png"))
            source = new.tobytes()
    calls = []

    def handle(request):
        calls.append(request)
        return response(wire)

    extractor = OpenAIExtractor(
        "explicit-private-replay",
        "test-model",
        httpx.Client(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)),
    )
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    ident = intake(engine, source)
    execute(engine, processor)
    expected_decision = label["workflow_expected_decision"] if scan == "digital" else "NEEDS_REVIEW"
    with Session(engine) as session:
        run = session.get(Run, ident)
        thread = run.thread_id
        assert run.decision == expected_decision
        ledger_count = session.scalar(select(func.count()).select_from(ApprovalLedger))
        assert ledger_count == int(expected_decision == "APPROVED")
        assert session.get(WorkflowRun, ident).source_mode == "MOCK_OPENAI"
        if scan != "digital":
            assert "Scanned" in run.reason
        request = session.scalar(
            select(ReviewRequest).where(
                ReviewRequest.run_id == ident, ReviewRequest.status == "OPEN"
            )
        )
        request_id = request.id if request else None
        generation = request.generation if request else None
        before = session.get(PurchaseOrder, po_id).committed_gross
    assert len(calls) == 1
    assert Worker(engine, processor).run_once() is False
    if request_id:
        respond(
            engine,
            request_id,
            ReviewResponse(
                generation=generation,
                action="REQUEST_INFO",
                payload={},
                reason="Explicit replay fixture stopped without financial authorization.",
            ),
            "private-replay-stop",
            "configured-reviewer",
        )
        execute(engine, processor)
        with Session(engine) as session:
            assert session.get(Run, ident).thread_id == thread
            assert session.get(Run, ident).job_state == "INTERRUPTED"
            assert session.get(PurchaseOrder, po_id).committed_gross == before
    assert len(calls) == 1
    extractor.close()
