# PS-1 implementation progress

## Current: DM Sans and before-upload OpenAI instructions (2026-11-17)

Applied the user's DM Sans selection as a pinned, locally bundled variable font, including the extended subset for ₹. Human-facing invoice/PO headings share the interface family; technical audit identifiers retain their existing mono treatment. Added ordered OpenAI connection/key/model instructions before personal-key submission, distinct missing-model/expired guidance, and truthful managed/mock instructions. Updated README, RUNNING.md and the credential guide to match the new navigation and remove the older blanket browser-key prohibition that conflicted with SPEC §3.5's authorized form.

**14 shared/provider/workflow browser cases and 8 role cases passed**, including actual Latin/₹ webfont loading, desktop/mobile setup guidance, submission prerequisites, role isolation and unchanged review/resume. Frontend formatting/TypeScript/build pass; API contract hashes and backend source are unchanged. This follow-up did not rerun the backend suite; the prior 220-test backend result below remains a dated baseline. No live OpenAI call, configuration-secret change, commit, push or deployment. Existing uncommitted redesign work and all user workspaces/records are preserved.

## Current: selected operational UI (2026-11-17, local review)

Implemented the user-selected queue/detail direction within the existing React application: dedicated workspace entry before authentication, server-derived role navigation, My invoices as submitter landing, Review queue as reviewer landing even when empty, a separate OpenAI connection screen, original-PDF expansion, required review rationale and secondary evidence/audit disclosures. The app uses Invoice operations branding and has no assignment footer. Actual invoice/candidate data replaces reference-image examples; mock/replay provenance stays explicit. No backend, API, migration, financial policy, worker ownership or approval behavior changed.

Verification: **220 backend tests passed, 3 opt-in live skips**; full migration roundtrip/parity is included. **14 shared/provider/workflow browser cases plus 8 role cases passed** at desktop/tablet/phone widths. Ruff (93 Python files), generated API hash comparison, frontend formatting/TypeScript/build passed. No live OpenAI calls. See [development details](docs/DEVELOPMENT.md) and [visual QA](design-qa.md). These changes are uncommitted and have not been pushed or deployed; prior public-deployment notes remain historical rather than evidence of this UI being hosted.

## Current: visible upload limits for Vercel (2026-11-14)

The Vercel direct-upload demo now caps PDFs at **4 MiB**, while normal local/API defaults and the database ceiling remain **12 MiB**. Both profiles accept one to five unencrypted PDF pages. The frontend reads active limits from additive fields on GET /openai/config, displays them beside the file picker and rejects oversized selections; API intake enforces the same active boundary. No file-size guess is used when configuration is unavailable. Settings and Vercel startup cap enforcement prevent widening the hosted profile by mistake. No financial/worker/history change or new paid model call.

Focused backend checks: **44 passed**, including exact-size acceptance and one-byte-over rejection for both profiles. Browser checks: **4 role cases plus 14 shared/provider/workflow cases passed**, including visible 4-/12-MiB limits and selection boundaries. Ruff (93 files), generated contracts, formatting, Git whitespace checks and production build pass. [DEPLOYMENT.md](docs/DEPLOYMENT.md) now treats the 4-MiB profile as selected. Next: configure the free external PostgreSQL connection and Vercel secrets, install migrations/checkpoints/policy/reviewed masters, validate hosted behavior, then deliberately activate one daemon within free quota. Public deployment remains unperformed; changes stay uncommitted.

## Current: predeployment verification and free-Vercel preparation (2026-11-14)

The agreed private profile has three fixed submitter identities and one financial reviewer. [PREDEPLOY.md](docs/PREDEPLOY.md) records **17 implemented API operations / 117 role probes**, exact files, manual operating steps and remaining gaps. Final routine backend verification: **216 passed, 3 paid-test skips in 294.48s**; migration roundtrips through 0008, Ruff (92 files), generated API/types, formatting and frontend production build pass. Actual-browser verification: **4 role cases plus 12 existing cases passed**, with clearly mocked extraction, real HTTP/worker/PostgreSQL and third-submitter duplicate isolation.

The user separately authorized one real synthetic BYOK invoice: **gpt-6-luna, one request, COMPLETED/APPROVED, one ledger**, 1130 input / 1312 output tokens, 12094ms provider latency, **USD 0.000797175 dated-rate estimate**; actual billing unknown. No other live invoice was created. The sanitized report is linked from PREDEPLOY.md; previous zero-live-call statements below describe earlier slices.

The selected hosting target is Vercel Hobby. Current Vercel Services/Daemons support preparing a separate persistent worker without replacing PostgreSQL/LangGraph. New ASGI startup guards, service routing, ignored private artifacts and a zero-instance daemon are prepared; the previous paid Render example is explicitly unselected. Local schema validation passes under Draft 7; the upstream schema's older declared meta-draft mismatch is disclosed. Docker and actual provider builds are not verified. **Deployment remains gated** on the Function payload cap vs current 12-MiB PDF contract, a configured session-preserving database, masters provisioning, free quotas and hosted acceptance. Four planned policy/re-evaluation/export operations remain unimplemented. [DEPLOYMENT.md](docs/DEPLOYMENT.md) is the current preparation guide.

No financial defaults, worker fencing, approval writers or migrations were changed. Existing user services/workspaces and earlier uncommitted work are retained; tests clean only their own schemas/processes. No payment, email, remote push, commit or public deployment occurred. Earlier records below retain their original historical measurements and limits.

## Historical role-access slice: individual submitter and reviewer permissions

The requested own-invoices-only contract is implemented in explicit `ACCESS_MODE=roles`. Individual submitter credentials grant Process Invoice/My Invoices and only their own limited invoice/source/status/cost/timeline. Reviewer credentials grant workspace finance/history/review, with no upload or OpenAI key form. Server-derived roles and immutable ownership protect direct API/URL access, search/counts/cursors, documents/events/SSE and encrypted provider sessions. Legacy ownerless history is reviewer-only; no reassignment or financial-policy change occurs. Shared demo compatibility is retained separately and does not isolate people.

Verified: **214 backend tests passed, 2 paid tests skipped**; final targeted role/migration checks **20 passed**. Browser: **3 role cases passed**, including PDF rendering/mobile isolation, plus **all 12 earlier browser regressions passed** separately. Ruff (89 files), migration roundtrip/parity through 0008, generated contracts, formatting, lockfile and production build passed. Screenshots use synthetic, clearly mocked extraction. Zero live model calls, public deployments or remote pushes. The fresh local-roles workspace has two individual submitter tokens and one reviewer token, with no operator key or completed runs. [ROLE_ACCESS.md](docs/ROLE_ACCESS.md) contains exact files and boundaries; RUNNING.md contains startup/credential steps. Public login/hosting remains unfinished; changes are uncommitted.

## Current extension: reviewers supply their own OpenAI key/model

The explicitly authorized reviewer credential flow is implemented behind `OPENAI_CREDENTIAL_MODE=reviewer`. Account-listed supported models are offered after private key submission. Keys are authenticated-encrypted temporarily (24-hour expiry, explicit disconnect revocation), and each run atomically freezes its credential/model for the separate worker. There is no operator-key fallback. Attempt authorization is serialized with disconnect; already-started requests can be billed. Financial rules, owner fencing and approval transactions remain intact. Server-key and labelled mock modes remain separate and compatible.

Final full backend: **198 passed, 2 live skips in 204.85s**, preserving all 180 prior tests. Focused checks: 44 passed, then 33 credential/workflow/recovery/migration cases after the final race fix. Chrome browser: all 12 passed, preserving the ten previous cases. Ruff (86 files), generated contracts, formatting, locked dependency resolution and frontend build passed. See DEVELOPMENT.md and [REVIEWER_KEYS.md](docs/REVIEWER_KEYS.md) for the exact files and limits. No live model calls were made. The fresh local-reviewer workspace has no operator key or completed runs; existing workspaces/processes remain untouched.

This is a private shared-workspace feature, not multi-tenant hosting/auth. Vercel deployment, HTTPS/proxy/upload compatibility, a reviewer-paid account smoke and broader financial document coverage remain unresolved. Changes are uncommitted; nothing was pushed or deployed. [RUNNING.md](docs/RUNNING.md) gives the new startup and credential instructions.

## Current local correction: clear mock-input failures

An unrelated PDF in the user's mock workspace produced a generic worker-exhaustion message despite zero real LLM calls. The demo-only extractor now persists MOCK_FIXTURE_NOT_FOUND before reservation/transport, and an additive authenticated read projection explains this error in run/history/audit with a next action. The exact legacy mock adapter's recorded HTTP 422 is also explained without rewriting history. No claim of resume/non-invoice classification is made; missing invoice information in live mode still requires review.

Financial rules/writers, evidence verifier, worker retry/ownership/checkpoints and reviewer authorization remain unchanged. No private PDF or key was transmitted, no live LLM call was made and the user's running demo/data was not reset. The UI explains mock restrictions before upload. Real extraction remains explicit via a separate --mode live workspace; instructions are in RUNNING.md.

Seven new backend regressions and one browser case cover the corrected boundary. Browser checks use isolated 8100/5273 ports alongside the user's current app. Final results are recorded in DEVELOPMENT.md. Existing uncommitted Phase 1/Slice 6A work remains uncommitted; no push/deployment or automatic advance to Phase 2.

Final results: **180 backend tests passed / 2 opt-in skips**, **10 Edge browser tests passed**; Ruff, migrations/parity/roundtrips, reproducible generated API types and frontend format/build passed. User services/demo/token remain intact; test-owned data/processes cleaned and PostgreSQL left running for the user. Restart the existing API/worker commands to load the new code; no demo reset is needed. Existing failed history gets the precise read-only explanation. No actual LLM call or content classification was made.

## Historical Phase 1 handoff

## Current: Product finalization Phase 1 — uncommitted for review

Only the authorized UI/UX phase was implemented on 2026-11-13. Existing uncommitted Slice 6A work remains intact; no new commit, push, deployment or live OpenAI call. SPEC §§4.1–4.3 remain canonical; financial writers, evidence verifier, worker fencing/checkpoints, approval uniqueness and review authorization are unchanged.

The interface now separates Review Queue, Process Invoice, Invoice History, Purchase Orders and Overview. It provides a warm-neutral visual system, actual recorded rule checklist, human-readable business stages, assessment-time overrun arithmetic, authenticated source-page navigation, explicit reviewer actions/candidates, current PO ledger and a dependency-aware scenario gallery. Search/pagination, unknown-data handling and mock/live/measurement coverage are explicit. Unknown checks never become passed checks; historical held assessments remain distinct from subsequent reviewer decisions.

**Final verification: 173 backend tests passed, 2 opt-in live skips in 265.80s**, preserving all 163 existing routine cases. Ten new read-contract cases cover certificate/unknown states, immutable versus current data, PO auth/drift/read-only behavior, bounded literal search/cursors and metric coverage. **Nine Edge browser cases passed in 2.2 minutes** after the final refinements, including 1440/768/390 workspace, PO selection and ledger detail checks. Ruff/format (79 files), real PostgreSQL migrations/parity/roundtrips, repeated generated API hashes, frontend Prettier/TypeScript/build and Git/exclusion checks passed. Existing PDF.js size and benign Node color-environment warnings remain disclosed. No new live API spending.

Exact incremental manifest: 63 files, including 33 actual browser screenshots. All pre-existing files are retained, HEAD stays 4202e41 and staging is empty. Disposable schemas and runner processes are cleaned; project PostgreSQL 55432 is stopped, separate 5432 service untouched.

Source filenames and reliable evidence geometry are absent from current persistence; filenames are not invented and links navigate verified pages only. Aggregate approval certificates cannot recreate missing individual held-check logs. Phase 2 layout-aware verification, Phase 3 realistic/independent fixtures, Phase 4 evaluator sessions/deployment and Phase 5 README/video remain explicitly deferred. H2 and scanned-identity corroboration are not forced to approve/reject.

Credential exposure from the earlier ZIP requires operator revocation/rotation, not just ignore rules. Exclusions were verified; secrets were not printed/copied and no rotation is claimed. See [SECURITY.md](docs/SECURITY.md). Exact Phase 1 manifest/design/screenshots: [PHASE1.md](docs/PHASE1.md). Current local instructions: [RUNNING.md](docs/RUNNING.md). Stop after Phase 1 with all changes uncommitted.

## Historical Slice 6A handoff

## Slice 6A complete, uncommitted for review — historical handoff

Slice 5 was reviewed against ba58c43, verified with **141 passing routine tests / 2 opt-in skips**, and committed separately as **4202e41**. No push. The initial closure review found no critical defect; a later printed-field omission defect was discovered, corrected and tested in the uncommitted Slice 6A changes. SPEC remains canonical and financial policy defaults are unchanged.

Slice 6A delivers the React/TypeScript invoice workspace: drag/drop upload, persistent run URLs, authenticated original PDF preview, real durable timeline/stage timing, extracted fields/local verification, vendor/PO context, financial reasons, history/filter/keyset pagination and coverage-labelled dashboard metrics. Read-only detail/history/document/summary APIs and bearer-header fetch SSE use persisted sequences with polling fallback. Reviewer actions retain the existing separate credential, offered PO, generation and idempotency boundary. No manual financial approval/override exists; resume still revalidates in the fenced worker and locked financial transaction.

Nullable immutable assessment observations power exact historical overrun reporting without guessing from current masters. Missing usage, billing, legacy balance observations and incomplete timings stay unknown. Duplicate holds are deduplicated, mocked/reused extraction is disclosed, and source snippets/bank fields/checkpoints remain private. The source safety correction now holds recognized printed bank suffix/PO/tax ID/SKU omissions; four new full-workflow regressions prevent bypass through dropped fields.

**Verification: 163 routine tests passed, 2 paid tests skipped by default; all original 141 remain unchanged.** Ruff/format, real PostgreSQL migration upgrade/downgrade/re-upgrade/metadata parity, repeated generated contract hashes, TypeScript/Vite production build, Prettier and Git checks passed. Final focused read/health suite: 11 passed. Six Edge browser tests passed (45.5s), covering actual HTTP upload, independent worker/database, PDF rendering, E2 review/resume, polling/SSE recovery, failures, history and mobile layout. Routine browser extraction is explicitly MOCK_OPENAI; all downstream processing is real.

Demonstrated H1 approval, actual E1 prior allocation then exact INR 5000 overrun hold, E2 offered selection/resume, E3 normalized **text** duplicate rejection and E4 bank mismatch hold. E3's image-only scan conservatively remains in review because local evidence cannot corroborate its identity. No scanned rejection or unexplained H2 rounding approval is claimed.

Explicit live frontend H1 separately passed with configured **gpt-6-luna**. The final source-guard run used 2 bounded Responses attempts (one evidence repair), 2283 input / 2713 output tokens, 22091ms summed provider latency and **USD 0.0015121200 estimated**; actual account billing unknown. Three explicit H1 smokes during this slice totalled four attempts and USD 0.0030413650 estimated. See [sanitized live usage](docs/benchmarks/slice6-live-h1.json). No other live scenarios/payments. Test-owned API/worker/Vite processes and disposable schemas are cleaned after each run.

Final cleanup verified zero remaining demo/test schemas and no active task-demo metadata. The project-only PostgreSQL cluster on 55432 is stopped; the separate 5432 service is untouched. All 58 changed/new files are named in the development manifest; the Slice 6A staging area is empty.

Concrete Docker/Render preparation uses independent always-on API/worker services and persistent direct PostgreSQL, with private credentials/PDFs and an explicit disabled worker gate. Docker is unavailable locally; no image build, hosted deployment, paid provisioning or public exposure was performed. Broad real-layout grounding, scans, >=20 real-document evaluation, full tax profiles, valid H2 justification, hosted identity/backup/retention and proxy/load acceptance remain open. Canvas text search/highlighting is deferred; the lazy PDF.js bundle produces a size warning.

Start/reset and scenario instructions: [RUNNING.md](docs/RUNNING.md). Exact file manifest, implementation reasons and verification details: [DEVELOPMENT.md](docs/DEVELOPMENT.md). Read/metric/safety decisions: [DECISIONS.md](docs/DECISIONS.md). Deployment boundary: [DEPLOYMENT.md](docs/DEPLOYMENT.md). Screenshots are under docs/screenshots. **Slice 6A remains uncommitted; no remote push.** Earlier records below are historical.

## Historical Slice 5 handoff

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
