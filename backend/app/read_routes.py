from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.access import Principal, visible_run
from app.contracts import API_PREFIX, JobState
from app.models import Document, RunEvent
from app.product_reads import purchase_order_detail, purchase_orders
from app.read_contracts import DashboardSummary, POLedgerView, POPage, RunPage
from app.read_service import dashboard, history
from app.streaming import event_stream


def add_read_routes(app, engine, require_auth, require_finance):
    @app.get(f"{API_PREFIX}/runs", response_model=RunPage, dependencies=[Depends(require_auth)])
    def get_history(
        actor: Annotated[Principal, Depends(require_auth)],
        state: JobState | None = None,
        decision: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"] | None = None,
        cursor: Annotated[str | None, Query(max_length=1000)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        q: Annotated[str, Query(max_length=120)] = "",
    ):
        with Session(engine) as session:
            return history(
                session, state, decision, cursor, limit, q.strip(), owner_id=actor.owner_id
            )

    @app.get(
        f"{API_PREFIX}/purchase-orders",
        response_model=POPage,
        dependencies=[Depends(require_finance)],
    )
    def get_purchase_orders(
        q: Annotated[str, Query(max_length=120)] = "",
        after: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        with Session(engine) as session:
            return purchase_orders(session, q.strip(), after, limit)

    @app.get(
        f"{API_PREFIX}/purchase-orders/{{po_id}}",
        response_model=POLedgerView,
        dependencies=[Depends(require_finance)],
    )
    def get_purchase_order(po_id: UUID):
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with Session(connection) as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                return purchase_order_detail(session, po_id)

    @app.get(
        f"{API_PREFIX}/dashboard/summary",
        response_model=DashboardSummary,
        dependencies=[Depends(require_finance)],
    )
    def get_dashboard():
        # One consistent read-only snapshot for multi-query aggregate calculations.
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with Session(connection) as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                return dashboard(session)

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/document",
        response_class=Response,
        dependencies=[Depends(require_auth)],
        responses={
            200: {
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}
            }
        },
    )
    def get_document(run_id: UUID, actor: Annotated[Principal, Depends(require_auth)]):
        with Session(engine) as session:
            run = visible_run(session, run_id, actor)
            content = session.get(Document, run.document_id).content
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="invoice-{run_id}.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/events/stream",
        response_class=StreamingResponse,
        dependencies=[Depends(require_auth)],
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    def get_stream(
        run_id: UUID,
        actor: Annotated[Principal, Depends(require_auth)],
        after_seq: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[int | None, Header(ge=0)] = None,
    ):
        cursor = max(after_seq, last_event_id or 0)
        with Session(engine) as session:
            visible_run(session, run_id, actor)
            last = session.scalar(
                select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run_id)
            )
            if cursor > last:
                raise HTTPException(422, detail="Event cursor is beyond persisted events.")
        return StreamingResponse(
            event_stream(engine, run_id, cursor),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
