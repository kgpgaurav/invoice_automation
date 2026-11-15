# Deployment preparation

## Selected target: Vercel Hobby, 2026-11-14

The user explicitly declined paid hosting and selected Vercel for both frontend and backend. No hosting/database account has been provisioned, connected or deployed. Current local verification is in [PREDEPLOY.md](PREDEPLOY.md). The Render material below is historical, not the selected target.

Current Vercel [Services](https://vercel.com/docs/services) and [Daemons](https://vercel.com/docs/daemons) provide a compatible preparation path: Vite frontend service, FastAPI service, and a separate persistent Python worker daemon sharing external PostgreSQL. The worker retains the existing PostgreSQL queue, session advisory locks, leases, durable checkpoints and atomic financial transaction. No Vercel Queue, alternative orchestrator or in-process FastAPI background worker is introduced. The older blanket statement that Vercel cannot run the worker was too broad; ordinary Functions and Daemons have different lifecycles.

`vercel.json` routes `/api/*` to `backend/vercel_app.py` and other requests to the frontend. The ASGI entrypoint refuses shared/server-key mode, missing reviewer/submitter slots and an operator OpenAI key. `.vercelignore` excludes local environments, documents, credentials, caches and test artifacts. The worker reuses Dockerfile and `scripts.hosted worker`; its configured instance count starts at **zero**, and PS1_ENABLE_WORKER remains a separate explicit activation gate. No fictitious HTTP health probe is attached to the worker, which does not serve HTTP.

### Hosting gates still open

- **Upload profile implemented:** the Vercel ASGI entrypoint caps the PDF at **4 MiB (4,194,304 bytes)**, leaving multipart headroom below the [Function request limit](https://vercel.com/docs/functions/limitations). Local/other API instances retain their 12-MiB default and can configure a lower MAX_PDF_BYTES. GET /openai/config returns active limits; the frontend displays and enforces them, and API intake rejects an over-limit request with 413 before provider use. The page limit stays five and encrypted PDFs remain invalid. An exact-size 4-MiB file is accepted by local API boundary tests; actual Vercel ingress still needs hosted testing.
- The [Container runtime](https://vercel.com/docs/functions/runtimes/container) also inherits Function limits. Services and Daemons are beta capabilities, so verify access on the actual Hobby account before relying on the prepared manifest. Supporting 12-MiB direct uploads on Vercel would require a separate storage-flow slice; it is not part of the selected 4-MiB demo profile.
- **Quota:** Hobby [Daemon limits](https://vercel.com/docs/daemons/limits) allow 5 active CPU-hours and 420 GB-hours of allocated memory per month. Idle workers still consume memory quota. The prepared worker requests 1 GiB; a continuous month exceeds that allowance. Stop it outside evaluation and confirm remaining account quota. Exhaustion stops daemons rather than making this an unlimited always-on free service. Actual account access and container memory need validation.
- **Database:** choose/provision the external free PostgreSQL project, TLS connection and credentials. Use an unpooled [Neon connection](https://neon.com/docs/connect/connection-pooling), or a direct/session-mode [Supabase connection](https://supabase.com/docs/guides/database/connecting-to-postgres) reachable from the runtime. Session-lock semantics are mandatory for worker/review writes. Do not use transaction pooling, including Neon's `-pooler` endpoint or Supabase transaction mode. Database quota/connection limits, poll-driven uptime, backups and retention still need validation.
- **Build/host:** Docker is unavailable locally. The Dockerfile image and actual Vercel Services/Daemon build, HTTPS routing, cold starts, PDF payload limits, streaming, restarts and account settings have not been tested on Vercel. Local checks are not hosted acceptance.
- **Product scope:** export, policy endpoints and re-evaluation remain unimplemented; broad real-layout/scanned corroboration and the complete gold set remain open. Static tokens are the agreed private case-study access scheme, not public signup.

### Private environment configuration

Configure these in server hosting secrets, never source, browser storage or VITE variables. API and daemon must use the same database, stable identity mappings and encryption secret.

| Setting | Required value/purpose |
|---|---|
| DATABASE_URL | PostgreSQL psycopg URI with provider-required TLS and session-preserving semantics |
| DATABASE_SCHEMA | Optional pre-created application schema, consistent on API/worker/migration commands |
| ACCESS_MODE | `roles` |
| OPENAI_CREDENTIAL_MODE | `reviewer` (the compatibility name for submitter-owned keys) |
| APP_API_TOKEN | Existing first submitter's private token |
| SUBMITTER_API_TOKENS | JSON containing the distinct `submitter-b` and `submitter-c` tokens |
| REVIEWER_API_TOKEN | Distinct financial-reviewer credential |
| BYOK_ENCRYPTION_KEY | One stable valid Fernet secret, retained across redeploys |
| PS1_POLICY_VERSION | `policy-1.1-demo` after explicit immutable policy registration |
| PS1_ENABLE_WORKER | Keep unset/`0` until all activation gates pass |

Omit OPENAI_API_KEY and OPENAI_MODEL: each submitter selects their model and supplies their own key. Omit FRONTEND_DIRECTORY from Vercel project settings; the frontend service serves the UI. Dockerfile's internal UI path belongs only to the container image. Do not copy backend/.env or .local into Vercel.

### Activation sequence after the open gates are resolved

1. Confirm actual free account capabilities and choose the database; select a supported nearby region for services/database rather than treating the prepared `iad1` as a measured latency choice. The selected Vercel upload profile is 4 MiB / five unencrypted pages.
2. Privately configure the four static access tokens, role/provider modes, database and encryption secret. Keep the daemon at zero instances and its worker gate disabled.
3. Run `python -m scripts.hosted migrate` with the intended server environment to install Alembic through 0008 and the separate LangGraph checkpoint schema. Serialize migrations. Never run the loopback-only demo reset against hosted data.
4. Explicitly register the unchanged policy with `python -m scripts.hosted register-policy --confirm-policy-version policy-1.1-demo`, then provision reviewed synthetic case-study vendor/PO masters with zero initial allocations. A guarded hosted master-data provisioning path is still required; no real invoice or approval ledger should be seeded as completed output.
5. Validate API readiness, all four roles and session-lock/checkpoint behavior on that exact host. `/readyz` proves API/business-schema readiness, not a running worker or available OpenAI billing.
6. Only then set PS1_ENABLE_WORKER=1 and activate one daemon instance. Rehearse the endpoint/role/PDF/review/resume/duplicate/overrun/restart cases and explicitly authorized paid smoke on disposable hosted test data. Stop the daemon outside the review window to preserve free quota.

The manifest passes local instance validation against the downloaded Vercel schema with Draft 7, including rejection of a negative worker count. The published schema declares Draft 4 but contains newer numeric exclusiveMinimum syntax; its declared-draft meta-validation fails upstream. The same schema is valid under Draft 7. This is documented rather than presented as a completed provider-side build.

## Historical Slice 6A Render reference — not selected

The following text predates the user's free-Vercel decision. It is retained as historical preparation only; do not apply render.yaml as the current deployment.

Reviewer-key extension (2026-11-14): the application now supports explicit `OPENAI_CREDENTIAL_MODE=reviewer`. API and worker must receive the same stable private `BYOK_ENCRYPTION_KEY` and use the same migrated database (through 0007). Omit the operator OPENAI_API_KEY in that mode. The existing Blueprint remains the server-key default; setting a new mode is an operator configuration change, not an automatic public deployment. Keep workspace/reviewer access credentials separate, require HTTPS, disable credential-body/header capture, and configure retention/backups and expired-ciphertext cleanup as described in SECURITY.md. BYOK does not resolve Vercel routing, worker quotas, the 12-MiB upload contract or public identity. No Vercel deployment is added by this feature.

This is configuration preparation only. Nothing was provisioned, exposed, pushed or deployed. Applying the Blueprint creates paid resources and needs separate authorization.

Chosen topology: Render Singapore paid web API (0.5 CPU / 512 MiB), independent paid background worker (1 CPU / 2 GiB), and paid PostgreSQL 17 (0.5 CPU / 1 GiB, 10 GiB persistent storage). The React build is static content served by the API image at the same HTTPS origin; this avoids cross-origin bearer handling and keeps streaming and document requests on one origin. API and worker share a private direct PostgreSQL connection string, with PDF BYTEA and isolated LangGraph checkpoint tables persistent in PostgreSQL. No ephemeral disk is authoritative.

The paid services are selected because free web services idle/sleep and free databases have lifecycle limits; see [Render free-instance limitations](https://render.com/docs/free). The [Blueprint reference](https://render.com/docs/blueprint-spec) documents current compute IDs, pre-deploy commands, private connection strings and secret generation. Worker **must use connectionString, never connectionPoolString**: Render's managed pool uses transaction pooling and explicitly does not support session advisory locks; see [direct-connection requirements](https://render.com/docs/postgresql-connection-pooling). All resources stay in the same region, external DB access is disabled, and frontend credentials are entered at runtime rather than baked into JavaScript.

Dockerfile builds the locked frontend and Python runtime. .dockerignore excludes environment files, secrets, uploaded PDFs, caches, test output and repository metadata. Runtime uses an unprivileged user. Build has no API-key argument or build-time API call. The hosted adapter explicitly changes Render's `postgresql://` driver prefix to `postgresql+psycopg://`; no database or financial policy is changed. API serves the built assets only when FRONTEND_DIRECTORY is configured.

After authorization to provision:

1. Review current Render plans/region and the Blueprint against the account. Set the requested OpenAI model and single provider key privately on the worker. API/reviewer credentials are independently generated secrets. Do not expose tokens via query strings or VITE variables.
2. Deploy API/image with the worker gate left disabled. API pre-deploy runs `python -m scripts.hosted migrate`: Alembic business migrations and explicit PostgreSQL checkpoint setup. Serialize migration operations; do not run concurrent deploy migrations. `/api/v1/readyz` checks business-schema readiness, not worker/OpenAI readiness.
3. Explicitly register the reviewed unchanged demo policy with `python -m scripts.hosted register-policy --confirm-policy-version policy-1.1-demo`. Provision authorized vendor/PO master data separately. Disposable local-demo reset scripts refuse remote databases and must never be repurposed for hosted financial history.
4. Confirm worker model access, secrets, direct DB session semantics, backups/retention and the reviewed master/policy data. Only then set PS1_ENABLE_WORKER=1 and start the separate worker. PS1_POLICY_VERSION must match the registered immutable version. Default gate exits without claiming jobs; a disabled Render worker will fail startup until an operator deliberately activates it. Do not provision the worker before planning that operational sequence.
5. Rehearse H1/E1/E2/E3/E4 on disposable hosted test data, browser review, SSE reconnection and post-commit crash recovery before opening user access. Streaming uses Authorization headers, no-store/no-buffering and keepalives; validate the actual hosted proxy behavior. No public invoice URL is issued.

The price snapshot supplied in the image is dated 2026-11-12. Estimates disclose that date; actual billing remains unknown. Update reviewed rates separately if needed, without changing financial policy. No payment or email transport exists.

Limits: Docker is unavailable on the implementation machine, so image build and Render Blueprint deployment were not executed. Container/host memory capacity, TLS/reverse-proxy behavior, backups, secret rotation, retention, dedicated DB role privileges and deployed reviewer identity still require validation. The local single-reviewer bearer boundary is suitable for the scoped demonstration, not multi-tenant production identity. Do not interpret local browser tests as hosted acceptance.
