# Product finalization — Phase 1 handoff

Date: 2026-11-13. Scope: product UI/UX only, under SPEC §§4.1–4.3. Phase 2 and subsequent phases were not started. Existing Slice 6A changes remain uncommitted alongside Phase 1. No commit, push, deployment or live OpenAI call occurred in this phase.

## Problems addressed

The previous interface combined history and metrics, made the upload path more obvious than exception handling, and required users to read raw joined finding codes and engineering events. It lacked a financial checklist, a PO ledger, and an immediately readable overrun calculation. Original field labels used generic title casing, source-page references were not interactive, and technical metadata competed with financial decisions. The visual vocabulary relied heavily on green panels and cards rather than a clear register of invoices and exceptions.

## Design and behavior

- Central CSS tokens use the requested warm background #F6F5F2, white surfaces, secondary #ECEAE4, text #171717/#5B5B57, borders #D9D7D1 and brand #6E7B4E. A darker olive provides readable interactive text/buttons. Approved, review, rejected and technical-failure colors are independent, accompanied by words/icons. Typography uses local system fonts with tabular numerals, monospace invoice/PO references and compact tables. Monetary formatting uses en-IN and decimal strings/BigInt, never frontend financial arithmetic.
- Review Queue is the default operational landing page when pending review records exist; otherwise the root opens Overview. Explicit run/view/PO URLs are preserved. All five navigation items work. The queue badge reads actual waiting-review totals, refreshes on run-state updates and has a bounded polling refresh. History search runs on the server against invoice/vendor/run references, with literal wildcard handling and query-bound keyset cursors.
- The decision card puts outcome, explanation, authorized amount or stored overrun arithmetic, and permitted next steps first. E1 displays 100000 - 70000 = 30000 available, then 35000 requested and 5000 excess using the existing immutable observation strings. It never derives those financial facts in JavaScript. Technical failure is explicitly distinct from rejection. Current PO master data is labelled separately from assessment-time balances.
- Checklist data is an authenticated read projection. Explicit VALIDATED + same-run committed ledger certifies mandatory passing checks. It does not infer a pass from a missing finding. Held assessments show only their recorded failure/hold; other checks remain not evaluated with neutral labels. Each item has status, business text, rule/finding ID, provenance, assessment revision and locally verified pages where available. A later reviewer rejection remains distinct from the older immutable held assessment. No financial evaluator or writer was changed.
- Six business stages group actual persisted node events: read document, extract, verify evidence, match PO, apply rules, record decision. Execution completion is not a financial pass. Missing events stay not recorded; interrupted stages do not become successes. Paired persisted intervals supply durations. Decision recording shares the existing financial transaction, so no separate duration is fabricated. Raw audit events, model/policy/cost and technical reasons are expandable. Existing authenticated fetch SSE, sequence recovery and polling fallback remain active.
- Desktop shows PDF left, rule/financial/review content right. Tablet/mobile stack the workspace. Only verified local page references produce source navigation; no bounding boxes are supplied or invented. Bundled PDF.js renders the original authenticated blob. Candidate selection is visually highlighted and requires one offered PO, rationale, generation, idempotency and the separate reviewer credential. Backend actions remain closed; no manual approval or spending override was added.
- Purchase Orders offers a bounded read-only searchable register and a ledger detail page. Detail reads one repeatable database snapshot, sums immutable allocations and compares them with current committed counters. A mismatch yields unknown available balance and a warning. Approved invoices link to their actual runs. The first 100 allocations are returned with a total/truncation disclosure; there is no invented historical running balance.
- Overview separates metrics from operational history. Straight-through numerator is approved workflow runs without any persisted review request; denominator is workflow runs with a final decision or current review hold. Unstarted, failed/stopped and unknown workflow records are excluded. Numerator/denominator, mock/live/replay coverage, measured time count, cost coverage and distinct held-overrun counts are disclosed. Zero denominator and unmeasured costs stay unknown. This is run-level automation, not labor saved or guaranteed invoice-level accuracy.
- Try a Scenario explains the existing local PDF fixtures and dependencies. It does not upload, seed, reset, download private files or claim independently isolated/repeatable scenarios. H2 stays unavailable. Mock mode is labelled in runs, history and aggregate measures.

## Scope and security

No layout-aware verifier, derived NET/GROSS basis, OCR, realistic fixture redesign, cookie sessions, public demo reset, spend gateway, payment, email, deployment or README rewrite was implemented. Financial writers, workflow/ownership code, source-verifier logic, configuration and previous migrations retain their pre-Phase-1 contents. No new business migration is needed for these read projections.

Source filenames are not persisted by the current intake schema. Before extraction the UI uses the actual run reference, not a hash-derived invented filename. A later per-intake safe filename column and explicit API/intake migration are required. The existing optional source value is not repurposed as a filename.

The shared-ZIP .env exposure needs operator credential revocation/rotation. Exclusions were checked without reading/printing secrets. No environment file was modified or archived. See [SECURITY.md](SECURITY.md); rotation has not been claimed completed. README remains the historical planning document until the explicitly deferred Phase 5 rewrite.

## Verification and screenshots

Final results: **173 backend tests passed / 2 opt-in skips in 265.80s; 9 Edge browser cases passed in 2.2 minutes**. Ruff/format, migrations/parity/roundtrips, reproducible OpenAPI/types, frontend formatting/TypeScript/production build and Git checks passed. Detailed commands are in DEVELOPMENT.md. Browser tests use actual PDFs, HTTP intake, separate worker, PostgreSQL, strict verification and financial transactions; only extraction is a disclosed mocked transport. No new live API spending was needed. Actual screenshots are generated by Playwright, not design mockups. Local test schema/process cleanup is part of the runner.

The browser checks cover H1, E1 prior allocation and overrun, E2 separate-auth/idempotent selection/resume, E3 text rejection and conservative scan hold, E4 bank mismatch, 401/403/404/409/network failures, SSE recovery/polling, search/pagination, read-only ledger links, scenario limits, loading/empty/error states, keyboard landmarks/focus, labelled controls, contrast and 1440/768/390 viewport behavior. These are programmatic accessibility checks and keyboard interactions; a manual NVDA/VoiceOver session and exhaustive assistive-technology audit are not claimed.

Visual refinement addressed tiny identifier headings, screenshot scroll/sticky artifacts, overly large clean-invoice balance blocks, stale queue badges, tablet PDF width and neutral wording for unrecorded checks. No extraction or financial safeguards were loosened to make a screen pass.

Key screenshots: [review queue](screenshots/phase1-review-queue.png), [clean invoice](screenshots/phase1-approved-1440.png), [overrun](screenshots/phase1-overrun-1440.png), [PO ledger](screenshots/phase1-po-ledger.png), [PO selection](screenshots/phase1-mock-review.png), [overview](screenshots/phase1-overview.png), [mobile overrun](screenshots/phase1-overrun-390.png), [tablet invoice](screenshots/phase1-approved-768.png).

## Deferred requirements and practical limits

Reliable geometry/exact source highlights, general table grounding, scans/OCR and basis derivation remain Phase 2 work. Realistic and independent fixture scenarios, a justified H2 and the >=20-layout evaluation remain Phase 3. Deployment, evaluator sessions/CSRF, public cost/abuse controls, reset isolation, backup/retention and credential operations remain Phase 4. Documentation/video finalization remains Phase 5. This milestone does not assert unrestricted production readiness or hosted acceptance.

The current approval certificate is aggregate; historical individually executed checks were not persisted. This UI cannot recover missing check logs from a held assessment. PO ledger responses are bounded at 100 displayed allocations and no load/performance acceptance is claimed for large datasets. History cursors bind filters/query but counts are current, not a cross-request snapshot. PDF.js still produces a large lazy-chunk warning. Original PDF access is available; text search/selection and exact evidence highlights remain unavailable.

## Exact incremental file manifest

The generated list below identifies Phase 1 files relative to the privately recorded 58-file uncommitted Slice 6A baseline. DEVELOPMENT.md explains the purpose of each source group. Existing Slice 6A files outside this list are preserved.

<!-- PHASE1_MANIFEST -->

63 incremental files (33 screenshots).

- `PROGRESS.md`
- `backend/app/product_reads.py`
- `backend/app/read_contracts.py`
- `backend/app/read_routes.py`
- `backend/app/read_service.py`
- `backend/tests/test_product_reads.py`
- `docs/DECISIONS.md`
- `docs/DEVELOPMENT.md`
- `docs/PHASE1.md`
- `docs/RUNNING.md`
- `docs/SECURITY.md`
- `docs/screenshots/phase1-approved-1440.png`
- `docs/screenshots/phase1-approved-390.png`
- `docs/screenshots/phase1-approved-768.png`
- `docs/screenshots/phase1-history-mobile.png`
- `docs/screenshots/phase1-mock-dashboard.png`
- `docs/screenshots/phase1-mock-h1.png`
- `docs/screenshots/phase1-mock-overrun.png`
- `docs/screenshots/phase1-mock-review.png`
- `docs/screenshots/phase1-overrun-1440.png`
- `docs/screenshots/phase1-overrun-390.png`
- `docs/screenshots/phase1-overrun-768.png`
- `docs/screenshots/phase1-overview.png`
- `docs/screenshots/phase1-po-ledger-1440.png`
- `docs/screenshots/phase1-po-ledger-390.png`
- `docs/screenshots/phase1-po-ledger-768.png`
- `docs/screenshots/phase1-po-ledger.png`
- `docs/screenshots/phase1-po-selection-390.png`
- `docs/screenshots/phase1-po-selection-768.png`
- `docs/screenshots/phase1-purchase-orders-1440.png`
- `docs/screenshots/phase1-purchase-orders-390.png`
- `docs/screenshots/phase1-purchase-orders-768.png`
- `docs/screenshots/phase1-queue-1440.png`
- `docs/screenshots/phase1-queue-390.png`
- `docs/screenshots/phase1-queue-768.png`
- `docs/screenshots/phase1-resumed-1440.png`
- `docs/screenshots/phase1-resumed-390.png`
- `docs/screenshots/phase1-resumed-768.png`
- `docs/screenshots/phase1-review-queue.png`
- `docs/screenshots/phase1-scenarios.png`
- `docs/screenshots/phase1-upload-1440.png`
- `docs/screenshots/phase1-upload-390.png`
- `docs/screenshots/phase1-upload-768.png`
- `docs/screenshots/phase1-upload.png`
- `frontend/index.html`
- `frontend/openapi.json`
- `frontend/src/App.tsx`
- `frontend/src/BusinessTimeline.tsx`
- `frontend/src/History.tsx`
- `frontend/src/InvoiceDecision.tsx`
- `frontend/src/Overview.tsx`
- `frontend/src/PDFPreview.tsx`
- `frontend/src/PurchaseOrders.tsx`
- `frontend/src/ReviewForm.tsx`
- `frontend/src/RuleChecklist.tsx`
- `frontend/src/RunView.tsx`
- `frontend/src/Scenarios.tsx`
- `frontend/src/Upload.tsx`
- `frontend/src/api.generated.ts`
- `frontend/src/api.ts`
- `frontend/src/styles.css`
- `frontend/src/ui.tsx`
- `frontend/tests/workflow.spec.ts`
