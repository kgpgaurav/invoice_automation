"""Per-session OpenAI credentials; never changes process-global provider configuration."""

import hashlib
import json
import secrets
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.extraction_client import ExtractionError, OpenAIExtractor
from app.provider_models import ProviderSession, RunProviderBinding

SUPPORTED_MODELS = ("gpt-6-luna", "gpt-6.1-terra")


def cipher(settings):
    try:
        return Fernet(settings.byok_encryption_key.get_secret_value().encode())
    except (AttributeError, ValueError):
        raise ValueError("Configure a stable BYOK_ENCRYPTION_KEY for API and worker") from None


def capability_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def discover_models(key, client=None):
    owns_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        response = client.get(
            "https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + key}
        )
        if response.status_code in (401, 403):
            raise HTTPException(400, "OpenAI rejected this key or its model-list permission.")
        if response.status_code != 200:
            raise HTTPException(503, "OpenAI model discovery is unavailable. Try again later.")
        ids = {row["id"] for row in response.json()["data"] if isinstance(row.get("id"), str)}
        result = [model for model in SUPPORTED_MODELS if model in ids]
        if not result:
            raise HTTPException(400, "This key lists no invoice models supported by this app.")
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(
            503, "OpenAI model discovery is unavailable. Try again later."
        ) from None
    finally:
        if owns_client:
            client.close()


def purge_expired(engine):
    with Session(engine) as session, session.begin():
        session.execute(
            update(ProviderSession)
            .where(
                ProviderSession.expires_at <= func.now(), ProviderSession.ciphertext.is_not(None)
            )
            .values(ciphertext=None)
        )


def create_provider_session(engine, settings, key, *, client=None, owner_id=None):
    encryption = cipher(settings)
    models = discover_models(key, client)
    token = secrets.token_urlsafe(32)
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.now()))
        ident = uuid4()
        row = ProviderSession(
            id=ident,
            owner_id=owner_id,
            capability_hash=capability_hash(token),
            ciphertext=encryption.encrypt(json.dumps({"id": str(ident), "key": key}).encode()),
            models_json=models,
            expires_at=now + timedelta(hours=24),
        )
        session.add(row)
        session.flush()
        expires_at = row.expires_at
    return {"session_token": token, "models": models, "expires_at": expires_at}


def find_session(session, token, *, lock=False, owner_id=None):
    query = select(ProviderSession).where(
        ProviderSession.capability_hash == capability_hash(token or "")
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    now = session.scalar(select(func.now()))
    if (
        row is None
        or row.owner_id != owner_id
        or row.ciphertext is None
        or row.revoked_at
        or row.expires_at <= now
    ):
        raise HTTPException(
            400, "OpenAI connection expired or disconnected. Connect your key again."
        )
    return row


def revoke_session(engine, token, *, owner_id=None):
    with Session(engine) as session, session.begin():
        row = session.scalar(
            select(ProviderSession)
            .where(ProviderSession.capability_hash == capability_hash(token or ""))
            .where(ProviderSession.owner_id == owner_id)
            .with_for_update()
        )
        if row:
            row.ciphertext = None
            row.revoked_at = session.scalar(select(func.now()))


def load_key(engine, settings, session_id):
    with Session(engine) as session, session.begin():
        row = session.get(ProviderSession, session_id)
        now = session.scalar(select(func.now()))
        if row is None or row.revoked_at or row.expires_at <= now or row.ciphertext is None:
            if row is not None:
                row.ciphertext = None
            unavailable = True
            encrypted = None
        else:
            unavailable, encrypted = False, row.ciphertext
    if unavailable:
        raise ExtractionError("BYOK_CREDENTIALS_UNAVAILABLE")
    try:
        payload = json.loads(cipher(settings).decrypt(encrypted))
        if payload["id"] != str(session_id):
            raise ValueError
        return payload["key"]
    except (InvalidToken, ValueError, UnicodeError, KeyError, TypeError):
        raise ExtractionError("BYOK_CREDENTIALS_UNAVAILABLE") from None


def guard_reservation(session, session_id):
    # Serialize authorization with disconnect in the short attempt-reservation transaction.
    # Once this transaction commits, the attempt is started and may be billed.
    row = session.scalar(
        select(ProviderSession).where(ProviderSession.id == session_id).with_for_update(read=True)
    )
    now = session.scalar(select(func.now()))
    if row is None or row.ciphertext is None or row.revoked_at or row.expires_at <= now:
        raise ExtractionError("BYOK_CREDENTIALS_UNAVAILABLE")


class SessionExtractor:
    def __init__(self, engine, settings, session_id, model, *, client_factory=None):
        self.engine, self.settings, self.session_id, self.model = (
            engine,
            settings,
            session_id,
            model,
        )
        self.client_factory = client_factory

    def extract(self, *args, before_attempt=lambda _: None, **kwargs):
        key = load_key(self.engine, self.settings, self.session_id)
        client = self.client_factory(key, self.model) if self.client_factory else None
        extractor = OpenAIExtractor(key, self.model, client=client)

        def reserve(attempt_id):
            load_key(self.engine, self.settings, self.session_id)
            before_attempt(attempt_id)

        try:
            return extractor.extract(*args, before_attempt=reserve, **kwargs)
        finally:
            extractor.close()


class ReviewerWorkflowProcessor:
    durable_workflow = True

    def __init__(
        self,
        engine,
        settings,
        policy_version,
        *,
        client_factory=None,
        rates=None,
        crash_hook=lambda _: None,
    ):
        self.engine, self.settings, self.policy_version = engine, settings, policy_version
        self.client_factory, self.rates = client_factory, rates
        self.crash_hook = crash_hook

    def check_ready(self):
        from app.workflow import check_workflow_infrastructure

        cipher(self.settings)
        check_workflow_infrastructure(self.engine, self.policy_version)
        purge_expired(self.engine)

    def __call__(self, worker, claim, pdf):
        from app.workflow import WorkflowProcessor

        purge_expired(self.engine)
        with Session(self.engine) as session:
            binding = session.get(RunProviderBinding, claim.run_id)
            if binding is None:
                raise ExtractionError("BYOK_BINDING_MISSING")
            session_id, model = binding.session_id, binding.model_id
        extractor = SessionExtractor(
            self.engine, self.settings, session_id, model, client_factory=self.client_factory
        )
        WorkflowProcessor(
            self.engine,
            extractor,
            self.policy_version,
            rates=self.rates,
            crash_hook=self.crash_hook,
            reservation_guard=lambda session: guard_reservation(session, session_id),
        )(worker, claim, pdf)


@contextmanager
def configured_processor(engine, settings, policy_version, *, rates=None):
    from app.workflow import WorkflowProcessor

    if settings.openai_credential_mode == "reviewer":
        yield ReviewerWorkflowProcessor(engine, settings, policy_version)
    else:
        extractor = OpenAIExtractor(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,
            settings.openai_model,
        )
        try:
            yield WorkflowProcessor(engine, extractor, policy_version, rates=rates)
        finally:
            extractor.close()


def run_configured_worker(worker, stop):
    import time

    next_cleanup = 0
    while not stop.is_set():
        if (
            isinstance(worker.processor, ReviewerWorkflowProcessor)
            and time.monotonic() >= next_cleanup
        ):
            purge_expired(worker.engine)
            next_cleanup = time.monotonic() + 60
        if not worker.run_once():
            stop.wait(1)
