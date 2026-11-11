"""Proof of the physical worker connection plus lease fencing in one short transaction."""

from contextlib import contextmanager

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import QueueItem
from app.worker import LostLease


@contextmanager
def owned_session(worker, claim):
    with claim.mutex:
        with _session(worker, claim) as session:
            yield session


@contextmanager
def _session(worker, claim):
    connection = claim.connection
    if connection.closed or connection.invalidated:
        raise LostLease("Worker connection lost")
    with Session(connection) as session, session.begin():
        locked = session.scalar(
            text("""SELECT EXISTS(SELECT 1 FROM pg_locks WHERE
            locktype='advisory' AND pid=pg_backend_pid() AND granted AND mode='ExclusiveLock'
            AND classid=((hashtextextended(:key,0) >> 32) & 4294967295)::oid
            AND objid=(hashtextextended(:key,0) & 4294967295)::oid AND objsubid=1)"""),
            {"key": f"ps1-worker:{claim.run_id}"},
        )
        if not locked:
            raise LostLease("Connection does not own the run advisory lock")
        job, _ = worker._owned(session, claim)
        deadline = job.lease_until
        session.info["ps1_owned_claim"] = (worker, claim)
        yield session
        session.flush()
        # Completion deliberately retires this lease within the fenced transaction.
        job = session.get(QueueItem, claim.job_id)
        if job.status == "LEASED":
            worker._owned(session, claim)
        else:
            if (
                job.claimed_by not in (None, claim.owner)
                or job.attempts != claim.attempt
                or deadline <= session.scalar(select(func.clock_timestamp()))
            ):
                raise LostLease("Claim expired during completion")
