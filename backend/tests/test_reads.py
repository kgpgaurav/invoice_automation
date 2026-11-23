import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import append_event
from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV12
from app.financial_models import ApprovalLedger
from app.main import create_app
from app.models import QueueItem, Run
from app.read_service import processing_time
from app.streaming import event_stream
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.ordinary_invoices import invoice
from tests.test_ordinary_invoices import ordinary_masters
from tests.test_ordinary_workflow import processor as ordinary_processor
from tests.workflow_helpers import execute, intake, mock_processor


def test_history_keyset_filters_and_auth(client, database, pdf):
    engine = database[0]
    ids = [intake(engine, pdf) for _ in range(4)]
    with Session(engine) as session, session.begin():
        timestamp = datetime(2026, 11, 1, tzinfo=UTC)
        for ident in ids:
            session.get(Run, ident).created_at = timestamp
    first = client.get("/api/v1/runs?limit=2").json()
    assert first["total_count"] == 4 and len(first["items"]) == 2
    intake(engine, pdf)  # new arrival must not duplicate earlier pages
    second = client.get("/api/v1/runs", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    found = [row["run_id"] for row in first["items"] + second["items"]]
    assert len(set(found)) == 4 and set(found) == {str(i) for i in ids}
    assert client.get("/api/v1/runs?decision=APPROVED").json()["total_count"] == 0
    assert client.get("/api/v1/runs?state=QUEUED").json()["total_count"] == 5
    for query in ("limit=0", "state=PAID", "cursor=bad", "cursor=W10"):
        assert client.get("/api/v1/runs?" + query).status_code == 422
    assert (
        client.get(
            "/api/v1/runs", params={"cursor": first["next_cursor"], "state": "QUEUED"}
        ).status_code
        == 422
    )
    client.headers.clear()
    for path in (
        "/runs",
        "/dashboard/summary",
        f"/runs/{ids[0]}/document",
        f"/runs/{ids[0]}/events/stream",
    ):
        assert client.get("/api/v1" + path).status_code == 401


def test_detail_pdf_and_events_never_expose_private_fields(workflow_db, settings):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    run_id = intake(engine, pdf)
    processor, _ = mock_processor(engine, pdf, expected)
    execute(engine, processor)
    with Session(engine) as s, s.begin():
        append_event(
            s,
            run_id,
            "privacy",
            "STAGE_FINISHED",
            {"operation": "AUDIT", "bank_account": "PRIVATE-BANK", "raw_text": "PRIVATE-SNIPPET"},
        )
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["approved_gross"] == "11800.00"
        assert (
            data["source_mode"] == "MOCK_OPENAI"
            and data["usage"]["cost_status"] == "not_applicable"
        )
        assert all(
            f["verification"] == "verified" for f in data["fields"] if f["required_for_approval"]
        )
        assert any(
            f["verification"] == "missing" and not f["required_for_approval"]
            for f in data["fields"]
        )
        assert all("bank" not in f["field"] for f in data["fields"])
        assert data["purchase_order"]["remaining_gross"] == "38200.00"
        assert data["purchase_order"]["relationship"] == "APPROVED_ALLOCATION"
        assert data["processing_time_status"] == "measured"
        for suffix in ("", "/events", "/events/stream"):
            text = client.get(f"/api/v1/runs/{run_id}{suffix}").text
            assert "PRIVATE-BANK" not in text and "PRIVATE-SNIPPET" not in text
            assert "raw_text" not in text and "extraction_json" not in text
        document = client.get(f"/api/v1/runs/{run_id}/document")
        assert document.content == pdf and document.headers["cache-control"] == "no-store"
        assert document.headers["content-type"] == "application/pdf"
        assert client.get(f"/api/v1/runs/{uuid4()}/document").status_code == 404


def test_sse_reconnect_uses_persisted_sequence_and_validates_cursor(client, database, pdf):
    engine = database[0]
    run_id = intake(engine, pdf)
    with Session(engine) as s, s.begin():
        s.scalar(select(QueueItem)).status = "DONE"
        for i in range(3):
            append_event(s, run_id, str(i), "STAGE_FINISHED", {"operation": "TEST"})
    path = f"/api/v1/runs/{run_id}/events/stream"
    result = client.get(path, params={"after_seq": 1}, headers={"Last-Event-ID": "2"})
    assert result.status_code == 200 and result.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert [line for line in result.text.splitlines() if line.startswith("id:")] == [
        "id: 3",
        "id: 4",
    ]
    again = client.get(path, headers={"Last-Event-ID": "4"})
    assert "id:" not in again.text and "caught_up" in again.text
    for headers in ({"Last-Event-ID": "bad"}, {"Last-Event-ID": "-1"}, {"Last-Event-ID": "100"}):
        assert client.get(path, headers=headers).status_code == 422
    assert client.get(f"/api/v1/runs/{uuid4()}/events/stream").status_code == 404


def test_supported_values_survive_an_unrelated_financial_contract_failure(workflow_db, settings):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, raw = invoice(layout="footer", numbered=False)
    data = raw.model_dump()
    data["line_items"][0]["unit_price"] = "2500.00001"
    wire = InvoiceExtractionV12.model_validate(data)
    checked = verify(wire, pdf)
    assert checked.document is None and "FINANCIAL_CONTRACT_INVALID" in checked.findings
    ident = intake(engine, pdf)
    handler, _ = ordinary_processor(engine, wire)
    execute(engine, handler)
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        detail = client.get(f"/api/v1/runs/{ident}").json()
    fields = {f["field"]: f for f in detail["fields"]}
    assert detail["decision"] == "NEEDS_REVIEW" and detail["approved_gross"] is None
    assert fields["tax_total"]["value"] == "1350.00"
    assert fields["tax_total"]["original_value"] is None
    assert fields["tax_total"]["verification"] == "verified"
    assert fields["tax_total"]["extraction_state"] == "DERIVED"
    assert fields["tax_total"]["calculation"] and fields["tax_total"]["pages"] == [1]
    assert fields["lines.1.quantity"]["verification"] == "verified"
    assert fields["lines.1.tax_amount"]["value"] == "1350.00"
    assert fields["lines.1.tax_amount"]["origin"] == "derived"
    assert fields["lines.1.unit_price"]["value"] == "2500.00001"
    assert fields["lines.1.unit_price"]["financial_validation_errors"]
    with Session(engine) as session:
        assert session.scalar(select(ApprovalLedger)) is None


def test_stream_cancel_releases_connections(database, pdf):
    engine = database[0]
    run_id = intake(engine, pdf)

    async def consume():
        stream = event_stream(engine, run_id, 0, poll_seconds=0.01)
        assert (await anext(stream)).startswith("retry:")
        assert "id: 1" in await anext(stream)
        await stream.aclose()

    asyncio.run(consume())
    assert engine.pool.checkedout() == 0


def test_dashboard_overrun_is_recorded_deduplicated_and_not_savings(workflow_db, settings):
    engine = workflow_db
    masters(engine, cap="1000")
    pdf, expected = case()
    processor, _ = mock_processor(engine, pdf, expected)
    for _ in range(2):
        intake(engine, pdf)
        execute(engine, processor)
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["total_runs"] == 2 and summary["awaiting_review"] == 2
        assert summary["overrun_known_identities"] == 1
        assert summary["potential_po_overrun_inr"] == "10800.00"
        assert (
            summary["actual_billed_cost_usd"] is None and summary["estimated_api_cost_usd"] is None
        )
        assert summary["processing_time_sample_count"] == 2
    # A later master amendment cannot rewrite the immutable observed excess.
    from app.financial_models import PurchaseOrder

    with Session(engine) as session, session.begin():
        session.scalar(select(PurchaseOrder)).approved_cap_gross = 20000
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        assert (
            client.get("/api/v1/dashboard/summary").json()["potential_po_overrun_inr"] == "10800.00"
        )


def test_legacy_observations_stay_unknown_after_migration(workflow_db, database, settings):
    from alembic import command

    engine, config = database
    masters(engine, cap="1000")
    pdf, expected = case()
    intake(engine, pdf)
    execute(engine, mock_processor(engine, pdf, expected)[0])
    # Round-trip the additive column with retained history, like a pre-Slice-6 assessment.
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005_workflow")
        command.upgrade(config, "head")
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["potential_po_overrun_inr"] is None
        assert summary["overrun_unknown_identities"] == 1


def test_processing_duration_excludes_review_wait_and_unknown_crash_interval():
    now = datetime.now(UTC)

    def event(seconds, operation="", type="STAGE_FINISHED", key=None):
        return SimpleNamespace(
            occurred_at=now + timedelta(seconds=seconds),
            payload_json={"operation": operation},
            type=type,
            event_key=key,
        )

    rows = [
        event(0, "WORKER_CLAIM"),
        event(10, type="REVIEW_REQUESTED"),
        event(200, "WORKER_CLAIM"),
        event(205, type="RUN_COMPLETED"),
    ]
    assert processing_time(rows) == (15000, "measured")
    assert processing_time([event(0, "WORKER_CLAIM"), event(200, "LEASE_EXPIRED")]) == (
        None,
        "incomplete",
    )
