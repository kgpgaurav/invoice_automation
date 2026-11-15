# Run the invoice workspace locally

## Individual submitters and financial reviewer

Use the role-separated workspace for personal invoice access. From backend in CMD, create it once if it does not already exist:

```cmd
uv run python -m scripts.demo create --name local-roles --mode reviewer --roles
```

Stop the old API and worker with Ctrl+C. Start these in two separate CMD windows from backend:

```cmd
uv run python -m scripts.demo api --name local-roles
```

```cmd
uv run python -m scripts.demo worker --name local-roles --enable-processing
```

Keep the frontend on http://127.0.0.1:5173 and refresh. The operator opens `.local/demos/local-roles/backend.env` privately and distributes only the intended person's token; never share the whole file. Sign in through **Workspace access token** using that person's credential:

| Credential | Identity and allowed screens |
|---|---|
| APP_API_TOKEN | First submitter (`submitter`): Process Invoice, My Invoices, their own status/source/usage |
| Value for `submitter-b` inside SUBMITTER_API_TOKENS JSON | Second submitter: same screens, separate invoice history |
| Value for `submitter-c` inside SUBMITTER_API_TOKENS JSON | Third submitter: same screens, separate invoice history |
| REVIEWER_API_TOKEN | Financial reviewer: Review Queue, workspace Invoice History, Purchase Orders and Overview; no upload or OpenAI key form |

The server determines the role; there is no permission-granting role dropdown. In role mode, the reviewer signs in once using the reviewer credential and does not re-enter it in each review form. Only submitters connect their OpenAI key/model before live upload. The internal configuration name `OPENAI_CREDENTIAL_MODE=reviewer` is retained from the evaluator-key feature; it does not mean that a financial reviewer needs an OpenAI key.

The agreed case-study setup has three fixed submitter slots and one reviewer. Tokens are generated once and stay unchanged across restarts. Privately assign one submitter slot per person; sharing a token shares that slot's invoice history. The local-roles workspace has the third slot added without changing its existing credentials or data; restart its API/worker to load that configuration. New `--roles` workspaces generate all four tokens. Older shared demos keep their existing behavior. Future sign-in improvements are proposed in README and are not required to run this private demonstration.

Each submitter uses their own OpenAI account/key. They connect once for multiple invoices in the same tab, up to 24 hours, rather than entering a key for every invoice. Refresh, a new/closed tab, explicit disconnect or expiry requires reconnecting for new uploads. Closing/refreshing does not revoke a connection already bound to submitted jobs. Personal app tokens, OpenAI keys and the server encryption secret are different credentials; [ROLE_ACCESS.md](ROLE_ACCESS.md#personal-credentials-after-deployment) explains who generates each and the hosted API/worker flow.

These are individually issued private access credentials, not email/password accounts or public signup. For hosted role mode set `ACCESS_MODE=roles`, give each person a unique secret, and configure SUBMITTER_API_TOKENS as a JSON mapping from stable safe actor IDs to secrets. APP_API_TOKEN is reserved for the default `submitter` identity. Never share one submitter's token among people or reuse their actor ID for another person. Token rotation preserves the actor ID so invoice ownership remains stable. Reviewer and submitter credentials must be distinct.

Existing shared-mode demos retain their earlier broad workspace visibility for compatibility; they do not provide person-level isolation. Old ownerless runs are reviewer-only when a migrated workspace enables role mode; no old ownership is guessed. The fresh local-roles workspace starts empty and does not copy private PDFs or keys from other demos. Details, PDF, events and SSE enforce ownership on the server; foreign resource IDs return 404. Finance features return 403 to submitters even if a URL is entered directly. The submitter's limited detail response omits PO balances/ledger, reviewer candidates and finance audit fields.

Browser role checks: from backend, `uv run python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273`. This creates its own mock-extraction role workspace, verifies two-person isolation and authorized review/resume, then removes only its test schemas/processes. It makes no live OpenAI calls. Shared-mode regressions use the same command without `--roles`.

## Reviewers use their own OpenAI key and model

Create a separate local workspace once, from backend in CMD:

```cmd
uv sync --locked
uv run python -m scripts.demo create --name local-reviewer --mode reviewer
```

This creates fresh synthetic masters, migrations through 0008, checkpoints and private workspace/reviewer credentials. It generates a stable encryption secret shared by that demo's API and worker, and does not copy your OPENAI_API_KEY. No model is called and no completed run is seeded. If an active workspace with this name already exists, retain it rather than recreating/resetting its history.

Stop your old API/worker with Ctrl+C. In separate CMD windows from backend, start:

```cmd
uv run python -m scripts.demo api --name local-reviewer
```

```cmd
uv run python -m scripts.demo worker --name local-reviewer --enable-processing
```

Keep the frontend on http://127.0.0.1:5173. Connect using APP_API_TOKEN from `.local/demos/local-reviewer/backend.env`, open Process Invoice, enter your **OpenAI API key** in **Your OpenAI connection**, and select an offered model. Workspace/reviewer tokens and the OpenAI key are three different credentials. The offered models are the intersection of the key's Models API result and the app-tested `gpt-6-luna` / `gpt-6.1-terra` list. Listing alone does not establish Responses permission, available credit or financial correctness. Uploading an invoice explicitly starts paid extraction under the supplied key. Reviewer mode never uses an operator-key fallback.

Keys are encrypted in the database with access expiring after 24 hours. **Disconnect OpenAI**, or workspace Disconnect, revokes the session and erases its active ciphertext; in-flight calls can finish and incur charges. The key and opaque connection are not saved in browser storage. Reload requires reconnecting; merely closing/reloading the tab is not guaranteed to revoke an already submitted server session. Existing queued jobs retain their original binding until expiry/revocation. Changing model affects new runs only. A failed expired-key run retains the PDF and can be submitted as a new run after reconnecting; no automatic paid resubmission occurs.

To upgrade an older marked local/mock/live demo without deleting data, first stop its API/worker, then run `uv run python -m scripts.demo migrate --name <existing-name>`. This verifies the actual loopback server and schema ownership marker before upgrading the selected schema and checkpoints. Do not change an existing workspace's credential mode while work is queued; create a fresh reviewer-mode workspace instead.

Hosted configuration: `OPENAI_CREDENTIAL_MODE=reviewer`, the same private stable `BYOK_ENCRYPTION_KEY` on API and worker, a shared session-preserving DATABASE_URL, and independent APP_API_TOKEN/REVIEWER_API_TOKEN. Generate a Fernet key privately with `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; paste it into server secrets, never into chat/source/frontend variables. Omit the operator OPENAI_API_KEY in reviewer deployments. Run `scripts.hosted migrate` and provision the immutable policy/masters before explicitly activating the worker. Idle worker cleanup runs every minute; `scripts.hosted purge-credentials` also removes expired ciphertext. If processes are down, physical cleanup waits for restart/operator cleanup, but expiry still blocks new calls. Hosted deployment, TLS and Vercel upload/worker limits remain separate unresolved gates in DEPLOYMENT.md.

## Upload returns HTTP 422

An HTTP 422 from `POST /api/v1/invoices/process` is an intake-validation failure before a run is queued or OpenAI is called. The PDF must be intact, unencrypted (including owner-only encryption), and contain one to five pages. Oversize uploads return 413. Request-field validation can also return 422; the response JSON identifies the failing field.

The frontend now displays the backend's structured `detail.message` instead of hiding it behind `Request failed (422)`. Refresh the frontend to load this fix. If the cause is still unclear, inspect F12 → Network → the failed POST → Response and share only that JSON, without request headers, credentials or PDF contents. Do not change credentials or reset a workspace to fix document validation.

## Mock mode, real OpenAI calls and unsupported uploads

`--mode mock` never calls the real OpenAI API. It supports only the exact generated scenario PDFs in that demo's fixture set; resaving/changing a PDF changes its hash. A resume or an unrelated invoice PDF is not analyzed or classified in this mode. Such an upload now has a readable `MOCK_FIXTURE_NOT_FOUND` explanation. This is a processing-mode failure with no financial decision, not a claim that the document was recognized as a non-invoice. Existing recorded fixture-adapter HTTP-422 failures receive the same read-only explanation; original history is not rewritten.

For the updated explanation, stop only your API and worker with Ctrl+C, restart their existing `scripts.demo api --name local` / `scripts.demo worker --name local --enable-processing` commands, then refresh the UI and reconnect using `.local/demos/local/backend.env`'s generated APP_API_TOKEN. Do not reset/recreate the demo or re-upload a private document just to recover an error explanation.

To explicitly use the already implemented live OpenAI pipeline, first revoke/replace any exposed key as described in SECURITY.md. Configure OPENAI_API_KEY and an account-accessible OPENAI_MODEL privately in ignored backend/.env. Then, from **backend in CMD**, create a separate workspace once:

```cmd
uv run python -m scripts.demo create --name local-live --mode live
```

After stopping the old local API/worker, run these in two separate CMD windows from backend:

```cmd
uv run python -m scripts.demo api --name local-live
```

```cmd
uv run python -m scripts.demo worker --name local-live --enable-processing
```

Keep the frontend on 5173, connect using the new `.local/demos/local-live/backend.env` APP_API_TOKEN, and deliberately upload a synthetic H1 first. A live upload sends its PDF to OpenAI and can incur charges; creating the workspace alone does not extract a document. Live mode checks model access and never silently falls back to mock data. Missing invoice fields/evidence require review; an explicit resume/non-invoice classifier is not implemented. General commercial-layout verification remains deferred.

Browser regressions can run alongside your current app without taking its ports: from backend, `uv run python -m scripts.browser_checks --api-port 8100 --ui-port 5273`. The runner checks for free ports before provisioning its own disposable schema and resets only its own data/processes. Defaults remain 8000/5173 for the original instructions below.

Phase 1 UI update (2026-11-13): follow the startup commands below unchanged. First complete the operator credential-rotation steps in [SECURITY.md](SECURITY.md) if the previous ZIP contained your .env. No key rotation is claimed by this repository change. Local demonstration credentials and the OpenAI key are separate; copy only the intended application/reviewer credential into its input.

After connecting, `/` opens Review Queue when actual review items exist, otherwise Overview. Navigation provides Review Queue, Process Invoice, Invoice History, Purchase Orders and Overview. Uploads start from **Process Invoice**, then **Process invoice** in the upload form. The reviewer form requires **Review rationale**, the separate reviewer credential and one of the backend-permitted actions. Changing a screen or navigation item grants no authorization.

Open an invoice to inspect the decision, recorded rule checklist and assessment-time balance breakdown for an overrun. Unrecorded individual checks remain **Not evaluated**. A clean approval's passed checks are certified by its committed VALIDATED assessment and ledger; these are not newly invented check-execution logs. Expand the supporting record to inspect provenance and revision. Verified field-page buttons navigate the original PDF; precise highlights remain unavailable. Tablet/mobile content stacks; wide data tables scroll inside their labelled region.

**Inspect PO ledger** opens read-only current PO data plus immutable approved-invoice allocations. Historical assessment balances remain on the invoice; today's cap does not rewrite them. The scenario gallery explains local PDFs and predecessor dependencies; it cannot seed, reset, download private files or execute cases. H2 is explicitly unavailable. See [Phase 1 handoff](PHASE1.md) for the exact changes, screenshots and verification limits.

Run from this repository. Prerequisites: Python 3.12, uv, Node 24 (or a supported current Vite runtime), and a dedicated native PostgreSQL 17 instance on loopback. The verified project cluster uses port 55432, role ps1, database postgres. The existing port-5432 service is not used. See DEVELOPMENT.md's native PostgreSQL setup if .local/pgdata does not exist; never initialize over an existing cluster. The disposable demo guard checks the actual server address and intentionally refuses remote/tunnel/container-address targets.

If this project's existing cluster is stopped, from repository root:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' -D .local/pgdata -l .local/postgres.log -o '-h 127.0.0.1 -p 55432' -w start
```

Install and create a clean **mock-extraction** workspace:

```powershell
Set-Location backend
uv sync --locked
uv run python -m scripts.demo create --name local --mode mock
```

The command creates a new, marked ps1_demo_<id> schema, business migrations through 0006, its separate PostgreSQL checkpoint schema, an unchanged immutable policy, and synthetic vendor/PO masters with zero committed balances. It generates actual PDFs and expected fields under .local/demos/local. **No completed financial run is seeded.** If your local connection differs, set PS1_DEMO_DATABASE_URL explicitly to its postgresql+psycopg URI before creation. No OpenAI key is needed for mock mode. Unknown PDFs in mock mode fail rather than receive invented extraction results.

Start two separate terminals from backend:

```powershell
# Terminal 1 — API, bound to loopback only
uv run python -m scripts.demo api --name local
```

```powershell
# Terminal 2 — explicit worker activation, limited to the marked demo
uv run python -m scripts.demo worker --name local --enable-processing
```

Start the frontend in a third terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Open .local/demos/local/backend.env **locally in your editor**, copy APP_API_TOKEN into **Workspace access token**, and connect. Use REVIEWER_API_TOKEN only in the review panel's separate reviewer field. Never put OPENAI_API_KEY in the browser, chat, VITE variables, URL or localStorage. Credentials are held only in tab memory; refreshing preserves the run URL but requires reconnecting.

Upload the generated PDFs through the UI in this order:

| PDF | Procedure / expected result |
|---|---|
| H1.pdf | Clean source; approve INR 11800.00 once on PO-001; remaining 38200.00 |
| E1-prior.pdf | Actually upload/process this 70000.00 partial invoice first; wait for approval |
| E1.pdf | Next 35000.00 against the remaining 30000.00; review, exact 5000.00 excess, no allocation |
| E2.pdf | Review; choose one of PO-SELECT-001/002, enter reviewer token and reason; resume revalidates and approves only if all rules still pass |
| E3-text.pdf | After H1: INV 001 normalizes to approved INV-001; reject, zero second allocation |
| E3-scan.pdf | Conservative review. Model transcription alone cannot corroborate the scanned identity; this is not a claimed scanned-duplicate rejection |
| E4.pdf | Printed last4 9876 vs master 1234; bank-change review, no funds posted |

Mock responses are explicitly labelled in the run and history. All PDF intake, evidence verification, financial checks, interrupts, reviewer actions and ledger transactions still execute. The fixture responses are not claimed as live model calls or field-accuracy evaluation. Unexplained H2 rounding is not approved.

For a live workspace, first configure the one OpenAI key and explicit model in ignored backend/.env (the measured initial candidate is gpt-6-luna; account access is checked at worker startup). Create **a separate** name with `uv run python -m scripts.demo create --name local-live --mode live`; run its API/worker after stopping the other demo's processes. Copy only that workspace's access credentials in the browser. Every live upload can incur model cost, at most two reserved attempts including repairs/recovery. Live mode never falls back silently to fixture responses.

Stop API/worker/Vite with Ctrl+C before resetting. Explicitly reset only your disposable schema:

```powershell
Set-Location backend
uv run python -m scripts.demo reset --name local --confirm local
```

This validates the loopback target, schema prefix and ownership marker, then drops only that demo and its derived checkpoint schema. It cannot reset public or remote production history. Generated private files remain ignored; creating the same inactive name again gives fresh schemas, credentials and zero balances. Do not start the ordinary production worker against a demo configuration with a different frozen source mode.

Verification:

```powershell
# Backend, with the disposable PostgreSQL instance running:
$env:TEST_DATABASE_URL='postgresql+psycopg://ps1@127.0.0.1:55432/postgres'
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m scripts.export_openapi
# Scoped browser runner owns its API/worker/Vite children and resets its schemas:
uv run python -m scripts.browser_checks
# Optional PAID live H1 only; explicit opt-in, other scenarios skipped:
uv run python -m scripts.browser_checks --live-h1
```

The browser runner requires ports 8000 and 5173 available. On Windows it uses installed Edge; set PS1_BROWSER_CHANNEL=chrome for installed Chrome. On other systems install Playwright Chromium (`npx playwright install chromium` from frontend). Logs, credentials and traces stay under ignored .local/test-results; sanitized synthetic screenshots are in docs/screenshots. If a test fails, inspect the private per-demo playwright.log; do not share credential files or raw traces.

Frontend checks from frontend: `npm.cmd run generate:api`, `npm.cmd run build`, `npm.cmd run format:check`. Generated API files are never edited manually. Deployment topology and its unvalidated hosting/container boundary are documented in DEPLOYMENT.md. Default `python -m app.worker` remains disabled; none of these instructions provisions or exposes paid services.
