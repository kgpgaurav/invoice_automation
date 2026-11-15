"""Separate-process execution; real processing requires explicit operator opt-in."""

import sys
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Event, RLock, Thread
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import Document, QueueItem, Run


class LostLease(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerPolicy:
    lease_seconds: int = 30
    heartbeat_seconds: int = 10
    max_attempts: int = 3
    retry_seconds: int = 5

    def __post_init__(self):
        if not (
            0 < self.heartbeat_seconds < self.lease_seconds
            and self.max_attempts > 0
            and self.retry_seconds >= 0
        ):
            raise ValueError("Invalid worker timing/attempt policy")


@dataclass
class Claim:
    job_id: UUID
    run_id: UUID
    owner: str
    attempt: int
    connection: object
    mutex: object = field(default_factory=RLock)

    def close(self):
        # Physically close: session advisory locks must never return to the pool.
        self.connection.invalidate()
        self.connection.close()


class Worker:
    def __init__(self, engine, processor=None, policy=None):
        self.engine = engine
        self.processor = processor
        self.policy = policy or WorkerPolicy()

    def claim(self):
        if self.processor is None:
            raise RuntimeError("Production processing disabled: no real processor exists.")
        connection = self.engine.connect()
        keep = False
        try:
            with Session(connection) as session, session.begin():
                now = session.scalar(select(func.clock_timestamp()))
                jobs = session.scalars(
                    select(QueueItem)
                    .where(
                        QueueItem.work_type.in_(
                            ("PROCESS", "RESUME")
                            if getattr(self.processor, "durable_workflow", False)
                            else ("PROCESS",)
                        )
                    )
                    .where(
                        or_(
                            and_(QueueItem.status == "READY", QueueItem.next_attempt_at <= now),
                            and_(QueueItem.status == "LEASED", QueueItem.lease_until <= now),
                        )
                    )
                    .order_by(QueueItem.next_attempt_at, QueueItem.id)
                    .with_for_update(skip_locked=True)
                    .limit(100)
                ).all()
                for job in jobs:
                    locked = session.scalar(
                        text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                        {"key": f"ps1-worker:{job.run_id}"},
                    )
                    if not locked:
                        continue
                    run = session.scalar(select(Run).where(Run.id == job.run_id).with_for_update())
                    workflow = getattr(self.processor, "durable_workflow", False)
                    terminal = workflow and run.decision in ("APPROVED", "REJECTED")
                    if not terminal and run.job_state not in ("QUEUED", "RUNNING", "INTERRUPTED"):
                        raise RuntimeError("Unsupported run state; reconciliation required")
                    if job.status == "LEASED":
                        if terminal:
                            self._reconcile_committed(session, job, run, now)
                        else:
                            self._retry(session, job, run, "LEASE_EXPIRED", now)
                        # Recovery commits first; delayed READY work is claimed next time.
                        return None
                    job.status = "LEASED"
                    job.attempts += 1
                    job.claimed_by = str(uuid4())
                    job.lease_until = now + timedelta(seconds=self.policy.lease_seconds)
                    if not terminal:
                        run.job_state, run.error_code, run.reason = "RUNNING", None, None
                    run.updated_at = now
                    append_event(
                        session,
                        run.id,
                        f"{job.id}:{job.attempts}:claim",
                        "STAGE_STARTED",
                        {"operation": "WORKER_CLAIM", "attempt": job.attempts},
                    )
                    claim = Claim(job.id, run.id, job.claimed_by, job.attempts, connection)
                    break
                else:
                    return None
            keep = True
            return claim
        finally:
            if not keep:
                connection.invalidate()
                connection.close()

    def _owned(self, session, claim):
        job = session.scalar(
            select(QueueItem)
            .where(QueueItem.id == claim.job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = session.scalar(select(func.clock_timestamp()))
        if (
            job.status != "LEASED"
            or job.claimed_by != claim.owner
            or job.attempts != claim.attempt
            or job.lease_until <= now
        ):
            raise LostLease("Claim expired or replaced")
        return job, now

    def heartbeat(self, claim):
        with Session(self.engine) as session, session.begin():
            job, now = self._owned(session, claim)
            job.lease_until = now + timedelta(seconds=self.policy.lease_seconds)

    def record(self, claim, key, payload):
        # Infrastructure-only operation: no document-origin payload or financial event.
        with Session(self.engine) as session, session.begin():
            self._owned(session, claim)
            append_event(
                session, claim.run_id, f"{claim.job_id}:operation:{key}", "STAGE_STARTED", payload
            )

    def _retry(self, session, job, run, code, now):
        exhausted = job.attempts >= self.policy.max_attempts
        job.status = "FAILED" if exhausted else "READY"
        job.claimed_by = None
        job.lease_until = None
        job.next_attempt_at = now + timedelta(
            seconds=min(60, self.policy.retry_seconds * 2 ** min(job.attempts - 1, 10))
        )
        run.job_state = "FAILED" if exhausted else "INTERRUPTED"
        run.error_code = "WORKER_ATTEMPTS_EXHAUSTED" if exhausted else code
        run.reason = "Worker execution failed; no financial decision was made."
        run.updated_at = now
        append_event(
            session,
            run.id,
            f"{job.id}:{job.attempts}:end",
            "RUN_FAILED" if exhausted else "STAGE_FAILED",
            {"operation": code, "attempt": job.attempts, "retry": not exhausted},
        )

    def _reconcile_committed(self, session, job, run, now):
        job.status, job.lease_until, job.claimed_by = "READY", None, None
        job.next_attempt_at = now
        append_event(
            session,
            run.id,
            f"{job.id}:{job.attempts}:reconcile",
            "STAGE_FAILED",
            {"operation": "RECOVER_COMMITTED_DECISION", "financial_post_unchanged": True},
        )

    def finish(self, claim, failed=False):
        if getattr(self.processor, "durable_workflow", False):
            from app.ownership import owned_session

            with owned_session(self, claim) as session:
                job, now = self._owned(session, claim)
                run = session.scalar(select(Run).where(Run.id == claim.run_id).with_for_update())
                if not failed:
                    raise RuntimeError("Workflow must complete through its fenced finalizer")
                if run.decision in ("APPROVED", "REJECTED"):
                    self._reconcile_committed(session, job, run, now)
                else:
                    self._retry(session, job, run, "PROCESSOR_ERROR", now)
            return
        with Session(self.engine) as session, session.begin():
            existing = session.scalar(
                select(QueueItem).where(QueueItem.id == claim.job_id).with_for_update()
            )
            if (
                not failed
                and existing.status == "DONE"
                and existing.claimed_by == claim.owner
                and existing.attempts == claim.attempt
            ):
                return
            job, now = self._owned(session, claim)
            run = session.scalar(select(Run).where(Run.id == job.run_id).with_for_update())
            if failed:
                if getattr(self.processor, "durable_workflow", False) and run.decision in (
                    "APPROVED",
                    "REJECTED",
                ):
                    self._reconcile_committed(session, job, run, now)
                else:
                    self._retry(session, job, run, "PROCESSOR_ERROR", now)
            else:
                # This boundary only supports explicit infrastructure test processors.
                job.status, job.lease_until = "DONE", None
                run.job_state, run.error_code = "INTERRUPTED", "TEST_PROCESSOR_ONLY"
                run.reason = "Test processor stopped; invoice processing is not implemented."
                run.updated_at = now
                append_event(
                    session,
                    run.id,
                    f"{job.id}:{job.attempts}:end",
                    "STAGE_FINISHED",
                    {"operation": "TEST_PROCESSOR_STOPPED", "invoice_processed": False},
                )

    def run_once(self):
        claim = self.claim()
        if claim is None:
            return False
        stop, lost = Event(), Event()

        def beat():
            while not stop.wait(self.policy.heartbeat_seconds):
                try:
                    self.heartbeat(claim)
                except Exception:
                    lost.set()
                    return

        thread = Thread(target=beat, daemon=True)
        thread.start()
        try:
            failed = False
            try:
                with Session(self.engine) as session:
                    run = session.get(Run, claim.run_id)
                    pdf = session.get(Document, run.document_id).content
                self.processor(self, claim, pdf)
            except Exception:
                failed = True
            if not failed and getattr(self.processor, "durable_workflow", False):
                return True  # Graph processor already committed its fenced completion/park.
            if lost.is_set():
                raise LostLease("Heartbeat failed; recovery required")
            self.finish(claim, failed=failed)
            return True
        finally:
            stop.set()
            thread.join()
            claim.close()

    def run(self, stop):
        while not stop.is_set():
            if not self.run_once():
                stop.wait(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Controlled PS-1 worker")
    parser.add_argument("--enable-processing", action="store_true")
    parser.add_argument("--setup-checkpoints", action="store_true")
    parser.add_argument("--policy-version")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.enable_processing and not args.setup_checkpoints:
        print(
            "Processing disabled. No jobs claimed. Use explicit operator opt-in.", file=sys.stderr
        )
        return 2
    from app.config import Settings
    from app.db import make_engine

    engine = make_engine(Settings())
    try:
        if args.setup_checkpoints:
            from app.checkpoints import setup_checkpoints

            setup_checkpoints(engine)
            return 0
        if not args.policy_version:
            parser.error("--policy-version must name an already registered policy")
        from app.provider_credentials import configured_processor, run_configured_worker

        settings = Settings()
        with configured_processor(engine, settings, args.policy_version) as processor:
            processor.check_ready()
            worker = Worker(engine, processor)
            if args.once:
                worker.run_once()
            else:
                import signal

                stop = Event()
                signal.signal(signal.SIGINT, lambda *_: stop.set())
                signal.signal(signal.SIGTERM, lambda *_: stop.set())
                run_configured_worker(worker, stop)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
