# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema v2 migration regression tests."""

import sqlite3

from asl3_connection_logger.database import initialize_database


def test_new_database_has_runtime_column(tmp_path):
    db = tmp_path / "new.db"

    initialize_database(db)

    with sqlite3.connect(db) as connection:
        version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(connection_sessions)"
            )
        }

    assert version == 3
    assert "runtime_id" in columns


def test_v1_database_migration(tmp_path):
    db = tmp_path / "legacy.db"

    with sqlite3.connect(db) as connection:
        connection.executescript("""
            CREATE TABLE schema_version (
                version INTEGER NOT NULL
            );
            INSERT INTO schema_version VALUES (1);

            CREATE TABLE connection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_node TEXT NOT NULL,
                remote_node TEXT NOT NULL,
                connected_at TEXT NOT NULL,
                disconnected_at TEXT,
                duration_seconds INTEGER,
                status TEXT NOT NULL DEFAULT 'active'
            );

            INSERT INTO connection_sessions
                (local_node, remote_node, connected_at, status)
            VALUES
                ('100001', '100002',
                 '2026-10-26T23:46:44+00:00', 'active');
        """)

    initialize_database(db)

    with sqlite3.connect(db) as connection:
        row = connection.execute(
            """
            SELECT remote_node, status, runtime_id
            FROM connection_sessions
            """
        ).fetchone()

        version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]

    assert version == 3
    assert row == ("100002", "active", None)


def test_migration_is_repeatable(tmp_path):
    db = tmp_path / "repeat.db"

    initialize_database(db)
    initialize_database(db)

    with sqlite3.connect(db) as connection:
        columns = [
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(connection_sessions)"
            )
        ]

    assert columns.count("runtime_id") == 1


def test_v2_database_migration_preserves_sessions(tmp_path):
    db = tmp_path / "v2.db"

    initialize_database(db)

    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE schema_version SET version = 2"
        )
        connection.execute(
            """
            INSERT INTO connection_sessions
                (local_node, remote_node, connected_at, status, runtime_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "100001",
                "100002",
                "2026-10-26T23:46:44+00:00",
                "completed",
                "test-runtime",
            ),
        )
        connection.execute("DROP TABLE node_metadata")
        connection.execute("DROP TABLE node_metadata_overrides")

    initialize_database(db)

    with sqlite3.connect(db) as connection:
        version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]

        session = connection.execute(
            """
            SELECT local_node, remote_node, status, runtime_id
            FROM connection_sessions
            """
        ).fetchone()

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert version == 3
    assert session == (
        "100001", "100002", "completed", "test-runtime"
    )
    assert "node_metadata" in tables
    assert "node_metadata_overrides" in tables


def test_v2_migration_failure_rolls_back(tmp_path, monkeypatch):
    import pytest
    import asl3_connection_logger.database as database

    db = tmp_path / "rollback.db"
    initialize_database(db)

    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE schema_version SET version = 2")
        connection.execute("DROP TABLE node_metadata")
        connection.execute("DROP TABLE node_metadata_overrides")

    original_connect = database.sqlite3.connect

    def failing_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)

        def authorize(action, arg1, arg2, db_name, source):
            if (
                action == sqlite3.SQLITE_CREATE_TABLE
                and arg1 == "node_metadata_overrides"
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        return connection

    monkeypatch.setattr(database.sqlite3, "connect", failing_connect)

    with pytest.raises(sqlite3.DatabaseError):
        initialize_database(db)

    with original_connect(db) as connection:
        version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]

        metadata_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert version == 2
    assert "node_metadata" not in metadata_tables
    assert "node_metadata_overrides" not in metadata_tables
