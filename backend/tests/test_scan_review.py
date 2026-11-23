"""A fully verifiable OCR overlay still cannot authorize a scanned invoice."""

import pymupdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval import approve
from app.document_classification import scan_pages
from app.evidence_verification import verify
from app.finance_rules import critical_check
from app.financial_models import ApprovalLedger
from app.models import Run
from tests.extraction_helpers import case, untrusted_extraction
from tests.financial_fixtures import POLICY, masters, run
from tests.workflow_helpers import execute, intake, mock_processor


def raster_overlay(pdf, *, logo=False):
    with pymupdf.open(stream=pdf, filetype="pdf") as source, pymupdf.open() as target:
        for page in source:
            new = target.new_page(width=page.rect.width, height=page.rect.height)
            bounds = pymupdf.Rect(5, 5, 25, 25) if logo else new.rect
            new.insert_image(bounds, stream=page.get_pixmap().tobytes("png"))
            new.show_pdf_page(new.rect, source, page.number)
        return target.tobytes()


def test_scan_policy_holds_even_with_every_required_field_verified(database):
    engine = database[0]
    masters(engine)
    pdf, expected = case()
    scanned = raster_overlay(pdf)
    raw = untrusted_extraction(scanned, expected)
    old = verify(raw, scanned, version="semantic-diagnostics-6")
    assert critical_check(old.document) is None
    checked = verify(raw, scanned)
    assert scan_pages(scanned) == (1,)
    assert all(e.verified for e in checked.document.evidence)
    assert critical_check(checked.document).code == "SCANNED_DOCUMENT_REQUIRES_REVIEW"
    assert (
        approve(engine, run(engine, scanned), old.document, POLICY.version).decision
        == "NEEDS_REVIEW"
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0


def test_small_logo_does_not_force_scan_review():
    pdf, expected = case()
    digital = raster_overlay(pdf, logo=True)
    assert scan_pages(digital) == ()
    assert not verify(untrusted_extraction(digital, expected), digital).needs_review


def test_mixed_document_requires_review():
    pdf, _ = case()
    scanned = raster_overlay(pdf)
    with (
        pymupdf.open(stream=pdf, filetype="pdf") as digital,
        pymupdf.open(stream=scanned, filetype="pdf") as scan,
    ):
        digital.insert_pdf(scan)
        assert scan_pages(digital.tobytes()) == (2,)


def test_workflow_interrupts_verified_scan_without_second_model_request(workflow_db):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    scanned = raster_overlay(pdf)
    ident = intake(engine, scanned)
    processor, calls = mock_processor(engine, scanned, expected)
    execute(engine, processor)
    assert len(calls) == 1
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "NEEDS_REVIEW"
        assert session.get(Run, ident).job_state == "WAITING_REVIEW"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
