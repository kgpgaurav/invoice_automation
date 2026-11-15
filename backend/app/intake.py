import hashlib
import json
from uuid import uuid4

import pymupdf
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.contracts import API_PREFIX, MAX_PDF_BYTES, MAX_PDF_PAGES, IntakeResponse
from app.models import Document, IntakeKey, QueueItem, Run, RunEvent


def validate_pdf(content: bytes, *, max_bytes: int = MAX_PDF_BYTES) -> None:
    if len(content) > max_bytes:
        raise HTTPException(
            413,
            detail={
                "code": "DOCUMENT_INVALID",
                "message": f"PDF exceeds {max_bytes / 1048576:g} MiB.",
            },
        )
    try:
        if not content.startswith(b"%PDF-"):
            raise ValueError
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.is_encrypted or document.needs_pass or document.metadata.get("encryption"):
                raise ValueError
            if not 1 <= document.page_count <= MAX_PDF_PAGES or document.is_repaired:
                raise ValueError
    except (ValueError, RuntimeError, pymupdf.FileDataError):
        raise HTTPException(
            422,
            detail={
                "code": "DOCUMENT_INVALID",
                "message": "Upload an intact, unencrypted PDF containing one to five pages.",
            },
        ) from None


def response_for(run_id) -> IntakeResponse:
    return IntakeResponse(run_id=run_id, links={"status": f"{API_PREFIX}/runs/{run_id}"})


def create_intake(
    engine,
    content: bytes,
    source: str | None,
    key: str | None,
    *,
    provider_token=None,
    model_id=None,
    owner_id=None,
) -> IntakeResponse:
    digest = hashlib.sha256(content).hexdigest()
    identity = [digest, source]
    if owner_id is not None:
        identity.append(owner_id)
        if key:
            key = "owner:" + hashlib.sha256(json.dumps([owner_id, key]).encode()).hexdigest()
    if provider_token or model_id:
        from app.provider_credentials import capability_hash

        identity += [capability_hash(provider_token or ""), model_id]
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
    with Session(engine) as session, session.begin():
        # Serialize requests for this optional key before creating any rows. The
        # unique key constraint remains the final guard; rollback removes all rows.
        if key:
            from sqlalchemy import text

            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
            )
            existing = session.get(IntakeKey, key)
            if existing:
                if existing.fingerprint != fingerprint:
                    raise HTTPException(
                        409, detail="Idempotency key already used for another payload."
                    )
                return response_for(existing.run_id)
        provider = None
        if provider_token or model_id:
            from app.provider_credentials import SUPPORTED_MODELS, find_session

            provider = find_session(session, provider_token, lock=True, owner_id=owner_id)
            if model_id not in provider.models_json or model_id not in SUPPORTED_MODELS:
                raise HTTPException(
                    400, "Choose a supported model listed for your OpenAI connection."
                )
        document_id, run_id = uuid4(), uuid4()
        session.add(Document(id=document_id, content=content, sha256=digest))
        session.flush()
        session.add(
            Run(
                id=run_id,
                owner_id=owner_id,
                document_id=document_id,
                document_uri=f"postgresql:documents/{document_id}",
                document_sha256=digest,
                source=source,
            )
        )
        session.flush()
        if provider is not None:
            from app.provider_models import RunProviderBinding

            session.add(
                RunProviderBinding(run_id=run_id, session_id=provider.id, model_id=model_id)
            )
        session.add_all(
            [
                QueueItem(run_id=run_id),
                RunEvent(
                    run_id=run_id,
                    seq=1,
                    stage="INTAKE",
                    type="RUN_QUEUED",
                    payload_json={
                        "notice": "PDF stored; awaiting processing. No decision recorded."
                    },
                ),
            ]
        )
        if key:
            session.add(IntakeKey(key=key, fingerprint=fingerprint, run_id=run_id))
    return response_for(run_id)
