"""Application repository boundary for development world discovery."""

from typing import Protocol

from cliova.application.persistence import PersistenceRepository
from cliova.simulation.types import WorldState


class WorldRepository(PersistenceRepository, Protocol):
    """Persistence boundary used by the HTTP world lifecycle."""

    def list_worlds(self) -> tuple[WorldState, ...]: ...
