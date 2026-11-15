"""Abrupt process exit with synthetic credentials and mocked OpenAI only."""

import os
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine
from app.models import Document, Run
from app.provider_credentials import ReviewerWorkflowProcessor
from app.worker import Worker, WorkerPolicy
from tests.extraction_helpers import case, response, untrusted_extraction
from tests.financial_fixtures import POLICY

settings = Settings(
    _env_file=None,
    database_url=sys.argv[1],
    database_schema=sys.argv[2],
    app_api_token="synthetic-private-workspace-token",
    openai_credential_mode="reviewer",
    byok_encryption_key=os.environ["PS1_TEST_BYOK_CIPHER"],
)
engine = make_engine(settings)
with Session(engine) as session:
    run = session.scalar(select(Run))
    pdf = session.get(Document, run.document_id).content
_, expected = case()


def client_factory(key, model):
    def handle(_):
        if sys.argv[3] == "complete":
            raise AssertionError("Recovery must reuse the persisted extraction")
        return response(untrusted_extraction(pdf, expected))

    return httpx.Client(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle))


def crash(point):
    if point == sys.argv[3]:
        os._exit(73)


try:
    processor = ReviewerWorkflowProcessor(
        engine, settings, POLICY.version, client_factory=client_factory, crash_hook=crash
    )
    processor.check_ready()
    assert Worker(engine, processor, WorkerPolicy(retry_seconds=0)).run_once()
finally:
    engine.dispose()
