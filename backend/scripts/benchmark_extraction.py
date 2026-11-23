"""Explicit live-only benchmark; never imported by routine tests or production workers."""

import argparse
import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

from app.evidence_verification import verify
from app.extraction_client import ExtractionError, OpenAIExtractor, Rates
from app.extraction_evaluation import field_metrics, grounding_metrics
from scripts.evaluation_manifest import load_cases
from scripts.extraction_fixtures import fixture_set


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Explicitly authorize API calls with costs"
    )
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--manifest", type=Path, help="Private labelled real-invoice manifest")
    parser.add_argument("--output", type=Path, help="Private report destination")
    parser.add_argument("--model", choices=["gpt-6-luna", "gpt-6.1-terra"])
    parser.add_argument("--route", choices=["pdf", "text", "markdown"])
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Retain schema-valid raw extractions privately under .local",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Live benchmark requires --live; routine tests never call OpenAI")
    if args.max_calls < 1:
        parser.error("--max-calls must be positive")
    import os

    key = os.environ.get("OPENAI_API_KEY") or dotenv_values(".env").get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured. No calls made.")
    root = Path(__file__).resolve().parents[2]
    if args.artifacts_dir:
        args.artifacts_dir = args.artifacts_dir.resolve()
        if not args.artifacts_dir.is_relative_to((root / ".local").resolve()):
            parser.error(
                "Extraction artifacts must stay under the ignored workspace .local directory"
            )
        args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    rate_file = json.loads((root / "docs/benchmarks/openai-rates-2026-11-12.json").read_text())
    path = args.output or root / ".local" / "extraction-benchmark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = load_cases(args.manifest) if args.manifest else [(*case, {}) for case in fixture_set()]
    report = {
        "mode": "LIVE_OPENAI",
        "models": {},
        "cases": [],
        "calls": 0,
        "pricing_date": rate_file["date"],
        "billing_cost": None,
        "dataset": "USER_LABELLED" if args.manifest else "SYNTHETIC_FIXTURES",
        "review_metric": "Extraction evidence hold only; financial workflow not evaluated",
    }
    started = time.monotonic()
    routes = [
        ("gpt-6-luna", "text"),
        ("gpt-6-luna", "markdown"),
        ("gpt-6-luna", "pdf"),
        ("gpt-6.1-terra", "pdf"),
    ]
    if args.model or args.route:
        routes = [(args.model or "gpt-6-luna", args.route or "pdf")]
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
            for name, pdf, expected, expected_grounding in cases:
                if args.fixture and name != args.fixture:
                    continue
                if report["calls"] >= args.max_calls or time.monotonic() - started > 4 * 3600:
                    report["stop_reason"] = "BENCHMARK_BUDGET"
                    save()
                    return
                case = {"fixture": name, "model": model, "route": route, "attempts": []}
                report["cases"].append(case)

                def record(attempt):
                    case["attempts"].append(attempt)
                    save()

                def reserve(_):
                    if report["calls"] >= args.max_calls or time.monotonic() - started > 4 * 3600:
                        raise ExtractionError("BENCHMARK_BUDGET")
                    report["calls"] += 1
                    save()

                try:
                    case_started = time.monotonic()
                    extraction = clients[model].extract(
                        pdf,
                        route,
                        record,
                        rates,
                        before_attempt=reserve,
                    )
                    if args.artifacts_dir:
                        digest = hashlib.sha256((name + model + route).encode()).hexdigest()
                        artifact = args.artifacts_dir / (digest + ".json")
                        artifact.write_text(
                            json.dumps(
                                dict(
                                    mode="LIVE_OPENAI",
                                    fixture_id=name,
                                    document_sha256=hashlib.sha256(pdf).hexdigest(),
                                    extraction=extraction.model_dump(mode="json"),
                                    schema_version=case["attempts"][-1]["schema_version"],
                                    prompt_version=case["attempts"][-1]["prompt_version"],
                                    attempt_ids=[a["attempt_id"] for a in case["attempts"]],
                                ),
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        case["private_extraction_artifact"] = str(artifact)
                    case["fields"] = field_metrics(expected, extraction.model_dump())
                    checked = verify(extraction, pdf)
                    case["review_findings"] = checked.findings
                    case["grounded_fields"] = sum(p["grounded"] for p in checked.provenance)
                    case["grounding"] = grounding_metrics(expected_grounding, checked.provenance)
                    case["evidence_requires_review"] = checked.needs_review
                    case["elapsed_ms"] = int((time.monotonic() - case_started) * 1000)
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
