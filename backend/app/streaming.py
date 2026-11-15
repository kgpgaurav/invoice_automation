"""Authenticated transport over committed events; no DB connection lives across awaits."""

import asyncio
import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models import QueueItem
from app.read_service import events, public_event


def batch(engine, run_id, cursor):
    with Session(engine) as session:
        rows = [public_event(e).model_dump_json() for e in events(session, run_id, cursor)]
        active = session.scalar(
            select(QueueItem.id)
            .where(QueueItem.run_id == run_id, QueueItem.status.in_(("READY", "LEASED")))
            .limit(1)
        )
        return rows, active is not None


async def event_stream(engine, run_id, cursor, *, lifetime=25, poll_seconds=0.5):
    import json

    deadline = time.monotonic() + lifetime
    heartbeat = time.monotonic()
    yield "retry: 1500\n\n"
    while time.monotonic() < deadline:
        rows, active = await run_in_threadpool(batch, engine, run_id, cursor)
        for data in rows:
            cursor = json.loads(data)["seq"]
            yield f"id: {cursor}\nevent: run-event\ndata: {data}\n\n"
        if len(rows) >= 500:
            continue
        if not active:
            yield 'event: stream-end\ndata: {"reason":"caught_up"}\n\n'
            return
        if time.monotonic() - heartbeat >= 10:
            yield ": keepalive\n\n"
            heartbeat = time.monotonic()
        await asyncio.sleep(poll_seconds)
    yield 'event: stream-end\ndata: {"reason":"reconnect"}\n\n'
