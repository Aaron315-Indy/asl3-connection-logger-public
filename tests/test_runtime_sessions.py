# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for Asterisk runtime transitions."""

import sqlite3

from asl3_connection_logger.collector import process_event


def sessions(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            """
            SELECT status, runtime_id, disconnected_at
            FROM connection_sessions
            ORDER BY id
            """
        ).fetchall()


def test_restart_creates_new_session(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )
    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:200",
    )

    assert sessions(db) == [
        ("interrupted", "boot-a:100", None),
        ("active", "boot-a:200", None),
    ]


def test_repeated_connect_same_runtime(tmp_path):
    db = tmp_path / "test.db"

    for _ in range(3):
        process_event(
            db, 100001, 100002, "connect",
            runtime_id="boot-a:100",
        )

    assert len(sessions(db)) == 1


def test_old_disconnect_cannot_close_new_session(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )
    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:200",
    )
    process_event(
        db, 100001, 100002, "disconnect",
        runtime_id="boot-a:100",
    )

    assert sessions(db)[-1][0] == "active"


def test_current_runtime_disconnect(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )
    process_event(
        db, 100001, 100002, "disconnect",
        runtime_id="boot-a:100",
    )

    assert sessions(db)[0][0] == "completed"


def test_legacy_session_replaced(tmp_path):
    db = tmp_path / "test.db"

    process_event(db, 100001, 100002, "connect")

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )

    assert sessions(db) == [
        ("interrupted", None, None),
        ("active", "boot-a:100", None),
    ]
