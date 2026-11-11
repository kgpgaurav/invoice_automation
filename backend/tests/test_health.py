from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.config import Settings
from app.db import Base
from app.main import create_app


def test_health_and_ready(client):
    assert client.get("/api/v1/healthz").json()["status"] == "ok"
    assert client.get("/api/v1/readyz").status_code == 200


def test_migration_roundtrip_and_metadata_parity(client, database):
    engine, config = database
    with engine.begin() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
    assert client.get("/api/v1/readyz").status_code == 503
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert client.get("/api/v1/readyz").status_code == 200


def test_stale_migration_not_ready(client, database):
    with database[0].begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='old'"))
    assert client.get("/api/v1/readyz").status_code == 503


def test_db_outage_does_not_break_liveness():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused@127.0.0.1:1/unused",
        app_api_token="test-only-token-with-at-least-24-characters",
    )
    engine = create_engine(
        settings.database_url.get_secret_value(), connect_args={"connect_timeout": 1}
    )
    with TestClient(create_app(settings, engine)) as client:
        assert client.get("/api/v1/healthz").status_code == 200
        response = client.get("/api/v1/readyz")
        assert response.status_code == 503
        assert "unused" not in response.text
    engine.dispose()
