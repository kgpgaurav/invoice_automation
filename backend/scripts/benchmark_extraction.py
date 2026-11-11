"""Explicit live-only benchmark; never imported by routine tests or production workers."""

import argparse
import json
import time
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

from app.evidence_verification import verify
from app.extraction_client import ExtractionError, OpenAIExtractor, Rates
from app.extraction_evaluation import field_metrics
from scripts.extraction_fixtures import fixture_set


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Explicitly authorize API calls with costs"
    )
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--fixture", default=None)
    args = parser.parse_args()
    if not args.live:
        parser.error("Live benchmark requires --live; routine tests never call OpenAI")
    import os

    key = os.environ.get("OPENAI_API_KEY") or dotenv_values(".env").get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured. No calls made.")
    root = Path(__file__).resolve().parents[2]
    rate_file = json.loads((root / "docs/benchmarks/openai-rates-2026-11-12.json").read_text())
    path = root / ".local" / "extraction-benchmark.json"
    path.parent.mkdir(exist_ok=True)
    report = {
        "mode": "LIVE_OPENAI",
        "models": {},
        "cases": [],
        "calls": 0,
        "pricing_date": rate_file["date"],
        "billing_cost": None,
    }
    started = time.monotonic()
    routes = [
        ("gpt-6-luna", "text"),
        ("gpt-6-luna", "markdown"),
        ("gpt-6-luna", "pdf"),
        ("gpt-6.1-terra", "pdf"),
    ]
    clients = {}

    def save():
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    try:
        for model, _ in routes:
            if model not in clients:
                clients[model] = OpenAIExtractor(key, model)
                report["models"][model] = clients[model].available(model)
        save()
        for model, route in routes:
            if report["models"][model] != 200:
                continue
            config = rate_file["models"][model]
            rates = Rates(
                *(Decimal(config[k]) for k in ("input", "cached", "output")),
                source=rate_file["date"] + " " + config["source"],
                cache_write=Decimal(config["cache_write"]),
            )
            for name, pdf, expected in fixture_set():
                if args.fixture and name != args.fixture:
                    continue
                if report["calls"] >= args.max_calls or time.monotonic() - started > 4 * 3600:
                    report["stop_reason"] = "BENCHMARK_BUDGET"
                    save()
                    return
                case = {"fixture": name, "model": model, "route": route, "attempts": []}
                report["cases"].append(case)

                def record(attempt):
                    report["calls"] += 1
                    case["attempts"].append(attempt)
                    save()
                    if report["calls"] >= args.max_calls and attempt["error_code"]:
                        raise ExtractionError("BENCHMARK_BUDGET")

                try:
                    extraction = clients[model].extract(pdf, route, record, rates)
                    case["fields"] = field_metrics(expected, extraction.model_dump())
                    checked = verify(extraction, pdf)
                    case["review_findings"] = checked.findings
                    case["grounded_fields"] = sum(p["grounded"] for p in checked.provenance)
                except ExtractionError as error:
                    case["error"] = error.code
                save()
                print(
                    f"{model} {route} {name}: "
                    + case.get("error", case.get("fields", {}).get("accuracy", "unknown")),
                    flush=True,
                )
    finally:
        for client in clients.values():
            client.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save()


if __name__ == "__main__":
    main()
