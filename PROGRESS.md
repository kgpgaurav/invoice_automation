# PS-1 implementation progress

Slice 5 closure for Slice 6A: reviewed against ba58c43 and verified **141 passed / 2 opt-in skips**, Ruff, migrations, generated types, frontend build and Git checks. No critical defect found. Slice 5 is committed as a separate baseline before Slice 6A; older uncommitted references below are historical. No push.

## Current: Slice 5 complete, uncommitted for review

Slice 4 was reviewed against df517a4, corrected without evidence exemptions, and committed separately as **ba58c43**. Clean and alternate-layout PDFs now both pass the strict local-evidence-to-financial regression. No remote push occurred. SPEC remains canonical; financial policy defaults are unchanged.

Slice 5 integrates the separate worker, OpenAI Responses extraction, deterministic financial engine and typed LangGraph with PostgreSQL checkpoints. The worker-owned finalizer proves physical advisory-lock ownership and owner/attempt/deadline fencing, re-verifies the original PDF and uses the existing atomic locked ledger transaction. Checkpoint replay cannot double-post funds. Private extraction/history and version metadata remain outside graph state.

Real PO-selection interrupts publish only after durable checkpointing, retire the queue lease and release worker ownership while waiting. Minimal authenticated review APIs use closed actions, generation and idempotency. Resume acquires fresh ownership on the same thread, revalidates vendor/PO/quantities/taxes/balance/duplicates/policy, and cannot waive spending limits. Rejection and request-info work without extraction; request-info stops rather than looping.

**Verification: 141 routine tests passed, 2 paid live tests skipped by default.** This preserves all original 114 regressions, adds 3 Slice 4 closure regressions and 24 Slice 5 routine cases. Ruff check/format, locked dependency check, real PostgreSQL migration upgrade/downgrade/metadata parity, generated API reproducibility, frontend TypeScript/Vite build and Git whitespace/ignored-secret checks passed. Abrupt exits before financial commit and after commit/before checkpoint recover in a fresh process with one ledger entry, unchanged original PDF and no repeat model call. Concurrent PO approvals cannot overspend; review conflicts/replay, changed balances, injected rollback, malformed extraction and checkpoint-before-review-publication recovery are covered.

**Explicit live H1 passed** using configured gpt-6-luna, a real synthetic PDF and isolated synthetic masters: extraction → local evidence → deterministic approval → one immutable ledger allocation. One Responses request, 1122 input / 1349 output tokens, 0 cached / 1119 cache-write tokens, 13.25s model latency, estimated USD **0.0008146750**; actual billing unknown. The disposable schemas were removed. See [live report](docs/benchmarks/slice5-live-h1.json).

Default worker invocation still exits without claiming jobs. Controlled operation requires explicit --enable-processing, registered immutable policy/masters, checkpoint setup and configured OpenAI credentials/model. The opt-in flag does not establish unrestricted production readiness. Single-reviewer token auth is local; broad real-layout grounding, scan corroboration, the >=20 real-document gold set, full tax profiles, valid H2 rounding evidence and deployed hosting/identity remain open. Existing UI is still the intake/status shell; review is an API path. No payment, email, ERP writes, review UI, SSE or exports were added.

Exact file manifest, reproduction commands, transaction/recovery contracts and observed failures/results: [DEVELOPMENT.md](docs/DEVELOPMENT.md) and [DECISIONS.md](docs/DECISIONS.md). Slice 5 is deliberately **uncommitted**. The records below are the historical Slice 4 handoff, superseded by this status.

## Historical Slice 4 handoff

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
