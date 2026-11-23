# Run locally

[Project guide](../README.md) · [Documentation](README.md) · [Verification](DEVELOPMENT.md)

These Windows CMD instructions create a separate, marked local demonstration with synthetic masters and PDFs. They do not seed completed decisions. If you already have a working workspace, keep its name/configuration and skip creation; do not reset its records to install an update.

## Prerequisites

- Python 3.12 or newer and `uv` (the verified environment uses Python 3.12).
- Node.js/npm (the verified environment uses Node 24).
- Native PostgreSQL running on loopback, with a database/user that can create schemas. Demo tooling checks the actual server address and refuses remote/tunnel targets.

Confirm your tools:

```cmd
uv --version
node --version
npm --version
psql --version
```

The project cluster used for verification runs at `127.0.0.1:55432`, with role `ps1` and database `postgres`. These are local development defaults, not a database automatically created by the app. Configure your own local database below if they do not exist.

For a fresh installation, an administrator can create a dedicated local role/database in PostgreSQL's SQL Shell once:

```sql
CREATE ROLE ps1 LOGIN PASSWORD 'replace-with-a-strong-local-password';
CREATE DATABASE ps1_demo OWNER ps1;
```

Reuse existing suitable roles/databases rather than rerunning creation. Use your server's actual port. In each backend CMD window, set a loopback URI for that dedicated database (URL-encode special password characters):

```cmd
set "PS1_DEMO_DATABASE_URL=postgresql+psycopg://ps1:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/ps1_demo"
```

Keep the real URI private. Do not point demo or test commands at Supabase/production. Backend demo operations use the generated workspace configuration, not an unrelated hosted `.env` file.

## Install dependencies

From the repository root:

```cmd
cd backend
uv sync --locked
```

In a separate CMD window at the repository root:

```cmd
cd frontend
npm.cmd ci
```

Let `uv` manage `backend/.venv`. If you activated a different root `.venv`, deactivate it first to avoid the environment-mismatch warning. You do not need to activate a venv when using `uv run`.

## Create a personal-key role workspace

From **backend**, create a new workspace once:

```cmd
uv run python -m scripts.demo create --name assignment-local --mode reviewer --roles
```

This runs migrations through the current head, creates durable checkpoints, seeds synthetic vendors/POs and generates sample PDFs plus app tokens in ignored `.local/demos/assignment-local/`. It generates an encryption secret for that workspace but does not copy an operator OpenAI key or invoke extraction. The historical mode name `reviewer` means personal extraction credentials; the invoice submitter supplies the key, not finance.

Creating an existing active name is refused. Choose a new name only when you want a separate dataset. Credentials and invoice identities are not interchangeable across workspaces.

## Start three terminals

**Terminal 1 — backend API**, from backend:

```cmd
uv run python -m scripts.demo api --name assignment-local
```

**Terminal 2 — persistent worker**, from backend:

```cmd
uv run python -m scripts.demo worker --name assignment-local --enable-processing
```

**Terminal 3 — frontend**, from frontend:

```cmd
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. API liveness/readiness are at **http://127.0.0.1:8000/api/v1/healthz** and **/api/v1/readyz**. The API root `/` is not a webpage and may return Not Found. The worker is usually quiet when idle; keep it running alongside the API.

If those ports are occupied by your existing app, reuse that app or choose a matching alternate pair. For the requested frontend port 5280 with the default API port:

```cmd
npm.cmd run dev -- --port 5280 --strictPort
```

If the API also uses a different port, pass `--port 8110` to its demo command and set `PS1_DEV_API_PORT=8110` in the frontend terminal before starting Vite. This changes the development proxy, not authentication or the database.

## Sign in and process a PDF

From backend, open the generated credentials file in your local editor:

```cmd
notepad ..\.local\demos\assignment-local\backend.env
```

Do not share or commit the file. Use only the appropriate value:

| Setting                          | Purpose                                         |
| -------------------------------- | ----------------------------------------------- |
| `APP_API_TOKEN`                  | Primary submitter app login                     |
| Values in `SUBMITTER_API_TOKENS` | Other independently named submitter logins      |
| `REVIEWER_API_TOKEN`             | Financial reviewer app login, in a separate tab |
| `BYOK_ENCRYPTION_KEY`            | Server-only; never enter it in the UI           |

1. Sign in as submitter through **Workspace access token → Connect**.
2. Open **OpenAI connection**, enter your own provider key, click **Connect OpenAI**, and select an offered model.
3. Use **Continue to submit invoice**, choose a generated PDF from that workspace, and submit it. This explicitly starts potentially billable extraction.
4. In a separate reviewer tab, connect using the reviewer app token to inspect POs and resolve exceptions. Finance needs no OpenAI key.

The complete [screen navigation and tutorial](../README.md#complete-app-navigation) covers ownership, key expiry, PDF limits, vendors, PO creation and review. Optional **Get demo access** can be enabled by adding `PUBLIC_DEMO_ACCESS=true` to this role/personal-key workspace's ignored backend.env and restarting its API. It intentionally shares the two designated assignment identities and requires no operator OpenAI key. Keep synthetic documents only in public assignment workspaces.

## Charge-free fixture workspace

Use a separate name for explicit mock extraction:

```cmd
uv run python -m scripts.demo create --name assignment-mock --mode mock --roles
```

Run its API/worker with `--name assignment-mock` in place of the personal-key name, after stopping only your own old API/worker. A workspace's mode is fixed; do not edit an existing personal-key workspace into mock mode. This mock role profile uses privately assigned app tokens; the public-token disclosure requires personal-key mode.

Mock mode accepts only its exact generated fixture PDFs and labels their extraction. Resaving changes the content hash; unrelated PDFs fail with a specific processing reason. PDF intake, worker execution, verification, rules, review and allocations still execute; there is no fresh OpenAI call.

## Fixture sequence

For exact fields to create your own happy-path and edge-case PDFs, use [the manual invoice sheet](DEMO_INVOICES.md). It includes matching PO/vendor values, GSTINs, tax calculations, dependencies and the expected final balances.

For a fresh demonstration, newly created disposable role workspaces enable **Overview → Reset demo data** for the reviewer. This is separate from `scripts.demo reset`, which removes a marked local workspace's schemas after its processes are stopped. The UI reset keeps the existing workspace/credentials and restores the prepared three vendors/four POs with zero approvals. It deletes all submitted PDFs, history, reviews, approvals, custom masters and OpenAI connections; every submitter must reconnect OpenAI. It requires typed **RESET DEMO**, refuses active workers and changed previews, and retains replay receipts.

For a hosted assignment workspace, apply the reviewed migration through **0011_demo_reset** first, then explicitly set **DEMO_RESET_ENABLED=true** on the API with **ACCESS_MODE=roles**, its reviewer credential and the existing dedicated **DATABASE_SCHEMA**. Leave it false when history must be retained. Keep the worker configured for the restored **policy-1.1-demo** baseline. Normal API/worker code deployment and migrations are separate operations; this feature does not activate a worker, change static tokens or run a model. Public reviewer access shares reset authority when enabled. No existing hosted/local records are reset merely by installing this code or migrating.

If reset says a worker is processing, wait for it to finish; an expired lease alone is not proof the worker stopped. If activity changed, refresh the preview and confirm again. If a response was lost, retry the same dialog/request so the original receipt is replayed without clearing newer work.

The run's physical ownership lock blocks a live owned worker. As with ordinary crash recovery/disconnect, a previously dispatched OpenAI request can still complete and incur charges after a database connection disappears; deleting the stored connection cannot cancel that external request. Ownership fencing prevents stale processing from writing back into the reset workspace.

| PDF                      | Expected behavior with the prepared masters                                              |
| ------------------------ | ---------------------------------------------------------------------------------------- |
| `H1.pdf`                 | Approve ₹11,800 once on PO-001; remaining cap ₹38,200                                    |
| `E1-prior.pdf`           | Process this ₹70,000 partial invoice before E1                                           |
| `E1.pdf`                 | ₹35,000 against ₹30,000 remaining: review with ₹5,000 excess, no allocation              |
| `E2.pdf`                 | Pause for substantiated PO selection; finance rationale/resume revalidates current terms |
| `E3-text.pdf`            | After H1, reject normalized duplicate `INV 001` without a second allocation              |
| `E3-scan.pdf`            | Conservative review when the scanned identity is not locally corroborated                |
| `E4.pdf`                 | Review a bank-last-four mismatch without posting funds                                   |
| `PO-created-invoice.pdf` | Create its supporting PO first, as described below                                       |

For `PO-created-invoice.pdf`, finance creates **PO-CREATED** for **Aster Office Supplies**, issue date **2026-10-01**, one **PAPER / Office paper** line with quantity **20**, net unit price **1000** and tax **18%**. Gross is **23600.00**; authorize that cap and enter a rationale. The sample invoice requests ten units / **11800.00**. It can approve once if all checks pass and leaves **11800.00**. Creating the PO does not process the invoice. New demo creation generates this input; migration alone does not add files to older folders.

Finance can register other vendors and create orders through the UI. The fixture mock extractor still accepts only its prepared PDFs; arbitrary custom invoices require a real personal-key workspace. An already approved invoice identity remains a duplicate, even if uploaded again under another submitter.

## Populate hosted demo masters

The operator can add the prepared synthetic vendor/PO dataset directly to the hosted PostgreSQL database. This is a separate command from the loopback-only local demo tooling. It does not transfer local invoices, keys, runs or approvals. Use the existing ignored deployment environment file with the intended DATABASE_URL and explicit DATABASE_SCHEMA; migrate it through the current head **0011_demo_reset** first. Never publish that file or paste credentials into SQL Editor.

From **backend** in CMD, preview the changes for schema **ps1_app**:

```cmd
uv run --locked --env-file ..\.local\deployment.env python -m scripts.hosted seed-demo --confirm-demo ps1-demo-v1 --confirm-schema ps1_app
```

The default **DRY_RUN** checks the connection's schema, migration head, unchanged `policy-1.1-demo` and existing masters without writing data. Review its counts and PO references. If this is the intended target, apply the same dataset:

```cmd
uv run --locked --env-file ..\.local\deployment.env python -m scripts.hosted seed-demo --confirm-demo ps1-demo-v1 --confirm-schema ps1_app --apply
```

Replace `ps1_app` in the command only when your configured dedicated schema differs. This operation reads only explicitly supplied environment values; it does not fall back to backend/.env. It adds missing compatible records and immutable creation audits in one locked transaction. Repeating it preserves IDs, allocations, counters and history. Conflicting policy, identity, status or PO terms stop the entire setup; no existing vendor is reactivated and no budget is reset.

| Approved synthetic vendor | PO reference | Authorized gross cap | Line tax | Full line gross |
| --- | --- | --- | --- | --- |
| Aster Office Supplies | PO-001 | INR 50,000.00 | 18% | INR 118,000.00 |
| Aster Industrial Supplies | PO-PARTIAL | INR 100,000.00 | 0% | INR 100,000.00 |
| Aster Technology Services | PO-SELECT-001 | INR 25,000.00 | 18% | INR 118,000.00 |
| Aster Technology Services | PO-SELECT-002 | INR 40,000.00 | 18% | INR 118,000.00 |

All four orders are issued **2026-10-01**, OPEN, INR, with one **PAPER / Office paper** line: quantity **100**, net unit price **1000**. Their independent spending caps are unchanged. The dataset uses synthetic tax IDs and bank last-four 1234. Fresh masters have zero allocations; the policy is registered only if absent and identical values are required if present.

Refresh **Purchase orders** as the reviewer to see them. Upload the actual generated PDFs as a submitter using a personal OpenAI connection and a running hosted worker. Seeding neither activates the worker nor calls OpenAI. For E1, genuinely process `E1-prior.pdf` before `E1.pdf`; for E3, process H1 first. `PO-CREATED` remains a separate reviewer-created order exercise. The add-only seeder does not reset history or balances; use the separately enabled reviewer reset described above for that purpose. No pre-approved invoice history is seeded.

## Update an existing local workspace

Stop only that workspace's API/worker with Ctrl+C. From backend:

```cmd
uv sync --locked
uv run python -m scripts.demo migrate --name assignment-local
```

Restart the same API/worker commands, update frontend dependencies with `npm.cmd ci`, restart Vite and reconnect. Migration validates the loopback server/schema ownership marker, upgrades business/checkpoint schemas and preserves records; it does not reseed or reset. Current head is **0011_demo_reset**. API and worker need matching reviewed source versions. Downgrade refuses while BLACKLISTED vendors would lose their status.

The CLI `scripts.demo reset` is deliberately separate and removes only a specifically confirmed disposable demo's schemas. The new reviewer UI reset is an in-place, confirmed data reset when explicitly enabled; it retains schemas and migration metadata. Neither reset is an installation or migration step. Hosted operations and credentials belong to the operator, outside these local commands.

See [DEVELOPMENT.md](DEVELOPMENT.md) for regression/build checks and [the troubleshooting table](../README.md#troubleshooting) for access, upload and queued-run failures.
