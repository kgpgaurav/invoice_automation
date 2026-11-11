# PS-1 implementation progress

Canonical requirements: SPEC.md. Archived plans are historical. Updated 2026-11-12.

| Slice | State | Evidence |
|---|---|---|
| 1 - durable intake/skeleton | Committed 97757cf | Upload/config/health/migrations and 20 original tests |
| 2 - worker infrastructure | Committed a0ba820 | Process competition, fencing, leases, recovery and 32 total tests |
| 3 - financial foundation | Committed df517a4 after review | Decimal rules/ledger/locking/rollback and 84 total tests |
| 4 - OpenAI extraction | Uncommitted for review | Live Luna/Terra Responses benchmark, strict schema, local verifier, usage persistence, mocked regression tests |

Final verification: **114 routine tests passed**, one opt-in live test skipped by default; the live test separately passed. Ruff, migration upgrade/downgrade/metadata checks, unchanged generated API types and frontend production build passed. All 84 prior regressions remain intact. PostgreSQL test instance stopped after validation.

Live account checks succeeded for gpt-6-luna and gpt-6.1-terra. The shared six-PDF matrix used 24 successful Responses calls in 286.5 seconds; all responses passed schema validation. Luna/PDF and Terra/PDF each matched 138/138 scored fields, including the scan. Luna text and Markdown each matched 115/138 (the image-only scan cannot be read from local text; 22 missing-field errors and one line-count mismatch). No missing fields were invented on the deliberately incomplete fixture. These are synthetic mini-set measurements, not production accuracy claims or the full >=20-document gold set.

Measured usage with dated standard-rate estimates (including cache writes): Luna/PDF **USD 0.005108050 total / six PDFs**, versus Terra/PDF **USD 0.04161050 / six PDFs**. Luna text and Markdown cost USD 0.00372860 and USD 0.003972700 respectively, but fail the scan. Luna/PDF is the provisional extraction candidate for this fixture scope; no claim of universal cheapest/most accurate model is made. Actual account billing is unavailable. See docs/benchmarks/slice4-measured.json for per-case values, tokens, latency and errors, and openai-rates-2026-11-12.json for attributed rates.

Two additional controlled Luna calls tested the evidence hold and the isolated live test; they are outside the 24-case benchmark totals. No live call invoked approval or changed a financial run. Production processing remains disabled. Scans, unknown evidence and inconsistent arithmetic still require review even when model field accuracy is high. The initial benchmark verifier held clean cases because bank evidence was masked; a narrow locally validated four-digit masking rule was added with positive/negative regression tests. A broader commercial-layout evidence verifier, real gold invoices, full tax/evidence validation and LangGraph/review orchestration remain future work.

Next milestone: review/commit Slice 4, then define a fenced worker-owned transaction/checkpoint integration before graph activation. The current approval service intentionally refuses the live worker's lock; do not remove this guard to make a demo run. No payment execution, vendor email, review UI or SSE is implemented.
