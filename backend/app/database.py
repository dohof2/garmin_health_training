from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import database_path


MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open the local SQLite database with safe application defaults."""
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(path: Path | None = None) -> list[str]:
    """Apply every unapplied SQL migration in filename order."""
    applied_now: list[str] = []

    with connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

        for migration in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
            if migration.name in applied:
                continue
            escaped_version = migration.name.replace("'", "''")
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{migration.read_text(encoding='utf-8')}\n"
                "INSERT INTO schema_migrations(version) "
                f"VALUES ('{escaped_version}');\n"
                "COMMIT;"
            )
            applied_now.append(migration.name)

    return applied_now


def schema_status(path: Path | None = None) -> dict[str, int]:
    """Return lightweight database counts for diagnostics."""
    with connect(path) as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        table_count = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    return {"migrations": migration_count, "tables": table_count}
