# SPDX-License-Identifier: GPL-3.0-or-later
"""SQLite database initialization for ASL3 Connection Logger."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_node TEXT NOT NULL,
    remote_node TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('connect', 'disconnect')),
    event_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS connection_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_node TEXT NOT NULL,
    remote_node TEXT NOT NULL,
    connected_at TEXT NOT NULL,
    disconnected_at TEXT,
    duration_seconds INTEGER,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'interrupted'))
);

CREATE INDEX IF NOT EXISTS idx_events_nodes
    ON connection_events(local_node, remote_node);

CREATE INDEX IF NOT EXISTS idx_events_timestamp
    ON connection_events(event_timestamp);

CREATE INDEX IF NOT EXISTS idx_sessions_nodes
    ON connection_sessions(local_node, remote_node);

CREATE INDEX IF NOT EXISTS idx_sessions_connected
    ON connection_sessions(connected_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_active
    ON connection_sessions(local_node, remote_node)
    WHERE status = 'active';
"""


def initialize_database(db_path):
    """Create database tables and initialize schema version."""

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)

        row = connection.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()

        if row is None:
            connection.execute(
                "ALTER TABLE connection_sessions "
                "ADD COLUMN runtime_id TEXT"
            )
            connection.execute(
                "INSERT INTO schema_version(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )

        elif row[0] == 1:
            connection.execute(
                "ALTER TABLE connection_sessions "
                "ADD COLUMN runtime_id TEXT"
            )
            connection.execute(
                "UPDATE schema_version SET version = 2"
            )

        elif row[0] != SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported database schema version: {row[0]}"
            )

        connection.commit()
