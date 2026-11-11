from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.evidence_verification import verify
from app.extraction_client import ExtractionError, OpenAIExtractor, Rates, estimated_cost
from app.extraction_evaluation import field_metrics
from app.extraction_schema import InvoiceExtractionV1, output_format
from app.pdf_input import inspect_pdf
from tests.extraction_helpers import case, payload, response, untrusted_extraction


def extractor(handler):
    return OpenAIExtractor(
        "unit-test-key",
        "test-model",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
        ),
        sleep=lambda _: None,
    )


def test_schema_required_nullable_and_no_model_trust_fields():
    schema = output_format()["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        assert set(definition["required"]) == set(definition["properties"])
    pdf, truth = case()
    data = untrusted_extraction(pdf, truth).model_dump()
    for key in ("confidence", "verified", "decision", "bbox"):
        with pytest.raises(ValidationError):
            InvoiceExtractionV1.model_validate(dict(data, **{key: True}))
    data["evidence"][0]["verified"] = True
    with pytest.raises(ValidationError):
        InvoiceExtractionV1.model_validate(data)


def test_responses_request_shape_and_measured_usage():
    pdf, truth = case()
    extraction = untrusted_extraction(pdf, truth)
    seen, attempts = [], []

    def handler(request):
        seen.append(payload(request))
        return response(extraction)

    client = extractor(handler)
    assert client.extract(pdf, "pdf", attempts.append) == extraction
    assert seen[0]["store"] is False and "tools" not in seen[0]
    assert seen[0]["text"]["format"]["strict"] is True
    assert seen[0]["input"][0]["content"][0]["file_data"].startswith("data:application/pdf;base64,")
    assert attempts[0]["usage"]["input_tokens"] == 100
    assert attempts[0]["estimated_cost_usd"] is None
    assert attempts[0]["prompt_version"] and attempts[0]["schema_version"]
    client.close()


@pytest.mark.parametrize(
    "status,retries", [(401, 1), (403, 1), (404, 1), (400, 1), (429, 2), (500, 2)]
)
def test_provider_failures_are_bounded_sanitized_and_recorded(status, retries):
    pdf, _ = case()
    attempts = []
    client = extractor(
        lambda _: httpx.Response(status, json={"error": "sensitive invoice/key text"})
    )
    with pytest.raises(ExtractionError, match=f"OPENAI_HTTP_{status}") as failure:
        client.extract(pdf, record=attempts.append)
    assert len(attempts) == retries and "sensitive" not in str(failure.value)
    assert all(a["usage"] is None and a["estimated_cost_usd"] is None for a in attempts)
    client.close()


def test_timeout_then_success_and_schema_retry_share_two_attempt_budget():
    pdf, truth = case()
    seen, attempts = [], []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            raise httpx.ReadTimeout("private detail")
        return response(untrusted_extraction(pdf, truth))

    client = extractor(handler)
    client.extract(pdf, record=attempts.append)
    assert len(attempts) == 2 and attempts[0]["error_code"] == "OPENAI_TRANSIENT_ERROR"
    client.close()


@pytest.mark.parametrize(
    "body,code,count",
    [
        ({"status": "completed", "output": []}, "EXTRACTION_SCHEMA_INVALID", 2),
        ({"status": "incomplete", "usage": None}, "OPENAI_INCOMPLETE", 1),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal"}]}],
            },
            "OPENAI_REFUSAL",
            1,
        ),
        (["unexpected"], "OPENAI_RESPONSE_INVALID", 1),
    ],
)
def test_malformed_refused_and_incomplete_responses(body, code, count):
    pdf, _ = case()
    attempts = []
    client = extractor(lambda _: httpx.Response(200, json=body))
    with pytest.raises(ExtractionError, match=code):
        client.extract(pdf, record=attempts.append)
    assert len(attempts) == count
    client.close()


def test_local_verification_ignores_model_method_and_checks_field_association():
    pdf, truth = case()
    extraction = untrusted_extraction(pdf, truth)
    checked = verify(extraction, pdf)
    assert not checked.needs_review
    assert all(e.method == "TEXT" and e.verified for e in checked.document.evidence)
    data = extraction.model_dump()
    data["total_gross"] = "1800.00"  # amount is present elsewhere, but belongs to tax
    assert verify(InvoiceExtractionV1.model_validate(data), pdf).needs_review
    data = extraction.model_dump()
    data["evidence"] = [dict(e, page=5) for e in data["evidence"]]
    assert verify(InvoiceExtractionV1.model_validate(data), pdf).needs_review


@pytest.mark.parametrize("name", ["missing", "scan", "inconsistent", "unsupported"])
def test_schema_validity_is_not_factual_correctness(name):
    pdf, truth = case(name)
    checked = verify(untrusted_extraction(pdf, truth), pdf)
    assert checked.needs_review
    if name == "scan":
        assert not any(p.strip() for p in inspect_pdf(pdf).pages)
        assert not any(p["grounded"] for p in checked.provenance)
    if name == "unsupported":
        assert checked.document.currency == "USD"
    if name == "missing":
        assert checked.document.invoice_date is None
    if name == "inconsistent":
        assert "ARITHMETIC_MISMATCH" in checked.findings


def test_numeric_strings_and_missing_fields_are_preserved():
    pdf, truth = case()
    data = untrusted_extraction(pdf, truth).model_dump()
    data["total_gross"] = 11800.0
    with pytest.raises(ValidationError):
        InvoiceExtractionV1.model_validate(data)
    data["total_gross"] = None
    assert InvoiceExtractionV1.model_validate(data).total_gross is None


def test_metrics_count_missing_and_invented_values_and_decimal_equivalence():
    assert field_metrics({"total_gross": "1.00"}, {"total_gross": "1"})["accuracy"] == "1"
    metrics = field_metrics(
        {"invoice_date": None, "total_gross": "10.00"},
        {"invoice_date": "2026-01-01", "total_gross": None},
    )
    assert metrics["missing_fields"] == ["total_gross"]
    assert metrics["invented_fields"] == ["invoice_date"]


def test_costs_are_derived_only_from_returned_usage_and_supplied_rates():
    rates = Rates(Decimal("1"), Decimal("0.1"), Decimal("5"), "dated test rate")
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "input_tokens_details": {"cached_tokens": 20},
    }
    assert estimated_cost(usage, rates) == Decimal("0.000332")
    assert estimated_cost(None, rates) is None
    assert estimated_cost(usage, None) is None
    usage["input_tokens_details"]["cached_tokens"] = 101
    assert estimated_cost(usage, rates) is None


def test_cache_writes_are_priced_separately_and_float_rates_rejected():
    rates = Rates(Decimal("1"), Decimal("0.1"), Decimal("5"), "test", Decimal("1.25"))
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 30},
    }
    assert estimated_cost(usage, rates) == Decimal("0.0003395")
    no_write_price = Rates(Decimal("1"), Decimal("0.1"), Decimal("5"), "test")
    assert estimated_cost(usage, no_write_price) is None
    with pytest.raises(ValueError):
        Rates(1.0, Decimal("0"), Decimal("1"), "float forbidden")
