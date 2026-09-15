"""Dependency providers for the HTTP boundary."""

import os

from cliova.application.worlds import WorldRepository
from cliova.infrastructure.persistence.worlds import PostgresWorldRepository


def get_repository() -> WorldRepository:
    """Return the authoritative PostgreSQL repository configured for this process."""

    database_url = os.environ.get("CLIOVA_DATABASE_URL")
    if not database_url:
        raise RuntimeError("CLIOVA_DATABASE_URL is required for persisted API routes")
    return PostgresWorldRepository(database_url)
