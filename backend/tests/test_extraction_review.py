import pytest

from app.approval import approve
from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV1
from tests.extraction_helpers import case
from tests.financial_fixtures import POLICY, masters, run


@pytest.mark.parametrize("layout", ["clean", "alternate"])
def test_independently_evidenced_pdf_is_eligible_for_financial_assessment(database, layout):
    # Evidence built independently of the verifier/parser, like a model response.
    pdf, expected = case(layout)
    fields = {k: v for k, v in expected.items() if k != "line_items" and v is not None}
    for line in expected["line_items"]:
        fields.update(
            {
                f"lines.{line['line_no']}.{k}": str(v)
                for k, v in line.items()
                if k != "line_no" and v is not None
            }
        )
    wire = InvoiceExtractionV1.model_validate(
        dict(
            expected,
            evidence=[
                {"field": key, "raw_text": str(value), "page": 1, "method": "TEXT"}
                for key, value in fields.items()
            ],
        )
    )
    checked = verify(wire, pdf)
    assert checked.findings == ()
    assert all(p["grounded"] for p in checked.provenance if p["state"] != "MISSING")
    engine = database[0]
    masters(engine)
    assert (
        approve(engine, run(engine, pdf), checked.document, POLICY.version).decision == "APPROVED"
    )


def test_malformed_decimal_separator_is_not_trusted():
    from app.evidence_verification import value_matches

    assert not value_matches("total_gross", "123", "1,23")
    assert value_matches("total_gross", "123000", "1,23,000")
