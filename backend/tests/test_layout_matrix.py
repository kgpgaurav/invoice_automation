"""Independent generated variations; no vendor-specific runtime fixes or live provider use."""

import pytest

from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV12
from app.finance_rules import critical_check
from tests.ordinary_invoices import invoice


@pytest.mark.parametrize("layout", ["stacked", "percentage", "footer", "split"])
@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize("inclusive", [True, False])
@pytest.mark.parametrize("qty", ["1", "3"])
def test_generated_layout_tax_and_row_variations(layout, numbered, inclusive, qty):
    pdf, wire = invoice(layout=layout, numbered=numbered, inclusive=inclusive, qty=qty)
    checked = verify(InvoiceExtractionV12.model_validate(wire.model_dump()), pdf)
    assert checked.findings == ()
    assert critical_check(checked.document) is None
