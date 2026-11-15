"""Private workspace identities. Roles/ownership are always derived on the server."""

import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel

from app.models import Run


@dataclass(frozen=True)
class Principal:
    role: str
    actor_id: str

    @property
    def owner_id(self):
        return self.actor_id if self.role == "submitter" else None


class AccessView(BaseModel):
    mode: Literal["shared", "roles"]
    role: Literal["workspace", "submitter", "reviewer"]
    actor_id: str
    pages: list[str]


def authenticate(settings, token):
    supplied = (token or "").encode()
    match = None
    entries = [(settings.app_api_token, "submitter", "submitter")]
    if settings.access_mode == "roles":
        entries += [
            (key, "submitter", ident) for ident, key in settings.submitter_api_tokens.items()
        ]
        if settings.reviewer_api_token:
            entries.append((settings.reviewer_api_token, "reviewer", "reviewer"))
    for key, role, ident in entries:
        if secrets.compare_digest(supplied, key.get_secret_value().encode()):
            match = Principal(role if settings.access_mode == "roles" else "workspace", ident)
    if match is None:
        raise HTTPException(
            401, "Valid access credential required.", headers={"WWW-Authenticate": "Bearer"}
        )
    return match


def require_role(principal, role):
    if principal.role not in ("workspace", role):
        raise HTTPException(
            403, detail={"code": "ROLE_FORBIDDEN", "message": f"{role.title()} access required."}
        )
    return principal


def visible_run(session, run_id, principal):
    run = session.get(Run, run_id)
    if run is None or (principal.owner_id is not None and run.owner_id != principal.owner_id):
        raise HTTPException(404, "Run not found.")
    return run


def access_view(settings, principal):
    pages = (
        ["upload", "history"]
        if principal.role == "submitter"
        else ["review", "history", "purchase-orders", "overview"]
        if principal.role == "reviewer"
        else ["review", "upload", "history", "purchase-orders", "overview", "scenarios"]
    )
    return AccessView(
        mode=settings.access_mode, role=principal.role, actor_id=principal.actor_id, pages=pages
    )


def submitter_reason(reason, code, decision):
    if decision == "NEEDS_REVIEW":
        descriptions = {
            "PO_MISSING": "Your invoice needs a verified purchase order.",
            "PO_AMBIGUOUS": "Your invoice does not establish a single supporting purchase order.",
            "PO_CAP_EXCEEDED": "The invoice exceeds the available purchase-order allowance.",
            "BANK_MISMATCH": "The invoice bank details need independent verification.",
            "PRICE_VARIANCE": "Invoice prices differ from the purchase-order terms.",
            "QTY_EXCEEDED": "Invoice quantities exceed the available purchase-order quantities.",
            "TAX_UNCLEAR": "The invoice tax information needs verification.",
            "CRITICAL_FIELD_MISSING": "Required invoice information is missing or unverified.",
            "UNVERIFIED_TOTAL": "The invoice total could not be verified.",
        }
        return descriptions.get(
            code, "Required invoice information or financial checks need review."
        ) + (" A financial reviewer will handle the exception and request information if needed.")
    return reason
