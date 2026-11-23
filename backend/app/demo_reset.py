"""Opt-in, single-transaction demo reset. Never operate on an unconfirmed schema."""

import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.access import Principal
from app.contracts import API_PREFIX
from app.db import Base
from app.demo_reset_model import DemoResetReceipt
from scripts.seed_demo import DATASET, fingerprint, seed_demo

TABLES = (
    "documents",
    "runs",
    "run_events",
    "run_queue",
    "intake_keys",
    "vendors",
    "vendor_actions",
    "purchase_orders",
    "po_lines",
    "policy_versions",
    "purchase_order_creations",
    "invoices",
    "approval_ledger",
    "approval_allocations",
    "financial_assessments",
    "api_usage",
    "provider_sessions",
    "run_provider_bindings",
    "workflow_runs",
    "review_requests",
    "review_actions",
)
CHECKPOINT_KEYS = {
    "checkpoints": ("thread_id", "checkpoint_ns", "checkpoint_id"),
    "checkpoint_blobs": ("thread_id", "checkpoint_ns", "channel", "version"),
    "checkpoint_writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
}


class ResetConflict(ValueError):
    pass


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: Literal["ps1-demo-v1"]
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: Literal["RESET DEMO"]


class ResetPreview(BaseModel):
    enabled: bool
    dataset: str = DATASET
    snapshot: str | None = None
    counts: dict[str, int] = {}


class ResetRecorded(BaseModel):
    reset_id: UUID
    dataset: str
    removed_counts: dict[str, int]
    restored_counts: dict[str, int]


def qualified(schema, table):
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
        raise ResetConflict("Invalid demo schema; reset refused.")
    # Table arguments come only from the explicit allowlists above.
    return f'"{schema}"."{table}"'


def target(session, schema):
    if (
        not schema
        or schema in ("public", "information_schema")
        or schema.startswith("pg_")
        or session.scalar(text("SELECT current_schema()")) != schema
    ):
        raise ResetConflict("Reset requires the configured dedicated nonpublic demo schema.")
    found = set(
        session.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname=:s"), {"s": schema})
    )
    if found != set(TABLES) | {"alembic_version", "demo_reset_receipts"}:
        raise ResetConflict(
            "Demo schema tables differ from the reviewed reset allowlist; migrate first."
        )
    checkpoint = schema + "_lg"
    found = set(
        session.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname=:s"), {"s": checkpoint}
        )
    )
    if found and found != set(CHECKPOINT_KEYS) | {"checkpoint_migrations"}:
        raise ResetConflict("Checkpoint schema differs from the reviewed reset allowlist.")
    return checkpoint if found else None


def snapshot(session, schema, checkpoint):
    counts, hashes = {}, {}
    sources = [
        (schema, table, tuple(c.name for c in Base.metadata.tables[table].primary_key))
        for table in (*TABLES, "demo_reset_receipts")
    ]
    if checkpoint:
        sources += [(checkpoint, table, keys) for table, keys in CHECKPOINT_KEYS.items()]
    mutable = (
        "updated_at",
        "status",
        "version",
        "attempts",
        "lease_until",
        "claimed_by",
        "next_attempt_at",
        "extraction_attempts",
        "review_generation",
        "revoked_at",
        "expires_at",
        "approved_cap_gross",
        "committed_gross",
        "committed_quantity",
        "quantity",
        "unit_price",
        "tax_rate",
        "legal_name",
        "normalized_tax_id",
    )
    for namespace, table, keys in sources:
        if namespace == schema:
            keys += tuple(
                k for k in mutable if k in Base.metadata.tables[table].columns and k not in keys
            )
        columns = ",".join(f"COALESCE(CAST(\"{k}\" AS text),'')" for k in keys)
        row_hash = f"md5(concat_ws('|',{columns}))"
        count, digest = session.execute(
            text(
                f"SELECT count(*), md5(COALESCE(string_agg({row_hash},'' ORDER BY {row_hash}),'')) "
                f"FROM {qualified(namespace, table)}"
            )
        ).one()
        label = table
        counts[label], hashes[label] = count, digest
    return counts, fingerprint(
        {"schema": schema, "dataset": DATASET, "counts": counts, "rows": hashes}
    )


def preview_reset(engine, schema):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(connection) as session, session.begin():
            checkpoint = target(session, schema)
            counts, state = snapshot(session, schema, checkpoint)
            return ResetPreview(enabled=True, snapshot=state, counts=counts)


def result(receipt):
    return ResetRecorded(
        reset_id=receipt.id,
        dataset=receipt.dataset,
        removed_counts=receipt.removed_counts,
        restored_counts=receipt.restored_counts,
    )


def reset_demo(
    engine, schema, body, key, actor, *, after_clear=lambda _: None, after_restore=lambda _: None
):
    if not key.strip() or len(key) > 128:
        raise ResetConflict("A valid reset idempotency key is required.")
    request_hash = fingerprint(body.model_dump())
    try:
        with Session(engine) as session, session.begin():
            # This also bounds waits for advisory keys used by the shared seeder.
            session.execute(text("SET LOCAL lock_timeout='100ms'"))
            locked = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k,0))"),
                {"k": "ps1-demo-reset:" + str(schema)},
            )
            if not locked:
                raise ResetConflict("Another demo reset is running. Retry the same request.")
            checkpoint = target(session, schema)
            prior = session.scalar(
                select(DemoResetReceipt).where(
                    DemoResetReceipt.actor_id == actor, DemoResetReceipt.idempotency_key == key
                )
            )
            if prior:
                if prior.request_hash != request_hash:
                    raise ResetConflict(
                        "Reset idempotency key was already used with different confirmation."
                    )
                return result(prior), True
            locked_tables = [
                qualified(schema, table) for table in sorted((*TABLES, "demo_reset_receipts"))
            ]
            if checkpoint:
                locked_tables += [qualified(checkpoint, table) for table in sorted(CHECKPOINT_KEYS)]
            session.execute(
                text("LOCK TABLE " + ",".join(locked_tables) + " IN ACCESS EXCLUSIVE MODE NOWAIT")
            )
            for run_id in session.scalars(
                text(f"SELECT id FROM {qualified(schema, 'runs')} ORDER BY id")
            ):
                owns = session.scalar(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k,0))"),
                    {"k": f"ps1-worker:{run_id}"},
                )
                if not owns:
                    raise ResetConflict(
                        "A worker is processing an invoice. Wait for it to stop before resetting."
                    )
            counts, state = snapshot(session, schema, checkpoint)
            if state != body.snapshot:
                raise ResetConflict(
                    "Demo activity changed. Refresh the reset preview and confirm again."
                )
            cleared = [qualified(schema, table) for table in TABLES]
            if checkpoint:
                cleared += [qualified(checkpoint, table) for table in CHECKPOINT_KEYS]
            # No CASCADE, no disabled triggers, no schema dropping, no migration-table changes.
            session.execute(text("TRUNCATE TABLE " + ",".join(cleared)))
            after_clear(session)
            seed_demo(session.connection(), schema, schema, DATASET, apply=True, actor=actor)
            after_restore(session)
            restored = {
                table: session.scalar(text(f"SELECT count(*) FROM {qualified(schema, table)}"))
                for table in (
                    "vendors",
                    "purchase_orders",
                    "runs",
                    "approval_ledger",
                    "provider_sessions",
                )
            }
            receipt = DemoResetReceipt(
                actor_id=actor,
                idempotency_key=key,
                request_hash=request_hash,
                dataset=DATASET,
                removed_counts={
                    table: count
                    for table, count in counts.items()
                    if table in TABLES or checkpoint and table in CHECKPOINT_KEYS
                },
                restored_counts=restored,
            )
            session.add(receipt)
            session.flush()
            return result(receipt), False
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) in ("55P03", "40P01", "57014"):
            raise ResetConflict(
                "The demo is busy. Wait for processing to finish and refresh the preview."
            ) from None
        raise


def add_demo_reset_routes(app, settings, engine, require_auth):
    def reviewer(actor: Annotated[Principal, Depends(require_auth)]):
        if actor.role != "reviewer":
            raise HTTPException(403, "Reviewer access required for demo reset.")
        return actor

    @app.get(
        f"{API_PREFIX}/demo/reset", response_model=ResetPreview, dependencies=[Depends(reviewer)]
    )
    def preview(response: Response):
        response.headers["Cache-Control"] = "no-store"
        if not settings.demo_reset_enabled:
            return ResetPreview(enabled=False)
        try:
            return preview_reset(engine, settings.database_schema)
        except ResetConflict as error:
            raise HTTPException(
                409, {"code": "DEMO_RESET_CONFLICT", "message": str(error)}
            ) from None

    @app.post(
        f"{API_PREFIX}/demo/reset",
        response_model=ResetRecorded,
        status_code=201,
        responses={200: {"model": ResetRecorded}},
    )
    def execute(
        body: ResetRequest,
        response: Response,
        actor: Annotated[Principal, Depends(reviewer)],
        x_idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        response.headers["Cache-Control"] = "no-store"
        if not settings.demo_reset_enabled:
            raise HTTPException(403, "Demo reset is not enabled for this workspace.")
        try:
            receipt, replay = reset_demo(
                engine, settings.database_schema, body, x_idempotency_key, actor.actor_id
            )
            response.status_code = 200 if replay else 201
            return receipt
        except ResetConflict as error:
            raise HTTPException(
                409, {"code": "DEMO_RESET_CONFLICT", "message": str(error)}
            ) from None
