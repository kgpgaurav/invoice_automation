"""Add-only, explicitly authorized synthetic master setup; never copy local history."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.finance_contracts import FinancialPolicy, normalized_name
from app.financial_models import (
    POCreation,
    PolicyVersion,
    POLine,
    PurchaseOrder,
    Vendor,
    VendorAction,
)
from app.po_contracts import POCreate
from app.vendor_contracts import VendorCreate
from app.vendor_service import lock_key
from scripts.demo_fixtures import master_records

DATASET = "ps1-demo-v1"
ACTOR = "hosted-demo-setup"


class SeedConflict(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def seed_demo(engine, schema, confirm_schema, confirm_demo, *, apply=False, actor=ACTOR):
    if not schema or schema in ("public", "information_schema") or schema.startswith("pg_"):
        raise SeedConflict("Set a dedicated nonpublic DATABASE_SCHEMA before demo setup.")
    if confirm_schema != schema or confirm_demo != DATASET:
        raise SeedConflict("Explicit schema and ps1-demo-v1 dataset confirmation are required.")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    policy = FinancialPolicy()
    policy_json = policy.model_dump(mode="json")
    report = {
        "dataset": DATASET,
        "schema": schema,
        "mode": "APPLIED" if apply else "DRY_RUN",
        "policy_version": policy.version,
        "policy_to_create": False,
        "vendors_to_create": 0,
        "vendors_existing": 0,
        "purchase_orders_to_create": [],
        "purchase_orders_existing": [],
    }
    try:
        with Session(engine) as session, session.begin():
            if session.scalar(text("SELECT current_schema()")) != schema:
                raise SeedConflict(
                    "Connected schema does not match the explicitly confirmed target."
                )
            if session.scalar(text("SELECT version_num FROM alembic_version")) != head:
                raise SeedConflict("Migrate this database to the current head before demo setup.")
            lock_key(session, f"ps1-seed-demo:{schema}:{DATASET}")
            stored_policy = session.get(PolicyVersion, policy.version)
            if stored_policy and stored_policy.config_json != policy_json:
                raise SeedConflict(
                    "The demo policy version already has different immutable values."
                )
            report["policy_to_create"] = stored_policy is None
            new_vendors, new_orders = [], []
            for name, tax, orders in master_records():
                body = VendorCreate(
                    legal_name=name,
                    status="ACTIVE",
                    tax_id=tax,
                    bank_last4="1234",
                    reason=f"Authorized synthetic master setup: {DATASET}.",
                )
                name_key = normalized_name(name)
                lock_key(session, f"ps1-vendor-name:IN:{name_key}")
                candidates = [
                    v
                    for v in session.scalars(select(Vendor).where(Vendor.jurisdiction == "IN"))
                    if v.normalized_tax_id == tax or normalized_name(v.legal_name) == name_key
                ]
                if len(candidates) > 1:
                    raise SeedConflict(f"Ambiguous existing synthetic vendor: {name}.")
                if candidates:
                    vendor = session.scalar(
                        select(Vendor)
                        .where(Vendor.id == candidates[0].id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if (
                        vendor.normalized_tax_id != tax
                        or normalized_name(vendor.legal_name) != name_key
                        or vendor.status != "ACTIVE"
                        or vendor.bank_last4 != "1234"
                    ):
                        raise SeedConflict(
                            f"Existing vendor identity/status conflicts with demo: {name}."
                        )
                    report["vendors_existing"] += 1
                else:
                    vendor = Vendor(
                        id=uuid4(),
                        legal_name=name,
                        name_key=name_key,
                        jurisdiction="IN",
                        tax_id_original=tax,
                        normalized_tax_id=tax,
                        status="ACTIVE",
                        bank_last4="1234",
                    )
                    new_vendors.append((vendor, body))
                    report["vendors_to_create"] += 1
                for number, cap, rate in orders:
                    order_body = POCreate.model_validate(
                        dict(
                            po_number=number,
                            vendor_id=vendor.id,
                            currency="INR",
                            issued_at="2026-10-01",
                            cap_gross=cap,
                            reason=f"Authorized synthetic master setup: {DATASET}.",
                            lines=[
                                dict(
                                    sku="PAPER",
                                    description="Office paper",
                                    quantity="100",
                                    unit_price="1000",
                                    tax_rate=rate,
                                )
                            ],
                        )
                    )
                    existing = session.scalar(
                        select(PurchaseOrder)
                        .where(PurchaseOrder.po_number == number)
                        .with_for_update()
                    )
                    if existing:
                        terms = session.scalars(
                            select(POLine)
                            .where(POLine.po_id == existing.id)
                            .order_by(POLine.line_no)
                            .with_for_update()
                        ).all()
                        matches = (
                            existing.vendor_id == vendor.id
                            and existing.currency == "INR"
                            and existing.status == "OPEN"
                            and existing.issued_at == order_body.issued_at
                            and existing.expires_at is None
                            and existing.approved_cap_gross == order_body.cap_gross
                            and len(terms) == 1
                            and terms[0].line_no == 1
                            and all(
                                getattr(terms[0], key) == value
                                for key, value in order_body.lines[0].model_dump().items()
                            )
                        )
                        if not matches:
                            raise SeedConflict(f"Existing PO terms conflict with demo: {number}.")
                        report["purchase_orders_existing"].append(number)
                    else:
                        new_orders.append(order_body)
                        report["purchase_orders_to_create"].append(number)
            if apply:
                if stored_policy is None:
                    session.add(
                        PolicyVersion(
                            version=policy.version, config_json=policy_json, created_by=actor
                        )
                    )
                for vendor, body in new_vendors:
                    session.add(vendor)
                    session.flush()
                    command = {
                        "kind": "CREATE",
                        "vendor_id": None,
                        "request": body.model_dump(mode="json"),
                    }
                    session.add(
                        VendorAction(
                            vendor_id=vendor.id,
                            actor_id=actor,
                            kind="CREATE",
                            idempotency_key=f"{DATASET}:vendor:{vendor.normalized_tax_id}",
                            request_hash=fingerprint(command),
                            snapshot_json=command
                            | {
                                "previous_status": None,
                                "status": "ACTIVE",
                                "seed_dataset": DATASET,
                            },
                        )
                    )
                session.flush()
                for body in new_orders:
                    order = PurchaseOrder(
                        id=uuid4(),
                        po_number=body.po_number,
                        vendor_id=body.vendor_id,
                        currency="INR",
                        status="OPEN",
                        issued_at=body.issued_at,
                        expires_at=None,
                        approved_cap_gross=body.cap_gross,
                        committed_gross=0,
                        version=1,
                    )
                    session.add(order)
                    session.flush()
                    session.add(
                        POLine(
                            po_id=order.id,
                            line_no=1,
                            committed_quantity=0,
                            **body.lines[0].model_dump(),
                        )
                    )
                    snapshot = body.model_dump(mode="json")
                    session.add(
                        POCreation(
                            po_id=order.id,
                            actor_id=actor,
                            idempotency_key=f"{DATASET}:po:{body.po_number}",
                            request_hash=fingerprint(snapshot),
                            snapshot_json=snapshot
                            | {
                                "line_total_gross": str(body.line_total_gross()),
                                "seed_dataset": DATASET,
                            },
                        )
                    )
                session.flush()
        return report
    except IntegrityError as error:
        raise SeedConflict(
            "Concurrent or conflicting master data prevented setup; no seed writes committed."
        ) from error
