# Sanitized evaluation evidence

[Documentation](../README.md) · [Verification](../DEVELOPMENT.md)

These files retain dated extraction/token measurements and pricing assumptions without provider keys, database credentials, invoice PDFs or personal deployment settings. They are evidence from controlled synthetic tests, not a guarantee of current model availability, present pricing, broad accuracy or successful hosted processing.

| File                                                                   | Purpose                                                                                                  |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [openai-rates-2026-11-12.json](openai-rates-2026-11-12.json)           | Dated standard-rate snapshot with attribution. Demo/benchmark/live-test scripts read it; keep it tracked |
| [slice4-measured.json](slice4-measured.json)                           | Recorded text/PDF extraction comparison, tokens, errors, latency and estimated costs                     |
| [slice5-live-h1.json](slice5-live-h1.json)                             | Controlled workflow H1 usage/result measurement                                                          |
| [slice6-live-h1.json](slice6-live-h1.json)                             | Controlled frontend/source-verification H1 measurement                                                   |
| [predeploy-live-h1-2026-11-14.json](predeploy-live-h1-2026-11-14.json) | Separately authorized personal-key H1 smoke and recorded usage                                           |

Token-derived USD figures are **estimates using the stated rate date**, not account billing receipts. Unknown billed cost stays unknown. An extraction response conforming to a schema is not proof of factual correctness; source/evidence and deterministic financial checks remain independent. Mock transport is explicitly labelled and does not count as a live extraction benchmark.

Routine regressions do not invoke billable extraction. Live tests/benchmark scripts require separate explicit activation and configured credentials; merely reading these records does not run them. The current project does not claim a universally cheapest model, broad commercial-layout/scan accuracy, or a valid H2 ₹2 rounding demonstration.
