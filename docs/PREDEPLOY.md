# Predeployment verification — 2026-11-14

The current local application passes the verification below. The selected Vercel profile now enforces **4-MiB, one-to-five-page, unencrypted PDFs**, while local/default APIs retain 12 MiB; active limits appear on the frontend. **Hosted deployment still needs** database, quota, ingress and hosted-build acceptance in [DEPLOYMENT.md](DEPLOYMENT.md). The results below describe the earlier predeployment audit; subsequent upload-limit checks are recorded at the top of DEVELOPMENT.md. Nothing was pushed or deployed. No existing user workspace, private PDF or credential was reset.

## Verified endpoint and role matrix

All paths have prefix `/api/v1`. The integrated real-PostgreSQL test made **117 requests covering all 17 implemented operations**, with the agreed three-submitter BYOK configuration and explicit MOCK_OPENAI transport. The test compares its operation coverage with the application's generated OpenAPI, so an untested added operation fails the matrix. Financial processing, queue work, checkpoints, local evidence checks and approval transactions execute normally; no trusted model flags or fabricated ledger entries are injected.

S1/S2/S3 are distinct static submitters. `200/404` means an own run is readable and another submitter's run is hidden. Finance can inspect workspace invoices. Review responses intentionally retain the existing 403 denial contract for anonymous callers. Successful status codes use valid existing resources; normal not-found/validation/conflict outcomes remain applicable.

| Method | Path | Anonymous | S1 | S2 | S3 | Finance |
|---|---|---:|---:|---:|---:|---:|
| GET | /healthz | 200 | 200 | 200 | 200 | 200 |
| GET | /readyz | 200 | 200 | 200 | 200 | 200 |
| GET | /openai/config | 200 | 200 | 200 | 200 | 200 |
| GET | /access | 401 | 200 | 200 | 200 | 200 |
| POST | /openai/sessions | 401 | 200 | 200 | 200 | 403 |
| DELETE | /openai/session | 401 | 204 | 204 | 204 | 403 |
| POST | /invoices/process | 401 | 202 | 202 | 202 | 403 |
| GET | /runs | 401 | 200 | 200 | 200 | 200 |
| GET | /runs/{run_id} | 401 | 200/404 | 200/404 | 200/404 | 200 |
| GET | /runs/{run_id}/document | 401 | 200/404 | 200/404 | 200/404 | 200 |
| GET | /runs/{run_id}/events | 401 | 200/404 | 200/404 | 200/404 | 200 |
| GET | /runs/{run_id}/events/stream | 401 | 200/404 | 200/404 | 200/404 | 200 |
| GET | /runs/{run_id}/review | 401 | 403 | 403 | 403 | 200 |
| POST | /reviews/{review_id}/respond | 403 | 403 | 403 | 403 | 202 |
| GET | /purchase-orders | 401 | 403 | 403 | 403 | 200 |
| GET | /purchase-orders/{po_id} | 401 | 403 | 403 | 403 | 200 |
| GET | /dashboard/summary | 401 | 403 | 403 | 403 | 200 |

Additional integrated assertions: individually bound provider keys/models; immutable owner scopes; repeated intake and review action replay; ordered nonduplicate SSE IDs; protected original PDFs; reviewer SELECT_PO/resume after the submitter disconnects OpenAI, without another model request; REQUEST_INFO stop; explicit reviewer rejection of an ungrounded scan; two actual approvals and no duplicate allocation. Existing regressions cover stale/competing actions, worker competition/crash/restart, lease/physical-connection fencing, approval rollback and concurrent PO allocation, typed arithmetic/tax/balance rules, malformed provider output, credential expiry/revocation and read-only history.

These SPEC routes remain **unimplemented** and are explicitly checked as 404: GET /policies/current, POST /policies, POST /runs/{run_id}/reevaluate and GET /runs/{run_id}/export. They are not counted as successful implemented endpoints. No payment execution or vendor email exists.

## Observed results

| Check | Result |
|---|---|
| Full backend pytest, isolated PostgreSQL 17 schemas | **216 passed, 3 opt-in paid skips in 294.48s** |
| Endpoint matrix plus Vercel entrypoint/profile guards | **2 passed in 12.73s** before the final full suite |
| Alembic upgrade/metadata parity/downgrade/re-upgrade | Passed in full backend suite, through 0008; checkpoint recovery/setup tests also pass |
| Post-recovery health/migration/endpoint recheck | **6 passed in 22.06s** after restoring the existing local PostgreSQL cluster |
| Three submitters and finance, real browser/API/separate worker | **4 passed in 26.2s**, explicit mocked extraction |
| Existing shared-mode and key/model browser regressions | **12 passed in 1.8m**; role cases intentionally skipped here and verified separately |
| Ruff check and formatting | Passed; 92 Python files |
| OpenAPI/TypeScript generation | Passed; regeneration is checked for reproducibility |
| Frontend Prettier, TypeScript and production build | Passed; 47 modules; existing large lazy PDF.js chunk warning remains |
| Prepared Vercel manifest | Local Draft-7 schema and negative-count validation passed; actual Vercel build not run |
| Docker image | Not built: Docker unavailable locally |
| Live BYOK synthetic H1 | **1 passed in 20.73s**, details below |

Browser runs use dedicated ports 8100/5273 and disposable marked schemas. Their subprocesses/schemas are cleaned afterward, prior screenshot artifacts restored, and a temporary test-process keep-awake request is cleared. User-owned API/worker/frontend processes are retained. Routine tests use no live OpenAI calls.

The final cleanup read found local PostgreSQL stopped. Its lifecycle log reported an interrupted prior session; the existing project cluster was restarted in place and recovered normally. It was then accepting connections, the six health/migration/endpoint checks above passed, and final cleanup confirmed zero remaining test schemas/active browser workspaces. No cluster reinitialization, user-data reset or port-5432 service change occurred. PostgreSQL 55432 is left running. Locked dependency checking also passes offline (71 packages) after correcting a PowerShell cache-path lookup to use the existing workspace cache.

## Authorized real OpenAI smoke

The user explicitly authorized **one synthetic invoice** under the key configured privately in backend/.env. The current BYOK API intake, owner-bound credential, real OpenAI Responses call, local evidence verification and normal financial transaction produced:

- Model: **gpt-6-luna**, account-listed and successfully used.
- Result: **COMPLETED / APPROVED**, one run and **one immutable approval ledger entry**.
- Usage: **1130 input / 1312 output tokens**, 0 cached, 1127 cache-write tokens.
- Provider latency: **12094 ms**; one Responses attempt.
- Estimate using the explicitly dated 2026-11-12 rate snapshot: **USD 0.000797175**. Actual account billing is unknown. Runtime BYOK cost fields are not backfilled from this report.
- Finance could read the result with its own token; another submitter received 404. The temporary provider connection was revoked after the check.

The live API uses FastAPI TestClient and the real worker/service implementation against an isolated database; it is not a Vercel-hosted or live-browser test. Browser end-to-end checks above use real subprocesses and labelled mock extraction. Only Luna was called live in this audit; Terra appears only in mocked multi-model isolation coverage. [Sanitized actual metrics](benchmarks/predeploy-live-h1-2026-11-14.json) contain no key, PDF or run ID.

An initial model-discovery request returned sanitized 503 before invoice submission. A subsequent non-billable model-list probe returned 200 and listed the configured model; the authorized invoice then succeeded. No second live invoice was created. Initial style findings were corrected by formatting. The downloaded Vercel schema's declared Draft-4 meta-check fails because it contains newer syntax; strict Draft-7 meta/instance validation passes, including a negative-count failure check. See DEPLOYMENT.md rather than treating this as provider-side validation.

## Reproduce without OpenAI charges

From backend in CMD (PostgreSQL must be running):

```cmd
set TEST_DATABASE_URL=postgresql+psycopg://ps1@127.0.0.1:55432/postgres
set PS1_PREDEPLOY_REPORT=.local/predeploy/endpoints.json
uv run pytest -q --tb=short -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
uv run python -m scripts.export_openapi
```

From frontend:

```cmd
npm.cmd run generate:api
npm.cmd run format:check
npm.cmd run build
```

Finish source/schema generation before starting browser checks, because Vite reloads clear tab-memory access. From backend, run these sequentially with ports free:

```cmd
set PS1_BROWSER_CHANNEL=chrome
uv run python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273
uv run python -m scripts.browser_checks --api-port 8100 --ui-port 5273
```

Paid flags PS1_LIVE_PREDEPLOY, PS1_LIVE_WORKFLOW and PS1_LIVE_EXTRACTION must remain unset for these routine checks. The opt-in live test is separately gated and is not needed to repeat the endpoint matrix. The sanitized 117-probe report is written only under ignored .local when PS1_PREDEPLOY_REPORT is set.

## Manual role walk-through

Use the existing **local-roles** workspace, not the older shared `local` demo. Stop the old API/worker yourself and start `uv run python -m scripts.demo api --name local-roles` and `uv run python -m scripts.demo worker --name local-roles --enable-processing` in separate backend terminals. Keep the frontend on http://127.0.0.1:5173. These commands use .local/demos/local-roles/backend.env; backend/.env's application token does not replace that demo's tokens.

1. Privately open .local/demos/local-roles/backend.env. APP_API_TOKEN is S1, the submitter-b/submitter-c values inside SUBMITTER_API_TOKENS are S2/S3, and REVIEWER_API_TOKEN is finance. Give each person only their token.
2. Sign in as S1: only Process Invoice and My Invoices appear. In this live BYOK workspace, connecting a key/model and uploading causes additional charges under the supplied key. The one authorized automated invoice above is already complete; manual uploads are additional paid requests.
3. With an explicitly chosen test upload, inspect its own PDF/status/outcome. Log in as S2/S3 in other browser tabs: the first person's run must be absent from history and return 404 by direct URL/API.
4. Finance sees Review Queue, all workspace invoices, Purchase Orders and Overview; no invoice-upload or OpenAI-key form. For an E2 missing-PO hold, choose a substantiated offered PO and rationale, resume and verify fresh validation. A hard spending cap cannot be overridden. H1/E1/E2/E3/E4 PDFs in that workspace are synthetic; E1 requires processing its prior partial invoice first. Scan corroboration remains conservative.
5. For direct API inspection, http://127.0.0.1:8000/docs lists implemented routes. Use Swagger Authorize with the intended app token; provider session/model and review generation/idempotency fields are separate. GET /healthz and /readyz are under /api/v1; `/` on the development API is not the frontend.

For a no-charge interactive fixture demo, create a separate new `--mode mock --roles` workspace using RUNNING.md. It must remain visibly mocked and accept only its generated PDFs; do not convert/reset the existing live workspace or submit personal documents to the mock adapter.

## Incremental files

- `backend/tests/test_predeploy_endpoints.py`: actual operation/role matrix, BYOK/financial integration and Vercel startup/disabled-worker guards.
- `backend/tests/test_predeploy_live.py`: separately gated one-invoice real-provider test and sanitized usage report.
- `frontend/tests/roles.spec.ts`: third static submitter's actual isolation and duplicate-rejection browser case.
- `backend/vercel_app.py`, `vercel.json`, `.vercelignore`: fail-closed private-demo ASGI entrypoint, frontend/API routing, disabled worker Daemon and private upload/build exclusions.
- `render.yaml`: mark the old paid/server-key reference as unselected.
- `SPEC.md`, `README.md`, `docs/DECISIONS.md`, `docs/DEPLOYMENT.md`, `docs/ROLE_ACCESS.md`, `docs/DEVELOPMENT.md`, `PROGRESS.md`, this report: agreed target, observed coverage, operating guide and unresolved gates.
- `docs/benchmarks/predeploy-live-h1-2026-11-14.json`: actual synthetic live-call metrics, with dated estimates and unknown billing.

No application dependency/lockfile, financial default, ownership fence, migration, worker/graph writer or approval transaction is changed by this audit. The subsequent Vercel upload profile is 4 MiB, with the 12-MiB local/default ceiling retained. All earlier uncommitted work remains uncommitted.
