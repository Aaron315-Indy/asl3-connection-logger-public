import sqlite3

from asl3_connection_logger.collector import process_event
from asl3_connection_logger.recovery import reconcile_sessions


def test_old_runtime_interrupted_even_if_reconnected(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )

    changed = reconcile_sessions(
        db, 100001, [100002],
        dry_run=False,
        runtime_id="boot-a:200",
    )

    assert len(changed) == 1

    with sqlite3.connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM connection_sessions"
        ).fetchone()[0]

    assert status == "interrupted"


def test_current_runtime_preserved(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:200",
    )

    changed = reconcile_sessions(
        db, 100001, [100002],
        dry_run=False,
        runtime_id="boot-a:200",
    )

    assert changed == []


def test_recovery_is_idempotent(tmp_path):
    db = tmp_path / "test.db"

    process_event(
        db, 100001, 100002, "connect",
        runtime_id="boot-a:100",
    )

    first = reconcile_sessions(
        db, 100001, [],
        dry_run=False,
        runtime_id="boot-a:200",
    )

    second = reconcile_sessions(
        db, 100001, [],
        dry_run=False,
        runtime_id="boot-a:200",
    )

    assert len(first) == 1
    assert second == []
