from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from contextvars import ContextVar

from .config import database_path
from .chat_access import READ_ONLY


MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"
_PREVIEW_CONNECTION = ContextVar('preview_connection', default=None)


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open the local SQLite database with safe application defaults."""
    target = path or database_path()
    preview = _PREVIEW_CONNECTION.get()
    if preview is not None and preview[0] == target.resolve():
        yield preview[1]
        return
    target.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro', uri=True) if READ_ONLY.get() else sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if READ_ONLY.get():
        connection.execute('PRAGMA query_only = ON')
    else:
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


@contextmanager
def rollback_preview(path=None):
    """Run an existing local validator/writer against one always-rolled-back connection."""
    target = path or database_path()
    with connect(path) as connection:
        token = _PREVIEW_CONNECTION.set((target.resolve(), connection))
        try:
            yield
        finally:
            connection.rollback()
            _PREVIEW_CONNECTION.reset(token)


def migrate(path: Path | None = None) -> list[str]:
    """Apply every unapplied SQL migration in filename order."""
    if READ_ONLY.get():
        return []
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
        migrations=sorted(MIGRATIONS_DIRECTORY.glob('*.sql'))
        current={row['version'] for row in connection.execute('SELECT version FROM schema_migrations')}
        if all(migration.name in current for migration in migrations):
            return []
        # Read applied versions under the same write lock as schema changes.
        # Startup requests can call migrate concurrently; executescript would
        # implicitly release this lock before applying the next migration.
        connection.execute('BEGIN IMMEDIATE')
        applied = {row['version'] for row in connection.execute('SELECT version FROM schema_migrations')}
        for migration in migrations:
            if migration.name in applied:
                continue
            statement = ''
            for character in migration.read_text(encoding='utf-8'):
                statement += character
                if character == ';' and sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ''
            if statement.strip():
                connection.execute(statement)
            connection.execute('INSERT INTO schema_migrations(version) VALUES(?)', (migration.name,))
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
