"""Short, idempotent purchase-order creation transaction; no model calls."""

import hashlib
import json

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.financial_models import POCreation, POLine, PurchaseOrder, Vendor
from app.po_contracts import POCreated, VendorChoice, VendorChoices


class POConflict(ValueError):
    pass


def active_vendors(engine, query, limit, *, include_unavailable=False):
    with Session(engine) as session:
        statement = select(Vendor)
        if not include_unavailable:
            statement = statement.where(Vendor.status == "ACTIVE")
        if query:
            statement = statement.where(Vendor.legal_name.icontains(query, autoescape=True))
        count = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = session.scalars(statement.order_by(Vendor.legal_name, Vendor.id).limit(limit)).all()
        return VendorChoices(
            items=[
                VendorChoice(
                    vendor_id=v.id,
                    legal_name=v.legal_name,
                    tax_id=v.tax_id_original,
                    status=v.status,
                )
                for v in rows
            ],
            total_count=count,
        )


def receipt(record):
    return POCreated(
        po_id=record.po_id,
        po_number=record.snapshot_json["po_number"],
        created_at=record.created_at,
    )


def create_purchase_order(engine, body, key, actor_id):
    snapshot = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"ps1-po-create:{actor_id}:{key}"},
            )
            previous = session.scalar(
                select(POCreation).where(
                    POCreation.actor_id == actor_id, POCreation.idempotency_key == key
                )
            )
            if previous:
                if previous.request_hash != fingerprint:
                    raise POConflict("This request key was already used for different PO details.")
                return receipt(previous), True
            vendor = session.scalar(
                select(Vendor).where(Vendor.id == body.vendor_id).with_for_update()
            )
            if vendor is None:
                raise LookupError("Vendor not found.")
            if vendor.status == "BLACKLISTED":
                raise POConflict("Purchase orders cannot be created for a blacklisted vendor.")
            if vendor.status != "ACTIVE":
                raise POConflict(
                    "The selected vendor is no longer active. Choose an active vendor."
                )
            order = PurchaseOrder(
                po_number=body.po_number,
                vendor_id=vendor.id,
                currency="INR",
                status="OPEN",
                issued_at=body.issued_at,
                expires_at=body.expires_at,
                approved_cap_gross=body.cap_gross,
                committed_gross=0,
                version=1,
            )
            session.add(order)
            session.flush()
            for number, line in enumerate(body.lines, 1):
                session.add(
                    POLine(
                        po_id=order.id, line_no=number, committed_quantity=0, **line.model_dump()
                    )
                )
            record = POCreation(
                po_id=order.id,
                actor_id=actor_id,
                idempotency_key=key,
                request_hash=fingerprint,
                snapshot_json=snapshot | {"line_total_gross": str(body.line_total_gross())},
            )
            session.add(record)
            session.flush()
            result = receipt(record)
        return result, False
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise POConflict(
                "A purchase order with this reference already exists. Search Purchase orders."
            ) from error
        raise
