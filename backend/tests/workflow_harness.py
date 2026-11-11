"""Abrupt process exit bypasses finally/connection cleanup; restart reads persisted graph."""

import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Document, Run
from app.worker import Worker, WorkerPolicy
from scripts.extraction_fixtures import expected_invoice
from tests.workflow_helpers import mock_processor

url, schema, mode = sys.argv[1:]
engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
with Session(engine) as session:
    run = session.scalar(select(Run))
    pdf = session.get(Document, run.document_id).content


def kill(point):
    if mode == point:
        os._exit(73)


processor, _ = mock_processor(engine, pdf, expected_invoice(), crash_hook=kill)
worker = Worker(engine, processor, WorkerPolicy(max_attempts=1, retry_seconds=0))
worker.run_once()
engine.dispose()
