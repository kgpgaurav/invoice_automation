# Development and verification

[Project](../README.md) · [Documentation](README.md) · [Local setup](RUNNING.md)

SPEC.md is the canonical contract; docs/DECISIONS.md records agreed refinements and unresolved questions. Read AGENTS.md before implementation. Historical operator/build journals are kept locally under ignored docs/local; they are not dependencies of this guide or the application.

## Publication cleanup — 23 November 2026

Reviewed the current Git publication candidates and strengthened `.gitignore`, `.dockerignore` and `.vercelignore` for environment/configuration files, local deployment metadata, documents/database exports, owner notes, test reports, caches and accidental command output. Removed 66 unused browser screenshots from Git tracking while verifying that their local bytes were preserved. The four README-linked illustrations remain public, together with application source, migrations, tests, lockfiles, examples, fixture definitions, benchmarks and project guides. Public docs do not depend on ignored files. Untracking affects the next repository tree; it does not remove earlier Git history.

Verification: **205 publication candidates**, including **201 text files** checked for credential markers and configured secrets without printing values; **45 private/generated path cases**, **39 required public files**, and **88 documentation links/anchors** passed. Existing checks also confirmed all six documented routes and 12 preserved owner documents. The documented disposable loopback database example is intentionally public and was distinguished from hosted credentials. `ruff check .` and `ruff format --check .` passed for **122 Python files**; `npm run build` passed with the existing PDF-preview chunk-size warning. Git whitespace checks passed. No application/API/financial behavior changed, so backend/browser regressions were not repeated for this repository-only follow-up. No database operation, provider call, commit, push or deployment was performed.

## Repository map

Manual-demo follow-up, **23 November 2026**: [DEMO_INVOICES.md](DEMO_INVOICES.md) provides reset/deployment steps and exact generator fields for nine manual PDFs, backed by [the synthetic data packet](fixtures/manual-invoices-v1.json). The existing three-vendor/four-PO baseline is reused without budget/tax changes or duplicate orders. Read-only hosted inspection confirmed all four prepared POs, expected terms/GSTINs and zero committed counters in ps1_app, still at migration 0010; no hosted data/schema was changed. The documented migration command's configuration was constructed successfully and its target matched the explicit deployment profile, without executing a migration. Stale RUNNING references to head 0010 and unavailable hosted reset were corrected.

`tests/test_manual_demo_plan.py` checks all nine inputs through the actual worker/checkpoint/source-verification/financial/review path using explicitly mocked Responses transport and a disposable PostgreSQL schema. It verifies every planned decision/code, E2 same-thread selection/resume, duplicate/bank/GST/price/tax holds, one extraction call per case, exactly three ledger entries totalling 93600.00 and final PO balances 38200/30000/13200/40000. The fixture packet omits optional invoice SKU/PO-line references, exercising exact description matching. This is financial/workflow verification, not a fresh model-accuracy measurement on third-party generator PDFs.

Focused packet/reset/hosted-seeding regressions: **54 passed**, 64.87s. After refining the packet to omit optional codes, the nine-case packet test passed again (**1 integration test**, 9.64s); the other 53 tests do not consume that packet. Ruff lint/format passed for **122 Python files**. Public-link, private-file preservation and Git hygiene checks passed. Application/API/frontend source is unchanged in this follow-up, so the previously recorded 400-backend/38-browser/build verification was not repeated. The suite now also contains the new packet integration test. Files changed here: the new guide, JSON packet and test, plus README, docs index, RUNNING, DECISIONS and this verification note. No reset, seed write, migration, paid extraction, commit, push or deployment was performed.

```text
backend/
  app/                 API, worker, workflow, extraction and financial services
  alembic/versions/    ordered business-schema migrations
  scripts/             local demos, contract export and verification runners
  tests/               unit, real-PostgreSQL and opt-in live tests
  pyproject.toml
  uv.lock
frontend/
  src/                 React screens and generated API types
  tests/               browser regressions
  openapi.json
  package.json
  package-lock.json
docs/
  README.md            public documentation index
  RUNNING.md           local setup and scenario inputs
  ROLE_ACCESS.md       role/ownership contract
  SECURITY.md          credentials and public-demo boundaries
  DECISIONS.md         implementation decisions
  benchmarks/          sanitized measurements and required dated rate data
  screenshots/         synthetic UI illustrations
  archive/             historical planning references
  local/               ignored personal runbooks/build journals
SPEC.md
AGENTS.md
README.md
```

Business schema head: **0011_demo_reset**. LangGraph uses a separate checkpoint schema. PDFs are stored privately in PostgreSQL; ephemeral frontend/API disk is not authoritative.

## Backend checks

Install with `uv sync --locked` from backend. Set TEST_DATABASE_URL to a **dedicated local PostgreSQL** connection whose user can create/drop test schemas. Tests use isolated random schemas and real PostgreSQL; no SQLite fallback. Never use a hosted/production database for this suite.

Example for the project's existing verified local cluster, from backend in CMD:

```cmd
set "TEST_DATABASE_URL=postgresql+psycopg://ps1@127.0.0.1:55432/postgres"
set "PYTHONUTF8=1"
uv run pytest -q --tb=short -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

Replace the example URI with your dedicated local setup when different. Routine tests mock external model transport. Three live tests are separately opt-in and skipped by default; do not set live-test flags unless you intend provider charges.

The suite includes worker claim/lease/restart/ownership fencing, transactional events, vendor/PO races, duplicate identities, Decimal boundaries, approval rollback/replay, role isolation and provider-session handling. `tests/test_health.py::test_migration_roundtrip_and_metadata_parity` upgrades, compares SQLAlchemy metadata, downgrades and re-upgrades in a disposable schema. The vendor tests also verify refusal of a lossy BLACKLISTED downgrade. Do not run migration downgrade against application data to exercise this check.

## Guarded hosted demo setup

See [the operator preview/apply commands](RUNNING.md#populate-hosted-demo-masters). `scripts/demo_fixtures.py::master_records` supplies the existing three vendors/four POs to both local setup and the new `scripts/seed_demo.py` service. `scripts/hosted.py seed-demo` requires explicit dataset/schema confirmations and defaults to dry-run. No API, migration, financial policy, worker activation or model call is added.

The seeder checks the connected schema/current Alembic head, locks the dataset and vendor names/rows, validates existing policy/masters, and inserts only missing masters with immutable vendor/PO creation records in one transaction. Compatible legacy IDs and allocations remain untouched, including after approval; conflicting terms or unavailable vendors abort. CLI errors redact configuration/database payloads. `tests/test_hosted_seed.py` covers dry-run, concurrent/repeated setup, rollback, immutable audit, conflicts, retained approvals, schema/head guards and CLI configuration/redaction.

Verification on **22 November 2026**:

- Full backend: **338 passed, 3 opt-in live skips**, 432.94s, including all earlier regressions and migration roundtrip/metadata parity; **26** cases cover the new setup command/service.
- Ruff check and format check passed for **109 Python files**. Frontend TypeScript/production build passed (Vite 21.90s); the existing PDF.js chunk-size warning remains. Browser suites and generated contracts were not rerun because no UI/API contract changed.
- Hosted preview confirmed Supabase/private schema **ps1_app**, current head, matching pre-existing policy and zero vendors/POs. Apply added **3 vendors, 4 POs/lines, 3 immutable vendor actions and 4 immutable PO creation records**. Existing run/document/queue/approval and other protected table counts stayed unchanged; no policy row was replaced or added.
- Authenticated read-only checks through the deployed API returned **3 vendors and 4 POs**, each new PO committed at zero. This verifies master visibility only. Worker activation, live hosted processing/recovery and paid extraction were not exercised. Source changes remain uncommitted; no push or application deployment was performed.

## Ordinary invoice verification and checklist

The 22 November layout/checklist extension uses `source_layout.py` to associate PDF headers, sender/recipient regions and table columns/rows independently of OpenAI. No fixture hash, vendor name or sample invoice is consulted. `evidence_verification.py` validates the model's snippets/pages/values against those associations, preserves raw extraction, and constructs trusted evidence locally. Clear printed subtotals omitted by a model can be recovered; source-supported tax sums, net/gross values and price-basis normalization have explicit DERIVED provenance. Absent tax never defaults to zero. An unsupported currency is preserved; Rs. notation needs corroborating Indian country/GST context before INR normalization. Geometry floats are used only for positions; financial calculations use finite Decimal under precision 48.

Prompt **invoice-extract-2**, verifier **layout-grounding-4**, and the unchanged strict wire schema **InvoiceExtractionV1.1** apply to new runs. The original prompt is retained byte-for-byte and `evidence_legacy.py` preserves **labelled-fields-3** dispatch. Frozen reads, source repair and review resume select their saved versions. The internal financial document records unresolved verification findings so a caller cannot bypass a failed verification report by passing its individually grounded values to approval.

`rule_trace.py` records the checks actually executed during the existing locked financial transaction. The immutable assessment's existing observations JSON contains the 13 outcomes; no database migration is added. Approval/ledger/PO writes, ownership fencing and typed tolerances are unchanged. Legacy assessments without a trace retain their conservative projection. Public extracted fields add compatible `required_for_approval`, `origin`, `original_value` and `calculation` metadata; generated OpenAPI/TypeScript are updated. The reviewer checklist is visible outside the source-field disclosure, with human field names and explicit optional/derived states.

Independent synthetic table fixtures cover a different supplier/item/PO, stacked/percentage/footer tax, unnumbered rows, inclusive prices, source omissions, buyer-ID substitution, wrong cells/pages, missing tax/PO, source-correct vendor mismatch, arithmetic inconsistency and partial balances. Workflow tests use mocked Responses transport with actual PDF intake, worker/checkpoints, financial transaction and review resume; no production fixture adapter is used. The user's private Zoho E1 and its already-recorded LIVE_OPENAI response were inspected locally without another model call: the new verifier grounds its required data, but its printed supplier GSTIN differs from the hosted PO vendor. The hosted PO-PARTIAL ledger also has zero approvals; an overrun demonstration still requires genuine prior allocation. No private PDF/extraction is committed and no hosted history/master/worker setting is changed by this extension.

An absent PO does not cause an extraction retry by itself. Missing identifying headers retain one bounded source-repair attempt, followed by review; neither path infers a PO. Unknown or ambiguous layouts, scans without local text, missing tax components and unsupported currencies remain review cases. The three synthetic layouts and one private recorded response do not replace the broader real-document evaluation set still required for production readiness. Existing runs stay on their frozen verifier; deploy the API and worker from the same checkout and use a fresh submission to test this extension. No migration is needed for this change.

Files in this extension:

- Local grounding and compatibility: `backend/app/source_layout.py`, `evidence_verification.py`, `evidence_legacy.py`, `extraction_schema.py`, `extraction_client.py`, `workflow.py` and `owned_finalizer.py`.
- Financial evidence and recorded checks: `backend/app/finance_contracts.py`, `finance_rules.py`, `approval.py` and `rule_trace.py`.
- Read projection/contracts: `backend/app/read_contracts.py`, `read_service.py`, `product_reads.py`, `frontend/openapi.json` and `frontend/src/api.generated.ts`.
- Checklist/source UI: `frontend/src/RuleChecklist.tsx`, `ReviewDetail.tsx`, `RunView.tsx`, `InvoiceDecision.tsx` and `ui.tsx`.
- Verification: `backend/tests/ordinary_invoices.py`, `test_ordinary_invoices.py`, `test_ordinary_workflow.py`, `test_product_reads.py`, `frontend/tests/workflow.spec.ts` and `roles.spec.ts`. The latter narrows a success-message locator that previously matched a simultaneous loading status too. The responsive screenshot matrix is split into three viewport cases so its 21 screen checks have independent time budgets; no assertions are removed.
- Contract/documentation: `SPEC.md`, `README.md`, `docs/DECISIONS.md` and this guide. The earlier uncommitted hosted-seeding changes remain separate existing work.

Verification on **22 November 2026**:

- Full backend: **364 passed, 3 opt-in live skips**, 742.14s, including all 338 earlier cases, **26** new ordinary-layout/workflow cases, migration roundtrip/metadata parity, financial concurrency and worker recovery. The initial run had one retry-count regression (363 passed); the identifying-header retry fix passed its nine-case subset and the full rerun above.
- Ruff lint/format passed for **115 Python files**. OpenAPI export and TypeScript generation passed; frontend formatting, TypeScript and production build passed (Vite 17.01s), retaining the existing PDF.js chunk-size warning.
- Browser suites: **17 role cases passed**, 2.8m, after narrowing the vendor-success locator; **20 shared/provider/workflow cases passed**, 6.6m, with 17 role skips already covered by the separate run. The first shared attempt passed 15 cases, then exhausted a 90-second budget in the combined 21-screen screenshot matrix; its final two cases were not run in that attempt. Splitting that matrix into three independent viewport cases preserved all assertions and passed the complete rerun. All 37 current cases use mock transport and disposable local schemas; none calls a paid API.
- Local documentation checks: **16 public Markdown files, 70 links/anchors, six navigation routes**, and twelve preserved private originals; no errors. Secret-pattern/ignore checks scanned 178 publishable text files with no flags, and Git whitespace passed with the repository's normal line-ending configuration.
- No new paid model call, database/master/history rewrite, hosted worker activation, application deployment, commit or push. The recorded-response check is local verification, not a new live-model benchmark or hosted acceptance test.

## Compact review and confirmed demo reset

The compact review/demo-reset extension adds `app/demo_reset.py`, `demo_reset_model.py` and migration `0011_demo_reset.py`, with strict reviewer routes, disabled-by-default schema/role configuration, immutable retained receipts, stale-preview fingerprints, explicit qualified table allowlists, NOWAIT locks and every existing run's session-advisory-lock check. The existing add-only seed service accepts a caller-bound connection and actor so baseline restoration shares the reset transaction; injected failure after restoration proves it does not independently commit. No worker code or ownership protocol is weakened. Checkpoint migration rows and business migrations are retained, and a cross-schema FK blocks reset instead of cascading.

`review_comparisons.py` adds reviewer-only current vendor/PO and recorded assessment-balance context to read responses, without reevaluating or changing decisions. It handles invalid untrusted numeric strings without breaking a review read. Source verification is independent of agreement with a master value; current context cannot become a historical pass. Submitter serialization omits all comparisons/PO master amounts. Compact timeline/checklist and submitter field presentation retain details in disclosures; `ReviewComparisons.tsx` exposes specific differences and available source links. `DemoReset.tsx` provides preview counts, typed confirmation, cancellation, precise busy/stale errors and a stable retry key; the reviewer sees it on Overview only when enabled. The explicit disposable role launcher enables the flag; default/hosted operation stays opt-in. Exact prompt/request/storage details are in [EXTRACTION.md](EXTRACTION.md).

Initial focused acceptance: **39 passed** (26 reset cases, nine comparison cases and four existing health/migration cases). This covers actual mock-transport approvals/reviews/checkpoints followed by reset and a fresh approval, custom master removal, encrypted connection removal, owner fencing including expired leases, schema/table/confirmation guards, rollback after clearing and after reseeding, concurrent resets and actual concurrent intake, cross-schema FK refusal, immutable receipts, replay with newer submissions, GST/source distinctions, assessment-time excess after current cap changes, malformed amounts and submitter redaction. Test corrections fixed a checkpoint count key and an assertion that incorrectly required extra trailing zeros in preserved source strings. A subsequent reset-receipt check ensures retained receipts are excluded from removed_counts; receipts survive a second reset. The final focused reset/endpoint run passed **29 cases** (27 reset cases and two existing endpoint cases).

Verification completed **23 November 2026**:

| Check | Result |
| --- | --- |
| Full backend | **400 passed, 3 opt-in live skips**, 553.96s; all 364 previous cases plus 27 reset and nine comparison cases |
| Endpoint matrix | All **25 implemented operations** covered across anonymous, three submitters and reviewer roles |
| Migrations | Full upgrade/downgrade/re-upgrade and metadata parity passed, including 0011; no existing workspace was migrated |
| Ruff lint / format | Passed for **121 Python files** |
| OpenAPI / TypeScript | Repeated generation produced identical SHA-256 hashes |
| Frontend format / type / build | Passed; Vite **22.71s**, existing PDF.js chunk-size warning |
| Role browser | **18 passed**, 2.1m, including reset cancellation, typed confirmation, lost response, same-key replay preserving a newer invoice and mobile overflow |
| Shared/provider/workflow browser | **20 passed**, 4.0m; 18 role skips covered separately; includes compact issue stage and recorded amount-difference display |
| Documentation / Git | 17 public Markdown files, working local links, six navigation routes, twelve preserved private originals; credential-pattern/ignore and whitespace checks passed |

The first full backend run recorded **398 passed / 1 failed / 3 live skips**: its endpoint coverage assertion still listed 23 operations and correctly caught the two new reset routes. The matrix now exercises their role and disabled-mode behavior, expects 25, and passed the focused and full reruns. No financial assertion was removed. All browser/model calls used mock transport. The exact prompt in EXTRACTION.md was checked against the source string without a provider request. Desktop/phone screenshots were inspected for compact progress, source fields and the PO-overrun comparison; reset dialog behavior/overflow was checked in the role browser case.

Files in this extension:

- Reset infrastructure: `backend/app/demo_reset.py`, `demo_reset_model.py`, `config.py`, `models.py`, `main.py`, `backend/alembic/versions/0011_demo_reset.py`, `backend/.env.example`, `backend/scripts/demo.py` and `seed_demo.py`.
- Review context: `backend/app/review_comparisons.py`, `read_contracts.py`, `read_service.py`, `frontend/openapi.json` and `frontend/src/api.generated.ts`.
- UI: `frontend/src/DemoReset.tsx`, `ReviewComparisons.tsx`, `BusinessTimeline.tsx`, `RuleChecklist.tsx`, `SubmitterRunView.tsx`, `ReviewDetail.tsx`, `RunView.tsx`, `Overview.tsx`, `App.tsx`, `api.ts` and `workspace.css`.
- Tests: `backend/tests/test_demo_reset.py`, `test_review_comparisons.py`, `test_predeploy_endpoints.py`, `frontend/tests/roles.spec.ts` and `workflow.spec.ts`.
- Guides/contracts: `README.md`, `SPEC.md`, `docs/EXTRACTION.md`, `docs/README.md`, `docs/RUNNING.md`, `docs/ROLE_ACCESS.md`, `docs/SECURITY.md`, `docs/DECISIONS.md` and this guide.

No user workspace or hosted data was reset, no paid call was made, and no credentials, production activation, commit, push or deployment changed. The new reset feature remains disabled by default; apply 0011 and deliberately enable its flag on a dedicated role-mode demo before using it. Existing source/review/approval policy and frozen run versions remain unchanged. Comparisons support inspection, not manual trusted-field editing or hard-rule overrides. A lost database connection cannot cancel an external provider request already dispatched; stale writers remain fenced. Broader layout/scan evaluation and hosted recovery acceptance remain open.

## Generated contracts and frontend checks

From backend:

```cmd
uv run python -m scripts.export_openapi
```

From frontend:

```cmd
npm.cmd ci
npm.cmd run generate:api
npm.cmd run format:check
npm.cmd run build
```

The OpenAPI exporter does not connect to a database. Decimal request fields remain strings. Regenerate before browser tests: rewriting OpenAPI during a Vite session can trigger a page reload and clear the intentionally tab-only authentication state.

## Browser checks

Install dependencies and an available Chrome browser. From backend in CMD:

```cmd
set "PS1_BROWSER_CHANNEL=chrome"
uv run python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273
uv run python -m scripts.browser_checks --api-port 8100 --ui-port 5273
```

Set PS1_DEMO_DATABASE_URL to your dedicated loopback database if the default 55432 connection is not available. Use free test ports, separate from your running preview. Each runner owns its API/worker/Vite processes and marked disposable schemas, then cleans only those. The role runner covers submitter/reviewer access; the other covers shared/provider/workflow cases and skips role cases already run separately. Both use explicitly labelled MOCK_OPENAI and incur no extraction charges.

## Recorded application verification

Latest financial/vendor milestone, **18 November 2026**, before this documentation cleanup:

| Check                                                   | Recorded result                                                     |
| ------------------------------------------------------- | ------------------------------------------------------------------- |
| Full backend suite                                      | **312 passed, 3 opt-in live skips**, 355.13s                        |
| Vendor/totals/endpoint subset                           | **47 passed**, 38.72s                                               |
| Role browser suite, including confirmed outcome wording | **17 passed**, 1.5m                                                 |
| Shared/provider/workflow browser suite                  | **18 passed**, 2.8m; 17 role skips covered by the separate run      |
| Ruff / Python formatting                                | Passed for 107 Python files                                         |
| Migrations                                              | Full roundtrip/metadata parity and blacklist downgrade guard passed |
| OpenAPI / TypeScript generation                         | Repeated generation produced identical hashes                       |
| Frontend format / TypeScript / production build         | Passed; Vite 13.31s                                                 |

Coverage includes reviewer vendor registration/status, duplicate-name/tax rejection, immutable audit, injected rollback, stale/blacklisted vendor checks under locks, exact net/tax/gross totals, independent PO caps, lost-response replay and fixture invoice allocation. Tests preserve earlier worker, financial, ownership and frontend behavior. No model confidence or generated verification flag authorizes approval.

The existing local preview was migrated/reloaded without changing its records, budgets or credentials. Manual 1440/390px screenshot checks used synthetic data or unsaved/cancelled drafts. These are local results, not proof of active hosted processing or broader invoice accuracy. The pre-existing PDF.js chunk-size warning remains. H2's fully justified rounding fixture, broader commercial/scan evaluation, hosted recovery acceptance and actual billed-cost measurement remain open.

The earlier 18 November documentation cleanup changed guides/ignore rules only. Its checks covered Markdown links/anchors, navigation against source, preserved local-document hashes, tracked/ignored boundaries and Git whitespace. The hosted setup extension above adds operator code and separate regression coverage; it does not alter the schema or financial authorization. See [benchmark evidence](benchmarks/README.md) for separately dated sanitized live measurements.

## Working conventions

- Preserve financial tolerances, identity normalization and the locked at-most-once approval transaction unless an explicit contract change is recorded.
- Keep production processing opt-in and OpenAI as the only provider. Never masquerade cached/mock extraction as live.
- Keep actual secrets in ignored environment files/server settings, with no VITE_ secret variables.
- Keep personal deployment/key runbooks, traces and build journals in ignored docs/local or .local. Public docs must not depend on them.
- Keep the rate JSON in docs/benchmarks tracked: demo/live-test scripts read it. `.gitignore` is not an access-control mechanism or a Git-history purge.
