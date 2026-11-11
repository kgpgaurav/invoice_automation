import os
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from alembic import command
from app.config import Settings
from app.main import create_app

TOKEN = "test-only-token-with-at-least-24-characters"


@pytest.fixture(scope="session")
def settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a local PostgreSQL database; no SQLite fallback.")
    return Settings(_env_file=None, database_url=url, app_api_token=TOKEN)


@pytest.fixture
def database(settings):
    # A random schema isolates tests from all existing tables. No public-schema writes.
    schema = "test_" + uuid4().hex
    admin = create_engine(settings.database_url.get_secret_value())
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"options": f"-c search_path={schema}"},
    )
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine, config
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def client(database, settings):
    with TestClient(create_app(settings, database[0])) as test_client:
        test_client.headers["Authorization"] = f"Bearer {TOKEN}"
        yield test_client


@pytest.fixture
def pdf():
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "Test intake PDF. No AI extraction.")
        return document.tobytes()


@pytest.fixture
def workflow_db(database):
    from tests.workflow_helpers import setup, teardown

    engine = database[0]
    setup(engine)
    yield engine
    teardown(engine)
