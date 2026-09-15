"""Application repository boundary for development world discovery."""

from typing import Protocol

from cliova.application.scheduling import SchedulingRepository
from cliova.simulation.types import WorldState


class WorldRepository(SchedulingRepository, Protocol):
    """Persistence boundary used by the HTTP world lifecycle."""

    def list_worlds(self) -> tuple[WorldState, ...]: ...
