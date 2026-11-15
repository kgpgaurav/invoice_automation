"""Explicit hosted commands; never provision accounts, seed demo masters or send payments."""

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path
from threading import Event

from alembic.config import Config

from alembic import command
from app.config import Settings
from app.db import make_engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("api", "migrate", "register-policy", "worker", "purge-credentials")
    )
    parser.add_argument("--confirm-policy-version")
    args = parser.parse_args()
    # Render supplies a direct PostgreSQL URI; the app explicitly uses psycopg 3.
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        os.environ["DATABASE_URL"] = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    settings = Settings()
    if args.command == "api":
        import uvicorn

        from app.main import create_app

        uvicorn.run(create_app(settings), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
        return
    engine = make_engine(settings)
    try:
        if args.command == "migrate":
            from app.checkpoints import setup_checkpoints

            config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            setup_checkpoints(engine)
        elif args.command == "purge-credentials":
            from app.provider_credentials import purge_expired

            purge_expired(engine)
        elif args.command == "register-policy":
            from app.approval import register_policy
            from app.finance_contracts import FinancialPolicy

            policy = FinancialPolicy()
            if args.confirm_policy_version != policy.version:
                parser.error(
                    "Explicitly confirm the unchanged demo policy version before registration"
                )
            register_policy(engine, policy, "authorized-hosted-operator")
        else:
            if os.environ.get("PS1_ENABLE_WORKER") != "1":
                raise SystemExit(
                    "Worker disabled. No jobs claimed. Explicit operator activation required."
                )
            import signal

            from app.extraction_client import Rates
            from app.provider_credentials import configured_processor, run_configured_worker
            from app.worker import Worker

            rates = None
            filename = os.environ.get("PS1_OPENAI_RATES_FILE")
            if filename:
                table = json.loads(Path(filename).read_text())
                quote = table["models"].get(settings.openai_model)
                if quote:
                    rates = Rates(
                        *(Decimal(quote[k]) for k in ("input", "cached", "output")),
                        source=table["date"] + " " + quote["source"],
                        cache_write=Decimal(quote["cache_write"]),
                    )
            with configured_processor(
                engine, settings, os.environ["PS1_POLICY_VERSION"], rates=rates
            ) as processor:
                processor.check_ready()
                stop = Event()
                signal.signal(signal.SIGINT, lambda *_: stop.set())
                signal.signal(signal.SIGTERM, lambda *_: stop.set())
                run_configured_worker(Worker(engine, processor), stop)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
