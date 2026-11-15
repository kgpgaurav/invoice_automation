# Credential exposure and safe sharing

## Individual private-workspace access (2026-11-14)

`ACCESS_MODE=roles` derives submitter/reviewer permissions from distinct operator-issued access credentials. Each submitter has a stable identity and can read only their own runs, PDFs, events, stream and limited invoice details. Search/counts/cursors and intake idempotency are owner-scoped. Finance/review endpoints require reviewer permission. Owners of runs/provider sessions are immutable; a bound provider session must have the same owner as its run. A leaked run ID or opaque provider capability alone is insufficient to act as another submitter. Ownerless legacy runs are reviewer-only; no ownership is inferred from source/PDF/model values. Client-supplied owner/role parameters grant no rights.

APP_API_TOKEN identifies the default submitter. SUBMITTER_API_TOKENS maps other stable IDs to individual secrets. REVIEWER_API_TOKEN grants finance access. Never share a submitter token, collide role credentials, or reassign a retired actor ID to another person. Keep one person's actor ID when rotating their credential. Configuration validation suppresses secret-bearing input values in errors. The UI loads allowed navigation from authenticated `/api/v1/access`; backend checks remain authoritative, including direct URLs. Switching credentials clears role/provider state before the new identity is rendered. Financial reviewers do not enter provider keys and submitters do not see reviewer credentials/forms.

This is private-workspace, token-based identity, not public signup, secure-cookie login, a full tenant system or RLS. Default shared mode is preserved for existing demos and must not be described as person-level isolation. Hosting must explicitly enable role mode and provision individual identities. Public session/authentication, rate controls, credential lifecycle and database privileges remain deployment work.

## Reviewer-supplied key mode (2026-11-14)

The user explicitly authorized encrypted temporary storage (maximum 24-hour access) for reviewer-supplied OpenAI keys. This is an opt-in extension; ordinary server-key/mock configurations remain separate. Only existing authorized workspace users can create/revoke provider sessions or submit their bound runs. An OpenAI key grants provider billing access, not workspace or financial-review authorization. This does not add public multi-tenant identity/data isolation.

Provider keys use authenticated Fernet encryption with session ID binding and a stable API/worker environment encryption secret. Opaque high-entropy session capabilities are hashed at rest. Provider secrets are not returned in responses, retained in browser storage, placed in URLs/checkpoints/events/usage, or echoed in validation errors. Session creation responses use no-store. Do not enable request-body/header capture or analytics for credential forms/endpoints at the hosting proxy. Hosted submission requires HTTPS; loopback HTTP is for local development only.

Disconnect clears active ciphertext, expiry prevents new attempts, and workers purge expired ciphertext every minute/startup; access also triggers cleanup. Downtime can delay physical cleanup. Closing a tab is not a guaranteed revocation signal; use Disconnect or revoke the project key in OpenAI. A request already dispatched can complete and be charged. Database backup copies follow the host's backup retention; deleting active ciphertext does not promise erasure of historical backups. Operators control the encryption secret and server, so this is temporary trusted-server custody, not a claim that the host cannot decrypt a key.

Keep the same encryption secret across API/worker restarts; replacing it makes existing sessions unreadable and requires reconnection. Keep hosted previews and production in separate databases/secrets. Do not configure the operator OpenAI key as a fallback in reviewer mode. Test transports use synthetic keys only; no third-party key was collected or used during implementation. Previously reported archive exposure still requires the independent rotation steps below.

Attempt authorization is serialized with disconnect in the short fenced reservation transaction. Once the attempt is reserved, it is considered started and can be billed even if disconnect follows before its network operation finishes. For Supabase deployment, credential and financial tables must not be exposed through a public Data API; use a private schema and backend-only database privileges. The browser needs no direct database credentials or Supabase API key.

The operator reported that a previously shared ZIP included backend/.env. Treat credentials in that archive as exposed. Git and Docker exclusions do not revoke credentials and do not sanitize a ZIP created by an arbitrary archive tool.

The operator must:

1. Revoke and replace the exposed OpenAI API key in the OpenAI account. Review account usage associated with that key. Update only the ignored local/server environment; never paste the replacement into chat, screenshots, source or frontend build variables.
2. Rotate exposed APP_API_TOKEN and REVIEWER_API_TOKEN independently. Replace any derived demo credentials that were shared. Restart the affected API/worker processes after updating private configuration. The application token must still be unable to submit reviewer actions.
3. Rotate any database credentials or other secrets contained in the archive. Confirm that the old credentials no longer authenticate. Do not print either old or new values during verification.
4. Remove the unsafe shared archive from distribution and request deletion of copies where possible. Deletion does not replace rotation. Do not re-share original sensitive invoices or browser traces containing credentials.

Rotation requires account/operator access and is **not claimed completed by this implementation**. Phase 1 made no live model calls. No secret values were printed or copied. Private .env files were not edited.

Verified exclusions: .gitignore excludes .env/.env.*, environments, .local databases/demo credentials, uploads, PDF documents, keys/logs, node_modules and build/test output. The intentional .env.example contains configuration names and sample descriptions, not live credentials. .dockerignore independently excludes environment files, .local, PDFs, uploads, keys, logs, repository metadata and test output. No environment file is tracked by Git. No archive was created in Phase 1.

For future sharing, construct an explicit allowlist of reviewed source, lockfiles, documentation and sanitized synthetic screenshots; inspect the archive entry list before distribution. Ordinary Windows “Send to ZIP” or a recursive Compress-Archive command does not honor .gitignore. A Git archive covers only committed tracked files, so it would omit the current uncommitted review changes and is not a complete Phase 1 package. Archive packaging and evaluator sessions remain later-phase work.

The current UI uses tab-memory bearer credentials. It never stores application/reviewer tokens in localStorage/sessionStorage or URLs; the OpenAI key stays server-side. Secure cookie sessions, expiry/CSRF/origin controls, public demo throttling and deployed identity are Phase 4 requirements, not implemented here. Do not publicly expose the local demonstration under the assumption that those safeguards exist.
