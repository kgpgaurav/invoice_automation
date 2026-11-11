from sqlalchemy import func, select

from app.models import Run, RunEvent


def append_event(session, run_id, key, event_type, payload, stage="WORKER"):
    """Caller owns the transaction. All writers serialize on the run row."""
    session.execute(select(Run.id).where(Run.id == run_id).with_for_update()).scalar_one()
    existing = session.scalar(
        select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.event_key == key)
    )
    if existing:
        if (existing.type, existing.stage, existing.payload_json) != (
            event_type,
            stage,
            payload,
        ):
            raise ValueError("Conflicting event operation key")
        return existing
    seq = (
        session.scalar(
            select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run_id)
        )
        + 1
    )
    event = RunEvent(
        run_id=run_id, seq=seq, event_key=key, stage=stage, type=event_type, payload_json=payload
    )
    session.add(event)
    session.flush()
    return event
