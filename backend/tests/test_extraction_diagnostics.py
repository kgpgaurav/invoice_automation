"""Generated documents/mocked outputs: diagnostic and repair regressions, not live accuracy."""

from copy import deepcopy
from decimal import Decimal

import httpx
import pymupdf
import pytest
from pydantic import ValidationError

from app.evidence_verification import repair_fields, verify
from app.extraction_client import ExtractionError
from app.extraction_evaluation import field_metrics, grounding_metrics
from app.extraction_repair import merge_repair, repair_model, schema_issues
from app.extraction_schema import InvoiceExtractionV1
from tests.extraction_helpers import case, payload, response, untrusted_extraction
from tests.ordinary_invoices import invoice
from tests.test_extraction import extractor


def field(checked, path):
    return next(p for p in checked.provenance if p["field"] == path)


def test_missing_extraction_is_distinct_from_absent_local_association():
    pdf, wire = invoice(po=None)
    data = wire.model_dump()
    data["invoice_date"] = None
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert field(checked, "invoice_date")["reason_code"] == "PRINTED_VALUE_NOT_EXTRACTED"
    assert field(checked, "po_reference")["reason_code"] == "NOT_EXTRACTED"
    assert repair_fields(checked) == ["invoice_date"]
    assert field(checked, "tax_total")["state"] == "DERIVED"
    assert field(checked, "tax_total")["original_value"] is None
    assert Decimal(field(checked, "tax_total")["normalized_value"]) == 1350


@pytest.mark.parametrize(
    "change,reason",
    [
        ("value", "SOURCE_VALUE_MISMATCH"),
        ("page", "CITATION_UNVERIFIED"),
    ],
)
def test_extracted_but_unverified_value_is_retained(change, reason):
    pdf, wire = invoice()
    data = wire.model_dump()
    if change == "value":
        data["total_gross"] = "1350"
    else:
        data["evidence"] = [
            dict(e, page=2) if e["field"] == "total_gross" else e for e in data["evidence"]
        ]
    original = deepcopy(data)
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert field(checked, "total_gross")["state"] == "UNVERIFIED"
    assert field(checked, "total_gross")["reason_code"] == reason
    assert field(checked, "total_gross")["original_value"] == data["total_gross"]
    assert repair_fields(checked) == ["total_gross"]
    assert data == original


def test_unrecognized_layout_is_not_reported_as_missing():
    _, wire = invoice()
    with pymupdf.open() as doc:
        doc.new_page().insert_text((50, 50), "Unconventional layout with no associated labels")
        pdf = doc.tobytes()
    checked = verify(wire, pdf)
    assert field(checked, "total_gross")["reason_code"] == "SOURCE_ASSOCIATION_UNSUPPORTED"
    assert field(checked, "total_gross")["state"] == "UNVERIFIED"
    assert repair_fields(checked) == []


def test_contradictory_source_and_printed_arithmetic_do_not_trigger_guessing():
    pdf, wire = invoice()
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        doc[0].insert_text((40, 550), "Grand total: INR 9900.00")
        conflict = doc.tobytes()
    checked = verify(wire, conflict)
    assert field(checked, "total_gross")["state"] == "AMBIGUOUS"
    assert "total_gross" not in repair_fields(checked)
    pdf, wire = invoice(total_adjust="1")
    checked = verify(wire, pdf)
    assert "ARITHMETIC_MISMATCH" in checked.findings
    assert field(checked, "total_gross")["state"] == "EXTRACTED"
    assert repair_fields(checked) == []


def test_scan_has_extracted_values_but_no_independent_grounding():
    pdf, truth = case("scan")
    wire = untrusted_extraction(pdf, truth)
    checked = verify(wire, pdf)
    assert field(checked, "total_gross")["reason_code"] == "NO_LOCAL_TEXT"
    assert field(checked, "total_gross")["original_value"] == wire.total_gross
    assert not any(p["grounded"] for p in checked.provenance)
    assert repair_fields(checked) == []


def test_financial_contract_errors_do_not_erase_extracted_values():
    pdf, wire = invoice()
    data = wire.model_dump()
    data["total_gross"] = "8850.001"
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.document is None
    gross = field(checked, "total_gross")
    assert gross["original_value"] == "8850.001"
    assert "decimal_max_places" in gross["financial_validation_errors"]
    assert "FINANCIAL_CONTRACT_INVALID" in checked.findings


def test_field_only_response_preserves_unrequested_values_and_evidence():
    pdf, wire = invoice()
    initial = wire.model_dump()
    model = repair_model(wire, ["invoice_date", "lines.1.quantity"])
    patch = model.model_validate(
        {
            "values": {"invoice_date": "2026-11-20", "lines.1.quantity": "3"},
            "evidence": [
                dict(field="invoice_date", raw_text="Nov 20, 2026", page=1, method="VISION")
            ],
        }
    )
    seen, attempts = [], []
    client = extractor(lambda request: (seen.append(payload(request)), response(patch))[1])
    repaired = client.extract(
        pdf,
        "pdf",
        attempts.append,
        previous=wire,
        repair_fields=["invoice_date", "lines.1.quantity"],
        max_attempts=1,
    )
    assert wire.model_dump() == initial
    assert repaired.total_gross == wire.total_gross and repaired.line_items == wire.line_items
    assert all(
        e in repaired.evidence
        for e in wire.evidence
        if e.field not in ("invoice_date", "lines.1.quantity")
    )
    schema = seen[0]["text"]["format"]["schema"]
    assert schema["$defs"]["InvoiceRepairValuesV1"]["required"] == [
        "invoice_date",
        "lines.1.quantity",
    ]
    assert attempts[0]["repair_fields"] == ["invoice_date", "lines.1.quantity"]
    with pytest.raises(ValidationError):
        model.model_validate(dict(patch.model_dump(), values={"invoice_date": None}))
    with pytest.raises(ValueError, match="unrequested"):
        merge_repair(
            wire,
            patch.model_copy(update={"evidence": [wire.evidence[0]]}),
            ["invoice_date", "lines.1.quantity"],
        )
    client.close()


def test_bad_patch_cannot_overwrite_a_previously_good_value_or_retry_past_budget():
    pdf, wire = invoice()
    data = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": wire.model_dump_json()},
                ],
            }
        ],
    }
    attempts = []
    client = extractor(lambda _: httpx.Response(200, json=data))
    with pytest.raises(ExtractionError, match="EXTRACTION_SCHEMA_INVALID"):
        client.extract(
            pdf,
            previous=wire,
            repair_fields=["invoice_date"],
            record=attempts.append,
            max_attempts=1,
        )
    assert len(attempts) == 1 and attempts[0]["schema_issues"]
    assert wire.invoice_date == "2026-11-20"
    client.close()


@pytest.mark.parametrize(
    "prompt,expected_type",
    [
        ("invoice-extract-3", "input_file"),
        ("invoice-extract-2", "input_text"),
    ],
)
def test_scan_routing_is_versioned_and_actual_input_path_recorded(prompt, expected_type):
    pdf, truth = case("scan")
    seen, attempts = [], []
    client = extractor(
        lambda request: (seen.append(payload(request)), response(untrusted_extraction(pdf, truth)))[
            1
        ]
    )
    client.extract(pdf, "text", attempts.append, prompt_version=prompt)
    assert seen[0]["input"][0]["content"][0]["type"] == expected_type
    assert attempts[0]["input_path"].startswith(
        "pdf:" if expected_type == "input_file" else "text:"
    )
    client.close()


def test_schema_errors_exclude_sensitive_values_and_arbitrary_keys():
    pdf, truth = case()
    data = untrusted_extraction(pdf, truth).model_dump()
    data["do-not-log-secret-key"] = "do-not-log-secret-value"
    with pytest.raises(ValidationError) as error:
        InvoiceExtractionV1.model_validate(data)
    assert schema_issues(error.value) == [{"path": "?", "code": "extra_forbidden"}]


def test_frozen_verifiers_have_identical_financial_results():
    pdf, wire = invoice()
    old, new = verify(wire, pdf, version="layout-grounding-4"), verify(wire, pdf)
    assert old.document == new.document and old.findings == new.findings
    assert all("state" not in p for p in old.provenance)


def test_completeness_is_distinct_from_accuracy_and_grounding_requires_labels():
    score = field_metrics(
        {"total_gross": "10", "invoice_date": "2026-11-20"},
        {"total_gross": "99", "invoice_date": None},
    )
    assert score["accuracy"] == "0" and score["completeness"] == "0.5"
    assert field_metrics({}, {})["accuracy"] is None
    assert (
        field_metrics(
            {"tax_mode": "UNKNOWN", "line_items": []}, {"tax_mode": "UNKNOWN", "line_items": []}
        )["completeness"]
        is None
    )
    assert (
        grounding_metrics(
            {"total_gross": False, "invoice_date": True},
            [
                {"field": "total_gross", "grounded": True},
                {"field": "invoice_date", "grounded": True},
            ],
        )["precision"]
        == "0.5"
    )
