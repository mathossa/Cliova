"""Deterministic derived SVG rendering for the strategic physical base map.

This renderer consumes only persisted Cliova geography/presentation state. It never invokes
WorldEngine and never writes simulation state; the SVG is therefore disposable cacheable output.
"""

from hashlib import sha256
from html import escape

from cliova.api.v1.map_projection import MAP_RENDER_VERSION
from cliova.simulation.types import WorldState

_BIOME_FILL = {
    "temperate": "#73865e",
    "semi_arid": "#9b8859",
    "arid": "#a69062",
    "boreal": "#526f66",
    "tropical": "#527a52",
    "alpine": "#8b8f89",
}
_OCEAN_FILL = "#17394a"


def _rect(
    *,
    x: int,
    y: int,
    width: int,
    fill: str | None = None,
    opacity: float | None = None,
) -> str:
    attributes = [f'x="{x}"', f'y="{y}"', f'width="{width}"', 'height="1"']
    if fill is not None:
        attributes.append(f'fill="{fill}"')
    if opacity is not None:
        attributes.append(f'fill-opacity="{opacity:.3f}"')
    return f"<rect {' '.join(attributes)}/>"


def render_physical_base_svg(world: WorldState) -> str:
    """Render #59 presentation runs as an immutable physical-only SVG asset."""
    geography = world.geography
    presentation = geography.presentation if geography is not None else None
    if geography is None or presentation is None:
        raise ValueError("world has no strategic presentation geometry")

    land_clip = "".join(
        _rect(
            x=run.x_start,
            y=run.y,
            width=run.x_stop - run.x_start,
        )
        for run in presentation.land_runs
    )
    geometry_by_id = {geometry.region_id: geometry for geometry in presentation.regions}

    region_layers: list[str] = []
    relief_layers: list[str] = []
    highland_layers: list[str] = []
    for region in geography.regions:
        geometry = geometry_by_id[region.id]
        fill = _BIOME_FILL.get(region.biome, "#687a64")
        for run in geometry.runs:
            width = run.x_stop - run.x_start
            region_layers.append(_rect(x=run.x_start, y=run.y, width=width, fill=fill))
            relief_layers.append(
                _rect(
                    x=run.x_start,
                    y=run.y,
                    width=width,
                    fill="#11171b",
                    opacity=0.04 + (0.18 * region.mean_elevation),
                )
            )
            if region.terrain in {"highland", "plateau"}:
                highland_layers.append(
                    _rect(
                        x=run.x_start,
                        y=run.y,
                        width=width,
                        fill="url(#highland-hatch)",
                        opacity=0.42 if region.terrain == "highland" else 0.24,
                    )
                )

    generation = geography.generation
    generation_note = (
        f"{generation.generator}:{generation.adapter_version}:{generation.upstream_version}"
        if generation is not None
        else "legacy-or-fixture"
    )
    metadata = escape(
        f"Cliova derived strategic base; render={MAP_RENDER_VERSION}; source={generation_note}"
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {presentation.width} {presentation.height}" '
        f'width="{presentation.width}" height="{presentation.height}" '
        'shape-rendering="crispEdges" '
        f'data-render-version="{MAP_RENDER_VERSION}">'
        f"<metadata>{metadata}</metadata>"
        "<defs>"
        f'<clipPath id="land-mask">{land_clip}</clipPath>'
        '<pattern id="highland-hatch" width="1" height="1" patternUnits="userSpaceOnUse">'
        '<path d="M0,1 L1,0" stroke="#d5d1be" stroke-width="0.08" opacity="0.7"/>'
        "</pattern>"
        "</defs>"
        f'<rect width="{presentation.width}" height="{presentation.height}" '
        f'fill="{_OCEAN_FILL}"/>'
        '<g clip-path="url(#land-mask)">'
        f"{''.join(region_layers)}"
        f"{''.join(relief_layers)}"
        f"{''.join(highland_layers)}"
        "</g>"
        '<g clip-path="url(#land-mask)" opacity="0.16">'
        f'<rect width="{presentation.width}" height="{presentation.height}" fill="none" '
        'stroke="#e8e0c4" stroke-width="0.08"/>'
        "</g>"
        "</svg>"
    )


def svg_etag(svg: str) -> str:
    """Stable strong ETag for browser/proxy caching of disposable render output."""
    return f'"{sha256(svg.encode("utf-8")).hexdigest()}"'
