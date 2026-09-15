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

- **Upstream:** `Mindwerks/worldengine`; plate tectonics, elevation, climate, precipitation/humidity, hydrology/erosion and biome generation for issue #59, plus rendering helpers reused for issue #24.
- **Revision:** release `v0.20.0`, commit `0e982b23439dbec1475da9755f774a5b2ab4dbe2` (inspected on 2026-09-15/16).
- **License/SPDX:** `MIT`; verified from the release's `LICENSE.txt` and package metadata.
- **Classification:** `licensed-reusable`.
- **Reuse mode:** `dependency`; Cliova pins `worldengine==0.20.0`, calls `worldengine.plates.world_gen` through a thin adapter, and uses the pinned `draw_satellite` plus `draw_rivers_on_image` rendering APIs for the disposable strategic physical base. No WorldEngine implementation source or colour tables are copied into Cliova.
- **Attribution/NOTICE:** WorldEngine's copyright and MIT permission notice must remain available with distributed copies/substantial portions. The installed dependency retains its license; Cliova also records the notice in `THIRD_PARTY_NOTICES.md`.
- **Rationale:** the upstream implementation already provides the substantial physical-generation mechanics requested by #59 and the biome/elevation/relief/water rendering needed by #24. The render path remains inside the WorldEngine adapter: it deterministically regenerates the upstream object from persisted seed/config metadata, renders a derived terrain PNG, immediately discards the upstream object, and caches only disposable presentation bytes. Authoritative Cliova simulation state remains the persisted aggregate geography and never depends on the regenerated render. Cliova adds only presentation composition, subtle colour/texture treatment and interactive overlays. WorldEngine 0.20.0 touches NumPy's legacy global RNG during generation; Cliova contains generation and rendering behind a lock with explicit Cliova-derived seeding and restores the prior RNG state.

### `shapely/shapely`

- **Upstream:** `shapely/shapely`; planar geometry union/dissolve for issue #24 strategic region presentation.
- **Revision:** release `2.1.2`, tag commit `5fb639d1056888d135fe56bfaf750c9648addeec` (inspected on 2026-09-16).
- **License/SPDX:** `BSD-3-Clause`; verified from `LICENSE.txt` at the release commit. Shapely uses GEOS, distributed under LGPL-2.1-or-later-compatible terms.
- **Classification:** `licensed-reusable`.
- **Reuse mode:** `dependency`; Cliova pins `shapely==2.1.2` and uses public `box` plus `unary_union` geometry APIs. No Shapely/GEOS implementation source is copied into Cliova.
- **Attribution/NOTICE:** retain the Shapely BSD-3-Clause notice for source/binary redistribution; dependency packaging carries its own license and Cliova records the notice in `THIRD_PARTY_NOTICES.md`.
- **Rationale:** #59 persists compact horizontal raster runs, but presenting every run as a separate GeoJSON polygon produced visible spreadsheet-like internal edges. Shapely/GEOS supplies the mature topology operation needed to dissolve those cells into contiguous region polygons without inventing custom polygonization/computational-geometry code.

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

### `fgmacedo/python-statemachine`

- **Upstream:** `fgmacedo/python-statemachine`; considered for issue #64's generic attention/decision lifecycle.
- **Revision:** release `v3.2.1`, commit `dc644e3` (inspected on 2026-09-15).
- **License/SPDX:** `MIT`; verified from the upstream repository and release metadata.
- **Classification:** `rejected` for this subsystem.
- **Reuse mode:** `rejected`; no dependency or source reuse.
- **Attribution/NOTICE:** none for Cliova under this decision because no source or dependency is incorporated.
- **Rationale:** mature and actively maintained, but its statechart/SCXML, callbacks and event-processing machinery is disproportionate to #64's intentionally tiny persisted lifecycle (`open`/`responded`/`expired`). It would not replace Cliova-specific PostgreSQL transaction boundaries or the #9/#17 future-input path, so existing immutable application models plus explicit SQL transitions are smaller and clearer.

### `oaxley/pyfsm`

- **Upstream:** `oaxley/pyfsm`; considered as a lightweight finite-state-machine primitive for issue #64.
- **Revision:** repository `main` documentation inspected on 2026-09-15.
- **License/SPDX:** `Apache-2.0`; verified from the upstream repository license/documentation.
- **Classification:** `rejected` for this subsystem.
- **Reuse mode:** `rejected`; no dependency or source reuse.
- **Attribution/NOTICE:** none for Cliova under this decision because no source or dependency is incorporated.
- **Rationale:** the library is small, but its generic FSM state/event/transition abstraction would still add a second lifecycle framework without solving deterministic tick eligibility, response queue locking, persistence or event references. Three explicit statuses are simpler to validate directly in Cliova's existing repository/application patterns.

### `tan-zhuo/genesis`

- **Upstream:** `tan-zhuo/genesis`; potentially relevant to simulation concepts, phase ordering and observable game behavior.
- **Revision:** `main` at `72ce49343c3bc464a195a44375ee9f7deb3a190f` (inspected for provenance decision on 2026-09-15).
- **License/SPDX:** `unknown`; no explicit compatible reusable license or direct permission has been verified for Cliova.
- **Classification:** `reference-only`.
- **Reuse mode:** `reference-only`.
- **Attribution/NOTICE:** no source is incorporated under this decision; if permission or a compatible license is established later, reassess obligations before any prospective reuse.
- **Rationale:** useful as a research reference for high-level concepts, abstract algorithms, behavioral requirements, simulation phases and externally observable behavior. Do not copy source, comments, tests, constants/tables with unclear rights, translate/port source, or preserve distinctive implementation structure through paraphrase. Any implementation materially informed by Genesis must proceed through an implementation-neutral specification and independent Cliova implementation.

This classification may be reviewed prospectively if an explicit compatible license or direct permission is later verified. Existing reference-only work does not become retroactively copied/adapted work merely because the upstream licensing status later changes.
