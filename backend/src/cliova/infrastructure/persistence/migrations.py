"""Minimal plain-SQL migration runner using the repository's existing Psycopg stack."""

import os
from pathlib import Path

import psycopg

_MIGRATION_LOCK_KEY = 0x434C494F5641  # ASCII-ish "CLIOVA", advisory-lock namespace only.
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[5] / "database" / "migrations"


def apply_migrations(database_url: str, migrations_dir: Path | None = None) -> tuple[str, ...]:
    """Apply pending ``*.sql`` migrations transactionally in lexical order."""

    directory = migrations_dir or _DEFAULT_MIGRATIONS_DIR
    files = tuple(sorted(directory.glob("*.sql")))
    if not files:
        raise RuntimeError(f"no SQL migrations found in {directory}")

    applied_now: list[str] = []
    with psycopg.connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_KEY,))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cliova_schema_migrations (
                version text PRIMARY KEY
            )
            """
        )
        rows = connection.execute("SELECT version FROM cliova_schema_migrations").fetchall()
        applied = {str(row[0]) for row in rows}

        for path in files:
            version = path.name
            if version in applied:
                continue
            connection.execute(path.read_text(encoding="utf-8"), prepare=False)
            connection.execute(
                "INSERT INTO cliova_schema_migrations (version) VALUES (%s)", (version,)
            )
            applied_now.append(version)

    return tuple(applied_now)


def main() -> None:
    """CLI entry point used by local development and deployment tooling."""

    database_url = os.environ.get("CLIOVA_DATABASE_URL")
    if not database_url:
        raise SystemExit("CLIOVA_DATABASE_URL is required")
    applied = apply_migrations(database_url)
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is up to date")


if __name__ == "__main__":
    main()
