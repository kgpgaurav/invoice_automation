"""Own and clean up a disposable browser demo and its child processes. Live H1 is opt-in."""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.demo import create, folder, reset

ROOT = Path(__file__).resolve().parents[2]


def ready(url, process):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Demo service stopped; inspect its private local log")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Demo service did not become ready")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-h1", action="store_true", help="Explicitly incur OpenAI cost for H1 only"
    )
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=5173)
    parser.add_argument("--roles", action="store_true", help="Run the isolated role-access cases")
    args = parser.parse_args()
    if args.api_port == args.ui_port or not all(
        1024 <= p <= 65535 for p in (args.api_port, args.ui_port)
    ):
        parser.error("Choose distinct API/UI ports between 1024 and 65535")
    for port in (args.api_port, args.ui_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                parser.error("Selected test port is busy; use --api-port / --ui-port")
    name = "browser-" + uuid4().hex[:10]
    create(
        name,
        "live" if args.live_h1 else "mock",
        os.environ.get(
            "PS1_DEMO_DATABASE_URL", "postgresql+psycopg://ps1@127.0.0.1:55432/postgres"
        ),
        roles=args.roles,
    )
    environment = dict(
        os.environ,
        PS1_BROWSER_DEMO=name,
        PS1_BROWSER_LIVE="1" if args.live_h1 else "0",
        PS1_DEV_API_PORT=str(args.api_port),
        PS1_BROWSER_BASE_URL=f"http://127.0.0.1:{args.ui_port}",
        PS1_BROWSER_ROLES="1" if args.roles else "0",
    )
    processes, logs = [], []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for label, command, cwd, url in (
            (
                "api",
                [
                    sys.executable,
                    "-m",
                    "scripts.demo",
                    "api",
                    "--name",
                    name,
                    "--port",
                    str(args.api_port),
                ],
                ROOT / "backend",
                f"http://127.0.0.1:{args.api_port}/api/v1/readyz",
            ),
            (
                "worker",
                [
                    sys.executable,
                    "-m",
                    "scripts.demo",
                    "worker",
                    "--name",
                    name,
                    "--enable-processing",
                ],
                ROOT / "backend",
                None,
            ),
            (
                "vite",
                [
                    "node",
                    str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.ui_port),
                ],
                ROOT / "frontend",
                f"http://127.0.0.1:{args.ui_port}",
            ),
        ):
            log = (folder(name) / (label + ".log")).open("w", encoding="utf-8")
            logs.append(log)
            child = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(child)
            if url:
                ready(url, child)
        result = subprocess.run(
            ["node", str(ROOT / "frontend/node_modules/@playwright/test/cli.js"), "test"]
            + (["roles.spec.ts"] if args.roles else []),
            cwd=ROOT / "frontend",
            env=environment,
            creationflags=flags,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout + result.stderr
        (folder(name) / "playwright.log").write_text(output, encoding="utf-8")
        from dotenv import dotenv_values

        for key, value in dotenv_values(folder(name) / "backend.env").items():
            if ("TOKEN" in key or "KEY" in key) and value:
                output = output.replace(value, "[REDACTED]")
                if key == "SUBMITTER_API_TOKENS":
                    import json

                    for credential in json.loads(value).values():
                        output = output.replace(credential, "[REDACTED]")
        print(output, flush=True)
        if args.live_h1:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from app.db import make_engine
            from app.extraction_store import APIUsage
            from app.models import Run
            from scripts.demo import load

            engine = make_engine(load(name)[2])
            with Session(engine) as session:
                run = session.scalar(select(Run))
                usage = session.scalars(select(APIUsage)).all()
                report = {
                    "mode": "LIVE_OPENAI_FRONTEND_H1",
                    "decision": run.decision if run else None,
                    "attempts": [
                        {
                            key: str(getattr(row, key)) if getattr(row, key) is not None else None
                            for key in (
                                "model_id",
                                "input_tokens",
                                "output_tokens",
                                "cached_tokens",
                                "cache_write_tokens",
                                "latency_ms",
                                "estimated_cost_usd",
                                "error_code",
                            )
                        }
                        for row in usage
                    ],
                    "actual_billed_cost_usd": None,
                }
                (ROOT / ".local/slice6-live-h1.json").write_text(
                    __import__("json").dumps(report, indent=2), encoding="utf-8"
                )
            engine.dispose()
        return result.returncode
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        for log in logs:
            log.close()
        reset(name, name)


if __name__ == "__main__":
    raise SystemExit(main())
