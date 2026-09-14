# Local development

Use Node.js **24**, Python **3.12**, and Docker with Compose v2 (for PostgreSQL).
The commands below target Bash on Linux/macOS or WSL. Run them from the repository root.

## Clean checkout

```bash
npm ci
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cp .env.example .env
cp .env.example apps/web/.env.local
set -a
source .env
set +a
```

Activate `.venv` in every terminal running backend commands. Root npm scripts use
`python` from your active environment. Python does not automatically load `.env`;
source it as above. Next.js reads `apps/web/.env.local` separately. When changing
`NEXT_PUBLIC_API_BASE_URL`, update that file and restart/rebuild the web app.
The environment/database settings reserve the future persistence boundary; the
current API and simulation do not require or connect to PostgreSQL.

## Run

```bash
npm run dev:api
```

In another terminal:

```bash
npm run dev:web
```

Open http://localhost:3000 and API documentation at http://localhost:8000/docs.
Run `npm run health:api` with the virtual environment active to check `/health`.
This checks the API process only, not database readiness. Override `CLIOVA_API_URL`
for a different API address. The existing Command Center still uses placeholder data.

Run a headless simulation without either server or PostgreSQL:

```bash
python -m cliova.cli --seed 42 --years 100
```

## Validate before opening a PR

```bash
npm run check
```

| Command | Checks |
| --- | --- |
| `npm run check:web` | ESLint, generated Next.js route types, TypeScript, production build |
| `npm run typecheck:web` | Route types and TypeScript, including on a clean checkout |
| `npm run check:backend` | Ruff lint/format, strict mypy, database-free tests |
| `npm run test:backend` | Unit/API tests without PostgreSQL |
| `npm run format:backend` | Apply Python formatting |
| `npm run test:integration` | Explicit PostgreSQL smoke/integration tests |

There is no separate browser test suite yet. The web gate uses lint, types and a
production build; add behavior tests alongside future interactive functionality.
CI reports Web, Python and PostgreSQL jobs separately on pull requests and main.

## PostgreSQL integration tests

```bash
npm run db:up
export CLIOVA_TEST_DATABASE_URL=postgresql://cliova:cliova@localhost:5434/cliova
npm run test:integration
npm run db:down
```

Compose waits for PostgreSQL readiness and binds only to `127.0.0.1`, default port
5434. Change `CLIOVA_POSTGRES_PORT` in `.env` and the database URLs together if that
port is occupied. Use disposable development/test databases only. Credentials in
`.env.example` are local examples, never production secrets.

Integration tests are marked `integration`; regular backend checks deselect them.
An explicitly requested integration run fails if its URL is missing or PostgreSQL
is unavailable. The initial smoke test creates a temporary table and verifies
transaction rollback; it does not create application schemas. Future persistence
integration tests belong under the same marker. CI uses an isolated service database.
`db:down` retains the named volume; removing volumes deletes local database data.
