# Sanitized evaluation evidence

[Documentation](../README.md) · [Verification](../DEVELOPMENT.md)

These files retain dated extraction/token measurements and pricing assumptions without provider keys, database credentials, invoice PDFs or personal deployment settings. Each report identifies synthetic fixtures or user-supplied invoices and its live/replay mode. They do not guarantee current model availability, present pricing, broad accuracy or successful hosted processing.

| File                                                                   | Purpose                                                                                                  |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [openai-rates-2026-11-12.json](openai-rates-2026-11-12.json)           | Dated standard-rate snapshot with attribution. Demo/benchmark/live-test scripts read it; keep it tracked |
| [slice4-measured.json](slice4-measured.json)                           | Recorded text/PDF extraction comparison, tokens, errors, latency and estimated costs                     |
| [slice5-live-h1.json](slice5-live-h1.json)                             | Controlled workflow H1 usage/result measurement                                                          |
| [slice6-live-h1.json](slice6-live-h1.json)                             | Controlled frontend/source-verification H1 measurement                                                   |
| [predeploy-live-h1-2026-11-14.json](predeploy-live-h1-2026-11-14.json) | Separately authorized personal-key H1 smoke and recorded usage                                           |
| [extraction-diagnostics-2026-11-23.json](extraction-diagnostics-2026-11-23.json) | Generated table with a scripted missing-date repair and local verifier timings; zero OpenAI calls |
| [expanded-extraction-2026-11-23.json](expanded-extraction-2026-11-23.json) | Sanitized five-document source comparison, two prompt-4 live checks, regression counts and limitations |

Token-derived USD figures are **estimates using the stated rate date**, not account billing receipts. Unknown billed cost stays unknown. An extraction response conforming to a schema is not proof of factual correctness; source/evidence and deterministic financial checks remain independent. Mock transport is explicitly labelled and does not count as a live extraction benchmark.

Routine regressions do not invoke billable extraction. Live tests/benchmark scripts require separate explicit activation and configured credentials; merely reading these records does not run them. The current project does not claim a universally cheapest model, broad commercial-layout/scan accuracy, or a valid H2 ₹2 rounding demonstration.

## User-provided layouts

Keep realistic invoice PDFs, labels and reports under ignored `.local/`, outside Git. Independently label each field from the document before running extraction. A manifest is a JSON array; PDF paths are relative to the manifest:

```json
[
  {
    "fixture_id": "unseen-layout-01",
    "source_pdf": "invoice.pdf",
    "expected_fields": {
      "invoice_number": "INV-001",
      "invoice_date": "2026-11-20",
      "total_gross": "11800.00"
    },
    "expected_grounding": {
      "invoice_number": true,
      "invoice_date": true,
      "total_gross": true
    }
  }
]
```

`expected_fields` may contain any supported extraction fields, including `line_items` in source order. Use null for genuinely absent/ambiguous values; independently labelled grounding keys use `lines.1.quantity` etc. Supply both supportable and unsupportable cases to measure false grounding, rather than counting citations as proof. Broaden labels beyond the short illustration above for meaningful completeness results.

From backend, **when intentionally authorizing paid calls**:

```cmd
uv run python -m scripts.benchmark_extraction --live --manifest ../.local/invoices/labels.json --model gpt-6-luna --route pdf --max-calls 10 --output ../.local/invoices/report.json
```

The maximum is checked before every Responses dispatch, including transport/schema retries. The runner records per-case field accuracy/completeness, independently labelled grounding precision/recall, evidence review findings, elapsed time, token usage and dated rate estimates. Completeness counts known expected field values, excluding UNKNOWN and structural row counts; exact-match accuracy retains expected nulls and row-count checks. Unknown denominators and billed cost remain null. Reports distinguish user-labelled datasets from generated fixtures. The rate snapshot is dated **12 November 2026**, not a promise of current pricing; confirm account availability/rates before a paid comparison.

This harness measures extraction and evidence holds, not final financial review rate or approvals. Workflow repair/resume/ledger safety is exercised separately in PostgreSQL regression tests. The initial diagnostic slice made no paid calls; the subsequently approved user-supplied batch is described below. Broader held-out accuracy and scanned corroboration remain unmeasured.

### Retain and compare fresh outputs privately

The subsequent five-document user-supplied benchmark used five explicitly approved live requests. It covers two digital layout families used for verifier refinement, with no scans or held-out claims. Aggregate measurements and limitations are recorded in [DEVELOPMENT.md](../DEVELOPMENT.md); raw documents/responses/labels/reports remain ignored and private.

The expanded-schema check used two further authorized requests on two of those original PDFs. All 20 additional printed fields were extracted correctly under declared numeric/address punctuation normalization; 19 had independent source grounding and one optional buyer address remains unverified. Raw exact-match accuracy remains separately reported as 101/108, including address formatting and tax-convention representation differences. API latency was 18.156–23.171 seconds; estimated total cost was USD 0.00311269 using the existing dated rate snapshot. These two cases are validation on the refinement set, not an independent unseen-layout benchmark. Every scanned document is required to review; rasterized/OCR-overlay workflow fixtures use labelled saved-output replay and are not fresh scan-accuracy measurements.

Add `--artifacts-dir ../.local/invoices/extractions` to an intentionally authorized live command to retain schema-valid raw responses and source hashes. Artifacts are refused outside workspace `.local`. Then compare the same saved responses without another API request:

```cmd
uv run python -m scripts.compare_extraction_artifacts --manifest ../.local/invoices/labels.json --report ../.local/invoices/report.json --output ../.local/invoices/comparison.json
```

For this comparison, each independently authored label entry also needs `expected_financial_fields` (same field shape, with justified canonical/derived values) and optionally `layout_family`. Do not generate gold labels from the verifier or the model under evaluation. The comparison checks the source hash and reports raw-wire match, canonicalized printed-field correctness/completeness, normalized-field match and grounding separately. It is explicitly an offline comparison of earlier live outputs, never represented as a new model call. Cost uses the earlier attempt measurements; account billing remains unknown.
