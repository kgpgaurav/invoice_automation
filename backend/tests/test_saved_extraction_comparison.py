"""Offline evaluation cannot replace source provenance or hide missing printed fields."""

import json

import pytest

from scripts.compare_extraction_artifacts import printed_score


def test_printed_score_separates_unit_formatting_from_missing_values():
    raw = {"currency": "Rs.", "tax_rate": "10%", "subtotal_net": None}
    score = printed_score({"currency": "INR", "tax_rate": "10", "subtotal_net": "1000.00"}, raw)
    assert score == {"correct": 2, "total": 3, "missing": ["subtotal_net"], "incorrect": []}
    assert raw["tax_rate"] == "10%" and raw["currency"] == "Rs."


def test_saved_comparison_refuses_an_artifact_for_another_pdf(tmp_path, monkeypatch):
    from scripts import compare_extraction_artifacts as comparison

    root = tmp_path / "project"
    private = root / ".local"
    private.mkdir(parents=True)
    monkeypatch.setattr(comparison, "__file__", str(root / "backend/scripts/compare.py"))
    source = private / "sample.pdf"
    source.write_bytes(b"not-the-original-document")
    labels = private / "labels.json"
    labels.write_text(
        json.dumps([dict(fixture_id="case", source_pdf="sample.pdf")]), encoding="utf-8"
    )
    artifact = private / "artifact.json"
    artifact.write_text(
        json.dumps(dict(mode="LIVE_OPENAI", document_sha256="wrong-hash")), encoding="utf-8"
    )
    report = private / "report.json"
    report.write_text(
        json.dumps(dict(cases=[dict(fixture="case", private_extraction_artifact=str(artifact))])),
        encoding="utf-8",
    )
    output = private / "comparison.json"
    monkeypatch.setattr(
        "sys.argv",
        ["compare", "--manifest", str(labels), "--report", str(report), "--output", str(output)],
    )
    with pytest.raises(ValueError, match="provenance mismatch"):
        comparison.main()
    assert not output.exists()
