# Submitter and financial-reviewer access

The user explicitly chose individual submitters seeing only their own invoices. SPEC §4.1 and DECISIONS.md record the contract before implementation. Role mode uses operator-issued personal access credentials within one private finance workspace. It does not add public signup or production multi-tenant identity.

| Feature | Submitter | Financial reviewer |
|---|---|---|
| Upload invoice | Allowed | Denied |
| OpenAI key/model setup | Own connection only | Denied |
| Invoice history/search/counts | Own runs only | Workspace runs |
| Invoice document and processing status | Own runs only | Workspace runs |
| Business outcome and own extraction usage | Own invoice | Workspace invoice |
| Review queue/actions/candidates | Denied | Allowed |
| PO directory, balances and allocation ledger | Denied | Allowed |
| Company dashboard/metrics | Denied | Allowed |
| Technical/financial audit screens | Hidden; limited submitter DTO | Allowed |
| Demo scenario gallery | Hidden | Hidden |

## Frontend navigation (17 November local update)

Signed-out users see only the access entry screen. Submitters land on My invoices, with Submit invoice and OpenAI connection; reviewers land on Review queue, with Invoice history, Purchase orders and Overview. OpenAI connection is a frontend alias of the server upload capability, so a direct URL never grants finance access to submitter setup. The account control supports disconnect; refresh still requires reconnecting. The queue/detail layout and mobile navigation change presentation only. Public deployment has not been updated in this slice.

## Enforcement

`GET /api/v1/access` returns a server-authenticated principal and allowed pages. APP_API_TOKEN is the default submitter identity; SUBMITTER_API_TOKENS adds individually named tokens; REVIEWER_API_TOKEN grants the configured finance role. A role or owner in a URL/form does not change identity. Role credentials must be unique, stable actor IDs must not be reused for different people, and configuration errors suppress sensitive inputs.

Migration 0008 adds nullable run/provider owner IDs, an owner/history index, immutable-owner triggers and a binding-owner trigger. Existing history is not reassigned. In role mode, ownerless legacy runs are visible only to finance. Intake derives owner from the principal and scopes idempotency to that person. SQL filtering scopes history/count/search and cursor metadata. Run/document/event/SSE reads check ownership before returning data; another person's or an absent ID returns the same 404. Finance features return 403. Submitter detail uses its own DTO, excluding PO balances, ledger/candidates, policy/thread IDs and internal finance checks. Waiting-review explanations direct the submitter to the financial reviewer rather than suggesting they select a PO.

Provider creation, use and revocation also require the originating submitter. The worker still uses the immutable per-run key/model binding. Company-wide financial duplicate detection and PO allocation remain global within the finance workspace: separate submitter identities do not allow duplicate approvals. No financial rule, row/advisory lock, lease, checkpoint or approval transaction is weakened.

Shared mode remains explicit compatibility for existing demos/regressions. The new local-roles workspace enables both role separation and submitter-supplied OpenAI keys, without an operator OpenAI key. RUNNING.md lists credentials and startup commands. Reviewers sign in once with their reviewer token and resume using stored extraction, without an OpenAI key or a second credential prompt.

## Personal credentials after deployment

The agreed case-study profile is three fixed submitter identities (`submitter`, `submitter-b`, `submitter-c`) and one financial reviewer. Each has a separate randomly generated application token, retained across restarts and privately assigned by the operator. One token represents one identity: multiple people using that token share its invoice access. README proposes stronger sign-in/session management as future work; it is not implemented by this static-token setup.

There are three separate secrets with different jobs:

| Secret | Who creates it | What it does |
|---|---|---|
| Personal application access token | Workspace operator, once per person | Identifies the submitter and limits them to their own invoices, or authorizes the financial reviewer |
| OpenAI API key | Each submitter in their own OpenAI account | Authorizes paid extraction under that account; does not grant invoice/reviewer access |
| BYOK_ENCRYPTION_KEY | Workspace operator, once per hosted environment | Encrypts temporary provider credentials; stays only in API/worker server secrets and is preserved across restarts/redeploys |

For the current private-access implementation, the operator generates a different random application token for each person. From backend, `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"` generates one token; run privately once per person and store each result directly in hosting secrets. APP_API_TOKEN belongs to the default `submitter` identity. Additional tokens go in SUBMITTER_API_TOKENS, for example `{"alice":"<alice-personal-token>","bob":"<bob-personal-token>"}`. REVIEWER_API_TOKEN is a separate generated token for finance. Set ACCESS_MODE=roles and OPENAI_CREDENTIAL_MODE=reviewer. Give each person only their own token. Stable actor IDs must stay with the same person; rotating their token must preserve their ID. Configuration is server-side; there is no automatic signup/token-delivery service. Apply configuration updates through a coordinated API/worker restart without resetting business data.

Each submitter creates an OpenAI API key through their own [OpenAI account](https://developers.openai.com/api/docs/quickstart), then enters it in the app and chooses an offered model. The app does not generate OpenAI keys. Connect once for multiple invoices in the same tab, up to the connection's 24-hour expiry. Refresh, a new/closed tab, disconnect or expiry requires reconnecting for new uploads. This is the app connection's lifetime, not an instruction to generate a new OpenAI key: reconnect using the same key if it is still valid. Closing/refreshing the tab does not revoke a submitted job's connection; it remains valid until expiry or explicit revocation. A new connection does not replace the key/model bound to old runs. Reviewing an already extracted invoice does not require the reviewer to supply an OpenAI key.

The hosted frontend sends authenticated requests to FastAPI over HTTPS. FastAPI persists the PDF, immutable owner and encrypted connection binding in PostgreSQL, then the continuously running separate worker reads that run's binding and processes it with that submitter's key. API and worker need the same persistent database and stable BYOK_ENCRYPTION_KEY. Use direct/session-preserving PostgreSQL connections for worker locks. No operator OpenAI key is needed in this mode and there is no fallback to another person's key. All secrets stay out of frontend VITE variables.

Hosting remains unprovisioned. Vercel's request-bound [Functions have duration limits](https://vercel.com/docs/functions/limitations); current [Daemons](https://vercel.com/docs/daemons) offer a distinct persistent-worker option, including on Hobby within quotas. The selected Vercel preparation keeps this separate worker and PostgreSQL architecture. The worker starts disabled, and upload-size, quota, database and hosted-test gates remain in [DEPLOYMENT.md](DEPLOYMENT.md). Public account signup/login remains outside this private-token implementation.

## Incremental files

| Files | Why |
|---|---|
| `backend/app/access.py` | Server principal, role checks, ownership checks, capabilities and submitter-specific explanations |
| `backend/alembic/versions/0008_run_owners.py`, `backend/app/models.py`, `backend/app/provider_models.py` | Immutable ownership, indexes, matching provider/run ownership |
| `backend/app/config.py`, `backend/.env.example` | Explicit access mode, individual identities, unique credentials, redacted configuration errors |
| `backend/app/main.py`, `backend/app/intake.py` | Server-derived intake owner, scoped idempotency, role-restricted upload/review, limited submitter detail |
| `backend/app/read_routes.py`, `backend/app/read_service.py`, `backend/app/read_contracts.py` | Protected finance endpoints, owner-filtered history/cursors/document/events/SSE, submitter DTO |
| `backend/app/provider_credentials.py`, `backend/app/provider_routes.py` | Provider sessions bound to submitter identity |
| `backend/scripts/demo.py`, `backend/scripts/browser_checks.py` | Fresh per-person role demo, JSON identity parsing, isolated role browser runner and nested-token redaction |
| `backend/tests/test_role_access.py` | Direct-API role/owner isolation, legacy handling, cross-user key use/revocation, idempotency, immutable ownership and one global financial posting |
| `frontend/src/App.tsx`, `frontend/src/History.tsx`, `frontend/src/SubmitterRunView.tsx`, `frontend/src/styles.css` | Server-authorized navigation, My Invoices, readable limited own-invoice page and guarded direct navigation |
| `frontend/src/BusinessTimeline.tsx`, `frontend/src/ReviewForm.tsx`, `frontend/src/RunView.tsx` | Simplified submitter progress and reviewer actions using the authenticated reviewer credential |
| `frontend/src/api.ts`, `frontend/openapi.json`, `frontend/src/api.generated.ts` | Role-aware errors/types and generated API contracts |
| `frontend/tests/roles.spec.ts`, `docs/screenshots/roles-submitter.png`, `docs/screenshots/roles-reviewer.png` | Actual local-browser role scenarios and synthetic, explicitly mocked-extraction screenshots |
| `SPEC.md`, `README.md`, `PROGRESS.md`, `docs/DECISIONS.md`, `docs/DEVELOPMENT.md`, `docs/RUNNING.md`, `docs/SECURITY.md`, this file | Agreed role contract, setup, verification and limits |

## Verification

Full backend: **214 passed, 2 paid-live skips in 227.08s**, preserving the original 198 and adding 16 role cases. Initial role/BYOK/migration subset: **38 passed in 57.28s**; final role projection/migration subset: **20 passed in 23.79s**. Migration tests cover full upgrade/downgrade/re-upgrade and metadata parity through 0008. Ruff (89 Python files), generated contracts, formatting, locked dependency resolution and production build pass; the existing PDF.js size warning remains. **All 3 role browser cases passed in 18.6s**, including rendered PDFs/mobile width and reviewer resume without an OpenAI key; **all 12 previous browser cases passed in 1.7m** in separate shared-mode verification. Screenshots show real synthetic labelled-mock execution and the distinct screens, not a live provider benchmark.

Early role browser assertions used `Needs Review` rather than the existing `Needs review` display label, then an exact `Review Queue` accessible name despite its actual count badge (`Review Queue 1`). Both were corrected after inspecting the actual page; no access check or financial rule was relaxed. Provider calls in every test use explicit mock transport. No live key/model call, payment, remote push or deployment occurred. Existing user workspaces/processes are retained. Public identity/cookies, hosting/proxy/upload limits and broad invoice-layout/scan verification remain outside this slice. Changes are uncommitted.
