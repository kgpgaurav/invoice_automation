# Slice 1: local infrastructure and durable intake

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
