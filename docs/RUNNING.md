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

## Update an existing local workspace

Stop only that workspace's API/worker with Ctrl+C. From backend:

```cmd
uv sync --locked
uv run python -m scripts.demo migrate --name assignment-local
```

Restart the same API/worker commands, update frontend dependencies with `npm.cmd ci`, restart Vite and reconnect. Migration validates the loopback server/schema ownership marker, upgrades business/checkpoint schemas and preserves records; it does not reseed or reset. Current head is **0010_vendor_management**. API and worker both need the new blacklist validation. Downgrade refuses while BLACKLISTED vendors would lose their status.

Reset is deliberately separate and destroys only a specifically confirmed disposable demo's schemas. It is not an installation, update or troubleshooting step. Hosted operations and credentials belong to the operator, outside these local commands.

See [DEVELOPMENT.md](DEVELOPMENT.md) for regression/build checks and [the troubleshooting table](../README.md#troubleshooting) for access, upload and queued-run failures.
