"""Thin deterministic integration boundary around Mindwerks/worldengine.

WorldEngine objects never cross this module. The adapter snapshots the physical layers
needed by Cliova into plain NumPy arrays and can produce disposable derived presentation
assets without exposing upstream objects to the rest of the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any

import numpy as np
from numpy.typing import NDArray
from worldengine.draw import draw_satellite  # type: ignore[import-untyped]
from worldengine.drawing_functions import draw_rivers_on_image  # type: ignore[import-untyped]
from worldengine.image_io import PNGWriter  # type: ignore[import-untyped]
from worldengine.plates import world_gen  # type: ignore[import-untyped]
from worldengine.step import Step  # type: ignore[import-untyped]

from cliova.simulation.randomness import random_for

WORLDENGINE_PACKAGE_VERSION = "0.20.0"
WORLDENGINE_REVISION = "0e982b23439dbec1475da9755f774a5b2ab4dbe2"
ADAPTER_VERSION = "worldengine-v1"
SEED_DOMAIN = "world.physical.worldengine.v1"
_WORLDENGINE_RNG_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class WorldEngineConfig:
    """Persistable inputs that materially affect upstream physical generation."""

    width: int = 32
    height: int = 16
    region_count: int = 8
    num_plates: int = 10
    ocean_level: float = 1.0
    gamma_curve: float = 1.25
    curve_offset: float = 0.2
    fade_borders: bool = True

    def __post_init__(self) -> None:
        if self.width < 8 or self.height < 8:
            raise ValueError("WorldEngine dimensions must both be at least 8 cells")
        cell_count = self.width * self.height
        if not 2 <= self.region_count <= cell_count:
            raise ValueError("region_count must fit within the generated grid")
        if self.num_plates <= 0:
            raise ValueError("num_plates must be positive")
        if self.ocean_level <= 0.0:
            raise ValueError("ocean_level must be positive")
        if self.gamma_curve <= 0.0:
            raise ValueError("gamma_curve must be positive")


DEFAULT_WORLDENGINE_CONFIG = WorldEngineConfig()


@dataclass(frozen=True, slots=True)
class PhysicalWorld:
    """Cliova-owned detached physical layers produced by WorldEngine."""

    width: int
    height: int
    worldengine_seed: int
    elevation: NDArray[np.float64]
    ocean: NDArray[np.bool_]
    temperature: NDArray[np.float64]
    precipitation: NDArray[np.float64]
    humidity: NDArray[np.float64]
    watermap: NDArray[np.float64]
    biome: NDArray[np.str_]
    plates: NDArray[np.int64]


def derive_worldengine_seed(seed: int) -> int:
    """Map any authoritative Cliova integer seed onto WorldEngine's 31-bit seed space."""
    rng = random_for(seed, 0, SEED_DOMAIN)
    # Keep zero available but remain within NumPy/Platec's portable signed-int range.
    return min(int(rng.random() * (2**31)), (2**31) - 1)


def _generate_upstream_world(*, seed: int, config: WorldEngineConfig) -> tuple[int, Any]:
    """Create the upstream object while it remains confined to this adapter module."""
    upstream_seed = derive_worldengine_seed(seed)
    world = world_gen(
        f"cliova-{upstream_seed}",
        config.width,
        config.height,
        upstream_seed,
        num_plates=config.num_plates,
        ocean_level=config.ocean_level,
        step=Step.full(),
        gamma_curve=config.gamma_curve,
        curve_offset=config.curve_offset,
        fade_borders=config.fade_borders,
        verbose=False,
    )
    return upstream_seed, world


def generate_physical_world(
    *, seed: int, config: WorldEngineConfig = DEFAULT_WORLDENGINE_CONFIG
) -> PhysicalWorld:
    """Run WorldEngine exactly once and detach its generated physical layers.

    WorldEngine 0.20.0's ``world_gen`` performs one ``numpy.random.randint`` for
    elevation noise before using explicit per-simulation sub-seeds. We therefore seed,
    lock and restore NumPy's legacy global RNG around that upstream call. The generated
    arrays are copied before the upstream object is discarded.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an integer")

    upstream_seed = derive_worldengine_seed(seed)
    with _WORLDENGINE_RNG_LOCK:
        previous_state = np.random.get_state()
        np.random.seed(upstream_seed)
        try:
            _, world = _generate_upstream_world(seed=seed, config=config)
        finally:
            np.random.set_state(previous_state)

    return PhysicalWorld(
        width=config.width,
        height=config.height,
        worldengine_seed=upstream_seed,
        elevation=np.asarray(world.layers["elevation"].data, dtype=np.float64).copy(),
        ocean=np.asarray(world.layers["ocean"].data, dtype=np.bool_).copy(),
        temperature=np.asarray(world.layers["temperature"].data, dtype=np.float64).copy(),
        precipitation=np.asarray(world.layers["precipitation"].data, dtype=np.float64).copy(),
        humidity=np.asarray(world.layers["humidity"].data, dtype=np.float64).copy(),
        watermap=np.asarray(world.layers["watermap"].data, dtype=np.float64).copy(),
        biome=np.asarray(world.layers["biome"].data, dtype=np.str_).copy(),
        plates=np.asarray(world.layers["plates"].data, dtype=np.int64).copy(),
    )


@lru_cache(maxsize=16)
def render_strategic_terrain_png(
    *,
    seed: int,
    config: WorldEngineConfig = DEFAULT_WORLDENGINE_CONFIG,
) -> bytes:
    """Regenerate a disposable deterministic WorldEngine terrain PNG.

    WorldEngine's satellite renderer already owns biome colour, elevation-aware relief,
    ice, lakes and river shading. Cliova reuses that renderer rather than maintaining a
    second terrain algorithm; the browser adds only presentation styling and overlays.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an integer")

    upstream_seed = derive_worldengine_seed(seed)
    with _WORLDENGINE_RNG_LOCK:
        previous_state = np.random.get_state()
        np.random.seed(upstream_seed)
        try:
            _, world = _generate_upstream_world(seed=seed, config=config)
            target = PNGWriter.rgba_from_dimensions(world.width, world.height)
            draw_satellite(world, target)
            # WorldEngine's satellite renderer colours rivers subtly. Reuse its dedicated
            # river overlay once more so major water features remain readable at strategic scale.
            draw_rivers_on_image(world, target, factor=1)
            with TemporaryDirectory(prefix="cliova-map-") as directory:
                output = Path(directory) / "world.png"
                target.complete(str(output))
                return output.read_bytes()
        finally:
            np.random.set_state(previous_state)
