"""Deterministic derived rendering for the strategic physical base map.

The renderer consumes persisted Cliova generation metadata and presentation extent. For
WorldEngine-backed worlds it reuses WorldEngine's satellite/terrain renderer to regenerate a
disposable physical asset; authoritative simulation state is never mutated.
"""

from base64 import b64encode
from hashlib import sha256
from html import escape

from cliova.api.v1.map_projection import MAP_RENDER_VERSION
from cliova.simulation.domains.world.worldengine_adapter import (
    WorldEngineConfig,
    render_strategic_terrain_png,
)
from cliova.simulation.types import PhysicalGenerationMetadata, WorldState

_BIOME_FILL = {
    "temperate": "#718b5a",
    "semi_arid": "#a78d58",
    "arid": "#c2a96c",
    "boreal": "#587565",
    "tropical": "#4d7d4e",
    "alpine": "#90948c",
}
_OCEAN_FILL = "#183f53"


def _parameter_values(
    generation: PhysicalGenerationMetadata,
) -> dict[str, str | int | float | bool]:
    return {parameter.key: parameter.value for parameter in generation.parameters}


def _required_int(values: dict[str, str | int | float | bool], key: str) -> int:
    value = values.get(key)
    if type(value) is not int:
        raise ValueError(f"generation parameter {key!r} must be an integer")
    return value


def _required_float(values: dict[str, str | int | float | bool], key: str) -> float:
    value = values.get(key)
    if type(value) not in {int, float}:
        raise ValueError(f"generation parameter {key!r} must be numeric")
    return float(value)


def _required_bool(values: dict[str, str | int | float | bool], key: str) -> bool:
    value = values.get(key)
    if type(value) is not bool:
        raise ValueError(f"generation parameter {key!r} must be a boolean")
    return value


def _worldengine_config(generation: PhysicalGenerationMetadata) -> WorldEngineConfig:
    values = _parameter_values(generation)
    return WorldEngineConfig(
        width=_required_int(values, "width"),
        height=_required_int(values, "height"),
        region_count=_required_int(values, "region_count"),
        num_plates=_required_int(values, "num_plates"),
        ocean_level=_required_float(values, "ocean_level"),
        gamma_curve=_required_float(values, "gamma_curve"),
        curve_offset=_required_float(values, "curve_offset"),
        fade_borders=_required_bool(values, "fade_borders"),
    )


def _worldengine_svg(world: WorldState, generation: PhysicalGenerationMetadata) -> str:
    geography = world.geography
    if geography is None or geography.presentation is None:
        raise ValueError("world has no strategic presentation geometry")

    presentation = geography.presentation
    png = render_strategic_terrain_png(
        seed=generation.world_seed,
        config=_worldengine_config(generation),
    )
    encoded = b64encode(png).decode("ascii")
    source = escape(
        f"{generation.generator}:{generation.adapter_version}:{generation.upstream_version}"
    )
    metadata = f"Cliova derived strategic terrain; render={MAP_RENDER_VERSION}; source={source}"
    texture_seed = (generation.worldengine_seed % 997) + 1
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {presentation.width} {presentation.height}" '
        f'width="{presentation.width}" height="{presentation.height}" '
        f'data-render-version="{MAP_RENDER_VERSION}" '
        'data-render-theme="stylized-strategic-terrain">'
        f"<metadata>{metadata}</metadata>"
        "<defs>"
        '<filter id="terrain-grade" x="0" y="0" width="100%" height="100%">'
        '<feColorMatrix type="saturate" values="1.18"/>'
        "<feComponentTransfer>"
        '<feFuncR type="gamma" amplitude="1.06" exponent="0.92" offset="0.01"/>'
        '<feFuncG type="gamma" amplitude="1.06" exponent="0.92" offset="0.01"/>'
        '<feFuncB type="gamma" amplitude="1.03" exponent="0.96" offset="0"/>'
        "</feComponentTransfer>"
        "</filter>"
        '<filter id="terrain-texture" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.32" numOctaves="2" '
        f'seed="{texture_seed}"/>'
        '<feColorMatrix values="0 0 0 0 .52 0 0 0 0 .48 0 0 0 0 .35 0 0 0 .12 0"/>'
        "</filter>"
        "</defs>"
        f'<rect width="{presentation.width}" height="{presentation.height}" '
        f'fill="{_OCEAN_FILL}"/>'
        f'<image x="0" y="0" width="{presentation.width}" height="{presentation.height}" '
        'preserveAspectRatio="none" filter="url(#terrain-grade)" '
        f'href="data:image/png;base64,{encoded}"/>'
        f'<rect width="{presentation.width}" height="{presentation.height}" '
        'filter="url(#terrain-texture)" opacity="0.28" '
        'style="mix-blend-mode:soft-light"/>'
        "</svg>"
    )


def _fallback_svg(world: WorldState) -> str:
    """Keep older presentation-only snapshots renderable without inventing upstream detail."""
    geography = world.geography
    presentation = geography.presentation if geography is not None else None
    if geography is None or presentation is None:
        raise ValueError("world has no strategic presentation geometry")

    geometry_by_id = {geometry.region_id: geometry for geometry in presentation.regions}
    layers: list[str] = []
    for region in geography.regions:
        geometry = geometry_by_id[region.id]
        fill = _BIOME_FILL.get(region.biome, "#687a64")
        for run in geometry.runs:
            width = run.x_stop - run.x_start
            layers.append(
                f'<rect x="{run.x_start}" y="{run.y}" width="{width}" height="1" fill="{fill}"/>'
            )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {presentation.width} {presentation.height}" '
        f'width="{presentation.width}" height="{presentation.height}" '
        f'data-render-version="{MAP_RENDER_VERSION}" '
        'data-render-theme="aggregate-fallback">'
        f'<rect width="{presentation.width}" height="{presentation.height}" '
        f'fill="{_OCEAN_FILL}"/>'
        f"{''.join(layers)}"
        "</svg>"
    )


def render_physical_base_svg(world: WorldState) -> str:
    """Render a disposable physical-only base asset for the persisted world."""
    geography = world.geography
    presentation = geography.presentation if geography is not None else None
    if geography is None or presentation is None:
        raise ValueError("world has no strategic presentation geometry")

    generation = geography.generation
    if generation is not None and generation.generator == "worldengine":
        return _worldengine_svg(world, generation)
    return _fallback_svg(world)


def svg_etag(svg: str) -> str:
    """Stable strong ETag for browser/proxy caching of disposable render output."""
    return f'"{sha256(svg.encode("utf-8")).hexdigest()}"'
