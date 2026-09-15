"""PostgreSQL adapter for development world discovery on top of #13 persistence."""

from typing import Any, cast

from psycopg.errors import UniqueViolation

from cliova.infrastructure.persistence.postgres import PersistenceError, PostgresPersistence
from cliova.simulation.types import WorldState


class WorldAlreadyExistsError(PersistenceError):
    """A deterministic development world identity already exists."""


class PostgresWorldRepository(PostgresPersistence):
    """Extend #13 persistence with the read-only world catalog needed by API v1."""

    def create_world(self, world: WorldState) -> None:
        try:
            super().create_world(world)
        except UniqueViolation as exc:
            raise WorldAlreadyExistsError(f"world {world.id.value} already exists") from exc

    def list_worlds(self) -> tuple[WorldState, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT world_id, seed, current_tick AS tick, current_year AS year,
                       schema_version, simulation_version, rng_algorithm,
                       payload_schema_version, state_json
                  FROM cliova_worlds
                 ORDER BY world_id
                """
            ).fetchall()

        return tuple(
            self._world_from_row(
                cast(dict[str, Any], row),
                expected_world_id=cast(Any, row["world_id"]),
            )
            for row in rows
        )
