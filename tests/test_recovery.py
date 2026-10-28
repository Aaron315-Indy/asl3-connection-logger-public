# SPDX-License-Identifier: GPL-3.0-or-later
"""Recovery and reconciliation tests."""

import sqlite3

from asl3_connection_logger.collector import process_event
from asl3_connection_logger.recovery import reconcile_sessions


def sessions(db):
    with sqlite3.connect(db) as connection:
        return connection.execute(
            """
            SELECT remote_node, status,
                   disconnected_at, duration_seconds
            FROM connection_sessions
            ORDER BY id
            """
        ).fetchall()


def test_recovery_dry_run(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")

    result = reconcile_sessions(
        db, 100001, [], dry_run=True,
    )

    assert len(result) == 1
    assert sessions(db)[0][1] == "active"


def test_recovery_interrupts_missing_node(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")

    result = reconcile_sessions(
        db, 100001, [], dry_run=False,
    )

    assert len(result) == 1
    assert sessions(db) == [
        ("100002", "interrupted", None, None),
    ]


def test_recovery_preserves_connected_node(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")

    result = reconcile_sessions(
        db, 100001, [100002], dry_run=False,
    )

    assert result == []
    assert sessions(db)[0][1] == "active"


def test_recovery_multiple_nodes(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")
    process_event(db, 100001, 123456, "connect")

    result = reconcile_sessions(
        db, 100001, [100002], dry_run=False,
    )

    assert result == [(2, "123456")]
    assert sessions(db)[0][1] == "active"
    assert sessions(db)[1][1] == "interrupted"


def test_recovery_repeated_execution(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")

    reconcile_sessions(db, 100001, [], dry_run=False)
    result = reconcile_sessions(db, 100001, [], dry_run=False)

    assert result == []
    assert sessions(db)[0][1] == "interrupted"
