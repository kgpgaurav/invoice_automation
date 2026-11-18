# Development and verification

[Project](../README.md) · [Documentation](README.md) · [Local setup](RUNNING.md)

SPEC.md is the canonical contract; docs/DECISIONS.md records agreed refinements and unresolved questions. Read AGENTS.md before implementation. Historical operator/build journals are kept locally under ignored docs/local; they are not dependencies of this guide or the application.

## Repository map

```text
backend/
  app/                 API, worker, workflow, extraction and financial services
  alembic/versions/    ordered business-schema migrations
  scripts/             local demos, contract export and verification runners
  tests/               unit, real-PostgreSQL and opt-in live tests
  pyproject.toml
  uv.lock
frontend/
  src/                 React screens and generated API types
  tests/               browser regressions
  openapi.json
  package.json
  package-lock.json
docs/
  README.md            public documentation index
  RUNNING.md           local setup and scenario inputs
  ROLE_ACCESS.md       role/ownership contract
  SECURITY.md          credentials and public-demo boundaries
  DECISIONS.md         implementation decisions
  benchmarks/          sanitized measurements and required dated rate data
  screenshots/         synthetic UI illustrations
  archive/             historical planning references
  local/               ignored personal runbooks/build journals
SPEC.md
AGENTS.md
README.md
```

Business schema head: **0010_vendor_management**. LangGraph uses a separate checkpoint schema. PDFs are stored privately in PostgreSQL; ephemeral frontend/API disk is not authoritative.

## Backend checks

Install with `uv sync --locked` from backend. Set TEST_DATABASE_URL to a **dedicated local PostgreSQL** connection whose user can create/drop test schemas. Tests use isolated random schemas and real PostgreSQL; no SQLite fallback. Never use a hosted/production database for this suite.

Example for the project's existing verified local cluster, from backend in CMD:

```cmd
set "TEST_DATABASE_URL=postgresql+psycopg://ps1@127.0.0.1:55432/postgres"
set "PYTHONUTF8=1"
uv run pytest -q --tb=short -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

Replace the example URI with your dedicated local setup when different. Routine tests mock external model transport. Three live tests are separately opt-in and skipped by default; do not set live-test flags unless you intend provider charges.

The suite includes worker claim/lease/restart/ownership fencing, transactional events, vendor/PO races, duplicate identities, Decimal boundaries, approval rollback/replay, role isolation and provider-session handling. `tests/test_health.py::test_migration_roundtrip_and_metadata_parity` upgrades, compares SQLAlchemy metadata, downgrades and re-upgrades in a disposable schema. The vendor tests also verify refusal of a lossy BLACKLISTED downgrade. Do not run migration downgrade against application data to exercise this check.

## Generated contracts and frontend checks

From backend:

```cmd
uv run python -m scripts.export_openapi
```

From frontend:

```cmd
npm.cmd ci
npm.cmd run generate:api
npm.cmd run format:check
npm.cmd run build
```

The OpenAPI exporter does not connect to a database. Decimal request fields remain strings. Regenerate before browser tests: rewriting OpenAPI during a Vite session can trigger a page reload and clear the intentionally tab-only authentication state.

## Browser checks

Install dependencies and an available Chrome browser. From backend in CMD:

```cmd
set "PS1_BROWSER_CHANNEL=chrome"
uv run python -m scripts.browser_checks --roles --api-port 8100 --ui-port 5273
uv run python -m scripts.browser_checks --api-port 8100 --ui-port 5273
```

Set PS1_DEMO_DATABASE_URL to your dedicated loopback database if the default 55432 connection is not available. Use free test ports, separate from your running preview. Each runner owns its API/worker/Vite processes and marked disposable schemas, then cleans only those. The role runner covers submitter/reviewer access; the other covers shared/provider/workflow cases and skips role cases already run separately. Both use explicitly labelled MOCK_OPENAI and incur no extraction charges.

## Recorded application verification

Latest financial/vendor milestone, **18 November 2026**, before this documentation cleanup:

| Check                                                   | Recorded result                                                     |
| ------------------------------------------------------- | ------------------------------------------------------------------- |
| Full backend suite                                      | **312 passed, 3 opt-in live skips**, 355.13s                        |
| Vendor/totals/endpoint subset                           | **47 passed**, 38.72s                                               |
| Role browser suite, including confirmed outcome wording | **17 passed**, 1.5m                                                 |
| Shared/provider/workflow browser suite                  | **18 passed**, 2.8m; 17 role skips covered by the separate run      |
| Ruff / Python formatting                                | Passed for 107 Python files                                         |
| Migrations                                              | Full roundtrip/metadata parity and blacklist downgrade guard passed |
| OpenAPI / TypeScript generation                         | Repeated generation produced identical hashes                       |
| Frontend format / TypeScript / production build         | Passed; Vite 13.31s                                                 |

Coverage includes reviewer vendor registration/status, duplicate-name/tax rejection, immutable audit, injected rollback, stale/blacklisted vendor checks under locks, exact net/tax/gross totals, independent PO caps, lost-response replay and fixture invoice allocation. Tests preserve earlier worker, financial, ownership and frontend behavior. No model confidence or generated verification flag authorizes approval.

The existing local preview was migrated/reloaded without changing its records, budgets or credentials. Manual 1440/390px screenshot checks used synthetic data or unsaved/cancelled drafts. These are local results, not proof of active hosted processing or broader invoice accuracy. The pre-existing PDF.js chunk-size warning remains. H2's fully justified rounding fixture, broader commercial/scan evaluation, hosted recovery acceptance and actual billed-cost measurement remain open.

This documentation-only update changes guides/ignore rules, not application code or schema. Its relevant checks are Markdown links/anchors, navigation against source, preserved local-document hashes, tracked/ignored boundaries and Git whitespace; it does not repeat paid or full application execution. See [benchmark evidence](benchmarks/README.md) for separately dated sanitized live measurements.

## Working conventions

- Preserve financial tolerances, identity normalization and the locked at-most-once approval transaction unless an explicit contract change is recorded.
- Keep production processing opt-in and OpenAI as the only provider. Never masquerade cached/mock extraction as live.
- Keep actual secrets in ignored environment files/server settings, with no VITE_ secret variables.
- Keep personal deployment/key runbooks, traces and build journals in ignored docs/local or .local. Public docs must not depend on them.
- Keep the rate JSON in docs/benchmarks tracked: demo/live-test scripts read it. `.gitignore` is not an access-control mechanism or a Git-history purge.
