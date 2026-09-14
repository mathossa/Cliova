"""Infrastructure smoke test, not a persistence implementation."""

import os

import psycopg
import pytest


@pytest.mark.integration
def test_postgres_connection_and_rollback() -> None:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE cliova_smoke (value integer)")
            cursor.execute("INSERT INTO cliova_smoke VALUES (42)")
            cursor.execute("SELECT value FROM cliova_smoke")
            assert cursor.fetchone() == (42,)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('pg_temp.cliova_smoke')")
            assert cursor.fetchone() == (None,)
