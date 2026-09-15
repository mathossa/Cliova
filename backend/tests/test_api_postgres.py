import os

import psycopg
import pytest

from cliova.application.development import create_development_world
from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.infrastructure.persistence.worlds import PostgresWorldRepository, WorldAlreadyExistsError

pytestmark = pytest.mark.integration

_PERSISTENCE_TABLES = (
    "cliova_history_event_causes",
    "cliova_history_events",
    "cliova_completed_ticks",
    "cliova_queued_inputs",
    "cliova_world_snapshots",
    "cliova_worlds",
)


def _database_url() -> str:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    return url


def test_postgres_world_catalog_lists_persisted_worlds_and_normalizes_duplicates() -> None:
    database_url = _database_url()
    apply_migrations(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE " + ", ".join(_PERSISTENCE_TABLES) + " RESTART IDENTITY CASCADE"
        )

    repository = PostgresWorldRepository(database_url)
    second = create_development_world(seed=2, world_key="catalog-second")
    first = create_development_world(seed=1, world_key="catalog-first")
    repository.create_world(second)
    repository.create_world(first)

    listed = repository.list_worlds()
    assert {world.id for world in listed} == {first.id, second.id}
    assert all(repository.load_world(world.id.value) == world for world in listed)

    with pytest.raises(WorldAlreadyExistsError):
        repository.create_world(first)
