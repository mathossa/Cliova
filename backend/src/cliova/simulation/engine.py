from collections.abc import Callable, Iterable
from typing import Protocol

from cliova.simulation.randomness import RandomSource, random_for
from cliova.simulation.types import SimulationChange, WorldState


class SimulationDomain(Protocol):
    """Domains read immutable state and return changes; randomness is explicit."""

    name: str

    def step(
        self, world: WorldState, year: int, rng: RandomSource
    ) -> list[SimulationChange]: ...


class SimulationEngine:
    """Owns ordered yearly orchestration; domains own domain rules."""

    def __init__(
        self,
        domains: Iterable[SimulationDomain] = (),
        *,
        rng_factory: Callable[[int, int, str], RandomSource] = random_for,
    ) -> None:
        self._domains = tuple(domains)
        names = [domain.name for domain in self._domains]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("domain names must be non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("domain names must be unique")
        self._rng_factory = rng_factory

    def step(self, world: WorldState) -> tuple[WorldState, list[SimulationChange]]:
        next_time = world.time.next_year()
        changes: list[SimulationChange] = []
        for domain in self._domains:
            rng = self._rng_factory(world.seed, next_time.tick, domain.name)
            changes.extend(domain.step(world, next_time.year, rng))
        # Commit time only after every domain succeeds. Domain changes are still
        # proposals: applying domain-owned state is outside the scaffold's scope.
        return WorldState(
            id=world.id, seed=world.seed, metadata=world.metadata, time=next_time
        ), changes

    def run(self, world: WorldState, years: int) -> tuple[WorldState, list[SimulationChange]]:
        if type(years) is not int or years < 0:
            raise ValueError("years must be non-negative")
        changes: list[SimulationChange] = []
        for _ in range(years):
            world, tick_changes = self.step(world)
            changes.extend(tick_changes)
        return world, changes
