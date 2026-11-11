import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events import append_event
from app.intake import create_intake
from app.models import Document, QueueItem, Run, RunEvent
from app.worker import LostLease, Worker, WorkerPolicy


def worker(engine, processor=lambda *_: None, attempts=3):
    return Worker(engine, processor, WorkerPolicy(3, 1, attempts, 0))


def seed(engine, pdf):
    return create_intake(engine, pdf, None, str(uuid4())).run_id


def expire(engine):
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second' "
                "WHERE status='LEASED'"
            )
        )


def process(engine, mode):
    with engine.connect() as c:
        schema = c.scalar(text("SELECT current_schema()"))
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.worker_harness",
            engine.url.render_as_string(hide_password=False),
            schema,
            mode,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert child.stdout.readline().strip() == "READY"
    return child


def stop(child):
    if child.poll() is None:
        child.terminate()
    child.communicate(timeout=10)


def test_two_processes_compete(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    children = [process(engine, "once"), process(engine, "once")]
    try:
        for child in children:
            child.stdin.write("go\n")
            child.stdin.flush()
        outputs = [child.communicate(timeout=15) for child in children]
        assert sum(out.count("CLAIMED") for out, _ in outputs) == 1
        assert all(child.returncode == 0 for child in children), outputs
        with Session(engine) as s:
            job = s.scalar(select(QueueItem))
            assert (job.status, job.attempts) == ("DONE", 1)
            assert s.scalar(select(Run)).decision is None
    finally:
        for child in children:
            stop(child)


def test_process_kill_lease_recovery_and_restart(database, pdf):
    engine = database[0]
    run_id = seed(engine, pdf)
    with Session(engine) as s:
        thread_id = s.get(Run, run_id).thread_id
    child = process(engine, "hold")
    try:
        child.stdin.write("go\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "CLAIMED"
        with Session(engine) as s:
            original = s.scalar(select(QueueItem)).lease_until
        time.sleep(1.2)
        with Session(engine) as s:
            assert s.scalar(select(QueueItem)).lease_until > original  # real heartbeat thread
        expire(engine)
        assert worker(engine).run_once() is False  # live owner still holds session lock
    finally:
        stop(child)
    expire(engine)
    # Fresh worker object/connection reconciles only the abandoned lease.
    assert worker(engine).run_once() is False
    assert worker(engine).run_once() is True
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert run.thread_id == thread_id
        assert run.job_state == "INTERRUPTED" and run.decision is None
        assert s.scalar(select(Document)).content == pdf
        assert s.scalar(select(QueueItem)).attempts == 2


def test_event_dedup_fencing_and_finish_replay(database, pdf):
    engine = database[0]
    run_id = seed(engine, pdf)
    w = worker(engine)
    claim = w.claim()
    try:
        w.record(claim, "check", {"operation": "TEST_CHECK"})
        w.record(claim, "check", {"operation": "TEST_CHECK"})
        with pytest.raises(ValueError):
            w.record(claim, "check", {"operation": "CONFLICT"})
        w.finish(claim)
        w.finish(claim)
        with pytest.raises(LostLease):
            w.heartbeat(claim)
        with Session(engine) as s:
            events = s.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            ).all()
            assert [e.seq for e in events] == [1, 2, 3, 4]
            assert events[-1].payload_json["invoice_processed"] is False
        assert w.run_once() is False
    finally:
        claim.close()


def test_stale_owner_after_reclaim_and_exhaustion(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    w = worker(engine, attempts=2)
    first = w.claim()
    expire(engine)
    first.close()  # emulate dead connection
    assert w.run_once() is False
    second = w.claim()
    try:
        with pytest.raises(LostLease):
            w.finish(first)
        w.finish(second, failed=True)
    finally:
        second.close()
    assert w.run_once() is False
    with Session(engine) as s:
        assert s.scalar(select(QueueItem)).status == "FAILED"
        run = s.scalar(select(Run))
        assert (run.job_state, run.error_code, run.decision) == (
            "FAILED",
            "WORKER_ATTEMPTS_EXHAUSTED",
            None,
        )


def test_claim_and_finish_rollback(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE run_events ADD CONSTRAINT injected CHECK (seq < 2)"))
    w = worker(engine)
    with pytest.raises(IntegrityError):
        w.claim()
    with engine.begin() as c:
        assert c.scalar(text("SELECT attempts FROM run_queue")) == 0
        assert c.scalar(text("SELECT job_state FROM runs")) == "QUEUED"
        c.execute(text("ALTER TABLE run_events DROP CONSTRAINT injected"))
    claim = w.claim()
    try:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE run_events ADD CONSTRAINT injected CHECK (seq < 3)"))
        with pytest.raises(IntegrityError):
            w.finish(claim)
        with engine.connect() as c:
            assert c.scalar(text("SELECT status FROM run_queue")) == "LEASED"
            assert c.scalar(text("SELECT job_state FROM runs")) == "RUNNING"
        with engine.begin() as c:
            c.execute(text("ALTER TABLE run_events DROP CONSTRAINT injected"))
        w.finish(claim)
    finally:
        claim.close()


def test_intake_concurrently_with_worker(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    with ThreadPoolExecutor(2) as pool:
        intake = pool.submit(seed, engine, pdf)
        execute = pool.submit(worker(engine).run_once)
        assert intake.result() and execute.result()
    assert worker(engine).run_once()
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Document)) == 2
        assert set(s.scalars(select(QueueItem.status))) == {"DONE"}


def test_events_api_order_auth_and_cursor(client, database, pdf):
    run_id = seed(database[0], pdf)
    assert worker(database[0]).run_once()
    path = f"/api/v1/runs/{run_id}/events"
    events = client.get(path).json()
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert all(e["occurred_at"].endswith("Z") for e in events)
    assert client.get(path + "?after_seq=1&limit=1").json() == events[1:2]
    assert client.get(path + "?after_seq=3").json() == []
    assert client.get(path + "?after_seq=-1").status_code == 422
    assert client.get(f"/api/v1/runs/{uuid4()}/events").status_code == 404
    client.headers.pop("Authorization")
    assert client.get(path).status_code == 401


def test_disabled_worker_cannot_claim(database, pdf):
    seed(database[0], pdf)
    with pytest.raises(RuntimeError, match="disabled"):
        Worker(database[0]).run_once()
    result = subprocess.run([sys.executable, "-m", "app.worker"], capture_output=True, text=True)
    assert result.returncode == 2 and "No jobs claimed" in result.stderr
    with Session(database[0]) as s:
        assert s.scalar(select(QueueItem)).attempts == 0


def test_event_transaction_rollback(database, pdf):
    engine = database[0]
    run_id = seed(engine, pdf)
    with pytest.raises(RuntimeError), Session(engine) as s, s.begin():
        append_event(s, run_id, "rollback", "STAGE_STARTED", {"operation": "TEST"})
        raise RuntimeError("injected")
    with Session(engine) as s, s.begin():
        assert append_event(s, run_id, "rollback", "STAGE_STARTED", {"operation": "TEST"}).seq == 2
