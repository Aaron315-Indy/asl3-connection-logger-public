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

    assert version == 2
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

    assert version == 2
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
