"""Export implemented contracts without connecting to a database."""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

settings = Settings(
    _env_file=None,
    database_url="postgresql+psycopg://unused@127.0.0.1/unused",
    app_api_token="schema-export-only-not-a-runtime-token",
)
path = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
path.write_text(json.dumps(create_app(settings).openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Exported {path.name}")
