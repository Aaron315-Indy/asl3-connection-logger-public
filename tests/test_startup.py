import sqlite3
from unittest.mock import patch

from asl3_connection_logger.collector import process_event
from asl3_connection_logger.startup import recover_previous_runtimes


def test_startup_only_interrupts_previous_runtime(tmp_path):
    db = tmp_path / "test.db"

    process_event(db, 100001, 100001, "connect",
                  runtime_id="old-runtime")
    process_event(db, 100001, 100002, "connect",
                  runtime_id="current-runtime")
    process_event(db, 100001, 100003, "connect")

    with patch(
        "asl3_connection_logger.startup.get_stable_runtime_id",
        return_value="current-runtime",
    ):
        changed = recover_previous_runtimes(
            db, 100001, dry_run=False
        )

        again = recover_previous_runtimes(
            db, 100001, dry_run=False
        )

    assert len(changed) == 1
    assert again == []

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT remote_node, status
            FROM connection_sessions
            ORDER BY remote_node
            """
        ).fetchall()

    assert rows == [
        ("100001", "interrupted"),
        ("100002", "active"),
        ("100003", "active"),
    ]


def test_startup_rejects_runtime_change(tmp_path):
    db = tmp_path / "test.db"
    process_event(db, 100001, 100001, "connect",
                  runtime_id="old-runtime")

    with patch(
        "asl3_connection_logger.startup.get_stable_runtime_id",
        side_effect=["current-runtime", "new-runtime"],
    ):
        try:
            recover_previous_runtimes(db, 100001, dry_run=False)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Runtime change was accepted")

    with sqlite3.connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM connection_sessions"
        ).fetchone()[0]

    assert status == "active"
