from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.approval import ApprovalConflict, approve
from app.evidence_verification import VERIFIER_VERSION
from app.extraction_schema import PROMPT_VERSION, SCHEMA_VERSION
from app.financial_models import ApprovalLedger, PurchaseOrder
from app.intake import create_intake
from app.owned_finalizer import finalize_owned
from app.worker import Claim, LostLease, Worker
from app.workflow_models import WorkflowRun
from tests.extraction_helpers import case, untrusted_extraction
from tests.financial_fixtures import POLICY, masters


def prepared(engine):
    pdf, expected = case()
    _, po_id, _ = masters(engine)
    run_id = create_intake(engine, pdf, None, None).run_id
    wire = untrusted_extraction(pdf, expected)
    with Session(engine) as s, s.begin():
        s.add(
            WorkflowRun(
                run_id=run_id,
                policy_version=POLICY.version,
                model_id="test-model",
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                verifier_version=VERIFIER_VERSION,
                route="pdf",
                extraction_json=wire.model_dump(),
            )
        )
    worker = Worker(engine, lambda *_: None)
    claim = worker.claim()
    return worker, claim, po_id, wire


def test_owned_transaction_posts_once_without_bypassing_fixture_api(database):
    engine = database[0]
    worker, claim, po_id, wire = prepared(engine)
    try:
        with pytest.raises(ApprovalConflict):
            from app.evidence_verification import verify
            from tests.extraction_helpers import case

            approve(engine, claim.run_id, verify(wire, case()[0]).document, POLICY.version)
        result = finalize_owned(worker, claim)
        assert result.decision == "APPROVED"
        assert finalize_owned(worker, claim) == result
        with Session(engine) as s:
            assert s.get(PurchaseOrder, po_id).committed_gross == Decimal("11800")
            assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
    finally:
        claim.close()


def test_owner_attempt_lease_and_physical_connection_are_all_required(database):
    engine = database[0]
    worker, claim, _, _ = prepared(engine)
    connection = engine.connect()
    fake = Claim(claim.job_id, claim.run_id, claim.owner, claim.attempt, connection)
    try:
        with pytest.raises(LostLease):
            finalize_owned(worker, fake)
        with engine.begin() as c:
            c.execute(
                text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'")
            )
        with pytest.raises(LostLease):
            finalize_owned(worker, claim)
        with Session(engine) as s:
            assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    finally:
        fake.close()
        claim.close()


def test_expiry_during_finalization_rolls_back_every_financial_write(database, monkeypatch):
    import app.owned_finalizer as finalizer

    engine = database[0]
    worker, claim, po_id, _ = prepared(engine)
    original = finalizer.assess_transaction

    def expire_after_writes(session, *args, **kwargs):
        result = original(session, *args, **kwargs)
        session.execute(
            text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'")
        )
        return result

    monkeypatch.setattr(finalizer, "assess_transaction", expire_after_writes)
    try:
        with pytest.raises(LostLease):
            finalize_owned(worker, claim)
        with Session(engine) as s:
            assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
            assert s.get(PurchaseOrder, po_id).committed_gross == 0
        monkeypatch.setattr(finalizer, "assess_transaction", original)
        assert finalize_owned(worker, claim).decision == "APPROVED"
    finally:
        claim.close()


def test_unlocking_physical_session_or_wrong_attempt_fails_closed(database):
    engine = database[0]
    worker, claim, _, _ = prepared(engine)
    try:
        false_attempt = Claim(
            claim.job_id, claim.run_id, claim.owner, claim.attempt + 1, claim.connection
        )
        with pytest.raises(LostLease):
            finalize_owned(worker, false_attempt)
        claim.connection.execute(text("SELECT pg_advisory_unlock_all()"))
        claim.connection.commit()
        with pytest.raises(LostLease):
            finalize_owned(worker, claim)
    finally:
        claim.close()


def test_shared_body_cannot_be_used_as_unfenced_production_entrypoint(database):
    from app.approval import assess_transaction
    from app.evidence_verification import verify
    from app.models import Run

    engine = database[0]
    worker, claim, _, wire = prepared(engine)
    try:
        with Session(engine) as s, s.begin(), pytest.raises(ApprovalConflict, match="fenced"):
            assess_transaction(
                s,
                s.get(Run, claim.run_id),
                verify(wire, case()[0]).document,
                POLICY.version,
                "untrusted",
                {},
                production=True,
            )
    finally:
        claim.close()
