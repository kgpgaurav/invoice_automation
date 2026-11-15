from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts.demo import confirm_loopback, folder, local_url
from tests.conftest import TOKEN


@pytest.mark.parametrize("value", ["../public", "public/../../", "", "ABC", "x" * 41])
def test_demo_paths_cannot_escape_private_workspace(value):
    with pytest.raises(ValueError):
        folder(value)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u@prod.example/db",
        "sqlite:///demo.db",
        "postgresql+psycopg://u@127.0.0.1/db?host=prod.example",
        "postgresql+psycopg://u@127.0.0.1/db?hostaddr=203.0.113.1",
    ],
)
def test_demo_mutation_refuses_remote_or_overridden_targets(url):
    with pytest.raises(ValueError):
        local_url(url)


@pytest.fixture
def ui_directory():
    base = Path(__file__).resolve().parents[2] / ".local" / "static-test"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="ui-", dir=base) as directory:
        path = Path(directory).resolve()
        assert path.is_relative_to(base.resolve())
        yield path


def test_loopback_guard_checks_actual_connected_server(database):
    with database[0].connect() as connection:
        confirm_loopback(connection)


def test_optional_built_ui_serves_assets_without_exposing_api_data(ui_directory):
    tmp_path = ui_directory
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<h1>Built UI</h1>")
    (tmp_path / "assets" / "app.js").write_text("// static build")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused@127.0.0.1:1/unused",
        app_api_token=TOKEN,
        frontend_directory=Path(tmp_path),
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/v1/runs").status_code == 401
        assert client.get("/assets/../.env").status_code == 404
