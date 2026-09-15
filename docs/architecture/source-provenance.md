# External source provenance

This registry records substantial external implementation sources considered for Cliova. The operational reuse policy is defined in [`AGENTS.md`](../../AGENTS.md#5-copyadapt-first-mandatory-open-source-gate). This registry is an engineering/provenance record, not legal advice or a claim of formal clean-room certification.

Record serious candidates when they materially influence a subsystem decision, including rejected and reference-only candidates. Keep entries short and update them prospectively if new licensing or provenance evidence appears.

For each candidate record:

- **Upstream** — repository/project and relevant subsystem.
- **Revision** — exact commit, tag or version inspected where practical.
- **License/SPDX** — verified license identifier, or `unknown` when no applicable permission has been established.
- **Classification** — `licensed-reusable`, `reference-only` or `rejected`.
- **Reuse mode** — `dependency`, `copied/adapted code`, `reference-only` or `rejected`.
- **Attribution/NOTICE** — obligations that apply to Cliova's chosen reuse mode.
- **Rationale** — concise fit/provenance decision, including rejection reasons where applicable.

## Current decisions

### `Leaflet/Leaflet`

- **Upstream:** `Leaflet/Leaflet`; browser pan/zoom, non-Earth coordinate handling, image overlays, GeoJSON polygon interaction and markers for issue #24.
- **Revision:** release `v1.9.4`, commit `d15112c9e8ac339f0f74f563959d0423d291308d` (inspected on 2026-09-15).
- **License/SPDX:** `BSD-2-Clause`; verified from the release `LICENSE`.
- **Classification:** `licensed-reusable`.
- **Reuse mode:** `dependency`; the Command Center loads the exact `1.9.4` browser distribution from the version-pinned unpkg URL and calls public `L.CRS.Simple`, `L.imageOverlay`, `L.geoJSON`, marker and map APIs. No Leaflet implementation source is copied into Cliova.
- **Attribution/NOTICE:** retain the Leaflet BSD-2-Clause copyright/license notice for redistribution; the notice is recorded in `THIRD_PARTY_NOTICES.md` and the map attribution identifies Leaflet at runtime.
- **Rationale:** the exact `CRS.Simple` implementation explicitly maps flat/game coordinates directly and supplies the Y-axis inversion needed for non-Earth maps. The exact GeoJSON implementation supplies polygon conversion and feature interaction, eliminating any need for custom pan/zoom, projection or hit-testing. MapLibre/vector-tile/PostGIS infrastructure was not introduced because the current persisted #59 world is a compact fixed game grid and does not require tile streaming.

### `Mindwerks/worldengine`

- **Upstream:** `Mindwerks/worldengine`; plate tectonics, elevation, climate, precipitation/humidity, hydrology/erosion and biome generation for issue #59, plus rendering helpers inspected for issue #24.
- **Revision:** release `v0.20.0`, commit `0e982b23439dbec1475da9755f774a5b2ab4dbe2` (inspected on 2026-09-15).
- **License/SPDX:** `MIT`; verified from the release's `LICENSE.txt` and package metadata.
- **Classification:** `licensed-reusable`.
- **Reuse mode:** `dependency`; Cliova pins `worldengine==0.20.0` and calls `worldengine.plates.world_gen` through a thin adapter. No WorldEngine implementation source is copied into Cliova.
- **Attribution/NOTICE:** WorldEngine's copyright and MIT permission notice must remain available with distributed copies/substantial portions. The installed dependency retains its license; Cliova also records the notice in `THIRD_PARTY_NOTICES.md`.
- **Rationale:** the upstream implementation already provides the substantial physical-generation mechanics requested by #59. For #24, `worldengine/draw.py`, including biome/elevation/satellite rendering and river drawing hooks, was inspected at the pinned revision. Those routines operate on the live upstream `World` object and detailed layers that #59 intentionally detaches/discards after generation. Re-running WorldEngine merely to draw would make rendering depend on regeneration rather than persisted authoritative presentation state, so #24 rejects that integration path and instead renders #59's stored land/region runs plus aggregate terrain/elevation into disposable SVG. WorldEngine 0.20.0 still performs one legacy global NumPy RNG draw inside `world_gen`; Cliova contains that call behind a lock with an explicit Cliova-derived seed and restores the prior RNG state.

### `networkx/networkx` graph Voronoi

- **Upstream:** `networkx/networkx`, `networkx.algorithms.voronoi.voronoi_cells`; deterministic aggregate-region partitioning for issue #59.
- **Revision:** `networkx-3.4`, commit `fe7795acbc31518bb5154de79afb0b9dab2f4846` (minimum supported dependency inspected on 2026-09-15).
- **License/SPDX:** `BSD-3-Clause`; verified from `LICENSE.txt`.
- **Classification:** `licensed-reusable`.
- **Reuse mode:** `dependency`; NetworkX was already a Cliova dependency and #59 calls its graph-Voronoi API rather than copying the implementation.
- **Attribution/NOTICE:** retain the NetworkX BSD-3-Clause copyright/license notice in source/binary redistributions as required by the upstream license. Dependency packaging continues to carry that license.
- **Rationale:** graph Voronoi provides a mature shortest-path partition primitive directly on Cliova's generated cell graph. It avoids inventing a bespoke segmentation algorithm and avoids adding a heavier image-segmentation dependency.

### `scikit-image` watershed segmentation

- **Upstream:** `scikit-image`, `skimage.segmentation.watershed`; considered as an alternative region-partition implementation for issue #59.
- **Revision:** stable documentation/API inspected on 2026-09-15.
- **License/SPDX:** `BSD-3-Clause`.
- **Classification:** `rejected` for this subsystem.
- **Reuse mode:** `rejected`; no dependency or source reuse.
- **Attribution/NOTICE:** none for Cliova under this decision because no scikit-image code is distributed or copied.
- **Rationale:** watershed is a mature segmentation algorithm, but adding scikit-image/SciPy solely for aggregate world partitioning is unnecessary while the already-present NetworkX graph-Voronoi implementation meets the deterministic partition requirement with a smaller dependency surface.

### `tan-zhuo/genesis`

- **Upstream:** `tan-zhuo/genesis`; potentially relevant to simulation concepts, phase ordering and observable game behavior.
- **Revision:** `main` at `72ce49343c3bc464a195a44375ee9f7deb3a190f` (inspected for provenance decision on 2026-09-15).
- **License/SPDX:** `unknown`; no explicit compatible reusable license or direct permission has been verified for Cliova.
- **Classification:** `reference-only`.
- **Reuse mode:** `reference-only`.
- **Attribution/NOTICE:** no source is incorporated under this decision; if permission or a compatible license is established later, reassess obligations before any prospective reuse.
- **Rationale:** useful as a research reference for high-level concepts, abstract algorithms, behavioral requirements, simulation phases and externally observable behavior. Do not copy source, comments, tests, constants/tables with unclear rights, translate/port source, or preserve distinctive implementation structure through paraphrase. Any implementation materially informed by Genesis must proceed through an implementation-neutral specification and independent Cliova implementation.

This classification may be reviewed prospectively if an explicit compatible license or direct permission is later verified. Existing reference-only work does not become retroactively copied/adapted work merely because the upstream licensing status later changes.
