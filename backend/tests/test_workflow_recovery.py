import os
import subprocess
import sys

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger, PurchaseOrder
from app.models import Document, QueueItem, Run, RunEvent
from app.worker import Worker, WorkerPolicy
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.workflow_helpers import intake, mock_processor


def child(engine, mode):
    with engine.connect() as c:
        schema = c.scalar(text("SELECT current_schema()"))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.workflow_harness",
            engine.url.render_as_string(hide_password=False),
            schema,
            mode,
        ],
        capture_output=True,
        text=True,
        timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


@pytest.mark.parametrize("point", ["before_financial_commit", "after_financial_commit"])
def test_abrupt_exit_then_fresh_process_reconciles_graph_and_ledger(workflow_db, point):
    engine = workflow_db
    _, po_id, _ = masters(engine)
    pdf, expected = case()
    run_id = intake(engine, pdf)
    first = child(engine, point)
    assert first.returncode == 73, first.stderr
    with Session(engine) as s:
        thread_id = s.get(Run, run_id).thread_id
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == (
            point == "after_financial_commit"
        )
    with engine.begin() as c:
        c.execute(text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'"))
    # Before commit normal retry policy applies. After commit reconciliation must work
    # even when the technical attempt budget was exhausted.
    processor, calls = mock_processor(engine, pdf, expected)
    worker = Worker(engine, processor, WorkerPolicy(max_attempts=3, retry_seconds=0))
    assert worker.run_once() is False
    second = child(engine, "complete")
    assert second.returncode == 0, second.stderr
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert run.thread_id == thread_id and run.decision == "APPROVED"
        assert run.job_state == "COMPLETED"
        assert s.scalar(select(QueueItem.status)) == "DONE"
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert s.scalar(select(func.count()).select_from(APIUsage)) == 1
        assert s.get(PurchaseOrder, po_id).committed_gross == 11800
        assert s.scalar(select(Document.content)) == pdf
        events = s.scalars(select(RunEvent).order_by(RunEvent.seq)).all()
        assert len({e.event_key for e in events}) == len(events)
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert worker.run_once() is False and calls == []
