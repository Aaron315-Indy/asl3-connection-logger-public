# SPDX-License-Identifier: GPL-3.0-or-later
"""Runtime-aware connection collector tests."""

import sqlite3

from asl3_connection_logger.collector import process_event


def test_new_session_records_runtime(tmp_path):
    db = tmp_path / "connections.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:12345",
    )

    with sqlite3.connect(db) as connection:
        runtime = connection.execute(
            "SELECT runtime_id FROM connection_sessions"
        ).fetchone()[0]

    assert runtime == "boot-a:12345"


def test_legacy_session_runtime_is_null(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")

    with sqlite3.connect(db) as connection:
        runtime = connection.execute(
            "SELECT runtime_id FROM connection_sessions"
        ).fetchone()[0]

    assert runtime is None
