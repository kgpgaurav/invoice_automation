from copy import deepcopy

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.financial_models import ApprovalLedger
from app.models import Run
from app.workflow_models import ReviewRequest
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.workflow_helpers import execute, intake, mock_processor


@pytest.mark.parametrize("field", ["bank_account_last4", "po_reference", "vendor_tax_id", "sku"])
def test_printed_optional_value_cannot_be_dropped_to_bypass_rules(workflow_db, field):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    omitted = deepcopy(expected)
    if field == "sku":
        omitted["line_items"][0][field] = None
    else:
        omitted[field] = None
    run_id = intake(engine, pdf)
    processor, calls = mock_processor(engine, pdf, omitted)
    execute(engine, processor)
    with Session(engine) as session:
        assert session.get(Run, run_id).decision == "NEEDS_REVIEW"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        request = session.scalar(select(ReviewRequest).where(ReviewRequest.run_id == run_id))
        assert request.kind == "EVIDENCE_OR_POLICY" and request.options_json == []
    assert len(calls) == 2  # One bounded source repair, then review; no financial waiver.
