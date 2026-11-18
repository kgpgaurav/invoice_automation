"""Atomic, idempotent, reviewer-authored master changes with immutable audit."""

import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.finance_contracts import normalized_name, tax_key
from app.financial_models import Vendor, VendorAction
from app.vendor_contracts import VendorRecorded


class VendorConflict(ValueError):
    pass


def lock_key(session, key):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key})


def receipt(record):
    return VendorRecorded(
        vendor_id=record.vendor_id, action_id=record.id, recorded_at=record.created_at
    )


def record_vendor(engine, body, key, actor_id, *, vendor_id=None):
    kind = "CREATE" if vendor_id is None else "STATUS"
    command = {
        "kind": kind,
        "vendor_id": str(vendor_id) if vendor_id else None,
        "request": body.model_dump(mode="json"),
    }
    fingerprint = hashlib.sha256(
        json.dumps(command, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        with Session(engine) as session, session.begin():
            lock_key(session, f"ps1-vendor-command:{actor_id}:{key}")
            previous = session.scalar(
                select(VendorAction).where(
                    VendorAction.actor_id == actor_id, VendorAction.idempotency_key == key
                )
            )
            if previous:
                if previous.request_hash != fingerprint:
                    raise VendorConflict(
                        "This request key was already used for different vendor details."
                    )
                return receipt(previous), True
            old_status = None
            if vendor_id is None:
                name = normalized_name(body.legal_name)
                lock_key(session, f"ps1-vendor-name:IN:{name}")
                existing = session.scalar(
                    select(Vendor.id).where(Vendor.jurisdiction == "IN", Vendor.name_key == name)
                )
                # Legacy identities remain untouched. Use the exact Python
                # normalization for Unicode names instead of DB collation rules.
                legacy_names = session.scalars(
                    select(Vendor.legal_name).where(
                        Vendor.jurisdiction == "IN", Vendor.name_key.is_(None)
                    )
                )
                if existing or any(normalized_name(value) == name for value in legacy_names):
                    raise VendorConflict(
                        "A vendor with this name already exists. Use its existing record."
                    )
                vendor = Vendor(
                    legal_name=body.legal_name,
                    name_key=name,
                    jurisdiction="IN",
                    tax_id_original=body.tax_id,
                    normalized_tax_id=tax_key(body.tax_id),
                    bank_last4=body.bank_last4,
                    status=body.status,
                )
                session.add(vendor)
                session.flush()
            else:
                vendor = session.scalar(
                    select(Vendor).where(Vendor.id == vendor_id).with_for_update()
                )
                if vendor is None:
                    raise LookupError("Vendor not found.")
                old_status = vendor.status
                vendor.status = body.status
            record = VendorAction(
                vendor_id=vendor.id,
                actor_id=actor_id,
                idempotency_key=key,
                kind=kind,
                request_hash=fingerprint,
                snapshot_json=command | {"previous_status": old_status, "status": body.status},
            )
            session.add(record)
            session.flush()
            result = receipt(record)
        return result, False
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise VendorConflict(
                "A vendor with this name or tax ID already exists. Use its existing record."
            ) from error
        raise
