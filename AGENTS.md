# Cliova agent instructions

## Product direction

Cliova is simulation-first. Do not add historical outcomes as fixed rules when they can emerge from lower-level mechanics. The simulation core is authoritative; UI and future LLM integrations may interpret or present outcomes but must not decide simulation truth.

## Architecture

- Keep `apps/web` separate from the Python backend.
- Keep the backend a modular monolith until scaling evidence requires separation.
- Simulation domains live under `backend/src/cliova/simulation/domains/`.
- Domains return explicit changes/events with causes; avoid hidden cross-domain mutation.
- `simulation/engine.py` owns tick orchestration.
- API routes may call application services, never reimplement simulation rules.
- Infrastructure code must not leak into domain rules.
- New cross-language payloads belong in `packages/contracts/`.

## Simulation requirements

- Deterministic results for the same seed, state and directives.
- Explainability is part of every mechanic, not a later UI feature.
- Prefer aggregate populations over simulating every person.
- Individually simulate only meaningful actors such as institutions, factions and notable individuals.
- Avoid premature optimization and premature microservices.

## Testing

Every simulation mechanic should have deterministic unit tests plus at least one multi-year behavior test. Bugs involving emergent behavior should receive a regression seed when possible.
