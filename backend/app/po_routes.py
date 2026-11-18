"""New spending authority belongs only to the authenticated reviewer role."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Response

from app.access import Principal
from app.contracts import API_PREFIX
from app.po_contracts import POCreate, POCreated, POPreview, POTotals, VendorChoices
from app.po_service import POConflict, active_vendors, create_purchase_order
from app.vendor_contracts import VendorCreate, VendorRecorded, VendorStatusChange
from app.vendor_service import VendorConflict, record_vendor


def add_po_routes(app, engine, require_auth):
    def reviewer(actor: Annotated[Principal, Depends(require_auth)]):
        if actor.role != "reviewer":
            raise HTTPException(
                403,
                detail={
                    "code": "ROLE_FORBIDDEN",
                    "message": "Reviewer access required to manage vendors and purchase orders.",
                },
            )
        return actor

    @app.get(
        f"{API_PREFIX}/vendors", response_model=VendorChoices, dependencies=[Depends(reviewer)]
    )
    def vendors(
        q: Annotated[str, Query(max_length=120)] = "",
        limit: Annotated[int, Query(ge=1, le=50)] = 50,
        include_unavailable: bool = False,
    ):
        return active_vendors(engine, q.strip(), limit, include_unavailable=include_unavailable)

    def vendor_command(body, response, actor, key, vendor_id=None):
        if not key.strip():
            raise HTTPException(422, "An idempotency key is required.")
        response.headers["Cache-Control"] = "no-store"
        try:
            result, replay = record_vendor(engine, body, key, actor.actor_id, vendor_id=vendor_id)
            response.status_code = 200 if replay or vendor_id is not None else 201
            return result
        except LookupError as error:
            raise HTTPException(404, {"code": "VENDOR_ERROR", "message": str(error)}) from error
        except VendorConflict as error:
            raise HTTPException(409, {"code": "VENDOR_ERROR", "message": str(error)}) from error

    @app.post(
        f"{API_PREFIX}/vendors",
        response_model=VendorRecorded,
        status_code=201,
        responses={200: {"model": VendorRecorded}},
    )
    def create_vendor(
        body: VendorCreate,
        response: Response,
        actor: Annotated[Principal, Depends(reviewer)],
        x_idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        return vendor_command(body, response, actor, x_idempotency_key)

    @app.patch(f"{API_PREFIX}/vendors/{{vendor_id}}/status", response_model=VendorRecorded)
    def change_vendor_status(
        vendor_id: UUID,
        body: VendorStatusChange,
        response: Response,
        actor: Annotated[Principal, Depends(reviewer)],
        x_idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        return vendor_command(body, response, actor, x_idempotency_key, vendor_id)

    @app.post(
        f"{API_PREFIX}/purchase-orders/preview",
        response_model=POTotals,
        dependencies=[Depends(reviewer)],
    )
    def preview_order(body: POPreview, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return POTotals.from_lines(body.lines)

    @app.post(
        f"{API_PREFIX}/purchase-orders",
        response_model=POCreated,
        status_code=201,
        responses={200: {"model": POCreated}},
    )
    def create_order(
        body: POCreate,
        response: Response,
        actor: Annotated[Principal, Depends(reviewer)],
        x_idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        if not x_idempotency_key.strip():
            raise HTTPException(422, "An idempotency key is required.")
        response.headers["Cache-Control"] = "no-store"
        try:
            result, replay = create_purchase_order(engine, body, x_idempotency_key, actor.actor_id)
            response.status_code = 200 if replay else 201
            return result
        except LookupError as error:
            raise HTTPException(404, {"code": "PO_CREATE_ERROR", "message": str(error)}) from error
        except POConflict as error:
            raise HTTPException(409, {"code": "PO_CREATE_ERROR", "message": str(error)}) from error
