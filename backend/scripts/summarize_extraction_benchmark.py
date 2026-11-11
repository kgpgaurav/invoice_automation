"""Publish synthetic-fixture metrics only; never publish keys, PDF text or provider bodies."""

import json
from decimal import Decimal
from pathlib import Path
from statistics import median

from app.extraction_client import Rates, estimated_cost


def summarize(report):
    groups = {}
    cases = []
    for case in report["cases"]:
        attempts = case["attempts"]
        metrics = case.get("fields", {})
        row = {k: case[k] for k in ("model", "route", "fixture")}
        row.update(
            fields=metrics,
            review_findings=case.get("review_findings"),
            error=case.get("error"),
            latency_ms=sum(a["latency_ms"] for a in attempts),
            input_tokens=sum((a.get("usage") or {}).get("input_tokens", 0) for a in attempts),
            output_tokens=sum((a.get("usage") or {}).get("output_tokens", 0) for a in attempts),
            cached_tokens=sum(
                (a.get("usage") or {}).get("input_tokens_details", {}).get("cached_tokens", 0)
                for a in attempts
            ),
            cache_write_tokens=sum(
                (a.get("usage") or {}).get("input_tokens_details", {}).get("cache_write_tokens", 0)
                for a in attempts
            ),
            estimated_cost_usd=(
                str(sum((Decimal(a["estimated_cost_usd"]) for a in attempts), Decimal("0")))
                if all(a["estimated_cost_usd"] is not None for a in attempts)
                else None
            ),
            returned_models=sorted({a["model_id"] for a in attempts}),
            attempt_count=len(attempts),
        )
        cases.append(row)
        groups.setdefault(case["model"] + "/" + case["route"], []).append(row)
    summary = {}
    for name, rows in groups.items():
        correct = sum(r["fields"].get("correct", 0) for r in rows)
        total = sum(r["fields"].get("total", 0) for r in rows)
        costs = [r["estimated_cost_usd"] for r in rows]
        summary[name] = {
            "cases": len(rows),
            "correct_fields": correct,
            "total_fields": total,
            "field_accuracy": str(Decimal(correct) / total) if total else None,
            "missing_errors": sum(len(r["fields"].get("missing_fields", [])) for r in rows),
            "invented_errors": sum(len(r["fields"].get("invented_fields", [])) for r in rows),
            "median_latency_ms": median(r["latency_ms"] for r in rows),
            "estimated_cost_usd": str(sum((Decimal(c) for c in costs), Decimal("0")))
            if all(c is not None for c in costs)
            else None,
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "cached_tokens": sum(r["cached_tokens"] for r in rows),
            "cache_write_tokens": sum(r["cache_write_tokens"] for r in rows),
        }
    return {
        "mode": "LIVE_OPENAI_SYNTHETIC_FIXTURES",
        "pricing_date": report["pricing_date"],
        "availability_status": report["models"],
        "response_attempts": report["calls"],
        "elapsed_seconds": report.get("elapsed_seconds"),
        "billing_cost": None,
        "cost_note": (
            "Estimated from returned usage and dated standard rates; "
            "not an account billing receipt."
        ),
        "summary": summary,
        "cases": cases,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    report = json.loads((root / ".local/extraction-benchmark.json").read_text())
    prices = json.loads((root / "docs/benchmarks/openai-rates-2026-11-12.json").read_text())
    if prices["date"] != report["pricing_date"]:
        raise ValueError("Use the benchmark's dated historical rates")
    for case in report["cases"]:
        price = prices["models"][case["model"]]
        rates = Rates(
            *(Decimal(price[k]) for k in ("input", "cached", "output")),
            source=price["source"],
            cache_write=Decimal(price["cache_write"]),
        )
        for attempt in case["attempts"]:
            cost = estimated_cost(attempt["usage"], rates)
            attempt["estimated_cost_usd"] = str(cost) if cost is not None else None
    result = summarize(report)
    (root / "docs/benchmarks/slice4-measured.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
