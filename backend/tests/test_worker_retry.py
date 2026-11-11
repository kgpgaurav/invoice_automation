from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import QueueItem, Run, RunEvent
from app.worker import Worker, WorkerPolicy
from tests.test_worker import seed, worker


def test_processor_failure_retry_and_committed_operation_replay(database, pdf):
    engine = database[0]
    run_id = seed(engine, pdf)

    def failing(w, claim, data):
        assert data == pdf
        w.record(claim, "stable", {"operation": "TEST_DURABLE_OPERATION"})
        raise RuntimeError("Never persist this potentially sensitive exception")

    assert worker(engine, failing).run_once()

    def retried(w, claim, data):
        w.record(claim, "stable", {"operation": "TEST_DURABLE_OPERATION"})

    assert worker(engine, retried).run_once()
    with Session(engine) as s:
        events = s.scalars(select(RunEvent).where(RunEvent.run_id == run_id)).all()
        assert sum(e.payload_json.get("operation") == "TEST_DURABLE_OPERATION" for e in events) == 1
        assert s.scalar(select(QueueItem)).attempts == 2
        assert s.get(Run, run_id).decision is None
        assert all("sensitive" not in str(e.payload_json) for e in events)


def test_expired_final_attempt(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    w = worker(engine, attempts=1)
    claim = w.claim()
    claim.close()
    with engine.begin() as c:
        c.execute(text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'"))
    assert w.run_once() is False
    with Session(engine) as s:
        assert s.scalar(select(QueueItem)).status == "FAILED"
        assert s.scalar(select(Run)).error_code == "WORKER_ATTEMPTS_EXHAUSTED"


def test_retry_backoff_prevents_early_claim(database, pdf):
    engine = database[0]
    seed(engine, pdf)
    w = Worker(engine, lambda *_: None, WorkerPolicy(30, 10, 3, 5))
    claim = w.claim()
    try:
        w.finish(claim, failed=True)
    finally:
        claim.close()
    assert w.run_once() is False
    with engine.connect() as c:
        assert c.scalar(text("SELECT next_attempt_at > clock_timestamp() FROM run_queue"))
