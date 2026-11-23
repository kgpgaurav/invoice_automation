"""Reverify saved live outputs without model calls, master data or financial posting."""

import argparse
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from app.evidence_verification import VERIFIER_VERSION, verify
from app.extraction_evaluation import field_metrics, flatten, grounding_metrics
from app.extraction_schema import InvoiceExtractionV1, InvoiceLineV1, parse_extraction


def printed_score(expected, extraction):
    truth, actual = flatten(expected), flatten(extraction)
    known = {
        k: v
        for k, v in truth.items()
        if v is not None and v != "UNKNOWN" and not k.endswith(".count")
    }
    correct, missing, wrong = 0, [], []
    numeric = {
        "quantity",
        "unit_price",
        "net_amount",
        "tax_amount",
        "gross_amount",
        "subtotal_net",
        "tax_total",
        "total_gross",
        "tax_rate",
    }
    for path, value in known.items():
        observed = actual.get(path)
        if path == "currency" and value == "INR" and observed in ("Rs", "Rs.", "INR"):
            observed = "INR"
        equal = observed == value
        if path.rsplit(".", 1)[-1] in numeric and observed is not None:
            try:
                token = str(observed).replace(",", "").strip()
                if path.endswith("tax_rate"):
                    token = token.removesuffix("%").strip()
                equal = Decimal(token) == Decimal(str(value))
            except InvalidOperation:
                equal = False
        correct += bool(equal)
        if actual.get(path) is None:
            missing.append(path)
        elif not equal:
            wrong.append(path)
    return dict(correct=correct, total=len(known), missing=missing, incorrect=wrong)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private = Path(__file__).resolve().parents[2] / ".local"
    if not args.output.resolve().is_relative_to(private.resolve()):
        parser.error("Private invoice comparison reports must stay under workspace .local")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    labels = {c["fixture_id"]: c for c in json.loads(args.manifest.read_text(encoding="utf-8"))}
    cases, attempts = [], []
    versions = ("layout-diagnostics-5", VERIFIER_VERSION)
    for case in report["cases"]:
        label = labels[case["fixture"]]
        artifact = json.loads(Path(case["private_extraction_artifact"]).read_text(encoding="utf-8"))
        content = (args.manifest.resolve().parent / label["source_pdf"]).read_bytes()
        if (
            artifact["mode"] != "LIVE_OPENAI"
            or artifact["document_sha256"] != hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("Artifact source/provenance mismatch")
        schema_version = artifact.get("schema_version") or case["attempts"][-1].get(
            "schema_version", "InvoiceExtractionV1.1"
        )
        raw = parse_extraction(artifact["extraction"], schema_version)
        entry = dict(
            fixture_id=case["fixture"],
            strict_raw_fields=case["fields"],
            versions={},
            canonical_printed_fields=printed_score(label["expected_fields"], raw.model_dump()),
        )
        for version in versions:
            wire = raw
            if version != VERIFIER_VERSION:
                # Frozen verifiers receive their original schema, never additive fields.
                core = {
                    k: getattr(raw, k)
                    for k in InvoiceExtractionV1.model_fields
                    if k != "line_items"
                }
                core["line_items"] = [
                    {k: getattr(line, k) for k in InvoiceLineV1.model_fields}
                    for line in raw.line_items
                ]
                wire = InvoiceExtractionV1.model_validate(core)
            checked = verify(wire, content, version=version)
            actual = {}
            if checked.document:
                actual = checked.document.model_dump(mode="json")
                actual["line_items"] = actual.pop("lines")
                actual.pop("verification_findings", None)
                actual.pop("evidence", None)
            entry["versions"][version] = dict(
                findings=list(checked.findings),
                normalized_fields=field_metrics(label["expected_financial_fields"], actual),
                grounding=grounding_metrics(label["expected_grounding"], checked.provenance),
                unresolved_required=[
                    dict(field=p["field"], state=p.get("state"), reason=p.get("reason_code"))
                    for p in checked.provenance
                    if p.get("required") and not p["grounded"]
                ],
            )
        cases.append(entry)
        attempts.extend(case["attempts"])
    latency = sorted(a["latency_ms"] for a in attempts)
    costs = [a["estimated_cost_usd"] for a in attempts]
    summary = dict(
        mode="OFFLINE_COMPARISON_OF_LIVE_ARTIFACTS",
        new_api_calls=0,
        source_api_calls=report["calls"],
        documents=len(cases),
        versions={},
        layout_families=len({label.get("layout_family") for label in labels.values()}),
        strict_raw_correct=sum(c["strict_raw_fields"]["correct"] for c in cases),
        strict_raw_total=sum(c["strict_raw_fields"]["total"] for c in cases),
        printed_correct=sum(c["canonical_printed_fields"]["correct"] for c in cases),
        printed_total=sum(c["canonical_printed_fields"]["total"] for c in cases),
        printed_missing=sum(len(c["canonical_printed_fields"]["missing"]) for c in cases),
        api_latency_p50_ms=median(latency) if latency else None,
        api_latency_p95_nearest_rank_ms=latency[math.ceil(0.95 * len(latency)) - 1]
        if latency
        else None,
        estimated_cost_usd=str(sum(map(Decimal, costs)))
        if costs and all(c is not None for c in costs)
        else None,
        billed_cost_usd=None,
        rate_date=report["pricing_date"],
        notice="Refinement set, not held out. Evidence holds are separate from financial review. "
        "Raw scores retain representation differences; printed scores canonicalize units/grouping. "
        "No new model calls, approvals or PO writes.",
    )
    for version in versions:
        values = [c["versions"][version] for c in cases]
        summary["versions"][version] = dict(
            normalized_correct=sum(v["normalized_fields"]["correct"] for v in values),
            normalized_total=sum(v["normalized_fields"]["total"] for v in values),
            grounded=sum(v["grounding"]["true_supported"] for v in values),
            missed_supported=sum(v["grounding"]["missed_supported"] for v in values),
            false_supported=sum(v["grounding"]["false_supported"] for v in values),
            evidence_holds=sum(bool(v["findings"]) for v in values),
        )
    root = Path(__file__).resolve().parents[1] / "app"
    hashes = {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest()
        for n in (
            "evidence_verification.py",
            "source_layout_v6.py",
            "evidence_layout_v6.py",
            "extended_verification.py",
            "extended_verification_v7.py",
            "extended_sources.py",
            "document_classification.py",
        )
    }
    args.output.write_text(
        json.dumps(dict(summary=summary, cases=cases, verifier_source_sha256=hashes), indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
