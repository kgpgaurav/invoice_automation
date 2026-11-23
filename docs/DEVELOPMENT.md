# Development and verification

[Project](../README.md) · [Documentation](README.md) · [Local setup](RUNNING.md)

SPEC.md is the canonical contract; docs/DECISIONS.md records agreed refinements and unresolved questions. Read AGENTS.md before implementation. Historical operator/build journals are kept locally under ignored docs/local; they are not dependencies of this guide or the application.

## Expanded extraction and mandatory scan review — 23 November 2026

Implemented SPEC §§1.1, 2.2, 3.3–3.5, 4.3 and 5.2 in the existing pipeline. New runs freeze prompt 4 / `InvoiceExtractionV1.2` / `extended-diagnostics-8`; earlier prompt/schema/verifier pairs retain their parsers and outputs, including deployed version 7. Added 20 nullable header fields and 11 nullable item fields for buyer/delivery/address, due date, payment terms, HSN/SAC, GST/cess components, discounts and charges. Raw outputs, source diagnostics and normalized/derived values persist separately in versioned JSON/history and appear in grouped API/UI projections. New health metadata identifies the deployed extraction versions and scan policy.

Scan detection covers image-only pages, substantial raster content with OCR overlays, and mixed documents, while excluding small logos. Every scan holds even when all fields verify. The hold is repeated at the worker-owned finalizer and direct financial boundary, including unposted legacy/resumed runs. Existing approved records remain immutable. Image-only extractions retain their vision citations but are not independently OCR-grounded; no repeated model answer is treated as corroboration. Unsupported mandatory evidence cannot approve.

Source-supported GST component calculations use Decimal, retain formulas/pages, and must agree with total tax. Nonzero discounts, shipping, other charges and rounding hold under the unchanged arithmetic policy. Supplied unsupported financial components also hold. Buyer identity never fills supplier identity. Optional descriptions/addresses do not become unconditional financial prerequisites. A quantity quote spanning a cell and adjacent unit verifies only against its unique source value, correct page and actual full page quote; incorrect numbers/pages and invented units fail. Original raw evidence stays unchanged.

Release validation:

- Full PostgreSQL backend suite: **502 passed, 3 opt-in live skips**, 707.56s. Command: `pytest -q --tb=short -p no:cacheprovider --basetemp=../.local/pytest-release-final-a32d`, with the dedicated loopback `TEST_DATABASE_URL` and private supplied-label/report environment paths.
- The final citation change was checked separately: **42 passed** in extended fields, semantic layouts and diagnostics, including four new citation boundary cases. Final benchmark/field compatibility subset: **20 passed**. Full collection plus these new cases covers **506 distinct non-live backend cases**.
- Shared/provider/workflow/detail browser suite: **33 passed**, 6.0m; role suite: **18 passed**, 2.9m. All **51 distinct browser cases** pass. The first shared attempt was interrupted by editing a watched test file; Vite's recorded reload cleared intentionally in-memory login. The unchanged suite passed after files were held stable.
- Ruff lint and formatting: **127 Python files** pass. Application and browser-fixture TypeScript, Prettier, OpenAPI generation and production frontend build pass; the existing lazy PDF.js chunk warning remains.
- Matrix: **32 generic layout variations** across four tax/table forms, numbered/unnumbered and inclusive/exclusive cases. Supplied-workflow replay: **15 cases**, original digital plus raster-only/OCR-overlay versions of each supplied PDF, using clearly marked saved model outputs and separate synthetic masters. Four original digital cases review for missing PO, ambiguous date or excess test PO cap; only the fully supported digital test case approves. All ten scan variants review without posting. Replay/review-stop preserves thread and attempt count.

Two further live requests used the remaining authorization on two original supplied PDFs: prompt-4 raw exact match **101/108 (93.52%)**, known-field completeness **48/48**, and all **20/20 additional printed fields** extracted correctly after declared numeric/address punctuation normalization. Independent grounding supports **19/20** of those additional fields; one optional buyer address remains UNVERIFIED. Mandatory labelled grounding after the citation fix is **35/35**; normalized core financial match **46/46**. These two cases have no extraction-evidence hold after re-verification; financial matching remains separate. Median API latency **20.6635s**, maximum **23.171s**; dated estimated total cost **USD 0.00311269**. Actual billing is unknown. Seven requests were used before the separate hosted scan smoke, within the ten-request authorization. This refinement set is not held out and proves no universal-layout or original-scan accuracy claim. [Sanitized measurements](benchmarks/expanded-extraction-2026-11-23.json) preserve denominators and limitations.

Initial full release regression exposed eight failures: expanded private assessment metadata broke duplicate-conflict parsing, older finalizer test fixtures mixed new schemas with the legacy verifier default, and a read test incorrectly required missing new optional fields to verify. The duplicate reader now validates only the frozen FinancialDocument keys while retaining audit metadata; fixtures explicitly freeze their verifier; optional-state assertions reflect the additive contract. A **76-test** affected workflow/read/access/supplied-scan rerun passed before the final full suite. No approval condition was waived.

Authorized production release completed on the existing Vercel Hobby/Supabase target: deployment `dpl_FoF6CeNbt1sBEL9BQwVf9cJPU35P`, with the previous deployment ID retained privately for rollback. CLI build logs confirm the frontend/API and new worker image; the public domain serves health/readiness 200 and the new schema/prompt/verifier/scan metadata. Frontend asset names/content match the new Linux deployment build; their hashes differ from the Windows build, so no cross-platform byte-identity claim is made. Expanded field strings are present in the served bundle. Unauthenticated run access returns 401 and submitter finance access 403. The worker is one ready instance in iad1 on the new image digest. No plan upgrade or new hosting provider was introduced.

The database was verified against authenticated hosted PO IDs using existing operator configuration. Only additive migration 0012 was needed at release; before/after fingerprints of all pre-existing source, workflow, audit and financial rows match. The worker was paused briefly for rollout and restored. An attempted production environment download was rejected by automatic approval review because it would create a new plaintext secret copy; that path was abandoned. Existing ignored operator configuration supplied the verified migration target without downloading or printing hosted secrets.

Fresh hosted scan acceptance used the same supplied content rasterized into image-only PDF: **one live request**, **26.457s provider latency**, 5,123 input / 3,000 output tokens. It reached WAITING_REVIEW / NEEDS_REVIEW with SCANNED_DOCUMENT_REQUIRES_REVIEW; an authorized REQUEST_INFO action resumed the **same thread**, then stopped without an additional model request. All financial/master fingerprints stayed unchanged. The test's temporary encrypted provider session was revoked. A transient HTTP polling RemoteProtocolError interrupted the observer; recovery read and finished the original run without resubmission. Live image-only field accuracy is not scored from this single acceptance smoke. Server cost remained explicitly unknown because no runtime rate table was configured; the separate dated estimate is **USD 0.0021403**, not an account bill. Total authorization use is **8/10 requests** with **USD 0.013160500** aggregate dated estimate across all eight. Two authorized requests remain unused. Private release receipts contain identifiers/source hashes; the tracked benchmark contains sanitized aggregates only. Source changes are deployed from the authorized working tree and remain uncommitted/unpushed.

Final adversarial follow-up: a generated invoice with two contradictory printed IGST amounts and a null raw IGST field exposed a gap in version 7's optional-component hold. Version 7 is now frozen in `extended_verification_v7.py`. Version 8 marks ambiguous numeric source components required and adds UNVERIFIED_FINANCIAL_DETAIL; the finalizer independently checks this ambiguity for unposted frozen runs too. **90 source/workflow tests** and **41 field/read/frozen tests** pass after the fix, including both version-7 and version-8 full workflows with zero ledger entries and one model request. Additional frozen prompt-3/verifier-6 and prompt-4/verifier-7 review/resume cases pass. Re-verifying all five original live artifacts with version 8 retains **225/225** normalized match, **165/165** labelled supported fields and two ambiguity holds. No additional paid request or migration was needed. Ruff passes for **128 Python files**. The hosted scan acceptance above deliberately retains its original verifier-7 run; it is not relabelled as a fresh version-8 call.

Final matching release **`dpl_5oy5kLRysENhXJjSf99U7qUbjbmW`** was built and promoted to the existing domain. Public health confirms **extended-diagnostics-8**, prompt 4, schema V1.2 and the scan hold; readiness returns 200 and authenticated role restrictions remain enforced. The worker has **one ready instance** on image `sha256:f11b6a69d14797e20472ea900ef0f8f6eefc93df0ffa1a56141c3195729646d7`. Served frontend assets match this deployment's build log. Final comparator/budget regressions add **7 passed**; those overlap earlier test counts. The source-only follow-up required neither another migration nor another live extraction. The original scan test/history and its stopped review outcome remain unchanged. The hosted schema remains 0012.

## User-supplied invoice evaluation — 23 November 2026 (earlier verifier slice)

The five supplied PDFs have text layers and span **two layout families**. No scanned PDF was supplied. Rendered inspection and independently authored labels remain under ignored `.local/real-invoice-evaluation/`. These documents were used for refinement, so this is **not a held-out benchmark or evidence of universal invoice support**. Source contents, addresses, identifiers and raw responses are not copied into tracked fixtures or reports.

New runs use `semantic-diagnostics-6`. The new source module handles decimal price continuations within one geometric cell, Seller/Client regions, Date of issue, multiline descriptions/headings, Net Price/Net Worth/Gross Worth/VAT columns, and multi-value Total rows. Printed gross cells and final display totals remain independent source candidates alongside calculations, so discrepancies still hold. Ambiguous dates retain both interpretations. Source-supported grouping/percent notation and heading-plus-cell citations normalize without changing the raw wire output. Frozen layout-4/diagnostics-5 parsing remains unchanged. Financial policy, API fields, locking, review actions and prompt/schema contracts are unchanged; no additional migration follows 0012.

The user approved **up to ten paid OpenAI requests**. All five PDFs completed in **five Responses requests**, one each, with no retries. The remaining allowance was not spent. Original live outputs, source hashes, attempts and usage are private; comparisons reverify those same outputs without model calls. No financial/database posting or hosted/deployment action occurred.

| Measurement | Result |
| --- | --- |
| Strict raw wire-target match | **207/225 (92.0%)**, including valid null/UNKNOWN, unit notation and raw/derived representation differences |
| Canonicalized known printed fields | **149/150 (99.33%)** correct and present; one omitted printed subtotal recovered independently by the source reader |
| Locally normalized field match | **225/225** against separately authored financial-field labels, including unknown/absent values |
| Supported-field grounding | **33/165 → 165/165**, zero false grounding in this labelled set |
| Evidence holds | **4/5 → 2/5**; both remaining holds concern ambiguous numeric dates |
| API latency | p50 **22.047s**, nearest-rank p95 **28.062s**, n=5 |
| Returned usage | **17,041 input / 12,654 output tokens** |
| Cost | **USD 0.007907510** total estimate using the existing **12 November 2026** snapshot; actual billing unknown |

Evidence holds are **not final financial review rate**. Printed PO spelling/absence, registered vendor identity, dates, balances, duplicate history and every financial check still apply. No invoice was approved and no PO balance changed. Independent scanned grounding and expanded buyer/due-date/discount/GST-component schema fields remain subsequent slices.

Final combined verification: **185 passed** (197.71s), covering extraction, offline artifact/source-hash checks, durable workflow/recovery/concurrency, review/read projections, financial rules and approval. Earlier intermediate runs passed 178 and 93 tests. Fifteen generic source tests pass, including unnumbered rows, contradictory printed line/final totals, wrong supplier/column/page, malformed percentage quantities, heading-plus-cell citations and raw-value retention. Initial tests exposed left-aligned cells and duplicate Total-label context; these were corrected with column association. Ruff lint/format passed for **134 Python files**, and Git whitespace checks passed. The old source-layout Git blob retains its original hash. No API/UI shape changed in this slice, so browser/build checks were not repeated.

The final combined command was `pytest tests/test_semantic_layouts.py tests/test_saved_extraction_comparison.py tests/test_extraction.py tests/test_extraction_safety.py tests/test_extraction_diagnostics.py tests/test_extraction_benchmark.py tests/test_extraction_repair_workflow.py tests/test_extraction_integration.py tests/test_extraction_review.py tests/test_ordinary_invoices.py tests/test_ordinary_workflow.py tests/test_workflow.py tests/test_workflow_reviews.py tests/test_workflow_safety.py tests/test_workflow_recovery.py tests/test_workflow_financial.py tests/test_workflow_concurrency.py tests/test_source_omission.py tests/test_review_comparisons.py tests/test_product_reads.py tests/test_finance_rules.py tests/test_approval.py -q --tb=short -p no:cacheprovider --basetemp=../.local/pytest-invoice-final-47bcd`, using the dedicated loopback test database. The live command used `scripts.benchmark_extraction --live` with the private manifest, `--model gpt-6-luna --route pdf --max-calls 10` and a private artifact directory. The five saved outputs were then evaluated with `scripts.compare_extraction_artifacts`; no new paid call was used for comparisons or code refinement.

Fresh outputs can be retained with `benchmark_extraction --artifacts-dir`, restricted to workspace `.local`. `compare_extraction_artifacts` validates source hashes and compares the saved output under both versions with **zero new model calls**, using independent raw, financial-field and support labels. The private `live-report.json` preserves original provider measurements; `live-comparison.json` includes final verifier source hashes. See [benchmark instructions](benchmarks/README.md).

## Extraction diagnosis and targeted repair — 23 November 2026

Implemented the first requested extraction vertical slice under SPEC §§1.1, 2.2, 3.3–3.5 and 5.2. Diagnosis found that native PDF vision input already exists, while source association is restricted to recognized local headers/tables; scans lack independent grounding, retries were generic and schema/verification failures lacked field-level reasons. Broader layout grounding, OCR corroboration and expanded buyer/due-date/GST/discount fields remain subsequent slices. No financial tolerance, matching, duplicate, approval transaction, ownership or review action was relaxed.

New `invoice-extract-3` / `layout-diagnostics-5` runs retain source states/reasons, raw versus normalized values, field-level financial typing errors and private per-attempt verification history. Strict field-only repair merges requested values/citations, retaining the initial successful output; schema, transport and source retries share the existing two-call reservation. Unsupported associations, contradictions and scans without independent support stay in review. Frozen prompts 1/2, schema V1.1 and legacy/layout-4 financial verification remain supported; the original layout verifier is retained in `evidence_layout_v4.py`. Public field metadata is additive and excludes private snippets/bank values. Migration **0012_extraction_diagnostics** adds only private workflow diagnostic history; it was exercised in disposable test schemas, not deployed or applied to the existing user workspace.

Verification performed:

- Before edits: extraction/safety/ordinary-layout/workflow baseline **55 passed** (36.55s).
- Full backend command `pytest -q --tb=short -p no:cacheprovider`: **415 passed, 3 opt-in live skips, 3 setup errors** (621.32s). All three errors were Windows denial of the default pytest temp directory in `test_presentation_config.py`, before application execution. Rerunning that file plus health/migration tests with `--basetemp=../.local/pytest-extraction-recovery-372ac` passed **9/9**, including full migration roundtrip and SQLAlchemy metadata parity.
- Final focused extraction/manifest/repair/frozen-workflow command with a separate workspace `--basetemp`: **27 passed** (30.34s). This includes five new manifest/budget tests and the additional frozen prompt-2/verifier-4 resume case added after the full run. Final collection is **427 tests**: all **424 non-live cases** are covered by the full run plus successful focused/setup reruns; three live cases intentionally remain skipped. An earlier focused attempt hit the same default-temp restriction for five new manifest tests; these passed with workspace temp storage. Initial lint/format/type failures were corrected. No application assertion remains failing.
- Shared/provider/workflow/detail browser command `python -m scripts.browser_checks --api-port 8101 --ui-port 5274`: **32 passed** (5.7m), including source-reason/ambiguity display, original amount retention, review/resume, scan hold and duplicate/budget controls. Its 18 role cases are intentionally assigned to the separate role workspace.
- Complementary `python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273`: **18 passed** (2.1m), giving **50 unique passing browser cases** across both profiles. Final metric/manifest checks passed **19/19** after excluding UNKNOWN/structural row counts from completeness. Ruff lint/format, frontend formatting/type checks and Git whitespace checks passed. The retained layout-4 verifier's Git blob hash exactly matches the pre-change verifier.
- Frontend OpenAPI export/type generation, application/browser-fixture type checking and formatting passed. `npm run build` initially hit sandbox parent-directory access in Vite's default config bundler; `npm run build -- --configLoader runner` passed (36.85s), retaining the existing large-PDF-preview-chunk warning. Browser runners use disposable mocked workspaces and no paid provider calls.

The [synthetic report](benchmarks/extraction-diagnostics-2026-11-23.json) uses one generated ordinary table and a scripted missing-date correction: field correctness **22/23 → 23/23**, expected-field completeness **13/14 → 14/14**, three independently labelled supported fields grounded after repair, and evidence hold resolved. This is a repair-mechanism regression, **not measured OpenAI extraction accuracy**. Twenty local verifier samples had medians **18.572ms (layout-4)** and **34.337ms (diagnostics-5)** in this concurrently loaded development session; extra diagnostic parsing adds local work. Real model latency/cost and real-layout accuracy remain unknown. Mock scan/genuinely absent-date cases now dispatch one request instead of two while still producing NEEDS_REVIEW and no ledger post. That measures request count, not a claimed percentage reduction in actual billed cost.

The live benchmark now accepts a private independently labelled manifest and checks its call budget before every dispatch. It reports field completeness and labelled grounding precision/recall separately from source-hold frequency, with actual usage and dated cost estimates. See [benchmark instructions](benchmarks/README.md). This task made **zero paid model calls**, no hosted writes, no commit/push/deployment, and preserved the pre-existing UI/documentation work.

## Invoice workspace UI — 23 November 2026

The new shared `InvoiceWorkspace` composes existing detail reads, source documents, financial checks and review actions. `InvoiceSummary`, `InvoiceFields`, `InvoiceIssues` and `invoicePresentation.ts` provide the common summary, metadata-based indicators, grouped values, line-item table and prioritized recorded findings. `RunView`, `ReviewDetail` and `SubmitterRunView` reuse that composition without changing their authorized data sources. Source badges explain their provenance on expansion. Unsupported buyer/address/due-date/discount/charge fields remain omitted, and no manual correction or arbitrary approval is introduced.

`invoice-detail.css` uses the existing DM Sans/olive identity with neutral surfaces, available-width layouts, a 42/58 document/data split, keyboard/pointer resizing and PDF collapse. Accessible data/comparison/check/review tabs retain draft input; narrow layouts stack panels. `DocumentPanel`/`PDFPreview` retain authenticated blob reads and add zoom plus explicit PDF retry. `ReviewComparisons` shows a table with source/business distinction, expected records, exact differences and historical/current labels. A display-only relative unit-price figure uses bounded decimal strings and BigInt with explicit two-decimal rounding; invalid or zero bases have no ratio and no financial outcome is calculated in JavaScript. `BusinessTimeline` preserves the six persisted stages and adds individual expansion, honest pending/failed states and execution-versus-review explanations. Existing review events supply the finance history.

Runtime dependencies are unchanged. Node development types and `tsconfig.browser.json` enable `npm run check:types` for application code plus all browser fixtures/configuration. Playwright artifacts are scoped to each disposable workspace so independent suites can run without clearing each other's traces. The new `tests/invoice-detail.spec.ts` uses explicit typed, mocked read projections for multi-line/missing/derived/conflicting data, state/error recovery, exact display ratios, responsive layout and keyboard/PDF controls. These do not execute financial decisions; the existing workflow and role suites still exercise the real mock processor, worker, checkpoints and approval/review transactions.

Backend regression: **401 passed, 3 opt-in live skips**, 494.67s, including migration/metadata parity. Ruff passed for **122 Python files**. Final browser results: **49 unique cases passed** — role suite **18 passed** (2.3m), shared/provider/workflow/detail suite **31 passed** (4.1m). The shared run intentionally skips the same 18 role cases that run in their separate role workspace; no required case is left untested. Application and browser-fixture type checks, frontend formatting and production build passed. Regenerated OpenAPI/TypeScript and all 122 backend Python files retain their pre-change hashes. Visual inspection covered 1440/768/390 widths, source/data grouping, mobile internal table scrolling, the actual worker-backed review form and queue reason wrapping. The baseline role suite also passed all 18 cases after starting the existing stopped local PostgreSQL test cluster without reinitialization. No hosted database operation, paid provider call, commit, push or deployment is part of this UI pass.

Early browser runs exposed a decorative review dot changing the tab's accessible name, a scan warning hidden too deeply, an unstable wrapping textarea label after typing, and assertions that assumed all detail panels were visible at once. The dot is decorative, the scan warning remains prominent, the rationale now has a stable explicit label, and assertions navigate the new tabs. A queue search assertion also counted the detail tables; it now targets the Review items region and verifies the expected supplier. A regression confirms late review metadata cannot override a manually chosen tab. Review drafts, same-key retries and real same-thread worker resume were rechecked. Initial standalone browser-fixture typing lacked Node declarations; development-only Node types resolve that. The restricted Windows build could not read a parent directory while bundling Vite config; the same build passed with filesystem access. The existing lazy PDF.js chunk still exceeds Vite's 500 kB advisory threshold.

Reproduce browser checks from backend with `PS1_BROWSER_CHANNEL=chrome`, distinct local API/UI ports and `PYTHONUTF8=1`:

```cmd
uv run python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273
uv run python -m scripts.browser_checks --api-port 8101 --ui-port 5274
```

These commands own disposable mock workspaces and remove only their own schemas/processes. The role suite runs separately because shared mode intentionally skips those cases. `PS1_BROWSER_GREP` can narrow an investigation; leave it unset for a full run. Routine checks do not incur provider charges. The additional UI projections are explicitly mocked read responses, not evidence of new live extraction accuracy. The refreshed README screenshot comes from the actual mock-worker role scenario, with its mock label visible; other captures remain ignored local QA artifacts.

Exact file changes for this UI task:

| Files | Purpose |
| --- | --- |
| `frontend/src/InvoiceWorkspace.tsx`, `InvoiceSummary.tsx`, `InvoiceIssues.tsx` | Shared role-aware workspace, concise metadata/indicators, recorded issues, tabs and existing review/history composition |
| `frontend/src/InvoiceFields.tsx`, `invoicePresentation.ts`, `invoice-detail.css` | Grouped values, multi-line table, source expansion, exact display ratio, responsive neutral layout and compact sidebar |
| `frontend/src/RunView.tsx`, `ReviewDetail.tsx`, `SubmitterRunView.tsx` | Reuse the workspace while retaining existing fetch, ownership, events/polling, error and audit behavior |
| `frontend/src/DocumentPanel.tsx`, `PDFPreview.tsx` | Authenticated preview, existing expansion/focus handling, page links, zoom, PDF collapse and retry |
| `frontend/src/ReviewComparisons.tsx`, `BusinessTimeline.tsx`, `InvoiceDecision.tsx`, `ReviewForm.tsx`, `main.tsx` | Comparison table, compact expandable stages, review-tab navigation, stable rationale label and stylesheet import |
| `frontend/tests/invoice-detail.spec.ts`, `roles.spec.ts`, `workflow.spec.ts` | Eleven additional detail-state/display/accessibility cases and adapted existing role/workflow assertions |
| `frontend/playwright.config.ts`, `tsconfig.browser.json`, `package.json`, `package-lock.json` | Per-workspace test artifacts, optional focused runs, browser-fixture type checking and development-only Node types |
| `README.md`, `SPEC.md`, `docs/DECISIONS.md`, `docs/DEVELOPMENT.md`, `docs/screenshots/ui-2026-11-18/review-queue.png` | Current navigation, authorized presentation extension, rationale, results and one refreshed synthetic screenshot |

No backend or generated API file changed. Persistent sign-in is unchanged: refresh still requires reconnecting under the existing tab-memory credential contract. Buyer/address/due-date/discount/charge fields, manual correction and exact evidence highlighting remain unsupported; adding them requires a separate data/workflow contract. This UI pass requires no database migration and does not rewrite saved assessments or approvals.

Publication verification: **213 files**, including **209 text files**, passed the credential/private-artifact scan; **45** ignore cases, **39** required-public-file checks, **89** links/anchors and **six** documented routes passed. All twelve preserved owner documents and 66 unused local captures retain their original hashes. Only the existing four README illustrations are public; one is refreshed here. Git whitespace checks passed. These 28 changed/new files remain uncommitted for review.

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

From frontend, `npm run check:types` also validates the browser fixtures against generated API types, while `npm run format:check` and `npm run build` verify formatting and production output.

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
