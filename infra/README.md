# Infrastructure

`compose.yaml` provides local PostgreSQL 17 on loopback port 5434 with a readiness
check and named volume. Use root `npm run db:up` / `npm run db:down` commands.
See [CONTRIBUTING.md](../CONTRIBUTING.md) for configuration and integration tests.

The current simulation and API run without a database. This service establishes
the development/test infrastructure for future persistence, not application storage.
Keep deployment and scheduling separate from simulation domain rules.
