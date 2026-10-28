# SPDX-License-Identifier: GPL-3.0-or-later
"""Connection event processing tests."""

import sqlite3
from datetime import datetime, timezone

from asl3_connection_logger.collector import process_event


def utc(hour, minute):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


def test_completed_session(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, "100001", "123456", "connect", utc(21, 17))
    process_event(db, "100001", "123456", "disconnect", utc(23, 34))

    with sqlite3.connect(db) as connection:
        session = connection.execute(
            """
            SELECT connected_at, disconnected_at,
                   duration_seconds, status
            FROM connection_sessions
            """
        ).fetchone()

        assert session[0] == utc(21, 17).isoformat()
        assert session[1] == utc(23, 34).isoformat()
        assert session[2] == 8220
        assert session[3] == "completed"


def test_duplicate_connect(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 123456, "connect", utc(21, 17))
    process_event(db, 100001, 123456, "connect", utc(21, 18))

    with sqlite3.connect(db) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM connection_sessions"
        ).fetchone()[0]

        assert count == 1


def test_unmatched_disconnect(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 123456, "disconnect", utc(23, 34))

    with sqlite3.connect(db) as connection:
        events = connection.execute(
            "SELECT COUNT(*) FROM connection_events"
        ).fetchone()[0]

        sessions = connection.execute(
            "SELECT COUNT(*) FROM connection_sessions"
        ).fetchone()[0]

        assert events == 1
        assert sessions == 0


def test_invalid_event(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        process_event(
            tmp_path / "connections.db",
            100001, 123456, "invalid",
        )


def test_repeated_connection(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect", utc(20, 0))
    process_event(db, 100001, 100002, "disconnect", utc(20, 5))
    process_event(db, 100001, 100002, "connect", utc(21, 0))
    process_event(db, 100001, 100002, "disconnect", utc(21, 10))

    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """
            SELECT duration_seconds, status
            FROM connection_sessions
            ORDER BY id
            """
        ).fetchall()

    assert rows == [
        (300, "completed"),
        (600, "completed"),
    ]


def test_disconnect_before_connect(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "disconnect", utc(20, 0))
    process_event(db, 100001, 100002, "connect", utc(20, 5))

    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT status FROM connection_sessions"
        ).fetchall()

    assert rows == [("active",)]


def test_fractional_duration_rounding(tmp_path):
    from datetime import timedelta

    db = tmp_path / "connections.db"
    start = utc(20, 0)

    process_event(db, 100001, 100002, "connect", start)
    process_event(
        db, 100001, 100002, "disconnect",
        start + timedelta(seconds=35, milliseconds=800),
    )

    with sqlite3.connect(db) as connection:
        duration = connection.execute(
            "SELECT duration_seconds FROM connection_sessions"
        ).fetchone()[0]

    assert duration == 36
