# Database

Cliova uses PostgreSQL, with PostGIS only when geographic persistence needs it. Database schema migrations live in `database/migrations/` as ordered plain SQL and are applied through the existing Psycopg stack:

```bash
CLIOVA_DATABASE_URL=postgresql://... python -m cliova.infrastructure.persistence.migrations
```

From the repository root, `npm run db:migrate` invokes the same migration runner after the backend is installed. Applied filenames are recorded in `cliova_schema_migrations`; pending migrations run transactionally under a PostgreSQL advisory lock.

The database stores authoritative state and history; it does not contain hidden game rules in triggers or stored procedures unless an Architecture Decision Record explicitly justifies it. Simulation domains remain independent of SQL.

## Persistence policy for 0.1

- `cliova_worlds` stores the latest authoritative serialized `WorldState` and explicit seed/schema/simulation/RNG metadata.
- `cliova_world_snapshots` stores tick 0 and every successfully completed tick. For 0.1 snapshots are retained indefinitely; there is no compaction or archival job yet.
- queued inputs store the actual serialized `SimulationInput` payload. `submitted_tick` is queue-envelope metadata identifying the exact tick for which that input is eligible; directive lifecycle state remains the authoritative #9 model inside `WorldState` after ingestion.
- completed ticks, history events and causal IDs are retained indefinitely in 0.1.
- each serialized payload has an explicit persistence payload version. `WorldState` also retains its own simulation/schema metadata, so later database migrations and world-state migrations can evolve independently.

Tick advancement uses a PostgreSQL transaction and a row lock on the world. Input submission takes the same world lock, so an input is deterministically assigned either to the in-progress next tick or to the following tick. A completed tick updates state, adds its snapshot and events, records completion, and marks the exact queued inputs consumed atomically. The `(world_id, tick)` completed-tick primary key and expected-tick check reject stale/duplicate commits.
