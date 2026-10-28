# SPDX-License-Identifier: GPL-3.0-or-later
"""Database initialization tests."""

import sqlite3

from asl3_connection_logger.database import (
    SCHEMA_VERSION,
    initialize_database,
)


def test_database_initialization(tmp_path):
    db_path = tmp_path / "connections.db"

    initialize_database(db_path)

    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        assert "connection_events" in tables
        assert "connection_sessions" in tables
        assert "schema_version" in tables

        version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]

        assert version == SCHEMA_VERSION


def test_database_initialization_is_repeatable(tmp_path):
    db_path = tmp_path / "connections.db"

    initialize_database(db_path)
    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_version"
        ).fetchone()[0]

        assert count == 1
