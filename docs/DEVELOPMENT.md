# Development and verification

## DM Sans and OpenAI setup guidance (2026-11-17 follow-up)

The user selected DM Sans and asked for instructions to connect OpenAI before adding an invoice, with documentation aligned to the new UI. Read the canonical SPEC/AGENTS and current docs first; recorded the decision before code. Preserve the existing uncommitted redesign and user data. This follow-up changes presentation/docs only under SPEC §§3.5/4.3; no backend source, API schema, credential mode/lifetime, migrations, financial rules, worker or secret configuration changed.

- `frontend/package.json` / `package-lock.json`: exact `@fontsource-variable/dm-sans@5.3.0` asset dependency. `frontend/src/main.tsx` imports its normal variable `standard.css`. Both Latin and extended subsets are bundled locally (62.72 / 31.29 kB WOFF2) so ₹ has font coverage, without a browser font-CDN request. Preserve upstream OFL text in `frontend/public/licenses/DM-Sans-OFL.txt`.
- `frontend/src/styles.css` / `workspace.css`: a shared `--font-ui` family, optical sizing and DM Sans for interface and human-facing invoice/PO headings. Preserve technical monospace identifiers, tabular numerals, font sizes, colors and layout.
- `frontend/src/App.tsx`: explicit pre-upload key/model sequence, distinct connected-without-model/expired text and truthful workspace-managed instructions. `OpenAIConnection.tsx` adds a three-step setup guide and connected-state guidance. `Upload.tsx` explains why personal-key submission is disabled; selected-file copy no longer claims readiness before connection/model prerequisites are met. Existing submission/idempotency/session cleanup remains unchanged.
- `frontend/tests/provider.spec.ts`: extend the existing real-browser test to check the three-step guide, missing key/model/ready instructions, disabled submission with a file alone, managed-profile compatibility, actual two-subset webfont loading for `Invoice ₹11,800.00`, computed family, and 1440/390px screenshots without overflow. Existing provider disconnect/late-response/boundary tests remain.
- `README.md`, `docs/RUNNING.md`, `docs/REVIEWER_KEYS.md`: current navigation, key/model-before-PDF tutorial, profile differences, key reuse/expiry and correct account disconnect. Correct the old mock-only “never enter a browser key” wording using SPEC's explicit personal-key form exception; financial reviewers do not need a key. `SPEC.md` records the expressly selected typography/setup clarification; DECISIONS/PROGRESS and visual QA record the result.

Final checks for this follow-up:

| Check | Result |
| --- | --- |
| Mocked shared/provider/workflow browser runner, Chrome, ports 8100/5273 | **14 passed in 2.7m**; 8 role-only cases skipped here and run separately |
| Same runner with `--roles` | **8 passed in 59.3s**, including reviewer resume without an OpenAI key |
| `npm.cmd run format:check` and `npm.cmd run build` | Passed, including TypeScript and both bundled font subsets; existing PDF.js chunk warning remains |
| API hash / backend diff checks | Generated OpenAPI/TypeScript hashes identical to the prior baseline; zero backend source changes |
| Isolated manual Playwright capture | DM Sans family confirmed; queue/document/modal and 768/390 layouts inspected; `consoleErrors: []`, `focusReturned: true` |
| Fresh `npm audit --json` | Zero vulnerabilities in the fresh audit report. Installation initially printed a conflicting four-high summary; no unrelated dependency upgrades or forced audit fixes were applied. |

No full backend/Ruff/migration rerun was needed for this CSS/copy slice; the **prior** 220-pass backend/migration result below is historical, not a newly repeated claim. All routine browser processing uses explicit mocked OpenAI and isolated loopback schemas; no provider charges. The manual local preview gained additional matching fixture rows during work, so its screenshot helper was changed from ambiguous display text to the original known run URL. No user records were reset, removed or approved by that helper. Accepted new DM Sans/setup screenshots are in `docs/screenshots/ui-2026-11-17/dm-sans-*.png`; older images retain their historical typography. Changes remain uncommitted, without push or deployment.

## Selected operational UI (2026-11-17, local review)

Read AGENTS.md, SPEC.md, README.md, DECISIONS.md and this development record before implementation; reviewed the existing frontend/access behavior and the live signed-out screen. Used the explicitly invoked Product Design image-to-code workflow and frontend-design guidance against the user's selected inline queue/detail mockup. The user authorized a fresh isolated Playwright browser after native Computer Use could not verify the URL. The decision and tradeoffs were recorded before code; SPEC §4.3 records only the explicitly requested presentation change. Financial rules, API payloads, database/migrations, owner checks, worker locks/leases and approval transactions are unchanged.

The signed-out app now shows a dedicated workspace-access screen without finance navigation or counts. Server-verified submitters land on My invoices, with Submit invoice and OpenAI connection. Reviewers land on Review queue even when empty, with Invoice history, Purchase orders and Overview. The connection route is checked against the existing server upload capability; no new permission or role picker. Shared mode retains its compatibility tools and separate reviewer credential. Access and provider capabilities remain in tab memory, with existing server expiry/revocation and cleanup of late provider responses.

Review queue uses real `/runs?state=WAITING_REVIEW` records, filters/cursors, selected URL state, refresh and event-driven updates. Desktop displays queue/detail together; tablet/phone select a row and return via Back to review queue or browser navigation. Selection is not authorization. The detail reuses RunView's authenticated document fetch, persisted event stream/poll fallback, generation-aware review response and idempotency. All offered PO candidates remain available, no PO is preselected, rationale is required, submit-pending protection remains, conflicts refresh the record and response messages do not imply approval. The original PDF renders in a bounded scrollable preview and a larger native modal with explicit initial focus, Escape close and restored focus. Known single-page PDFs omit disabled paging; multi-page paging remains. Technical/check/evidence detail is secondary. All displayed counts, values, reasons and receipt ages derive from API records; absent fields remain unknown.

Changed source files and purpose (all paths below are relative to the repository):

| Files | Purpose |
| --- | --- |
| `frontend/src/App.tsx` | Entry gate, server-derived role navigation/defaults, OpenAI setup route/prerequisites and account disconnect; remove assignment chrome/footer |
| `frontend/src/ReviewQueue.tsx` (new) | Actual-data queue, URL selection/search/cursors, responsive list/detail and loading/empty/error states |
| `frontend/src/ReviewDetail.tsx` (new) | Compact invoice/outcome/document/PO/review composition using existing run/review DTOs |
| `frontend/src/DocumentPanel.tsx` (new) | Private PDF preview and accessible expansion, without another document endpoint |
| `frontend/src/RunView.tsx` | Optional embedded presentation reusing existing fetching/events/refresh/review behavior; secondary extracted disclosure |
| `frontend/src/ReviewForm.tsx` | Compact offered-candidate/action/rationale layout, explicit disabled reasons and revalidation copy; existing request fingerprint/idempotency guard preserved |
| `frontend/src/PDFPreview.tsx` | Omit redundant controls only when the document is known to have one page |
| `frontend/src/Upload.tsx`, `OpenAIConnection.tsx` | Submit-invoice copy, setup guidance, secondary security explanation, provider double-submit guard; existing upload/session cleanup unchanged |
| `frontend/src/History.tsx`, `Overview.tsx`, `PurchaseOrders.tsx`, `SubmitterRunView.tsx` | Consistent sentence-case headings, simpler chrome and distinct empty-history copy |
| `frontend/src/workspace.css` (new), `main.tsx` | Focused workspace styling using the established neutral/olive tokens, compact type, responsive shell/cards/forms/dialog; existing component styles reused |
| `frontend/src/ui.tsx`, `frontend/package.json`, `package-lock.json`, `frontend/public/favicon.svg` (new) | Replace handwritten icons with one exact UI-only dependency, `@phosphor-icons/react@2.1.10`; favicon exported from its Invoice icon |
| `frontend/index.html` | Invoice operations title, description and favicon |
| `frontend/tests/provider.spec.ts`, `roles.spec.ts`, `workflow.spec.ts` | Preserve existing semantic regressions with new navigation/copy; add four role-entry/navigation cases and expand reviewer PDF/mobile/pending-submit checks |
| `.gitignore` | Ignore browser intermediates in `output/playwright/` and `.playwright-cli/`; existing secret/environment/PDF ignores retained |
| `README.md`, `SPEC.md`, `docs/DECISIONS.md`, `docs/ROLE_ACCESS.md`, `docs/RUNNING.md`, `PROGRESS.md`, this file | Agreed presentation contract, exact local tutorial, decisions, results and limits; no claim that the new UI is deployed |
| `design-qa.md` (new), `docs/screenshots/ui-2026-11-17/` (8 PNGs) | Source comparison, findings/fixes, screenshots of actual synthetic/mock runtime and explicit verification boundaries |

Verification commands and final results:

| Check | Result |
| --- | --- |
| Backend `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=../.local/pytest-ui`, explicit loopback TEST_DATABASE_URL | **220 passed, 3 opt-in live skips, 304.86s**; includes all migration upgrade/metadata-parity/downgrade/re-upgrade, finance, queue, concurrency, ownership and rollback regressions |
| `.venv/Scripts/ruff.exe check .` / `format --check .` | Passed; 93 Python files formatted |
| `PS1_BROWSER_CHANNEL=chrome python -m scripts.browser_checks --api-port 8100 --ui-port 5273` | **14 passed in 2.9m**, 8 role-only cases skipped here and run separately |
| Same runner with `--roles` | **8 passed in 1.4m**, including the three existing submitters, reviewer resume, entry gate, defaults, denial, empty/error/no-results, mobile/back/selected URLs, modal focus and pending-response guard |
| `python -m scripts.export_openapi` / `npm run generate:api` | Passed; SHA-256 of both OpenAPI and generated TypeScript identical before/after |
| `npm run format:check` / `npm run build` | Passed, including TypeScript; final centering-only CSS adjustment rebuilt successfully |
| Isolated CLI browser capture | Original reference width 1487, desktop 1440, tablet 768, phone 390; actual rendered PDF inspected, no document overflow, `consoleErrors: []`, focus restored after Escape |
| Git / configured-secret checks | Whitespace check passed; no staged files; 219 tracked/unignored files scanned with zero configured non-example credential matches. The initial match was the already-public loopback development URL in `.env.example`, classified explicitly without printing values. |

Test setup used fresh marked loopback PostgreSQL schemas and mocked extraction only. Browser runners reset only their own schemas/processes and retain private inactive local files. Existing user services, workspaces and hosted data were not reset. The same existing project PostgreSQL cluster on 55432 was started without initialization; 5432 was untouched. The retained visual preview uses its own isolated mock API/worker/UI on 8110/5280, with configuration under ignored `.local/ui-preview.json` and its generated demo folder. It contains no live OpenAI key. Do not use its synthetic masters/credentials as production configuration.

Failures investigated and corrected: Windows sandbox blocked Vite config traversal, so build/browser commands were rerun with the required filesystem access. A formatting save triggered hot reload during the first reviewer test and cleared tab-only authentication; stable reruns passed. The next modal test exposed initial-focus behavior and was fixed explicitly; the later dependent empty-queue assertion then passed. The old post-refresh signed-out assertion was updated to the new entry-screen contract without removing its retained-run-URL check. One formatting command used the wrong working directory and was rerun correctly. No failing financial test, disabled assertion or hidden retry was used to reach the final results.

Warnings/limits: pytest emitted one existing Windows cache-directory ACL warning; tests themselves passed. Vite retains its existing >500-kB PDF.js chunk warning; browser output retains the benign Node NO_COLOR/FORCE_COLOR warning. Broader real-layout/multi-page visual evaluation, exact font/pixel matching and hosted browser tests are not claimed. Original highlighting, policy editor, re-evaluation/export gaps, commercial-layout/scanned evidence limits and hosted worker/master-data activation remain outside this UI slice. No live provider call, production worker activation, remote mutation, commit, push or deployment occurred. Changes are left uncommitted for review.

## Active PDF-size note and Vercel upload profile (2026-11-14)

The user reaffirmed Vercel and requested a frontend note stating allowed PDF size and next deployment steps. SPEC was read fully; §§3.5 and 4.3 and the explicit deployment-profile clarification govern this small slice. DECISIONS.md records the safe 4-MiB Vercel profile before code. Normal local/other API instances retain their 12-MiB default and database ceiling; both use one-to-five-page unencrypted PDFs.

Changes: Settings validates max_pdf_bytes within the existing database ceiling; Vercel's ASGI adapter caps it at 4 MiB (or preserves a lower configured value). API intake reads only active-limit-plus-one and returns a 413 naming that limit before provider use. Existing GET /openai/config adds non-secret max_pdf_bytes/max_pdf_pages; there is no new endpoint. App/Upload use these authoritative values for a visible accessible note, picker help, selection validation and disabled upload while configuration is unavailable. The note and backend boundary agree. Generated OpenAPI/TypeScript are regenerated, not manually edited. .env.example explains the optional local override. SPEC/README/deployment/predeployment/progress records reflect the chosen profile. No financial policy, database migration/history, worker lock/lease, graph or approval writer changes; no existing credentials/workspace settings are replaced.

Focused real-PostgreSQL validation: **44 passed in 77.69s**, covering exact 4-/12-MiB acceptance, one-byte-over rejection with no run inserted, invalid configuration bounds, the Vercel profile guard, existing intake/config/health/migration checks, and reviewer-key regressions. Ruff/format pass (93 Python files). OpenAPI/type generation, Prettier, TypeScript and production build pass (47 modules; existing lazy PDF.js size warning). Initial Prettier warnings in the new browser cases were fixed before the final checks. Browser verification: **4 role cases passed in 24.0s**, then **14 shared/provider/workflow cases passed in 2.2m**, including both displayed-limit/selection boundaries; the four role cases are intentionally skipped in the shared-profile run and were verified separately. These checks use explicit mocked extraction, real HTTP/separate worker/PostgreSQL, and preserve the existing documentation screenshots. Git whitespace checks pass using the repository's normal Windows line-ending configuration; a diagnostic override disabling autocrlf produced CRLF false positives and was discarded without rewriting files. Cleanup confirms zero remaining isolated test schemas or active disposable browser workspaces. No new live model call, deployment, commit or push is part of this slice; the prior 216-test full-suite and live-smoke results below remain historical.

## Predeployment API, roles and Vercel preparation (2026-11-14)

Read the canonical SPEC fully and reviewed current README, decisions, development notes, APIs, worker/provider boundaries and deployment files before changes. The user requested full submitter/financial-reviewer verification, explicitly authorized one real synthetic invoice, and selected free Vercel hosting rather than paid Render. [PREDEPLOY.md](PREDEPLOY.md) contains the exact file manifest, 17-operation/117-probe role matrix, manual testing guide and observed results; [DEPLOYMENT.md](DEPLOYMENT.md) records the current target and remaining gates.

New endpoint integration tests combine three static owners, encrypted per-owner model sessions, real PDF intake/queue/graph/evidence/financial services with explicit MOCK_OPENAI transport, all review actions, duplicate/cross-owner denial, event order and key-disconnected financial resume. They assert coverage against generated OpenAPI. A separately gated live test uses the actual configured key only after opt-in. The Vercel entrypoint rejects shared/server-key/incorrect-slot/operator-key configuration; its daemon starts with zero instances and retains the existing worker activation gate. The old Render file is labelled unselected. No financial default, migration, provider/worker writer, ownership fence or approval transaction changes. All earlier uncommitted work and user workspaces/processes are preserved.

Final routine verification: **216 passed, 3 opt-in skips in 294.48s** on isolated PostgreSQL, including full migration upgrade/metadata parity/downgrade/re-upgrade through 0008. Initial pre-guard full run was 215 passed/3 skips in 278.03s; focused final matrix/entrypoint guards passed 2 tests in 12.73s. All **4 role browser cases passed in 26.2s** and all **12 shared/key-model browser cases passed in 1.8m**, using actual API/separate worker/database and mocked extraction. The new role case covers the third static submitter and a globally rejected duplicate. Ruff/format pass (92 Python files), generated API/types and frontend format/TypeScript/build pass (47 modules). The existing lazy PDF.js size warning and benign browser Node color warning remain.

Authorized live result: **one synthetic H1 invoice, one actual gpt-6-luna Responses attempt, COMPLETED/APPROVED and one ledger entry**; 1130 input/1312 output tokens, 0 cached/1127 cache-write, 12094ms provider latency. The dated 2026-11-12 rate estimate is **USD 0.000797175**; actual billed cost remains unknown. The live test passed in 20.73s and checked finance read plus foreign-submitter denial. It used in-process ASGI/worker services with real provider HTTP and isolated PostgreSQL, not a hosted/live-browser claim. Temporary credentials were revoked; the isolated schemas were removed. The public sanitized report contains no keys, PDFs or run IDs. No other live invoice was processed in this audit.

Failures/findings: an initial model-discovery call returned sanitized 503 before intake; a subsequent non-billable model-list request returned 200 and confirmed the configured model, then the single authorized invoice succeeded. Initial new-test Ruff line-length findings were formatted without rule changes. The public Vercel schema declares Draft 4 but includes newer exclusiveMinimum syntax, failing its own declared meta-validation; strict Draft-7 meta/manifest validation passed and rejected a negative instance count. Temporary schema tools are confined to ignored .local, without dependency/lockfile changes. The first paid-test invocation had Windows pytest-cache ACL warnings; final tests disable only pytest's cache provider, not any tests.

The earlier blanket claim that Vercel cannot run this worker was corrected after current primary docs showed Hobby Daemons. Free quota is bounded and actual provider/container/database execution is unverified; Docker is unavailable locally. The active 12-MiB upload contract still conflicts with the Function 4.5-MB request cap pending the user's explicit upload/storage decision. External PostgreSQL, masters provisioning, quota and hosted acceptance remain open. Four planned SPEC endpoints remain 404 and are explicitly documented, not invented. No public deployment, resource provisioning, payment, email, commit or push occurred.

Final environment checks: the local project PostgreSQL cluster was found stopped during cleanup; its filtered lifecycle log showed interruption. Restarting that same cluster completed ordinary recovery, without reinitialization or data reset. A post-recovery health/migration/endpoint subset passed **6 tests in 22.06s**; subsequent cleanup confirmed zero test schemas and zero active browser-test workspaces. Port 55432 remains running and the separate 5432 service is untouched. The offline lock check passed with 71 packages after correcting a shell cache-path lookup; generated OpenAPI/TypeScript hashes reproduce and a 16-file scan found no literal configured secrets. Git whitespace/staging/ignore checks pass, with no staged changes.

## Fixed case-study tokens (2026-11-14)

The user selected two or three static submitter tokens and one financial reviewer, with stronger authentication proposed in README. The decision was recorded before changes in DECISIONS.md and narrowly clarified in SPEC §4.1. Use three fixed, individually assigned submitter identities and one reviewer; a token is generated once per workspace and retained across restarts. This is not a public/shared submitter token, new signup flow or global account limit.

Changed files: `backend/scripts/demo.py` generates `submitter-b` and `submitter-c` alongside the existing default submitter/reviewer for new role-mode demos. `backend/tests/test_role_access.py` now authenticates three submitters and verifies distinct intake/idempotency, owned histories and cross-owner denial after API recreation. `backend/.env.example`, README.md, SPEC.md, DECISIONS.md, RUNNING.md, ROLE_ACCESS.md and this record document the fixed profile, issuance, limitations and proposed future individual sign-in/session management. README clearly labels stronger authentication as unimplemented. No frontend, API schema, migration, financial rule, worker or OpenAI credential-lifetime change.

The ignored local-roles/backend.env received only the missing `submitter-c` mapping. All pre-existing credentials/mappings and every other setting were compared and preserved; no history was reset and no token was printed. Restart the existing local-roles API/worker to load the additional credential. Older local/shared/live workspaces remain unchanged. Hosted credentials are still private configuration; no remote deployment or public distribution occurred.

Verification: `.venv/Scripts/python.exe -m pytest tests/test_role_access.py tests/test_demo_safety.py tests/test_reviewer_credentials.py -q --tb=short` passed **45 tests in 64.66s** on isolated PostgreSQL schemas. Ruff check/format passed (89 Python files). A separately created disposable reviewer-key role demo proved all four credentials unique, three submitter roles plus one reviewer, two app recreations with unchanged stored credentials, and no operator OpenAI key; only that demo's marked schemas were reset afterward. Git whitespace/ignored-secret checks pass. No check failed. Full backend/frontend suites were not repeated for this provisioning/docs slice; prior results below are historical. No live OpenAI calls, payment, email, commit, push or deployment occurred.

## Submitter key notes and slogan removal (2026-11-14)

Read AGENTS.md, SPEC.md, README.md, DECISIONS.md and this development record before changes. The user requested removal of slogan-style UI labels and an explanation of individual keys after deployment. SPEC §§3.5, 4.1 and 4.3 govern this copy/documentation slice; no API, credential lifetime, financial policy, worker, migration or generated contract changes.

`frontend/src/App.tsx` removes the sidebar slogan and clarifies the access-token prompt. `OpenAIConnection.tsx` explains each submitter's own account/billing, multiple uploads per connection, reconnection after refresh/new tab/disconnect/expiry, and the absence of an OpenAI-key requirement for financial review. Existing encryption, disconnect, billing and model-support disclosures remain. `Upload.tsx` replaces promotional copy with a factual processing explanation and removes the decorative privacy badge and duplicate scenario shortcut; shared-mode scenario navigation remains in the sidebar. `styles.css` removes the deleted sidebar block's rules. `docs/DECISIONS.md`, `ROLE_ACCESS.md`, `RUNNING.md` and this record explain the existing contract and deployed credential issuance. The two role screenshots are refreshed using synthetic mocked extraction; older screenshot artifacts are retained unchanged.

ROLE_ACCESS.md distinguishes operator-issued individual app tokens, submitter-created OpenAI keys and the server-only encryption secret. It includes a private token-generation command, stable actor-ID mapping, server configuration, persistent API/worker/database flow and the pending public-signup/hosting boundary. Reconnection can use the same still-valid OpenAI key; the 24-hour lifetime belongs to the app connection. No credential is generated/exposed by this documentation work and no external provider is called.

Verification: **3 role browser cases passed in 17.7s**, and the final shared-mode run passed **all 12 existing browser cases in 1.6m**, including key/model setup/disconnect, authentication failures, review/resume, financial scenarios and desktop/tablet/mobile layout. Role cases are intentionally skipped in that shared run and verified separately. TypeScript/Vite production build passes (47 modules; existing PDF.js size warning), as do Prettier and Git whitespace checks. No backend source changed, so pytest/Ruff/migrations/generated contracts were not rerun for this presentation-only change; the prior 214-pass record below remains historical.

The initial sandboxed Vite build/runner could not read ancestor directories; the runner removed its owned schema/processes, and execution with normal Windows filesystem access resolved that restriction. The first shared-mode run passed six cases, including both key/model tests, then missed the invalid-token alert; its recorded page was disconnected and showed no /access API call. The next run passed that authentication check but stopped during layout checks with Chrome's `net::ERR_NETWORK_IO_SUSPENDED` and a 26-minute elapsed interval. The final complete run passed with a temporary test-process system keep-awake request, cleared in finally without changing saved power settings. No source/test assertion or financial/auth rule was changed to obtain a pass. Test-owned schemas/processes were cleaned and older screenshot artifacts restored; user services/workspaces remain intact. No paid provider call, deployment, commit or push occurred.

## Individual submitter and financial-reviewer access (2026-11-14)

The user requested role-appropriate visibility and explicitly selected submitters seeing only invoices they personally submitted. The contract was recorded in DECISIONS.md before code and SPEC §4.1. [ROLE_ACCESS.md](ROLE_ACCESS.md) gives the exact incremental file manifest and permission matrix; RUNNING.md documents the fresh local-roles workspace and credentials.

Opt-in `ACCESS_MODE=roles` authenticates individual operator-issued submitter tokens and one financial-reviewer token. Submitters receive Process Invoice/My Invoices and an own-invoice status/source/usage view; review queue/actions/candidates, PO ledger/register, company dashboard and internal audit screens are unavailable. Reviewers see finance/review/history, sign in once, and do not get upload or OpenAI setup. The API derives role/owner; URLs, forms or local UI changes do not grant access. Legacy shared mode remains explicit compatibility and does not isolate people.

Migration 0008 adds nullable immutable run/provider owner IDs and owner/history indexing, plus provider/run-owner consistency. New intake ownership is principal-derived and idempotency is person-scoped. History/search/counts/cursors, PDFs, run detail, events and SSE enforce owner scope; foreign and missing resources both return 404. Finance endpoints return 403 to submitters. A separate submitter detail DTO omits PO balances/ledger/candidates and finance audit data; review-required explanations direct submitters to finance. Old ownerless history is reviewer-only in role mode and is not guessed or rewritten. Provider setup/use/revocation also requires the originating submitter. Financial policy, company-wide duplicate identity, worker fencing and atomic approval allocation remain unchanged.

Verification: **214 passed, 2 paid-live skips in 227.08s**, preserving all 198 prior backend cases and adding 16 role tests. Initial role/BYOK/migration checks: **38 passed in 57.28s**. Final role-projection/migration checks: **20 passed in 23.79s**. Migrations roundtrip through 0008 with metadata parity. Browser: **3 role cases passed in 18.6s** (including actual PDF rendering and a 390px submitter overflow check), and **all 12 previous browser cases passed in 1.7m** in separate shared-mode verification. The three role cases are intentionally skipped in shared-mode runs and verified separately with `--roles`. Ruff/format checks pass (89 Python files), OpenAPI/generated TypeScript and production frontend build pass; the existing PDF.js chunk warning remains. Locked dependency resolution passes offline (71 packages).

Early browser assertions were corrected after inspecting actual accessible names: `Needs review` casing and the `Review Queue 1` badge. Screenshots initially captured PDF rendering before completion; final cases wait for rendered PDF data, blur/scroll to top, and capture the synthetic labelled-mock views. No financial or authorization rule was relaxed. Source/schema generation completed before final browser runs; no Vite reload was introduced during those runs. No live OpenAI call was made.

Fresh local-roles is provisioned with zero runs, synthetic zero-allocation masters, two distinct submitter credentials, one reviewer credential and no operator OpenAI key. Existing workspaces/processes are retained. Individual tokens implement identity for this private slice; public signup/cookie sessions, hosting/proxy/upload limits, provider-paid smoke tests and broad invoice/scanned grounding remain separate work. Changes are uncommitted; no push/deployment, payment or email occurred.

## Reviewer-supplied OpenAI keys and models (2026-11-14)

The user explicitly requested a reviewer-entered key/model flow and selected encrypted temporary storage (24-hour expiry or explicit disconnect). The contract was recorded in DECISIONS.md before code and extended in SPEC §3.5. The implementation and exact incremental file manifest are in [REVIEWER_KEYS.md](REVIEWER_KEYS.md); operating steps are in [RUNNING.md](RUNNING.md).

Migration 0007 adds authenticated-encrypted provider sessions, hashed opaque capabilities, expiry/revocation constraints and immutable run/session/model bindings. The API discovers account-listed models from the application's tested allowlist without a paid probe. Intake binds that selection atomically/idempotently to the stored PDF and durable queue. The separately enabled worker uses each run's own credential, checks expiry/revocation before every attempt, and never falls back to the operator's key. A session-row shared lock serializes attempt authorization with disconnect in the existing short owner-fenced reservation transaction. Once reserved, that attempt has started and can be billed; no transaction remains open during the provider call. Existing financial locks, policy, review authorization and two-attempt budget remain unchanged.

Fernet ciphertext includes the session identity to detect row substitution. Request-validation errors omit submitted input; connection responses use no-store. UI plaintext is cleared after connection attempts, opaque sessions remain in tab memory, model selection is explicit, workspace Disconnect revokes the provider session first, and late setup responses are revoked. Active ciphertext is erased on disconnect and purged on expiry/access/worker cleanup. Backup retention and downtime-delayed physical cleanup are disclosed in SECURITY.md. This is one private shared finance workspace, not public multi-tenant identity or data isolation.

Final verification: full backend **198 passed, 2 opt-in live skips in 204.85s**, preserving all 180 prior tests and adding 18 credential cases, including the disconnect-versus-attempt race. Initial full run before that final refinement: 197 passed/2 skips. Focused input-redaction/expiry/intake/migration subset: **44 passed in 65.38s**; final credential/workflow/review/recovery/migration subset: **33 passed in 89.54s**. **12 Chrome browser cases passed in 1.7 minutes**, including both new UI-only key/model/disconnect tests and all ten original browser regressions. Ruff and formatting passed (86 Python files); OpenAPI export/generated TypeScript and frontend production build passed. The existing lazy PDF.js chunk-size warning remains. Locked dependency resolution passed offline (71 packages). The guarded local-reviewer migration command passed without deleting data; secrets remain Git-ignored and nothing is staged.

The first browser attempt was interrupted by Vite's logged OpenAPI JSON reload during schema regeneration, clearing tab-memory auth. It was rerun after generation completed; no financial rule was relaxed and every browser case passed. Early Ruff line-length/style findings were formatted/fixed. The earlier deliberately skipped live tests were not activated. All provider responses in this slice were mocked, including actual subprocess crash/restart tests; zero live OpenAI requests or actual reviewer keys were used. A paid BYOK account smoke and hosted deployment are not claimed.

A fresh `local-reviewer` workspace is provisioned on the existing loopback PostgreSQL cluster, with 0007/checkpoints, synthetic zero-allocation masters, fresh application/reviewer credentials and an encryption secret, **no operator OpenAI key and zero runs**. Existing local/mock/live workspaces and user-owned API/worker processes were not reset or stopped. Ordinary production processing still requires explicit opt-in. Reviewer-mode cost estimates remain unknown rather than using the wrong model's rates. Hosted Vercel/TLS/upload-size compatibility, public identity/rate limits, broad PDF layouts/scans and payment-ready export remain separate unfinished gates. Work stays uncommitted; no push or deployment.

## Current local correction: unsupported mock uploads (2026-11-13)

The user's unrelated PDF was accepted as a valid PDF container but could not match the mock demo's registered fixture hashes. The existing adapter emitted mock HTTP 422, eventually leaving FAILED/null decision and WORKER_ATTEMPTS_EXHAUSTED. This obscured the cause. Read the canonical SPEC fully before this correction; §§3.6 and 4.3 govern transparent mock/live mode and readable failure explanations. No document classifier, model call, evidence relaxation or financial change was added.

Changes:

- `backend/scripts/demo.py`: private FixtureExtractor rejects unknown hashes with fixed MOCK_FIXTURE_NOT_FOUND before attempt reservation or transport. Registered fixture behavior remains unchanged. Existing graph code persists this cause through its ownership-fenced error handler; existing bounded worker retry limits are unchanged.
- `backend/app/product_reads.py`, `read_contracts.py`, `read_service.py`: additive processing_failure object with safe code/message/next action/provenance on detail/history. Only failed MOCK_OPENAI runs qualify. The exact legacy fixture-extraction adapter's recorded HTTP-422 errors can explain older failures without updating run/event/usage history. Live errors, other model IDs and mixed error histories are not reclassified as fixture failures.
- `frontend/src/InvoiceDecision.tsx`, `History.tsx`, `RunView.tsx`, `Upload.tsx`, `styles.css`: show the actual failure prominently, retain the technical worker outcome in audit metadata and explain the mock upload restriction before intake. No financial decision or content classification is invented.
- `frontend/openapi.json`, `src/api.generated.ts`: regenerated optional typed failure projection, reproducible without manual edits.
- `backend/tests/test_mock_input_failure.py`: seven new tests for no transport/reservation on unknown mock input, registered fixture compatibility, actual worker persistence/no ledger, privacy/read-only projections and precise legacy/live/error distinctions. The test PDF is synthetic; the user's personal document was not read or transmitted.
- `frontend/tests/workflow.spec.ts`: new tenth browser case uploads a valid but unregistered synthetic PDF variant and verifies failure/cause in run/history, zero recorded/reserved model attempts, no decision and no passed checks. `docs/screenshots/mock-unsupported-pdf.png` records that actual isolated result; the existing synthetic Phase 1 captures are refreshed by regression tests.
- `backend/scripts/browser_checks.py`, `frontend/vite.config.ts`, `frontend/playwright.config.ts`: optional loopback-only test API/UI ports and a busy-port check, needed to avoid stopping the user's current services on 8000/5173. Defaults remain unchanged; test runs use 8100/5273.
- `docs/DECISIONS.md`, `docs/RUNNING.md`, this file and PROGRESS.md: record the cause, bounded compatible correction, live opt-in instructions and verification. No .env, financial writer, worker/ownership/checkpoint/evidence source, prior migration, README or SPEC change.

Verified the user's existing failed run using an in-process authenticated app read: it returns the legacy fixture-mismatch explanation while preserving FAILED/null decision and the original event count. No personal PDF content or credential was printed. The user-owned API/worker are not automatically restarted or reset; apply the new code by restarting their existing commands, as documented in RUNNING.md. The database remains running for the user's app.

Verification results follow after the final test run. Initial focused suite: **14 passed in 17.47s** (seven new mock-error cases plus seven read regressions). OpenAPI/type hashes reproduce, TypeScript/production build and final formatting pass; the existing large lazy PDF.js chunk warning remains. One format check initially required formatting the newly appended browser test. The first browser run was invalidated by that formatter triggering a Vite page reload and clearing its in-memory login after H1; the dev log confirms the reload. Formatting completed before the next isolated run. No test was removed or financial safeguard relaxed.

Final verification: **180 passed / 2 opt-in live skips in 227.03s**, preserving all 173 prior routine cases; Ruff check/format passed (80 files). Full migration/parity/downgrade/re-upgrade tests passed in that PostgreSQL suite. **10 browser tests passed in 2.0 minutes** on 8100/5273, including the unsupported synthetic PDF with zero model reservations/requests and null decision. Generated OpenAPI/type hashes reproduce; frontend format, TypeScript and production build pass (45 modules). The lazy PDF.js >500KB warning and benign Node color-environment warning remain. Git whitespace/staging checks pass; no commit/push. User-owned API/frontend remain healthy on 8000/5173 and accept the existing generated token; their active demo is preserved. All test-owned schemas/processes were cleaned; PostgreSQL is intentionally left running for the user's app. No real model call or personal PDF upload was made by this correction. Changes remain uncommitted.

## Historical Phase 1 handoff

## Current: Product finalization Phase 1 — UI/UX redesign (2026-11-13)

Only Phase 1 of the supplied roadmap is implemented. Read AGENTS.md, SPEC.md, README.md, PROGRESS.md, DECISIONS.md, this file, RUNNING.md and DEPLOYMENT.md completely before changes. SPEC §§4.1–4.3 remain canonical. Reviewed the uncommitted Slice 6A boundary and recorded hashes of its 58 files privately before edits. Those changes remain uncommitted and were not discarded or committed. Baseline HEAD remains 4202e41; no push/deployment.

The previous UI combined overview/history, prioritized raw field/finding/event output over financial context, and lacked an operational queue, rule checklist and PO ledger. Phase 1 adds a review-first navigation, restrained warm-neutral design system, auditable results and balance arithmetic, business-stage timeline, page-level document navigation, real PO inspection and clearer permitted review actions. [PHASE1.md](PHASE1.md) contains the full product explanation, design tradeoffs, **exact incremental file manifest**, screenshots and deferred requirements. [RUNNING.md](RUNNING.md) contains current local instructions.

### Source changes and their purposes

| Files | Purpose |
|---|---|
| `backend/app/product_reads.py` | Read-only checklist certificates/business explanations, bounded searchable PO directory and immutable PO ledger projection; no call to the evaluator or financial writes |
| `backend/app/read_contracts.py` | Additive typed checklist/finding provenance, PO/ledger models, current reason/cost/update metadata and explicit straight-through/fixture coverage |
| `backend/app/read_service.py` | Wire checklist to latest immutable assessment and same-run ledger; query-bound literal history search; retain current decision-event codes separately from old assessment findings; calculate documented run-level straight-through metrics |
| `backend/app/read_routes.py` | Authenticated read-only PO list/detail and bounded search parameter; repeatable-read/read-only detail transaction |
| `backend/tests/test_product_reads.py` | Ten new cases: unknown/no-ledger checks never pass, historical hold/rejection provenance, PO auth/read-only/drift/history, literal search/bounded pagination, query-bound cursor, metric coverage/resolved review and empty denominator |
| `frontend/src/App.tsx`, `frontend/src/ui.tsx`, `frontend/index.html` | Five functional navigation views, review-first landing, current queue badge, skip link/active-page semantics, corrected terminology and product title |
| `frontend/src/styles.css` | Central warm-neutral/semantic tokens, compact right-aligned financial tables, readable headings, focus states and stacked tablet/mobile workspace |
| `frontend/src/History.tsx`, `frontend/src/Overview.tsx` | Separate review queue/history/overview, server search/filter/cursors, next actions, source-mode labels and denominator/measurement disclosures |
| `frontend/src/InvoiceDecision.tsx`, `frontend/src/RuleChecklist.tsx` | Outcome/explanation hierarchy, stored E1 arithmetic, actual ledger links, explicit recorded check status and expandable rule/revision/provenance; neutral labels for unknown checks |
| `frontend/src/BusinessTimeline.tsx`, `frontend/src/RunView.tsx` | Collapse actual node intervals into business stages, preserve SSE/polling and complete technical audit disclosure, prioritize document/financial context and source-page links |
| `frontend/src/ReviewForm.tsx` | Exception-specific context, selected offered candidate, rationale and separate reviewer authorization; existing closed action/generation/idempotency flow preserved |
| `frontend/src/PDFPreview.tsx` | Navigate only locally verified source pages; no boxes/highlights invented; render original PDF responsively |
| `frontend/src/PurchaseOrders.tsx` | Read-only searchable directory and current-versus-historical ledger detail, reconciliation warning and actual approved-invoice links |
| `frontend/src/Scenarios.tsx`, `frontend/src/Upload.tsx` | Clear Process Invoice path and explanatory existing-fixture gallery with dependency warnings, unavailable one-click/private download actions and unavailable H2 |
| `frontend/src/api.ts`, `frontend/openapi.json`, `frontend/src/api.generated.ts` | Add generated read types and consistent en-IN decimal-string formatting; generated files regenerated only |
| `frontend/tests/workflow.spec.ts` | Preserve original six workflow scenarios and add queue/ledger/gallery, 1440/768/390 layout matrix, keyboard/focus/labels/contrast and loading/read-error coverage; real screenshots with explicit mock disclosure |
| `docs/DECISIONS.md`, `docs/DEVELOPMENT.md`, `docs/RUNNING.md`, `PROGRESS.md`, `docs/PHASE1.md`, `docs/SECURITY.md` | Contract proposals before code, implementation/result record, exact file list, current run instructions, scope limits and operator credential-rotation responsibilities |
| `docs/screenshots/phase1-*.png` | Actual synthetic browser captures, including clean/held/resumed runs, PO selection, queue, history, overview, register/ledger and upload at tested viewports; exact names listed in PHASE1.md |

Financial rule/defaults, approval/finalizer/ownership/worker/checkpoint/review writers, source verifier and previous migrations are unchanged in Phase 1. Hash checks also prove the nine pre-existing uncommitted financial/workflow/intake/config source files remain byte-for-byte unchanged. No new migration, provider dependency, AI integration or frontend credential persistence was introduced. README rewrite is explicitly deferred to Phase 5.

### Read contract and measurement boundaries

An explicit immutable VALIDATED assessment backed by its same-run approval ledger certifies the existing mandatory approval checks. This is positive recorded authorization, not the absence of a finding; it does not pretend individual execution logs exist. Missing ledger/unknown certificate/no assessment cannot pass. Held assessments short-circuit, so unrecorded other checks remain not evaluated. Each check carries its own finding code and revision: a reviewer rejection changes the current decision reason while the earlier cap hold remains immutable. Rules are never rerun against today's master data to manufacture historical check results.

PO detail reads a consistent read-only snapshot, exposes current authorized/committed/remaining values separately from ledger allocations and invoice assessment-time observations, and returns null available balance if counters disagree with ledger sums. No amendment/posting API exists. First 100 chronological allocations are displayed with an exact total/truncation flag; there is no guessed historical running balance.

Straight-through rate = approved workflow runs without any recorded review request / workflow runs with a final approved/rejected decision or current WAITING_REVIEW. The denominator excludes unstarted, failed/stopped and unknown workflow coverage; a resolved-review approval stays outside the numerator. Report both counts, mock/live/replay coverage and null for an empty denominator. This is not an independently deduplicated invoice or labor-savings measure. Existing overrun/cost/time definitions remain intact.

Intake does not store original filenames. Before extraction show the actual run reference. A later nullable safe per-intake filename column/API contract is needed; source metadata and SHA hashes are not filenames. Evidence has verified pages but no reliable boxes, so source links navigate pages only. Realistic invoice layouts, geometric grounding, independent scenario resets, cookie sessions and deployment belong to later phases and were not implemented.

### Phase 1 verification record

| Final command/check | Observed result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q` with TEST_DATABASE_URL on isolated PostgreSQL 17 schemas | **173 passed, 2 opt-in live skips in 265.80s**; all original 163 routine cases preserved plus 10 new read-contract cases |
| `pytest tests/test_product_reads.py -q` | **10 passed in 23.28s**, including manual rejection versus immutable prior finding |
| `ruff check .`, `ruff format --check .` | Passed; **79 files formatted** |
| Migration upgrade/metadata parity/downgrade/re-upgrade and retained legacy observation roundtrip | Passed in the full real PostgreSQL suite; no new Phase 1 migration |
| `python -m scripts.export_openapi`, `npm.cmd run generate:api` repeated | Passed; both hashes identical on repeat, generated files never manually edited |
| `uv lock --check --offline` with workspace cache | Passed; 68 packages, backend lockfile unchanged |
| `npm.cmd run format:check`, `npm.cmd run build` | Passed Prettier, TypeScript and Vite; 45 modules, main JS 284.79KB (87.99KB gzip), lazy PDF chunk 502.14KB and worker 1271.92KB; size warning disclosed |
| `python -m scripts.browser_checks` | **9 passed in 2.2 minutes**, Edge, actual HTTP/worker/database with explicitly mocked extraction; viewport matrix and selection/ledger details at 1440/768/390 |
| Browser accessibility boundary | Keyboard skip/main/nav, visible focus, labelled controls, status text/icons, loading/empty/error states and seven central normal-text/semantic contrast pairs >=4.5:1 passed; no manual screen-reader audit claimed |
| Git/exclusion checks | HEAD 4202e41 unchanged, staging empty, whitespace clean, .env untracked/ignored, no key-shaped secret in incremental text; 58 pre-existing uncommitted files retained |
| File accounting | **63 incremental files: 30 source/docs/contracts + 33 real synthetic screenshots**, exact list in PHASE1.md |
| Cleanup | Zero remaining demo/test schemas; all task-demo metadata inactive; owned API/worker/Vite processes ended; project PostgreSQL 55432 stopped, separate 5432 service untouched |

The earlier full run passed 172 tests / 2 skips before adding the manual-rejection projection regression. All final checks above pass. No live model call or new API cost was incurred in Phase 1.

Before final refinement, nine Edge browser cases passed in 1.7 minutes. The final run above repeated all nine after neutralizing unknown-check labels, refreshing queue counts after real state changes, stacking tablet PDFs and distinguishing manual rejection from prior assessment history. The original six scenario/failure/browser tests remain covered with updated product-facing selectors.

Initial failures were inspected and corrected: a metric test accidentally reused an already approved identity, so duplicate protection correctly prevented a second approval; distinct test identities fix the metric test without changing the guard. A Windows command-pipe encoding converted rupee assertions/arrow glyphs to question marks; UTF-8 patch edits restored the intended literals. The browser then passed all nine cases. Visual inspection fixed an undersized monospace heading and captures taken after a page-link scroll. Initial Ruff long-string findings were corrected before the final checks. No failing case was removed or safety rule relaxed. A benign Node NO_COLOR/FORCE_COLOR warning and the existing lazy PDF.js size warning are disclosed.

Credential exclusions were verified without reading/printing secrets. The previously shared ZIP exposure requires operator rotation/revocation; no rotation is claimed. No .env was edited/copied, no archive was created and no new paid extraction was performed. See [SECURITY.md](SECURITY.md). Local accessibility checks cover semantic labels, focus/keyboard and programmatic contrast; no manual screen-reader or hosted/load acceptance is claimed.

## Historical Slice 6A handoff

## Slice 6A: invoice workspace, read APIs and demonstrations (2026-11-12)

SPEC §§3.4, 4.1–4.3 and 5.1–5.3 and the explicit Slice 6A request govern this milestone. Read AGENTS.md, SPEC.md, DECISIONS.md, this file, PROGRESS.md and README.md completely before implementation. Archived plans were not used as active contracts. Financial policy defaults, worker ownership fencing, approval transactions and the separate reviewer boundary remain in force. Slice 6A is **uncommitted for review**; nothing was pushed or deployed.

Slice 5 closure: reviewed the entire diff against ba58c43, covering physical owning-connection/lease fencing, transactional authorization, checkpoint recovery before/after financial commit, interrupts/resume, trusted reconstruction, immutable history and idempotent review generations. The initial review found no critical defect; **141 passed, 2 opt-in skips in 165.19s**, with Ruff, migration roundtrip/parity, generated contracts, frontend build and Git checks passing. Committed the clean baseline separately as **4202e41**. A subsequently discovered source-omission defect is explicitly fixed and tested in the uncommitted Slice 6A changes below; the baseline commit was not silently amended.

### Implemented behavior and invariants

The UI now supports drag/drop upload, URL-based run navigation, an authenticated original-PDF preview, persisted workflow stages/events with timestamps and measured durations, original extracted values with local verification status/pages, vendor/PO context, financial reasons, source mode, model/policy and nullable cost/usage. History has status/decision filters and keyset pagination; dashboard metrics are global and labelled separately from table filters. No stage animation claims processing that did not occur. MOCK_OPENAI and reused extraction remain visibly disclosed. Credentials are held only in tab memory; browser refresh requires reconnecting but retains the run URL. The browser receives neither the OpenAI key nor private JSON evidence, bank fields, snippets or checkpoints.

The review panel submits only backend-permitted actions, an offered PO when required, a nonempty reason, generation and an idempotency key. Auth/network retries retain the identical key/body; edits create a new key. Conflicts refresh state without silently posting another action. The application token cannot resolve reviews. There is no manual approval, tolerance override, payment execution or email integration. Resume continues through the existing separate worker and locked financial finalizer.

Authenticated fetch SSE uses persisted sequence IDs and Last-Event-ID, closes/reconnects bounded streams, and releases database sessions before waiting. Polling uses the same cursor and deduplicates by sequence. Tokens never enter query strings. Run detail is additive; old status fields and intake/event envelopes remain compatible. PDF bytes are authenticated/no-store and rendered by bundled PDF.js from an in-memory blob. Current PO information is explicitly labelled as an approved allocation, assessed PO or printed-reference lookup, never asserted to be historical matching without evidence.

Dashboard accounting uses Decimal. Processing duration sums observed worker intervals and excludes queue/human wait; abandoned/open intervals are unknown. Average duration discloses the number measured. Estimated live cost excludes mock activity, accounts for missing reservations/usage and discloses coverage; actual account billing is unknown. Potential PO overrun flagged uses new immutable assessment observations captured in the existing locked financial transaction, not current balances, reason-text parsing or a savings claim. Only latest current PO_CAP_EXCEEDED holds are eligible; identical verified invoice identities are deduplicated using the maximum recorded excess, while missing/conflicting signatures remain unknown. No legacy assessment is backfilled from current masters.

**Safety correction discovered during this slice:** an otherwise valid model response could omit a recognized printed optional bank suffix, PO reference, tax ID or SKU, thereby avoiding that field's checks. Local verification now emits PRINTED_FIELD_OMITTED for every recognized printed record absent from extracted fields. Such omissions share the existing two-attempt source-repair budget; unresolved omissions cannot approve or obtain PO_SELECTION over a printed PO. Four new full-workflow regressions assert two bounded mock calls, review and zero ledger posts. This corrects enforcement of the existing labelled-fields-3 contract without changing its financial defaults; committed history is never rewritten. General unrecognized commercial layouts remain conservative and are not claimed solved by this correction.

### Exact Slice 6A file manifest and purpose

Paths below are relative to the repository. Generated files are regenerated only through the OpenAPI tools; PDFs, credentials, browser traces, runtime databases and build output are ignored.

| Files | Why changed/created |
|---|---|
| `backend/app/read_contracts.py` | Typed additive run detail, source fields, PO relationship, stage timing, usage, history and dashboard responses; UTC timestamps and decimal strings |
| `backend/app/read_service.py` | Read-only whitelisted projections, local verification reconstruction, keyset cursors, stage/processing intervals, usage coverage and exact overrun aggregation |
| `backend/app/read_routes.py` | Authenticated history/dashboard, original PDF and SSE endpoints; read-only repeatable dashboard snapshot and correct OpenAPI PDF/stream media types |
| `backend/app/streaming.py` | Bounded ordered durable-event streaming, keepalives, cursor recovery and disconnect cleanup without holding database connections while waiting |
| `backend/app/main.py` | Wire additive detail/routes, sanitize public event payloads and optionally serve a built static frontend |
| `backend/app/approval.py`, `backend/app/financial_models.py` | Capture nullable immutable PO balance observations in the existing atomic assessment transaction |
| `backend/alembic/versions/0006_observations.py`, `backend/app/models.py` | Nullable observations column and history ordering index, matching SQLAlchemy metadata; prior migrations unchanged |
| `backend/app/config.py`, `backend/app/db.py`, `backend/.env.example` | Validated optional isolated schema/search path and static frontend path; no secret/default production activation |
| `backend/app/intake.py` | Replace obsolete skeleton notice with an accurate stored/awaiting-processing message |
| `backend/app/evidence_verification.py`, `backend/app/workflow.py` | Fail closed on printed-field omissions and include them in the existing bounded critical-source repair path |
| `backend/scripts/demo_fixtures.py` | Actual synthetic H1/E1/E2/E3/E4 PDFs, image-only scan, expected transcriptions and zero-allocation vendor/PO masters |
| `backend/scripts/demo.py` | Explicit disposable create/API/worker/reset commands; loopback server and marked-schema guards, real workflow and disclosed fixture transport |
| `backend/scripts/browser_checks.py` | Own/terminate loopback API/worker/Vite subprocesses, run Edge/Chromium tests, isolate paid H1, record sanitized usage and reset only owned demo schemas |
| `backend/scripts/hosted.py` | Concrete hosted API/migration/checkpoint/policy/worker entrypoints, psycopg URI adaptation and explicit worker activation gate |
| `backend/tests/test_reads.py` | Seven real-PostgreSQL cases for history/filter/auth, private data, SSE recovery/cancellation, observed financial metrics, legacy migration and timing semantics |
| `backend/tests/test_demo_safety.py` | Eleven cases for path/schema/remote/query override guards, actual server loopback verification and static UI/API authentication |
| `backend/tests/test_source_omission.py` | Four full workflow safety regressions for dropped bank suffix/PO/tax ID/SKU |
| `frontend/src/App.tsx`, `frontend/src/main.tsx` | Workspace shell, in-memory authorization, persistent URL navigation and actual API/database health |
| `frontend/src/Upload.tsx` | Drag/drop/input PDF validation, useful errors and retry-safe upload idempotency |
| `frontend/src/RunView.tsx` | Real event timeline/polling/streaming, results, source verification, financial context, timing and cost disclosure |
| `frontend/src/PDFPreview.tsx` | Lazy bundled PDF.js canvas rendering, page navigation, responsive scaling and cleanup of the authenticated original document |
| `frontend/src/ReviewForm.tsx` | Separate reviewer credential, closed actions/candidates, reason, generation, stable replay keys and actionable auth/conflict/network errors |
| `frontend/src/History.tsx` | Global metric coverage, filtered cursor history, loading/error/empty states and run links |
| `frontend/src/api.ts`, `frontend/src/ui.tsx`, `frontend/src/vite-env.d.ts` | Generated-type client, bearer fetch/stream parsing, sequence deduplication, precise decimal formatting and shared presentation primitives |
| `frontend/src/styles.css` | Responsive workspace, readable financial data, timeline, review form, PDF and narrow-screen layout |
| `frontend/openapi.json`, `frontend/src/api.generated.ts` | Generated additive API schemas/types including binary PDF and text/event-stream responses |
| `frontend/package.json`, `frontend/package-lock.json` | Locked PDF.js runtime plus Playwright/Prettier tooling and verification scripts |
| `frontend/.prettierrc.json`, `frontend/.prettierignore` | Consistent handwritten source formatting; generated contracts excluded from manual formatting |
| `frontend/playwright.config.ts`, `frontend/tests/workflow.spec.ts` | Six browser-level cases across actual HTTP intake, separate worker/database, review/resume, failures, fallback, history and responsive layout |
| `.dockerignore`, `Dockerfile`, `render.yaml`, `docs/DEPLOYMENT.md` | Reproducible container/Render preparation, separate always-on services, direct persistent PostgreSQL, private build context and disabled worker gate |
| `docs/RUNNING.md` | Exact local startup, credentials, PDF scenario order, explicit live mode, reset and check commands |
| `docs/benchmarks/slice6-live-h1.json` | Sanitized actual usage/latency and dated cost estimates for three explicit synthetic live browser H1 smokes |
| `docs/screenshots/slice6-upload.png`, `docs/screenshots/slice6-mock-h1.png`, `docs/screenshots/slice6-mock-review.png`, `docs/screenshots/slice6-mock-overrun.png`, `docs/screenshots/slice6-mock-dashboard.png`, `docs/screenshots/slice6-mobile.png`, `docs/screenshots/slice6-live-upload.png`, `docs/screenshots/slice6-live-h1.png` | Browser screenshots of the actual synthetic workspace, including explicit mock/live modes |
| `docs/DECISIONS.md`, `docs/DEVELOPMENT.md`, `PROGRESS.md` | Proposed read/metric/demo contracts, implemented details, safety correction, observed verification and remaining boundaries |

README.md and SPEC.md are unchanged: no financial-policy or canonical product contract change was agreed. Backend dependencies and lockfile are unchanged in this slice. The 141 existing routine tests are preserved unchanged.

### Reproduce and demonstrate

Follow [RUNNING.md](RUNNING.md) for three local terminals, credentials, generated PDFs and reset. Each demo has new business/checkpoint schemas, generated credentials, unchanged policy and synthetic masters with zero committed balances. No finished run or ledger row is seeded. The loopback guard checks both the URI and actual PostgreSQL server address; remote, tunnel/container-address and path-escape targets are refused. Default ordinary worker invocation still claims nothing. The runner explicitly enables only its isolated demo worker and terminates its own processes afterward.

All six browser tests passed through actual frontend/API/worker/PostgreSQL. Routine extraction alone uses the explicitly labelled mock transport, restricted to exact generated PDF hashes:

| Scenario | Actual observed result |
|---|---|
| H1 | PDF locally verified, approved once for INR 11800.00; ledger/PO balance asserted; original PDF canvas rendered |
| E1 | First 70000.00 invoice actually uploaded/approved; next 35000.00 held against remaining 30000.00, exact 5000.00 excess, no second allocation; polling continued after stream failure |
| E2 | Missing PO opened two offered candidates; application credential failed review authorization; separate reviewer same-key retry selected one PO; worker resumed and revalidated before approval |
| E3 text | INV 001 normalized to H1 INV-001 and rejected as duplicate, no second ledger |
| E3 scan | Image-only duplicate stayed in review because transcription cannot establish trusted local identity; scanned rejection is deliberately not claimed |
| E4 | Bank suffix mismatch held for review; no posting |
| Failure/navigation checks | 401/403/404/409/network states, retry-safe REQUEST_INFO, SSE recovery/no duplicate events, filters/keyset pagination, reload/run URL, token-storage absence and 390px layout passed |

Live opt-in frontend H1 separately passed using the configured OpenAI account/model and actual PDF, real worker/financial transaction and disposable synthetic masters. The final run required one bounded critical-source repair: **2 Responses attempts, 2283 input / 2713 output tokens, 1127 cached / 1150 cache-write tokens, 22091ms summed provider latency, USD 0.0015121200 estimated**. Both responses were schema-valid; that alone did not establish verified facts. Actual billing is unknown. Across three explicit H1 smokes during UI/source fixes: **4 attempts, USD 0.0030413650 total estimated**; no other live scenarios or payments. See the [sanitized report](benchmarks/slice6-live-h1.json) for per-attempt values and dated rate source. This is not a broader accuracy benchmark.

### Slice 6A verification record

| Command/check | Observed result |
|---|---|
| Full `.venv/Scripts/python.exe -m pytest -q` against isolated real PostgreSQL 17 schemas | **163 passed, 2 opt-in live skips in 188.13s**: original 141 + 22 new routine cases |
| Final `pytest tests/test_reads.py tests/test_health.py -q` after response-media annotations/intake wording | **11 passed in 18.21s**, including full upgrade/downgrade/re-upgrade and metadata parity, plus legacy nullable observations |
| `ruff check .`, `ruff format --check .` | Passed; **77 files formatted** |
| `uv lock --check --offline` with workspace UV_CACHE_DIR | Passed; 68 packages resolved. Default Windows cache location was inaccessible; local cache avoids it |
| `python -m scripts.export_openapi`, `npm.cmd run generate:api` repeated | Passed; both OpenAPI and generated TypeScript hashes unchanged on repeat |
| `npm.cmd run format:check`, `npm.cmd run build` | Passed Prettier, TypeScript and Vite production build; lazy PDF.js chunk triggers Vite's >500KB warning |
| `python -m scripts.browser_checks` | **6 passed in 45.5s**, Edge headless, mocked extraction clearly disclosed; test-owned services/schemas cleaned |
| `python -m scripts.browser_checks --live-h1` | **1 passed, 5 skipped in 34.9s**, explicit paid live H1 only; two bounded requests in final run |
| Git checks | Whitespace clean, nothing staged for Slice 6A, baseline 4202e41 retained, environment/database/upload/build artifacts ignored, no remote/push |
| Final cleanup/manifest | All 58 changed/new files named above; zero remaining demo/test schemas and no active task-demo metadata; project PostgreSQL 55432 stopped, separate port-5432 service untouched |
| Blueprint syntax | YAML parsed and service/private-database shape checked locally; not provider-validated |
| Container/hosted execution | Not run: Docker unavailable; no paid resources provisioned or services exposed |

Earlier failed checks led to concrete fixes: Windows pytest temporary-directory ACLs required a contained workspace temporary directory; PostgreSQL server-address text included /32 until host() was used; the native Edge PDF viewer cropped the preview, replaced by bundled PDF.js; an inaccessible screen-reader label overflowed the mobile viewport, fixed and retested. Initial TypeScript/PDF.js option and Ruff/format errors were corrected. An old Windows output encoding failed on browser check symbols; runner output is now UTF-8. All executable checks above pass. Browser output includes one benign Node NO_COLOR/FORCE_COLOR warning. No failed test is hidden or bypassed.

### Remaining limits

Scanned identity corroboration, broad commercial layouts, the >=20 real-document gold set, full jurisdiction tax profiles and a fully justified H2 rounding case remain blockers to unrestricted processing. Unrecognized/missing evidence remains a hold. The canvas preview does not yet offer text selection, search or evidence highlighting; original PDF access remains available. PDF.js adds a large lazy chunk/worker; no performance claim on low-end devices is made. Dashboard queries are verified for correctness on scoped fixtures, not load-tested for a large tenant.

Deployment preparation selects direct/session-preserving PostgreSQL and separate always-on Render API/worker services, with same-origin static UI and private secrets/PDF data. Docker image build, actual Render provisioning, hosted streaming/proxy behavior, memory sizing, backups/retention, dedicated database privileges and deployed identity/secret rotation were not validated. The local single-reviewer bearer model is not multi-tenant production auth. [DEPLOYMENT.md](DEPLOYMENT.md) records the explicit activation sequence. No remote push, production master mutation, unrestricted worker activation, payments or emails occurred.

## Historical Slice 5 record

## Historical Slice 5: durable graph and review backend (2026-11-12)

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
