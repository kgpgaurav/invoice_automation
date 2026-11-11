# Development and verification

Slice 5 closure before Slice 6A: reviewed the complete uncommitted diff against ba58c43, including owning-connection/lease fencing, transactional financial authorization, checkpoint recovery, source reconstruction, immutable history and idempotent review generations. No critical defect found. Re-ran the full real-PostgreSQL suite: **141 passed, 2 opt-in skips in 165.19s**. Ruff check/format, migration down/up/metadata parity, OpenAPI generation, frontend build and Git checks passed. Commit this Slice 5 baseline separately before new implementation; earlier uncommitted statements are historical. No push.

## Current Slice 5: durable graph and review backend (2026-11-12)

Slice 4 was reviewed against df517a4 and committed separately as **ba58c43** after 117 passing routine tests. The clean/alternate evidence regressions pass without fixture exemptions: exact local labelled evidence remains required; geometric PDF lines fix merged columns. The older Slice 4 records below describe earlier measurements. Slice 5 is uncommitted; no push occurred. SPEC §§2.3, 3.1–3.4 and 4.1 govern this backend milestone. Financial policy defaults are unchanged.

### Implemented boundary and files

- `backend/app/ownership.py`: require the actual advisory-lock-owning physical PostgreSQL connection plus locked queue owner/attempt/deadline, before and after each transaction. A per-claim mutex serializes graph checkpoint callbacks and node transactions on that connection. No model request holds a transaction.
- `backend/app/owned_finalizer.py`: reconstruct trusted evidence from the private untrusted extraction and original hash-checked PDF. Reuse the existing financial transaction, with current vendor/identity/PO/line locks, committed-allocation reconciliation and immutable ledger constraints. Never accept caller-supplied trusted flags or a freely selected PO. Return the committed ledger result on graph replay. `backend/app/approval.py` shares the existing transaction body; its direct fixture-only/advisory-lock guards remain intact.
- `backend/app/workflow.py`: typed StateGraph with loading, extraction, local verification, matching, finalization, review preparation, a side-effect-free interrupt, and authorized action application. Stable run/thread IDs survive resume. Graph state holds IDs, generations, routing codes and candidate IDs, with no PDF, snippets, secrets or connections. LangSmith tracing is explicitly disabled. All graph effects and checkpoint writes are fenced. Public events reflect executing nodes, not timers. Each OpenAI attempt is reserved before HTTP; two attempts total across transport/schema repair/one critical-source retry and restarts. Known arithmetic/currency failures are held without another extraction. Persisted extraction reused after recovery is explicitly labelled, never represented as another live call.
- `backend/app/checkpoints.py`: explicit PostgreSQL PostgresSaver setup and fenced writes. Tables live in `<business_schema>_lg`; library migrations use a direct autocommit connection, separate from business Alembic migrations. No in-memory fallback. Worker startup preflight checks the registered policy, checkpoint migration version and configured model availability before claiming jobs.
- `backend/app/workflow_models.py`, model registration in `backend/app/models.py`, migration `backend/alembic/versions/0005_workflow_workflow_artifacts_and_review_lifecycle.py`: private frozen model/policy/prompt/schema/graph/verifier/route/mode metadata, bounded extraction reservations, source extraction/history, review requests/generations and immutable reviewer actions. At most one PREPARED/OPEN review per run; one action per request and one resume job per generation. Financial history remains append-only. Earlier migrations are unchanged.
- `backend/app/review_contracts.py`, `backend/app/reviews.py`, `backend/app/main.py`: planned authenticated review read/respond paths. Closed SELECT_PO/REJECT/REQUEST_INFO actions; strict payload, generation, idempotency header and nonempty reason. A configured reviewer actor is supplied server-side. Resolution/action/event/RESUME enqueue commit together. Busy ownership, stale generations and conflicting repeats return 409; retry an identical request after a busy response. Persisted identical replay returns 202 without another action/job. Read responses include candidate PO IDs, readable numbers, current status/currency and remaining gross for display; posting always rechecks under locks. No manual approval override.
- `backend/app/config.py`, `backend/.env.example`: optional separate REVIEWER_API_TOKEN, at least 24 characters, ignored locally like existing credentials. The application upload/read token alone cannot resolve reviews. Unconfigured reviewer access fails closed.
- `backend/app/worker.py`: PROCESS/RESUME claiming for the graph processor, heartbeat/lease/session-lock protection retained. Completed financial decisions are preserved during crash reconciliation even at technical retry exhaustion. A successfully checkpointed interrupt is published OPEN/WAITING_REVIEW and its queue lease retired before releasing the worker connection. REQUEST_INFO stops INTERRUPTED with no financial verdict. Default CLI exits 2 without claiming; explicit controlled processing uses the real OpenAI adapter only.
- `backend/app/extraction_client.py`: add a fenced pre-attempt reservation callback, shared remaining-attempt limit, and optional critical-source repair instructions. Existing Responses/Structured Outputs, nullable values, usage and error handling remain in use.
- `backend/pyproject.toml`, `backend/uv.lock`: locked LangGraph 1.2.20 / checkpoint-postgres 3.2.0 and dependencies. No additional model provider, Redis or tracing service is configured.
- `frontend/openapi.json`, `frontend/src/api.generated.ts`: regenerate only the additive review API contracts; no frontend UI source change.
- `backend/tests/conftest.py`: isolate checkpoint schemas alongside existing random real PostgreSQL business schemas and remove both after tests. New `test_owned_finalizer.py`, `test_workflow.py`, `test_workflow_concurrency.py`, `test_workflow_financial.py`, `test_workflow_reviews.py`, `test_workflow_recovery.py`, `test_workflow_safety.py`, `test_workflow_live.py`, `workflow_helpers.py`, `workflow_harness.py` cover ownership, HTTP intake to decision, mocked extraction, cap/duplicate safety, real interrupts, authorization, stale/replayed actions, rollback, concurrent allocations and abrupt subprocess termination. Live smoke is separately opt-in.
- `docs/DECISIONS.md`, this file and root `PROGRESS.md`: contract refinements, recovery rules, verification results and activation limits. `docs/benchmarks/slice5-live-h1.json` retains the sanitized live H1 model/usage/latency/estimate; no document contents, credential or run identifier.

### Controlled operation

From backend, install with `uv sync --locked`; apply business migrations with `uv run alembic upgrade head` (**0005_workflow**). Register the intended immutable policy through `register_policy(engine, FinancialPolicy(...), "local-operator")`; do not overwrite an existing version. Provision reviewed vendor/PO masters explicitly. Tests create synthetic masters only in disposable schemas; the worker does not fabricate them.

Configure DATABASE_URL, APP_API_TOKEN, OPENAI_API_KEY and explicit OPENAI_MODEL in ignored backend/.env. For review responses configure a separate REVIEWER_API_TOKEN. Use a direct or session-pooled PostgreSQL connection; transaction pooling cannot preserve session advisory locks. No worker is started by FastAPI or uploads.

```powershell
# Explicit checkpoint installation; does not process invoices or register financial masters.
uv run python -m app.worker --setup-checkpoints
# Controlled single-job operation after policy, masters and schema setup:
uv run python -m app.worker --enable-processing --policy-version policy-1.1-demo --once
```

Omitting `--once` runs the explicitly enabled separate worker until SIGINT/SIGTERM. Default `uv run python -m app.worker` remains disabled. Readiness still reports API/business-schema readiness only, not a running worker. The existing UI is still the Slice 1 intake/status shell and its static notice is historical; no review UI/SSE was added in this backend slice.

Review API: application bearer GET `/api/v1/runs/{id}/review`; reviewer bearer POST `/api/v1/reviews/{review_id}/respond` with `X-Idempotency-Key` and body `{"generation":1,"action":"SELECT_PO","payload":{"po_id":"<offered UUID>"},"reason":"<supporting rationale>"}`. REJECT/REQUEST_INFO require `payload:{}`. API resolution queues work; it never posts an approval. A selected PO is a reviewer input alongside the original null printed reference, not forged PDF evidence. Resume uses the same checkpoint thread and freshly acquired ownership. Changed state/balance creates a new hold; REQUEST_INFO is a stopped workflow requiring corrected source intake, not an endless question loop.

### Recovery and limits

PDF bytes remain in PostgreSQL. Successful extraction artifacts persist before checkpoint return; API usage is saved after each response. A crash between a provider response and persistence can leave unknown billing; reservations cap reissued calls but do not promise exactly-once model billing. Missing usage/cost stays null. Runtime estimates are nullable unless explicit dated Rates are supplied; the controlled live smoke supplies the existing dated snapshot.

Before financial commit, all invoice/ledger/allocation/counter/assessment/decision/event effects roll back together. After financial commit but before a graph checkpoint, recovery preserves the terminal decision, requeues reconciliation even at attempt exhaustion and returns the existing ledger result. Checkpoint-before-public-review recovery re-enters the side-effect-free interrupt and publishes the existing PREPARED request. No lock/transaction is retained while awaiting human input. Nonterminal technical failures remain bounded FAILED/null-decision outcomes; waiting review is not a technical retry.

This validates the single-reviewer local backend boundary. Broad commercial-layout grounding, scan corroboration, >=20 real-document gold evaluation, full tax profiles, valid H2 rounding approval, deployed identity/hosting and backup/retention remain open. No payment execution, ERP writes, vendor email, full review UI, exports or SSE is added. Unrestricted production activation is not claimed.

### Slice 5 verification record

| Command/check | Observed result |
|---|---|
| Full `python -m pytest -q` against real PostgreSQL 17 | **141 passed, 2 skipped in 148.31s**; original 114 regressions preserved, 3 Slice 4 closure tests + 24 Slice 5 routine cases; no routine warnings |
| Explicit `PS1_LIVE_WORKFLOW=1 python -m pytest tests/test_workflow_live.py -q -s` | **1 passed in 19.65s**, real Luna/PDF to one approval; one benign Windows pytest-cache permission warning under escalated execution |
| `ruff check .` / `ruff format --check .` | Passed; 65 files formatted |
| `uv lock --check --offline` | Passed; 68 locked packages resolved |
| Migration upgrade / metadata parity / downgrade-to-base / re-upgrade | Passed in isolated schemas, including 0005; checkpoint setup/version preflight separately passed in real graph/live tests |
| `python -m scripts.export_openapi`, `npm.cmd run generate:api` | Passed; regenerated type-file hash unchanged on repeat |
| `npm.cmd run build` | Passed TypeScript and Vite production build; 28 modules |
| Git checks | Whitespace passed; no staged Slice 5 changes; .env/.venv/.local PDFs ignored; no remote/push |

Verified outcomes: H1 approved once; E1 prior 70000 + next 35000 against 100000 cap holds the next invoice with 5000 excess and no over-allocation; E2 interrupts/resumes to approval only after fresh PO checks. Missing/unverifiable/scanned/unsupported/arithmetic failures never approve. Two graph owners sharing a 15000 PO cap post one 11800 invoice and hold the other. Ownership loss, wrong connection/attempt, post-write lease expiry and injected financial-event failure prevent posting or roll back all financial effects. Abrupt subprocess exit before commit and after commit/before checkpoint recovers with the same PDF/thread, one ledger entry and one recorded API request; committed-decision reconciliation works at exhausted technical attempt limits. PREPARED interrupt recovery, concurrent review conflicts, repeated actions, stale generations, immutable action history and action/queue rollback pass. A REQUEST_INFO stop emits STAGE_FINISHED with no financial decision and never a misleading RUN_COMPLETED event.

Live H1 used **gpt-6-luna**, one request, **1122 input / 1349 output**, **0 cached / 1119 cache-write tokens**, **13250ms** model latency, **USD 0.0008146750** estimated at the dated standard rates; actual billed cost is unknown. See [sanitized report](benchmarks/slice5-live-h1.json) and the [official rate source](https://developers.openai.com/api/docs/models/gpt-6-luna). No payment executed; only synthetic masters in disposable test schemas were posted.

Earlier failed checks found a status-notice regression and a stale ORM queue read; both were corrected without weakening ownership or old tests. The post-write lease-expiry regression now proves financial rollback. An initial retry-count test expected one call for scans; it was corrected to assert SPEC's bounded critical-source retry, while arithmetic/currency failures use one call. Initial Ruff line/import issues were corrected. Vite used the previously approved ancestor-directory access on Windows. No failed check remains. The project-only test PostgreSQL cluster is stopped after validation; the separate port-5432 service is unaffected. Slice 5 remains uncommitted for review.

## Current Slice 4: OpenAI extraction (2026-11-12)

Closure before Slice 5: reviewed all uncommitted extraction sources/tests/migration/report against df517a4. Investigated original clean/alternate UNVERIFIED_TOTAL independently: clean is resolved by narrow bank mask handling; alternate remained broken because get_text(sort=True) merged columns. Local page inspection now preserves geometric lines, retaining exact label/value/page checks. Independent evidence regressions demonstrate both clean and alternate become eligible for the existing financial assessment; no fixture-specific exemption or evidence relaxation. Also reject malformed numeric grouping rather than silently stripping arbitrary commas. Verifier version is labelled-fields-3. Original benchmark findings remain unchanged historical measurements. Full closure regression: 117 passed, one opt-in live skip, existing TestClient warning; Ruff and frontend build passed; migration roundtrip included. Commit Slice 4 separately before ownership/graph changes. Earlier uncommitted statements below are historical.

Slice 3 closure review and regression checks passed before its separate commit **df517a4**. Reviewed allocation locks, Decimal precision, canonical identity, immutable history, replay, migration teardown and transaction rollback against a0ba820; no critical defect was found. All 84 tests passed again, as did Ruff, migration roundtrip/parity, Git whitespace checks and frontend production build. No push occurred. The earlier Slice 3 uncommitted statement below is historical; Slice 4 alone is left uncommitted.

SPEC §§1.1, 3.5–3.6 and 5.2 plus the explicit Slice 4 user requirements govern this work. The only SPEC clarification is preserving printed currencies and nullable missing line fields/rate/basis at the extraction boundary; financial INR-only policy and all approval defaults are unchanged. No HTTP route or UI was added. Production worker code and the financial locking guards are unchanged.

### Exact source changes

- `app/extraction_schema.py`: sole Pydantic InvoiceExtractionV1/line/evidence schema and derived strict JSON output format; all keys required, missing values nullable, decimal values strings, no confidence/verified/bbox/decision fields. Fixed prompt/schema versions. No financial tools are supplied to the model.
- `app/pdf_input.py`: bounded authentic-PDF intake reuse, local page text, optional pymupdf4llm Markdown, and versioned input paths. Local page text is retained separately for verification; original PDF goes inline base64 on the multimodal route.
- `app/extraction_client.py`: OpenAI-only HTTPS Responses transport using httpx, configurable explicit model/key, store=false, 45s timeouts, two total attempts shared across transient/schema retries, sanitized refusal/incomplete/provider errors, actual usage/latency recording, and Decimal price estimation. Invalid financial evidence is not a reason for another model call. Model inventory lookup is separate from actual Responses capability verification.
- `app/evidence_verification.py`: independent labelled-field/value/page association, model-snippet checking, arithmetic/tax/header-line reconciliation and conversion into Slice 3 FinancialDocument. Only local rules create evidence flags. Any unresolved findings clear every financial trusted flag, so using the diagnostic document alone cannot bypass review. Image-only scans remain unverified; no invented bounding boxes. The narrow masked-last-four rule requires a unique exactly matching local four-digit bank value. Version labelled-fields-2 adds that mask handling.
- `app/extraction_store.py`, model registration in `models.py`, migration `0004_extraction_extraction_api_usage.py`: per-attempt usage ledger with run/document hash, requested/returned model, input/cached/cache-write/output tokens, latency, schema/prompt/path versions, sanitized error and nullable estimated cost/rate provenance. Record callbacks open short transactions after calls, not during calls; attempt replay is idempotent and conflicting replay fails. Prior migrations are unchanged.
- `app/extraction_evaluation.py`: field-level correctness, missing errors, invented values and incorrect fields; decimal formatting equivalence does not hide wrong values. Evidence quality and schema validity are measured separately from field accuracy.
- `scripts/extraction_fixtures.py`: six synthetic one-page PDF/expected-data builders, single-column and two-column layouts, missing date/PO, scan, inconsistent total and USD fixture. PDFs/manifest/rendered PNGs are generated privately under `.local/extraction-fixtures` (ignored), not mistaken for real extraction results. All six pages were rendered with PyMuPDF and visually inspected for clipping/legibility.
- `scripts/benchmark_extraction.py`, `scripts/summarize_extraction_benchmark.py`: explicit --live harness, model lookups, four model/input routes, bounded attempt count and four-hour time ceiling; private resumable per-attempt report and a sanitized published synthetic metric summary. Rates are dated external inputs; cache-write charges are included. No extraction-content caching is implemented or replay hidden.
- `tests/extraction_helpers.py`, `test_extraction.py`, `test_extraction_safety.py`, `test_extraction_integration.py`, `test_extraction_live.py`: mocked external calls, failures, retries, hostile trust fields, false snippets, scans, precision, costs, usage persistence and explicit fixture-only financial boundary checks. The integration handler asserts zero checked-out database connections during the model call. Live test is opt-in and skips by default.
- `pyproject.toml` / `uv.lock`: httpx is now a runtime dependency; pymupdf4llm added and locked. `.env.example` names the measured provisional model without any key. No secret was printed or staged.
- `docs/benchmarks/openai-rates-2026-11-12.json` and `slice4-measured.json`: attributed standard-rate snapshot and actual synthetic-case results. `SPEC.md`, DECISIONS, this file and root PROGRESS.md document the explicit contract clarification, results and integration blockers.

### Reproduce locally

From backend: `uv sync --locked`, `uv run alembic upgrade head` (now **0004_extraction**), and configure OPENAI_API_KEY/OPENAI_MODEL locally in ignored `.env`. Never put the key in chat or a VITE variable. Runtime model remains explicit; .env.example suggests gpt-6-luna based on this mini-set only. All previously documented local API/frontend startup commands remain valid; uploads stay queued.

Routine checks: `uv run pytest -q --tb=short`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python -m scripts.export_openapi`; frontend `npm.cmd run generate:api` and `npm.cmd run build`. TEST_DATABASE_URL must point to the isolated local PostgreSQL instance as before. Tests never fall back to SQLite or spend on OpenAI by default.

Explicit paid evaluation: `uv run python -m scripts.benchmark_extraction --live --max-calls 28`, then `uv run python -m scripts.summarize_extraction_benchmark`. This sends only the generated synthetic fixture PDFs/text to OpenAI. The benchmark default maximum is 24; the observed matrix used 24 attempts with no retries. `uv run python -m scripts.extraction_fixtures` regenerates the private PDFs, manifest and page PNGs. Preserve the private report before rerunning; this initial harness overwrites its fixed report filename. To run the isolated live test, explicitly set PS1_LIVE_EXTRACTION=1 and OPENAI_MODEL, then run only tests/test_extraction_live.py. No live test calls approval.

### Live results and limits

Account model lookup: Luna and Terra both HTTP 200, followed by successful Responses/strict-schema/PDF requests. Six fixtures per route, 23 scored fields per fixture (including line-count), with expected nulls and numeric equivalence. Core benchmark wall time **286.5s**, well inside the four-hour ceiling.

| Route | Fields correct | Median latency | Total input / output tokens | Estimated USD / 6 PDFs |
|---|---:|---:|---:|---:|
| Luna / PyMuPDF text | 115/138 (83.33%) | 10.609s | 6418 / 5898 | 0.00372860 |
| Luna / pymupdf4llm Markdown | 115/138 (83.33%) | 11.023s | 6398 / 6391 | 0.003972700 |
| Luna / original PDF | 138/138 (100%) | 11.9845s | 9496 / 7843 | 0.005108050 |
| Terra / original PDF | 138/138 (100%) | 13.547s | 9496 / 5949 | 0.04161050 |

Both text routes score 100% on the five text-bearing fixtures, but each incurs 22 missing-field errors and one line-count mismatch on the scan. Both PDF routes preserve missing date/PO and unsupported USD, and correctly transcribe the inconsistent 12000 total instead of silently repairing it. Arithmetic verification still holds that case. All 24 responses were schema-valid; schema success did not imply factual correctness on the scan/text path, nor trusted source grounding. Luna/PDF is the provisional extraction choice for this mini-set; this does not prove universal cost/accuracy superiority or full golden-set acceptance. Scans require review despite correct model transcription.

Costs use returned tokens, including cache writes, with the [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) and [Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra) published standard rates dated in the rate snapshot. Cache-write rates were added after inspecting returned usage; published costs were recomputed from the original actual token counts, not rerun/model estimates. Account billing receipts are unavailable, so billing_cost stays null. A diagnostic Luna PDF call (1122 input, 1364 output tokens) and isolated live test passed outside the 24-case table; their costs are excluded from the comparative table. The live test validates usage in memory; the diagnostic usage is retained under ignored `.local`.

The benchmark recorded the initial stricter verifier's false holds on clean bank-last4 snippets. Version 2's narrow mask support is regression-tested; the table remains the original measured extraction run, not retrospectively relabelled as approved. Table/complex-layout field association is intentionally conservative and can require review even when values are correct. The full >=20 real-layout gold set, production local evidence verifier and scan corroboration remain blockers.

Future graph integration must retain the worker session lock through the model call with no open transaction, then fence persisted extraction/events by owner+attempt+lease. The current financial service deliberately refuses that worker lock; a future owner-bound finalizer must use the verified owning connection and recheck under row locks. Do not drop the lock guard or bypass the fixture restriction. Production worker, graph, review UI, SSE, payment and email stay disabled/unimplemented. Usage may be uncertain if a process dies between a successful provider call and persistence; nothing claims exactly-once model billing. Optional content-hash caching is deferred.

### Final Slice 4 verification record

| Command/check | Observed result |
|---|---|
| Full routine `python -m pytest -q --tb=short` | **114 passed, 1 skipped in 64.42s**; all original 84 tests preserved, 30 additional routine cases; one existing upstream TestClient warning |
| Explicit PS1_LIVE_EXTRACTION=1 test, Luna/PDF | **1 passed in 12.00s**; no financial service call; upstream warning plus sandbox/user pytest-cache permission warning |
| `ruff check .` / `ruff format --check .` | Passed; 46 files formatted |
| All-revision migration upgrade / metadata parity / downgrade / re-upgrade | Passed within full PostgreSQL suite, including 0004 and all financial immutable triggers |
| OpenAPI export + generated API types | Passed; zero public-contract diff against df517a4 |
| Frontend TypeScript/Vite production build | Passed; 28 modules |
| Git whitespace / ignored-secret checks | Passed; local .env remains ignored, no remote push |

The local key was absent initially; the user configured it without sharing it in chat. Both account model lookups and actual Responses requests then succeeded. The initially empty local OPENAI_MODEL was set to gpt-6-luna after measurement; existing nonempty user values were not overwritten. No key was printed, copied into source or committed. The first extraction-focused run passed 26 tests, then safety/cost additions were included in the final 114-test run. Initial Ruff formatting issues were corrected before final validation. No live provider errors or malformed schemas occurred in the 24-call matrix; those failure paths are covered by mocked tests. Core measured results precede the narrow masked-bank verifier refinement and remain labelled accordingly. The project-only PostgreSQL instance was stopped after verification; Slice 4 changes remain uncommitted for review.

## Current Slice 3: deterministic financial foundation (2026-11-12)

Closure for Slice 4: reviewed all financial source, migration, fixtures/tests and the diff against a0ba820, focusing on locked allocation, identity, precision, replay and atomic rollback. No critical defect found. Re-ran all 84 tests (56.42s, one existing upstream warning), migration roundtrip/parity, Ruff check/format and frontend production build; all passed. Git whitespace check passed. Slice 3 is committed separately before extraction work; earlier uncommitted statements below are historical.

Slice 2 was reviewed against 97757cf, passed all 32 regression tests, Ruff, Git checks and frontend build, and was committed separately as **a0ba820**. No critical ownership/transaction/migration/idempotency defect was found. No remote push occurred. All Slice 3 work remains uncommitted for review.

Financial contracts and fixture calculations were recorded before implementation in [DECISIONS.md](DECISIONS.md), under SPEC §§1.1–1.3, 2.1–2.3 and 5.1–5.2. No SPEC policy defaults or public API contracts changed. Original source fields/evidence are kept alongside normalized identity keys; unsupported currency is preserved and reviewed.

Files added:

- `backend/app/finance_contracts.py`: frozen internal verified-document/evidence/line contracts, vendor/PO enums, bounded Decimal types, conservative invoice/tax/name normalization and separate price/rounding cap helpers. Floats, nonfinite numbers, negative money, zero quantities and excess source precision fail validation. INR totals use two decimals; unit price four, quantity six, rate six. Decimal arithmetic uses an isolated 48-digit context during evaluation/posting and ROUND_HALF_UP line computation.
- `backend/app/financial_models.py`: vendors, POs, PO lines, immutable policies, canonical approved invoices, ledger, quantity allocations and private assessment snapshots. Foreign keys, vendor/key uniqueness, unique invoice/run approvals, PO cap/quantity checks, INR checks and state constraints are present. Assessment revisions preserve a future path to append authorized review decisions on the same run; the foundation writes revision 0 only.
- `backend/alembic/versions/0003_finance_financial_domain_foundation.py`: frozen explicit schema DDL, indexes and immutable-history triggers. UPDATE/DELETE of policies, invoices, assessments, ledger and allocations are rejected. Migration 0001/0002 remain unchanged. No policy or financial fixture is automatically seeded in application databases. Database committed gross/quantity defaults are zero.
- `backend/app/finance_rules.py`: pure vendor/PO/line matching and deterministic evidence, currency, bank, date, tax, arithmetic, price, available gross and aggregate quantity checks. Missing PO cannot auto-match even with one candidate. Conflicting explicit line/SKU identifiers cannot fall back to fuzzy descriptions. Net and inclusive-gross prices reconcile against explicit tax rates and approved net PO prices.
- `backend/app/approval.py`: explicit policy registration and internal `approve(engine, run_id, document, policy_version)`. Only labelled `fixture:` runs are accepted in this slice. No HTTP endpoint calls the service. Same-run identical replay returns its stored immutable result; changed data/policy conflicts. Only PostgreSQL deadlock/serialization failures retry (three attempts maximum). Matching keys serialize per vendor/invoice; vendor, PO and ordered PO lines are reread under row locks. Ledger/allocation sums must agree with PO counters or the invoice is held. Ledger, allocations, counters, assessment, run result and event commit in one short transaction. A worker-owned run is refused.
- `backend/tests/financial_fixtures.py`, `test_finance_rules.py`, `test_approval.py`, `test_approval_boundaries.py`: synthetic deterministic master/document builders and pure/PostgreSQL tests. Each test resets via its isolated schema. H1 and E1–E4 exercise explicit calculations from DECISIONS; no extraction/PDF accuracy is implied.

Existing files changed: `models.py` registers the financial mappings; `events.py` accepts an optional explicit stage while retaining WORKER as its default and preserving event deduplication; DECISIONS/DEVELOPMENT record contracts and results. The API implementation, worker implementation, frontend source, dependencies and prior migrations remain unchanged. OpenAPI/type regeneration must yield no diff for this slice.

### Transaction and safety invariants

Approval takes the same run advisory-lock namespace as the worker, then run/vendor/identity/PO/line locks. Re-read validations use database UTC date and current master state; stale preflight information cannot authorize posting. Unique canonical identity and unique invoice/run ledger constraints backstop the service. No financial use of float or model judgment exists. Gross cap and aggregate accepted quantities are checked before posting, with database over-commit checks as a further guard. Waiting/held cases allocate nothing. A failed transaction leaves no partial invoice, ledger, allocation, counter, assessment, event or run decision. Replaying a committed approval adds no second event or allocation. No paid state or payment execution exists.

An internal NEEDS_REVIEW assessment remains provisional: its run is INTERRUPTED with a null public decision until a real review request and graph interrupt exist. Approved/rejected fixture results are real deterministic database decisions tested only in isolated schemas; no demonstration approval is seeded or exposed through an application endpoint. Production worker processing remains disabled. Existing intake uploads remain queued unless a direct internal caller explicitly assesses a fixture run.

### Limits and remaining blockers

H2 is **not** an approved fixture. The exact 49998 + 0 tax → printed 50000 discrepancy is reviewed because a ₹2 difference and passing numeric caps do not prove a legitimate rounding convention. The rounding-cap helper is necessary-condition arithmetic only. A verified source convention is still needed before implementing an aggregate rounding waiver. Four synthetic rule/ledger edge cases are covered; scanned-document extraction, real PDF gold fixtures, real evidence verification, full GST/jurisdiction compliance and credit notes are not implemented.

Review corrections/resume are not implemented; a future authorized review writer can append an assessment revision, never mutate historical evidence or approve twice. No human-review UI, OpenAI, LangGraph, SSE, email, export or payment integration was added. Production checkpoint/ledger reconciliation and worker fencing integration remain activation prerequisites. The direct financial service is intentionally unavailable for ordinary uploads; the `fixture:` restriction is an internal development guard, not a deployed authentication mechanism. Database roles/master-data authorization and hosting remain future deployment work.

### Slice 3 verification

Commands run from backend use `.venv/Scripts/python.exe` / `ruff.exe`, equivalent to `uv run`. Tests use `TEST_DATABASE_URL=postgresql+psycopg://ps1@127.0.0.1:55432/postgres` and random isolated real PostgreSQL schemas. The existing migration roundtrip test covers all revisions: upgrade, metadata parity, downgrade to base, upgrade again. The lock-wait test observes an actual PO FOR UPDATE attempt before allowing a concurrent closure to commit.

Intermediate results: migration checks passed 4/4; first focused financial run had 23 failures and 20 passes, all failures caused by the zero-overrun Decimal literal rejecting its serialized string. Replaced that literal with an equivalent Decimal range fixed at zero; the focused suite then passed 43/43. Further duplicate-history/lock/quantity boundary coverage brought the full suite to 84 passing tests before the final assessment-revision/default refinement. Final results are recorded below after rerun. Initial formatting/import findings were corrected; no failures are hidden.

| Final check | Observed result |
|---|---|
| `python -m pytest -q --tb=short` | **84 passed in 60.59s**; includes all 32 prior regressions and 52 financial cases; one existing upstream TestClient deprecation warning |
| `ruff check .` / `ruff format --check .` | Passed; 31 Python files formatted |
| Migration upgrade → metadata comparison → downgrade to base → upgrade | Passed in the full suite, including immutable trigger/function teardown and revision 0003 |
| `python -m scripts.export_openapi` / `npm.cmd run generate:api` | Passed; generated JSON/types have zero diff against Slice 2 |
| `npm.cmd run build` | TypeScript + Vite production build passed; 28 modules |
| `git diff --check` | Passed; informational Windows line-ending notices only |

For local schema installation use the existing backend setup and `uv run alembic upgrade head` (head now **0003_finance**). The API readiness check requires this head. No financial policy/master data is installed automatically. Financial tests are the executable fixture setup/reset mechanism for this foundation; do not use tests or synthetic builders against production. No separate financial HTTP smoke endpoint or UI has been introduced. The project-only PostgreSQL test instance was stopped after verification. No remote push occurred; only Slice 2 is committed, and Slice 3 remains reviewable as uncommitted changes.

## Slice 2 historical record: worker infrastructure (2026-11-11)

Closure review 2026-11-12: reviewed the complete Slice 2 tracked diff against 97757cf plus all new worker/migration/test files. Ownership uses a dedicated connection that is invalidated (physically closed) on release; lease recovery cannot take a live session lock; owner/attempt/deadline fence mutations; claims, retries and events commit together; failure rolls back the claim and releases its lock; exhaustion never creates a financial decision. Migration down/up and event deduplication are covered by regression tests. No critical defect was found. Full regression: 32 passed in 31.34s, one existing TestClient warning; Ruff check/format and frontend production build passed. Git diff whitespace check passed and no remote exists. Slice 2 is committed separately before financial work; the earlier uncommitted statement below is historical.

Read [DECISIONS.md](DECISIONS.md) for the worker contract refinement recorded before implementation. SPEC §§1.2, 3.1, 3.4, 4.1–4.2 and 5.5 govern this slice. Financial policy and existing endpoint contracts remain unchanged.

Git is initialized. The clean Slice 1 baseline is `97757cf` (includes ignore hardening). Verified ignored examples: backend/.env, backend/.venv, .local/pgdata, uploads, arbitrary PDFs, SQLite files and private-key files. The staged baseline contained only source/docs/lockfiles and the deliberate local-development .env.example. No API-key/private-key marker matches were found. No remote was configured or pushed. Sandbox/user ownership differed, so Git required an execution-scoped safe.directory exception and approved .git writes; no global Git safety setting was changed. Baseline whitespace check flagged only existing SPEC Markdown hard breaks and its final blank line, preserved verbatim.

New/changed files:

- `app/worker.py`: separate-process worker engine, atomic SKIP LOCKED claims, dedicated session lock per run, unique owner/attempt fencing, heartbeat, bounded technical retries, expired-owner recovery and transactional lifecycle writes. Defaults: 30s lease, 10s heartbeat, three attempts and 5s exponential retry delay capped at 60s.
- `app/events.py`: transaction-owned append helper; run row lock serializes sequence allocation; operation keys deduplicate identical events and reject conflicting reuse. Events are never changed by the helper.
- `models.py`, `alembic/versions/0002_worker.py`: nullable event operation key/unique constraint, active-run lease uniqueness and queue eligibility index. Migration 0001 remains unchanged.
- `contracts.py`, `main.py`: authenticated `GET /api/v1/runs/{id}/events?after_seq=0&limit=100`, returning an ordered list of §4.2 envelopes. Limit 1–500, after_seq >= 0, unknown run 404; timestamps UTC. Run status notice reflects disabled production processing. Existing frontend source is unchanged.
- `tests/worker_harness.py`, `test_worker.py`, `test_worker_retry.py`, `tests/__init__.py`: explicit subprocess test processors and integration checks. No test processor is bundled into the application CLI.
- Generated `frontend/openapi.json` and `src/api.generated.ts`: include the planned events endpoint; no unrelated UI changes.

### Running and activation boundary

From backend, use the existing setup below, then `uv run alembic upgrade head`. The worker process entrypoint is `uv run python -m app.worker`. **It intentionally exits 2 with “Production processing disabled … No jobs claimed.”** It does not load credentials, connect or mutate queued uploads. There is no production enable switch. `Worker.run(stop_event)` provides the execution loop; its per-job `run_once` path is tested in separate processes through explicitly injected test callbacks. Only PROCESS queue work is eligible in this slice. Tests acknowledge infrastructure work as queue DONE / run INTERRUPTED with TEST_PROCESSOR_ONLY and a null decision; no invoice COMPLETED/APPROVED result or extraction stage is fabricated.

Recovery runs while claiming eligible work, not as a startup blanket update. Only expired LEASED rows whose run session lock is free are returned to READY (run INTERRUPTED) or failed after the claim budget. Work retains its original PDF, run, thread and generation; business re-evaluation/new-run behavior remains deferred. Queue work and events commit together. Retry failures store generic codes/messages rather than raw exceptions or document contents.

The API readiness endpoint now expects migration 0002. Migrations are explicit, never on API/worker startup. Tests use isolated random PostgreSQL schemas and include both revisions in metadata parity and full down/up checks. Run `uv run pytest -q` with TEST_DATABASE_URL as below. Worker tests terminate their own subprocesses; no user process is killed. The competition and crash tests use real separate processes, while tests control the database lease deadline to avoid long sleeps.

### Limits and unresolved activation requirements

Session advisory locks require a direct or session-pooled PostgreSQL connection; transaction pooling is unsupported. A live process with an expired lease keeps its lock, so recovery waits for that process/connection to end. This deliberately favors serialization over availability. Attempt fencing prevents stale DB writes after requeue/reclaim; arbitrary CPU computation or external side effects cannot be made exactly once if a connection dies or a process crashes before committing. Test callbacks can repeat uncommitted computation. Future processors must cooperate with fencing and idempotency; financial posting still requires SPEC §2.3.

Production activation remains blocked on a real processor, checkpoint/ledger reconciliation, typed financial contracts, and graph/review work in later slices. No checkpoint/ledger reconciliation is claimed here because those tables and processors do not exist. SSE, browser timeline rendering, hosted deployment and live extraction remain deferred. Ordered events are available to polling clients without modifying the frontend. The existing Slice 1 smoke script still checks only queued intake, which is valid with production processing disabled.

### Slice 2 verification record

Final commands used the project virtual environment in backend, with `TEST_DATABASE_URL=postgresql+psycopg://ps1@127.0.0.1:55432/postgres`. All database tests used random isolated schemas on the project-only PostgreSQL 17 cluster.

| Command | Final observed result |
|---|---|
| `python -m pytest -q` | **32 passed in 26.40s** (20 Slice 1 regressions + 12 worker/events tests); one existing upstream Starlette/httpx TestClient deprecation warning |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed; 22 Python files |
| `python -m scripts.export_openapi` | Passed |
| `npm.cmd run generate:api` | Passed |
| `npm.cmd run build` | TypeScript and Vite production bundle passed; 28 modules |
| `git diff --check` against baseline | Passed; informational Windows LF/CRLF notices only |
| `git remote -v` | Empty; no remote configured or contacted |

Coverage includes real competing subprocesses, actual process termination/restart, heartbeat extension, live-owner exclusion even after lease expiry, stale attempt rejection, bounded technical retries/backoff/exhaustion, stable operation replay across attempts, conflicting event rejection, duplicate completion acknowledgement, injected database failures rolling back claim/event/state changes, concurrent intake, authenticated/cursor-ordered event reads and disabled production CLI behavior. Migration metadata parity and downgrade/re-upgrade tests cover revision 0002 as well as 0001. Test output had no failures; initial Ruff import/format findings were fixed before the final check.

Environment failures: initial sandbox Git commands hit ownership and .git index write restrictions; scoped ownership exceptions plus approved Git execution created the baseline successfully. A diagnostic process inventory query was denied by the sandbox; subprocess test results and bounded cleanup verified completion without needing that inventory. No global Git configuration was changed. The isolated PostgreSQL cluster started for this task was stopped after verification; the existing port-5432 service was not modified. Slice 2 changes remain uncommitted for review against baseline `97757cf`.

## Slice 1 historical setup and verification

SPEC.md v0.2-draft remains canonical. Read AGENTS.md and SPEC.md before changes. See [DECISIONS.md](DECISIONS.md) for unresolved contracts, local choices, tradeoffs and implementation order. README.md remains the original planning document because AGENTS.md restricts its edits to explicit agreed contract changes.

## Implemented boundary

FastAPI/Pydantic configuration, SQLAlchemy/PostgreSQL connectivity, explicit Alembic migration, liveness/readiness, authenticated PDF intake and queued-run lookup. React/TypeScript/Vite/Tailwind provides an upload form and server-polled status; types are generated from the implemented OpenAPI subset. PDF validation uses PyMuPDF. No OpenAI calls, worker, LangGraph, review, extraction, financial rules, approval ledger, SSE, history or export is implemented. There are no invented processing events or financial results. The single persisted event is the actual RUN_QUEUED intake event.

## Exact initial source structure and purpose

```text
AGENTS.md / SPEC.md / README.md        existing; unchanged
.gitignore                             excludes environments, secrets, PDFs and build output
compose.yaml                           optional loopback-only PostgreSQL 17 development service
backend/
  .env.example                         server-side config; one optional OpenAI key, no active model
  pyproject.toml / uv.lock              Python dependencies, locked resolution, pytest/Ruff config
  alembic.ini                          explicit migration configuration
  alembic/
    env.py / script.py.mako            migration runner and future revision template
    versions/0001_intake_baseline.py    documents/runs/events/queue/intake-key tables only
  app/
    __init__.py
    config.py                          validated environment settings and secret fields
    db.py                              engine factory, UTC session timezone and connection timeout
    contracts.py                       implemented API models, state enum and fixed PDF limits
    models.py                          SQLAlchemy persistence mappings
    intake.py                          PDF checks and atomic/idempotent intake transaction
    main.py                            app factory, bearer auth, health/readiness and intake/status API
  scripts/
    export_openapi.py                   exports schema without a database connection
    smoke_intake.py                     live HTTP check through Vite using a synthetic PDF
  tests/
    conftest.py                        isolated random PostgreSQL schema per test
    test_health.py                     health, DB outage, migration parity and roundtrip
    test_intake.py                     persistence, auth, PDF limits, rollback and concurrency
    test_config.py                     required settings, PostgreSQL-only URL and secret masking
frontend/
  package.json / package-lock.json      React/Vite/Tailwind dependencies and reproducible npm install
  index.html / tsconfig.json            HTML entry and strict TypeScript settings
  vite.config.ts                       loopback dev server and same-origin /api proxy
  openapi.json                          generated implemented-backend schema
  src/
    api.generated.ts                   generated API types; never edit manually
    main.tsx                           credential entry, upload and persisted status polling
    styles.css                         responsive intake shell and Tailwind entry
docs/
  DECISIONS.md                          ambiguities, decisions and next-slice order
  DEVELOPMENT.md                        this structure, setup, scope and verification record
  archive/                              historical documents; not used as active specifications
```

Generated/ignored `.venv`, `backend/.venv`, `.local`, `node_modules` and `dist` are not source. No Git repository was present at kickoff; no commit was made.

## Run locally (PowerShell)

Prerequisites: CPython 3.12+, uv, Node 22.12+ (tested on Node 24), and PostgreSQL 17. Use your own dedicated development database or the optional Docker Compose service. No OpenAI key is needed for this slice.

From repository root, if Docker is available:

```powershell
docker compose up -d db
```

Docker was unavailable on the implementation machine, so verification used the installed PostgreSQL binaries and an isolated cluster in `.local/pgdata` on port 55432. It is distinct from the existing PostgreSQL service on port 5432. Do not run both the isolated cluster and Compose on the same port. Native alternative (run once for initdb):

```powershell
# Adjust to your installation. This cluster is disposable local development only.
$pgBin = 'C:\Program Files\PostgreSQL\17\bin'
New-Item -ItemType Directory -Force .local | Out-Null
& "$pgBin\initdb.exe" -D .local/pgdata -U ps1 --auth=trust --encoding=UTF8 --locale=C
& "$pgBin\pg_ctl.exe" -D .local/pgdata -l .local/postgres.log -o '-h 127.0.0.1 -p 55432' -w start
& "$pgBin\createdb.exe" -h 127.0.0.1 -p 55432 -U ps1 ps1
```

Native local trust authentication requires no password, is bound to loopback, and is only for this disposable cluster. Use authenticated PostgreSQL for hosting. Do not initialize over an existing cluster or point tests at production.

Backend terminal:

```powershell
Set-Location backend
uv sync --locked --python 3.12
Copy-Item .env.example .env
# Edit DATABASE_URL if using an existing dedicated database.
# Replace APP_API_TOKEN with your own random credential (24+ characters).
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

The API intentionally does not migrate or connect during import. A live API can report database unavailability through readiness. `.env` is resolved from the backend working directory. All runtime settings stay server-side; never put keys into Vite variables.

Frontend terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Enter the same APP_API_TOKEN, choose an unencrypted 1–5 page PDF up to 12 MiB and click **Create intake run**. You should receive a run ID and QUEUED status with no financial decision. Refreshing keeps the run ID in the URL; re-enter the token to read it again. The credential is not stored in local/session storage. Retry a failed request with the same file selection to reuse its idempotency key; selecting a file creates a new key.

Only these endpoints exist, under `/api/v1`:

- `GET /healthz`: process liveness, no DB call.
- `GET /readyz`: 200 only when PostgreSQL has the current migration revision; otherwise sanitized 503. This does not claim a running worker or an available OpenAI account.
- `POST /invoices/process`: bearer-authenticated multipart PDF + optional source; optional X-Idempotency-Key; atomic 202 intake. Same key/payload returns the original run; changed bytes/source returns 409.
- `GET /runs/{id}`: bearer-authenticated minimal persisted status subset. Unknown UUID returns 404; invalid UUID returns 422.

FastAPI's `/docs` and `/openapi.json` expose the implemented subset, not the complete planned product API. The UI uses Vite's `/api` proxy locally, so no permissive CORS middleware is needed. A deployed static frontend will need a same-origin API reverse proxy or an explicit allowed-origin decision. Preview/static hosting alone does not proxy the API.

## Verification commands

Backend, against a disposable local PostgreSQL database (tests create/drop only random `test_<uuid>` schemas):

```powershell
Set-Location backend
$env:TEST_DATABASE_URL = 'postgresql+psycopg://ps1@127.0.0.1:55432/postgres'
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m scripts.export_openapi
# With Vite and API already running and backend .env configured:
uv run python -m scripts.smoke_intake
```

Frontend:

```powershell
Set-Location frontend
npm.cmd run generate:api
npm.cmd run build
```

Tests intentionally fail with an actionable message if TEST_DATABASE_URL is absent. There is no SQLite substitution. PostgreSQL migration tests perform upgrade → metadata parity → downgrade → upgrade. Intake tests cover concurrent same-key submissions, changed-payload conflicts, persisted PDF/run/event/queue records, app recreation, UTC timestamps, unauthorized access, invalid/encrypted/oversized/six-page PDFs, missing run IDs and a real database constraint failure proving all intake records roll back together.

See the verification record below for observed results and limits. Stop this slice here; the next recommended milestone is durable worker claims/events/recovery with explicitly disclosed stub processing and deterministic fixture seed/reset definitions. Financial decisions require the unresolved policy/evidence contracts and §2.3 transaction tests before LangGraph nodes.

## Observed verification record — 2026-11-11

Commands used the project virtual environment directly (`backend/.venv/Scripts/python.exe` and `ruff.exe`), equivalent to the `uv run` commands above.

| Check | Observed result |
|---|---|
| `python -m pytest -q` with real isolated PostgreSQL 17 | **20 passed in 10.40s**; one upstream Starlette warning about its deprecated httpx TestClient adapter |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed; 15 Python files formatted |
| `python -m alembic upgrade head` on dedicated `ps1` database | Passed; migration also tested down/up and against ORM metadata in isolated schemas |
| `python -m scripts.export_openapi` | Passed without connecting to DB |
| `npm.cmd run generate:api` | Passed |
| `npm.cmd run build` | Passed TypeScript check and Vite production bundle (28 modules) |
| `python -m scripts.smoke_intake` | Passed running Vite page/transformed module, proxied health/readiness, PDF upload and persisted queued status; synthetic run retained in local DB |
| Visual browser interaction | **Not verified**: browser access host unavailable; both attempted Chrome windows returned `window is minimized` and could not be captured by the available UI interface |
| Docker Compose path | Not run: Docker unavailable; native PostgreSQL used instead |

Failures encountered and resolved:

- Initial `uv python install 3.12` download was denied by sandbox network restrictions. Retried through the approved execution path; isolated runtime and locked backend dependencies installed successfully.
- Initial `ruff check . --fix` found import/format/line-length issues; formatting and fixes applied; final checks passed.
- First pytest run: **14 passed / 1 failed** because a DB-local `+05:30` timestamp escaped the UTC contract. Added API UTC normalization and UTC DB session setting; regression passed. Later added configuration and owner-only encryption cases, producing the final 20 passing tests.
- Initial sandboxed `npm.cmd run build` passed TypeScript, then Vite/esbuild could not read ancestor directories. Approved execution with normal filesystem access passed; no source workaround needed.
- Sandboxed `pg_ctl start` could not create its Windows restricted token; approved launch of only the isolated local cluster succeeded.
- Owner-only encryption was found by a targeted PyMuPDF check; validation now rejects its encryption metadata even when no user password is needed to open it.

These checks establish local intake infrastructure only. They do not establish model accuracy, financial correctness, worker recovery, a deployed live workflow or visual UI quality. SPEC's later acceptance gates remain open. Temporary API/Vite and the project-only PostgreSQL instance are stopped after verification; startup commands above reproduce them. The existing PostgreSQL service on port 5432 is unaffected.

Implementation references: the app uses the documented [FastAPI lifespan pattern](https://fastapi.tiangolo.com/advanced/events/) for engine cleanup; migrations follow the [Alembic environment pattern](https://alembic.sqlalchemy.org/en/latest/tutorial.html). These references inform framework wiring and do not alter SPEC business policy.
