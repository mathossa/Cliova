# Contracts

This package is the boundary between browser and backend. Put stable cross-runtime schemas here: API payloads, directive shapes, simulation event representations and generated OpenAPI artifacts.

`v1.ts` mirrors the explicit `/api/v1` HTTP DTOs used by the 0.1 vertical slice. It is intentionally separate from frontend view models and from Python simulation/persistence models. The browser should adapt these contracts into feature-specific display state instead of depending on internal `WorldState` shapes.

Do **not** move simulation rules here. Contracts describe data; the Python simulation remains authoritative.
