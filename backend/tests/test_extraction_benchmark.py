"""Private gold manifests and pre-dispatch benchmark limits; no paid calls."""

import json

import httpx
import pytest

from scripts.evaluation_manifest import load_cases
from tests.extraction_helpers import case
from tests.test_extraction import extractor


def test_private_manifest_loads_independent_field_and_grounding_labels(tmp_path):
    pdf, _ = case()
    (tmp_path / "sample.pdf").write_bytes(pdf)
    manifest = tmp_path / "labels.json"
    manifest.write_text(
        json.dumps(
            [
                dict(
                    fixture_id="unseen-layout-01",
                    source_pdf="sample.pdf",
                    expected_fields={"total_gross": "11800.00"},
                    expected_grounding={"total_gross": True},
                )
            ]
        ),
        encoding="utf-8",
    )
    ident, content, expected, grounding = load_cases(manifest)[0]
    assert ident == "unseen-layout-01" and content == pdf
    assert expected == {"total_gross": "11800.00"} and grounding == {"total_gross": True}


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [{}],
        [
            dict(
                fixture_id="bad",
                source_pdf="unused.pdf",
                expected_fields={"tax_total": None},
                expected_grounding={"tax_total": "true"},
            )
        ],
    ],
)
def test_unlabelled_or_nonboolean_grounding_truth_is_rejected(tmp_path, entries):
    manifest = tmp_path / "labels.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(manifest)


def test_benchmark_budget_is_checked_before_dispatch_even_after_transient_errors(
    tmp_path, monkeypatch
):
    from scripts import benchmark_extraction

    dispatched = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={})
        dispatched.append(request)
        return httpx.Response(500, json={})

    client = extractor(handler)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(benchmark_extraction, "OpenAIExtractor", lambda *args: client)
    pdf, expected = case()
    monkeypatch.setattr(benchmark_extraction, "fixture_set", lambda: [("clean", pdf, expected)])
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchmark",
            "--live",
            "--max-calls",
            "1",
            "--model",
            "gpt-6-luna",
            "--route",
            "pdf",
            "--output",
            str(report),
        ],
    )
    benchmark_extraction.main()
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert len(dispatched) == saved["calls"] == 1
    assert saved["billing_cost"] is None
    assert saved["cases"][0]["error"] == "BENCHMARK_BUDGET"
