from datetime import datetime
import pytest

from asl3_connection_logger.collector import process_event
from asl3_connection_logger.web import read_dashboard


def test_dashboard_reads_sessions(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")
    process_event(db, 100001, 100002, "disconnect")
    process_event(db, 100001, 123456, "connect")

    result = read_dashboard(db)

    assert result["counts"]["completed"] == 1
    assert result["counts"]["active"] == 1
    assert len(result["sessions"]) == 2
    assert len(result["top_nodes"]) == 2


def test_dashboard_filters(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect")
    process_event(db, 100001, 123456, "connect")

    result = read_dashboard(db, remote="100002")

    assert len(result["sessions"]) == 1
    assert result["sessions"][0]["remote_node"] == "100002"


def test_dashboard_rejects_invalid_filters(tmp_path):
    with pytest.raises(ValueError):
        read_dashboard(tmp_path / "missing.db", status="hacked")


def test_dashboard_limit(tmp_path):
    db = tmp_path / "connections.db"

    for node in range(100001, 100006):
        process_event(db, 100001, node, "connect")

    result = read_dashboard(db, limit=2)
    assert len(result["sessions"]) == 2


def test_dashboard_date_range(tmp_path):
    db = tmp_path / "connections.db"

    process_event(db, 100001, 100002, "connect",
                  timestamp=datetime.fromisoformat("2026-10-01T12:00:00+00:00"))
    process_event(db, 100001, 100002, "disconnect",
                  timestamp=datetime.fromisoformat("2026-10-01T13:00:00+00:00"))
    process_event(db, 100001, 123456, "connect",
                  timestamp=datetime.fromisoformat("2026-10-20T12:00:00+00:00"))

    result = read_dashboard(
        db, date_from="2026-10-15", date_to="2026-10-25"
    )

    assert len(result["sessions"]) == 1
    assert result["sessions"][0]["remote_node"] == "123456"


def test_dashboard_invalid_date_range(tmp_path):
    with pytest.raises(ValueError):
        read_dashboard(
            tmp_path / "missing.db",
            date_from="2026-10-25",
            date_to="2026-10-01",
        )
