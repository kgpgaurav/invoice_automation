"""Explicit hosted operations, including guarded synthetic master setup; never send payments."""

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
        "command",
        choices=("api", "migrate", "register-policy", "worker", "purge-credentials", "seed-demo"),
    )
    parser.add_argument("--confirm-policy-version")
    parser.add_argument("--confirm-demo")
    parser.add_argument("--confirm-schema")
    parser.add_argument(
        "--apply", action="store_true", help="Write the explicitly confirmed demo masters"
    )
    args = parser.parse_args()
    # Render supplies a direct PostgreSQL URI; the app explicitly uses psycopg 3.
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        os.environ["DATABASE_URL"] = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if args.command == "seed-demo":
        if not args.confirm_demo or not args.confirm_schema:
            parser.error("seed-demo requires --confirm-demo and --confirm-schema")
        try:
            # A hosted seed reads the explicitly supplied process/environment-file
            # values, never the unrelated local backend/.env.
            settings = Settings(_env_file=None)
        except Exception as error:
            raise SystemExit(
                f"Cannot load seed settings ({type(error).__name__}); "
                "check configuration privately."
            ) from None
    else:
        settings = Settings()
    if args.command == "api":
        import uvicorn

        from app.main import create_app

        uvicorn.run(create_app(settings), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
        return
    try:
        engine = make_engine(settings)
    except Exception as error:
        if args.command != "seed-demo":
            raise
        raise SystemExit(
            f"Cannot initialize seed database ({type(error).__name__}); "
            "check configuration privately."
        ) from None
    try:
        if args.command == "seed-demo":
            from scripts.seed_demo import SeedConflict, seed_demo

            try:
                report = seed_demo(
                    engine,
                    settings.database_schema,
                    args.confirm_schema,
                    args.confirm_demo,
                    apply=args.apply,
                )
            except SeedConflict as error:
                raise SystemExit(str(error)) from None
            except Exception as error:
                raise SystemExit(
                    f"Demo setup stopped ({type(error).__name__}); "
                    "inspect database configuration privately."
                ) from None
            print(json.dumps(report, indent=2))
        elif args.command == "migrate":
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
                from app.evidence_verification import VERIFIER_VERSION
                from app.extraction_schema import PROMPT_VERSION, SCHEMA_VERSION

                print(
                    json.dumps(
                        dict(
                            event="WORKER_READY",
                            prompt_version=PROMPT_VERSION,
                            schema_version=SCHEMA_VERSION,
                            verifier_version=VERIFIER_VERSION,
                            scan_review_required=True,
                        )
                    ),
                    flush=True,
                )
                stop = Event()
                signal.signal(signal.SIGINT, lambda *_: stop.set())
                signal.signal(signal.SIGTERM, lambda *_: stop.set())
                run_configured_worker(Worker(engine, processor), stop)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
