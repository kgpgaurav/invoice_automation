import httpx
import pymupdf
import pytest

from app.evidence_verification import verify
from app.extraction_client import ExtractionError, OpenAIExtractor
from app.extraction_schema import InvoiceExtractionV1
from app.finance_rules import critical_check
from app.pdf_input import inspect_pdf
from tests.extraction_helpers import case, untrusted_extraction


def test_review_document_cannot_bypass_findings_with_trusted_flags():
    pdf, truth = case("inconsistent")
    checked = verify(untrusted_extraction(pdf, truth), pdf)
    assert checked.needs_review and checked.document
    assert not any(e.verified for e in checked.document.evidence)
    assert critical_check(checked.document).decision == "NEEDS_REVIEW"


def test_masked_bank_snippet_is_grounded_only_to_exact_local_last4():
    pdf, truth = case()
    data = untrusted_extraction(pdf, truth).model_dump()
    for item in data["evidence"]:
        if item["field"] == "bank_account_last4":
            item["raw_text"] = "****1234"
    assert not verify(InvoiceExtractionV1.model_validate(data), pdf).needs_review
    data["bank_account_last4"] = "9876"
    assert verify(InvoiceExtractionV1.model_validate(data), pdf).needs_review


def test_duplicate_labels_and_wrong_field_snippets_do_not_ground():
    pdf, truth = case()
    original = untrusted_extraction(pdf, truth)
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        document[0].insert_text((40, 750), "Total Gross: 1.00")
        duplicate = document.tobytes()
    checked = verify(original, duplicate)
    assert checked.needs_review
    assert not next(p for p in checked.provenance if p["field"] == "total_gross")["grounded"]
    raw = original.model_dump()
    for evidence in raw["evidence"]:
        if evidence["field"] == "total_gross":
            evidence["raw_text"] = "Tax Total: 1800.00"
    assert verify(InvoiceExtractionV1.model_validate(raw), pdf).needs_review


def test_invalid_financial_precision_and_unknown_basis_are_held():
    pdf, truth = case()
    raw = untrusted_extraction(pdf, truth).model_dump()
    raw["line_items"][0]["price_basis"] = None
    assert verify(InvoiceExtractionV1.model_validate(raw), pdf).document is None
    raw = untrusted_extraction(pdf, truth).model_dump()
    raw["total_gross"] = "11800.001"
    assert verify(InvoiceExtractionV1.model_validate(raw), pdf).needs_review


def test_markdown_route_and_page_text_remain_separate():
    pdf, _ = case("alternate")
    local = inspect_pdf(pdf, "markdown")
    assert "pymupdf4llm" in local.path_version
    assert "Invoice" in local.text and len(local.pages) == 1
    with pytest.raises(ValueError):
        inspect_pdf(pdf, "other-provider")


def test_configuration_missing_never_makes_call():
    with pytest.raises(ExtractionError, match="CONFIGURATION_MISSING"):
        OpenAIExtractor(None, "test-model")


def test_no_schema_retry_after_inconsistent_but_valid_extraction():
    from tests.extraction_helpers import response

    pdf, truth = case("inconsistent")
    attempts = []
    client = OpenAIExtractor(
        "test",
        "test-model",
        httpx.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx.MockTransport(lambda _: response(untrusted_extraction(pdf, truth))),
        ),
    )
    extraction = client.extract(pdf, record=attempts.append)
    assert verify(extraction, pdf).needs_review and len(attempts) == 1
    client.close()
