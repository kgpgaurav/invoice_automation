"""Explicit loopback-only disposable demos; production worker entrypoint stays separate."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import signal
from pathlib import Path
from threading import Event
from uuid import uuid4

import httpx
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from app.checkpoints import setup_checkpoints
from app.config import Settings
from app.db import make_engine
from app.evidence_verification import labelled_records
from app.extraction_client import ExtractionError, OpenAIExtractor, Rates
from app.extraction_schema import InvoiceExtractionV1
from app.pdf_input import inspect_pdf
from app.worker import Worker
from app.workflow import WorkflowProcessor
from scripts.demo_fixtures import dataset, seed

ROOT = Path(__file__).resolve().parents[2]


def folder(name):
    if not re.fullmatch(r"[a-z0-9-]{1,40}", name):
        raise ValueError("Demo name must be 1–40 lowercase letters/digits/hyphens")
    result = (ROOT / ".local" / "demos" / name).resolve()
    if not result.is_relative_to(ROOT / ".local" / "demos"):
        raise ValueError("Invalid demo path")
    return result


def local_url(url):
    parsed = make_url(url)
    if any(key in parsed.query for key in ("host", "hostaddr", "service", "dbname", "port")):
        raise ValueError(
            "Demo URL must not override its connection target through query parameters"
        )
    if parsed.drivername != "postgresql+psycopg" or parsed.host not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError(
            "Demo operations require explicit loopback PostgreSQL; production is refused"
        )
    return parsed


def confirm_loopback(connection):
    from ipaddress import ip_address

    address = connection.scalar(text("SELECT host(inet_server_addr())"))
    if address is None or not ip_address(address).is_loopback:
        raise ValueError("Connected database is not on loopback; refusing demo mutation")


def load(name):
    path = folder(name)
    metadata = json.loads((path / "metadata.json").read_text())
    if not metadata.get("active") or not re.fullmatch(r"ps1_demo_[a-f0-9]{20}", metadata["schema"]):
        raise ValueError("Not an active disposable demo")
    values = {k: v for k, v in dotenv_values(path / "backend.env").items() if v is not None}
    settings = demo_settings(values)
    local_url(settings.database_url.get_secret_value())
    if settings.database_schema != metadata["schema"]:
        raise ValueError("Demo metadata/configuration mismatch")
    return path, metadata, settings


def demo_settings(values):
    parsed = {k.lower(): v for k, v in values.items()}
    if isinstance(parsed.get("submitter_api_tokens"), str):
        parsed["submitter_api_tokens"] = json.loads(parsed["submitter_api_tokens"])
    return Settings(_env_file=None, **parsed)


def create(name, mode, url, *, roles=False):
    target = folder(name)
    if (target / "metadata.json").exists() and json.loads(
        (target / "metadata.json").read_text()
    ).get("active"):
        raise ValueError("Demo already exists; explicitly reset it first")
    local_url(url)
    credentials = dotenv_values(ROOT / "backend" / ".env")
    key = os.environ.get("OPENAI_API_KEY") or credentials.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL") or credentials.get("OPENAI_MODEL")
    if mode == "live" and not (key and model):
        raise ValueError("Live demo requires locally configured OpenAI key and model")
    schema = "ps1_demo_" + uuid4().hex[:20]
    marker = "ps1-disposable-demo:" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as c:
        confirm_loopback(c)
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
        c.execute(text(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'"))
    target.mkdir(parents=True, exist_ok=True)
    config = dict(
        DATABASE_URL=url,
        DATABASE_SCHEMA=schema,
        APP_API_TOKEN=secrets.token_urlsafe(32),
        REVIEWER_API_TOKEN=secrets.token_urlsafe(32),
        OPENAI_MODEL=model if mode == "live" else "fixture-extraction",
    )
    if mode == "live":
        config["OPENAI_API_KEY"] = key
    if mode == "reviewer":
        from cryptography.fernet import Fernet

        config["OPENAI_CREDENTIAL_MODE"] = "reviewer"
        config["BYOK_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        config.pop("OPENAI_MODEL", None)
    if roles:
        config["ACCESS_MODE"] = "roles"
        config["SUBMITTER_API_TOKENS"] = json.dumps(
            {actor: secrets.token_urlsafe(32) for actor in ("submitter-b", "submitter-c")}
        )
    (target / "backend.env").write_text(
        "\n".join(k + "=" + str(v) for k, v in config.items()) + "\n", encoding="utf-8"
    )
    engine = make_engine(demo_settings(config))
    try:
        alembic = Config(str(ROOT / "backend" / "alembic.ini"))
        with engine.begin() as c:
            alembic.attributes["connection"] = c
            command.upgrade(alembic, "head")
        setup_checkpoints(engine)
        seed(engine)
        fixtures = []
        for ident, content, expected in dataset():
            (target / (ident + ".pdf")).write_bytes(content)
            fixtures.append(
                dict(id=ident, sha256=hashlib.sha256(content).hexdigest(), expected=expected)
            )
        (target / "fixtures.json").write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
        (target / "metadata.json").write_text(
            json.dumps(dict(schema=schema, marker=marker, mode=mode, active=True)), encoding="utf-8"
        )
    except BaseException:
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}_lg" CASCADE'))
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        raise
    finally:
        engine.dispose()
        admin.dispose()
    print(
        f"Created disposable {mode.upper()} demo '{name}'. "
        f"Credentials/PDFs: .local/demos/{name}. No completed runs seeded."
    )


def reset(name, confirm):
    path, meta, settings = load(name)
    if confirm != name:
        raise ValueError(
            "Reset requires --confirm with the exact demo name; stop its API/worker first"
        )
    admin = create_engine(settings.database_url.get_secret_value())
    schema = meta["schema"]
    try:
        with admin.begin() as c:
            confirm_loopback(c)
            marker = c.scalar(
                text(
                    "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace "
                    "WHERE nspname=:schema"
                ),
                {"schema": schema},
            )
            if marker != meta["marker"]:
                raise ValueError("Ownership marker mismatch; refusing reset")
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}_lg" CASCADE'))
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        meta["active"] = False
        (path / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    finally:
        admin.dispose()
    print(
        "Reset only marked disposable schemas. Private local files retained; "
        "create again for fresh credentials/data."
    )


class FixtureExtractor(OpenAIExtractor):
    """Explicit demo transport; unknown PDFs never become fabricated fixture data."""

    def __init__(self, hashes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixture_hashes = frozenset(hashes)

    def extract(self, pdf, *args, **kwargs):
        if hashlib.sha256(pdf).hexdigest() not in self.fixture_hashes:
            # Persisted by the existing graph error handler; no reservation or model call.
            raise ExtractionError("MOCK_FIXTURE_NOT_FOUND")
        return super().extract(pdf, *args, **kwargs)


def extractor_for(path, meta, settings):
    if meta["mode"] == "live":
        return OpenAIExtractor(settings.openai_api_key.get_secret_value(), settings.openai_model)
    fixtures = {
        f["sha256"]: f["expected"] for f in json.loads((path / "fixtures.json").read_text())
    }

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"id": "fixture-extraction"})
        data = json.loads(request.content)["input"][0]["content"][0]["file_data"]
        content = base64.b64decode(data.split(",", 1)[1])
        expected = fixtures.get(hashlib.sha256(content).hexdigest())
        if expected is None:
            return httpx.Response(422)
        records = labelled_records(inspect_pdf(content).pages)
        evidence = [
            dict(field=key, raw_text=row, page=page, method="TEXT")
            for key, matches in records.items()
            for page, row, _ in matches
        ]
        if not records:
            # Explicit fixture transcription for a scan; local verification still refuses it.
            evidence = [
                dict(
                    field="invoice_number",
                    raw_text="Invoice Number: " + expected["invoice_number"],
                    page=1,
                    method="VISION",
                )
            ]
        wire = InvoiceExtractionV1.model_validate(dict(expected, evidence=evidence))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "fixture-extraction",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": wire.model_dump_json()}],
                    }
                ],
            },
        )

    return FixtureExtractor(
        fixtures.keys(),
        "explicit-mock-only",
        "fixture-extraction",
        client=httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        ),
        sleep=lambda _: None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "reset", "api", "worker", "migrate"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--mode", choices=("mock", "live", "reviewer"), default="mock")
    parser.add_argument("--roles", action="store_true", help="Individual submitter/reviewer access")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "PS1_DEMO_DATABASE_URL", "postgresql+psycopg://ps1@127.0.0.1:55432/postgres"
        ),
    )
    parser.add_argument("--confirm")
    parser.add_argument("--enable-processing", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "create":
        return create(args.name, args.mode, args.database_url, roles=args.roles)
    if args.command == "reset":
        return reset(args.name, args.confirm)
    path, meta, settings = load(args.name)
    engine = make_engine(settings)
    try:
        if args.command == "migrate":
            with engine.begin() as connection:
                confirm_loopback(connection)
                marker = connection.scalar(
                    text(
                        "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace "
                        "WHERE nspname=:schema"
                    ),
                    {"schema": meta["schema"]},
                )
                if marker != meta["marker"]:
                    raise ValueError("Demo ownership marker mismatch; refusing migration")
                config = Config(str(ROOT / "backend" / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            setup_checkpoints(engine)
            print("Migrated only this marked local demo and its checkpoint schema.")
            return
        if args.command == "api":
            import uvicorn

            from app.main import create_app

            uvicorn.run(
                create_app(settings, engine, mock_mode=meta["mode"] == "mock"),
                host="127.0.0.1",
                port=args.port,
            )
        else:
            if not args.enable_processing:
                parser.error("Worker requires explicit --enable-processing; no jobs claimed")
            if meta["mode"] == "reviewer":
                from app.provider_credentials import configured_processor, run_configured_worker

                with configured_processor(engine, settings, "policy-1.1-demo") as processor:
                    processor.check_ready()
                    worker = Worker(engine, processor)
                    if args.once:
                        worker.run_once()
                    else:
                        stop = Event()
                        signal.signal(signal.SIGINT, lambda *_: stop.set())
                        signal.signal(signal.SIGTERM, lambda *_: stop.set())
                        run_configured_worker(worker, stop)
                return
            extractor = extractor_for(path, meta, settings)
            rates = None
            if meta["mode"] == "live":
                table = json.loads(
                    (ROOT / "docs/benchmarks/openai-rates-2026-11-12.json").read_text()
                )
                quote = table["models"].get(settings.openai_model)
                if quote:
                    from decimal import Decimal

                    rates = Rates(
                        *(Decimal(quote[k]) for k in ("input", "cached", "output")),
                        source=table["date"] + " " + quote["source"],
                        cache_write=Decimal(quote["cache_write"]),
                    )
            try:
                processor = WorkflowProcessor(
                    engine,
                    extractor,
                    "policy-1.1-demo",
                    source_mode="LIVE_OPENAI" if meta["mode"] == "live" else "MOCK_OPENAI",
                    rates=rates,
                )
                processor.check_ready()
                worker = Worker(engine, processor)
                if args.once:
                    worker.run_once()
                else:
                    stop = Event()
                    signal.signal(signal.SIGINT, lambda *_: stop.set())
                    signal.signal(signal.SIGTERM, lambda *_: stop.set())
                    worker.run(stop)
            finally:
                extractor.close()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
