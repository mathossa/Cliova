from collections.abc import Iterable
from typing import Protocol

from cliova.simulation.types import SimulationChange, WorldState


class SimulationDomain(Protocol):
    """Contract implemented by simulation domains as they are introduced."""

    name: str

    def step(self, world: WorldState, year: int) -> list[SimulationChange]: ...


class SimulationEngine:
    """Owns deterministic yearly orchestration; domains own domain rules."""

    def __init__(self, domains: Iterable[SimulationDomain] = ()) -> None:
        self._domains = tuple(domains)

    def step(self, world: WorldState) -> tuple[WorldState, list[SimulationChange]]:
        next_year = world.year + 1
        changes: list[SimulationChange] = []
        for domain in self._domains:
            changes.extend(domain.step(world, next_year))
        world.year = next_year
        return world, changes

    def run(self, world: WorldState, years: int) -> tuple[WorldState, list[SimulationChange]]:
        if years < 0:
            raise ValueError("years must be non-negative")
        changes: list[SimulationChange] = []
        for _ in range(years):
            world, tick_changes = self.step(world)
            changes.extend(tick_changes)
        return world, changes
