# Reviewer-supplied OpenAI keys: implementation record

The user requested real extraction billed to each reviewer's supplied OpenAI project key, with account-accessible model selection. They chose authenticated-encrypted temporary server storage, expiring after 24 hours or explicit disconnect. SPEC §3.5 records this authorized extension; OpenAI remains the sole provider and Python remains the financial authority.

## Behavior and boundaries

1. Existing workspace authentication is required. POST `/api/v1/openai/sessions` receives a key, calls only the OpenAI Models API, intersects IDs with the tested PDF/Responses/Structured Outputs allowlist, encrypts the key and returns an opaque capability, model IDs and expiry. No paid capability probe occurs. Missing model-list permission fails clearly. Listing is not proof of Responses permission or available credits.
2. Reviewer-mode multipart intake requires `model_id` and `X-OpenAI-Session`. A short transaction validates/locks that session and atomically writes the immutable provider binding with PDF/run/queue/event/idempotency data. Changing model or connection with the same intake idempotency key returns 409. Existing server-mode requests remain compatible and reject unexpected provider overrides.
3. The separately enabled worker resolves the binding per run. Credentials are checked before every new outgoing attempt outside any DB transaction; no process-global key/model mutation occurs. The existing two-attempt budget, leases, session advisory locks, owner fencing, checkpoint writes and atomic PO allocation are preserved. Model changes do not rewrite old runs. Restart can reuse persisted extraction without a new call even if the original key has since been revoked.
4. DELETE `/api/v1/openai/session` revokes the capability and clears its active ciphertext. Expiry also blocks future attempts. Cleanup runs on worker startup, each minute while idle, access and an explicit operator command. Downtime can delay physical cleanup but not authorization expiry. In-flight requests can finish and be charged. Financial history and original PDFs remain intact. No owner-key fallback exists in reviewer mode.
5. The browser clears the entered plaintext key after connection attempts; opaque capability/model are tab-memory only. Explicit workspace Disconnect revokes the provider connection first. Late responses after setup unmount are revoked rather than restored into application state. Reload/closing the tab is not guaranteed revocation. This remains one private shared finance workspace; BYOK is not public multi-tenant authentication or isolation.

## Incremental files

| Files | Purpose |
|---|---|
| `backend/app/provider_models.py`, `backend/alembic/versions/0007_provider_sessions.py` | Encrypted/expiring sessions, capability hashes, immutable per-run binding and schema constraints |
| `backend/app/provider_credentials.py` | Account model discovery, encryption/decryption/session binding, revocation/expiry/cleanup, per-run extractor and configured worker dispatch |
| `backend/app/provider_routes.py` | Authenticated credential connection/disconnection and non-secret configuration |
| `backend/app/main.py`, `backend/app/intake.py`, `backend/app/models.py` | Route wiring, input redaction, transactional/idempotent intake binding and model registration |
| `backend/app/config.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/uv.lock` | Explicit credential mode, encryption-secret setting and locked cryptography dependency |
| `backend/app/workflow.py`, `backend/app/worker.py`, `backend/scripts/hosted.py` | Shared infrastructure readiness, opt-in per-run provider dispatch and cleanup; original financial fencing unchanged |
| `backend/scripts/demo.py` | Fresh keyless reviewer-mode local demo; ownership-checked migration of older local demos |
| `backend/app/read_contracts.py`, `backend/app/product_reads.py` | Readable persisted expired/revoked-credential failure without a financial verdict |
| `frontend/src/OpenAIConnection.tsx`, `frontend/src/App.tsx`, `frontend/src/Upload.tsx`, `frontend/src/styles.css` | Key/model setup, explicit disconnect, late-response protection and upload gating |
| `frontend/openapi.json`, `frontend/src/api.generated.ts` | Generated additive API contracts |
| `backend/tests/test_reviewer_credentials.py`, `backend/tests/reviewer_harness.py` | Real PostgreSQL tests with synthetic keys/mock transport, concurrent workers, rollback, immutable binding and abrupt process restart |
| `frontend/tests/provider.spec.ts` | UI-only mocked connection/model/disconnect and late-response checks; upload deliberately stopped before processing |
| `AGENTS.md`, `SPEC.md`, `README.md`, `docs/DECISIONS.md`, `docs/DEVELOPMENT.md`, `docs/RUNNING.md`, `docs/SECURITY.md`, `docs/DEPLOYMENT.md`, `PROGRESS.md`, this file | Align the explicitly authorized key-storage exception, contract extension, operating instructions, exact results and limits |

## Verification and limits

Final full backend: **198 passed, 2 opt-in live skips in 204.85 seconds**, preserving all 180 prior tests and adding 18 credential cases. This includes upgrade/downgrade/re-upgrade and SQLAlchemy metadata parity through 0007. Final focused credential/workflow/recovery/migration subset: **33 passed in 89.54 seconds**. Ruff (86 formatted files), OpenAPI/generated TypeScript, dependency lock verification and the production frontend build pass; the existing PDF.js bundle-size warning remains. Guarded local-reviewer migration passed; private configuration is Git-ignored and staging remains empty.

The initial browser run passed both new UI cases and H1; it was then interrupted by Vite's logged `page reload openapi.json` during API regeneration, clearing tab credentials by design. Generation and browser execution were then kept sequential: **all 12 Chrome browser tests passed in 1.7 minutes**, preserving all ten previous cases. Final focused credential/input/intake/migration checks: **44 passed in 65.38s**. This was not a financial-approval failure and no business rule was relaxed.

Attempt authorization now shares a provider-session row lock with disconnect inside the existing short reservation transaction. This closes a revocation race between loading the key and reserving a provider attempt. An attempt is considered started when reserved and may be charged after disconnect; financial/network operations do not hold this transaction open. A dedicated regression injects disconnect in that interval and passes in the final full suite.

No live OpenAI request or actual reviewer key was used in this implementation. API/worker financial integration and restart tests mock provider transport; UI connection tests mock endpoints and stop before intake. A real reviewer-paid BYOK smoke is not claimed. Reviewer-mode token-cost estimates currently remain unknown rather than applying one model's rates to another. Models outside the tested allowlist are not offered. Hosted deployment, TLS/proxy behavior, 12-MiB upload compatibility, public identity/rate limits and broad commercial/scanned invoice verification remain independent unfinished gates. No payment/email, remote push or deployment occurred; changes remain uncommitted.
