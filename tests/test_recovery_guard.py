# SPDX-License-Identifier: GPL-3.0-or-later

import sqlite3
import pytest

from asl3_connection_logger.collector import process_event
from asl3_connection_logger.recovery import reconcile_sessions


def test_runtime_change_aborts_without_updates(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )

    def changed_runtime():
        raise RuntimeError("Asterisk restarted")

    with pytest.raises(RuntimeError, match="restarted"):
        reconcile_sessions(
            db,
            100001,
            [],
            dry_run=False,
            runtime_id="boot-a:100",
            runtime_guard=changed_runtime,
        )

    with sqlite3.connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM connection_sessions"
        ).fetchone()[0]

    assert status == "active"


def test_runtime_guard_allows_valid_recovery(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )

    checked = []

    reconcile_sessions(
        db,
        100001,
        [],
        dry_run=False,
        runtime_id="boot-a:100",
        runtime_guard=lambda: checked.append(True),
    )

    assert checked == [True]

    with sqlite3.connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM connection_sessions"
        ).fetchone()[0]

    assert status == "interrupted"
