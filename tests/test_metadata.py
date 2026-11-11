"""Node metadata integration tests."""

import json
import sqlite3

import pytest

from asl3_connection_logger.database import initialize_database
from asl3_connection_logger.metadata import (
    cache_node,
    fetch_node,
    normalize_record,
    resolve_node,
)


SAMPLE = {
    "name": 100001,
    "User_ID": "N0CALL",
    "callsign": "N0CALL",
    "Location": "Example Location",
    "node_frequency": "Example Hub",
    "node_tone": "",
    "SiteName": "",
    "Affiliation": "",
    "regseconds": 1793307211,
}


def test_normalize_directory_record():
    result = normalize_record(SAMPLE)

    assert result["node_number"] == "100001"
    assert result["callsign"] == "N0CALL"
    assert result["frequency"] == "Example Hub"
    assert result["tone"] is None


def test_reject_invalid_directory_record():
    with pytest.raises(ValueError):
        normalize_record({"name": "invalid"})


def test_cache_and_resolve(tmp_path):
    db = tmp_path / "metadata.db"
    initialize_database(db)

    cache_node(db, normalize_record(SAMPLE))

    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        result = resolve_node(connection, "100001")

    assert result["callsign"] == "N0CALL"
    assert result["location"] == "Example Location"


def test_local_override_precedence(tmp_path):
    db = tmp_path / "metadata.db"
    initialize_database(db)

    cache_node(db, normalize_record(SAMPLE))

    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO node_metadata_overrides
                (node_number, description, location)
            VALUES (?, ?, ?)
            """,
            ("100001", "Example Hub", "Custom Location"),
        )
        connection.commit()

        result = resolve_node(connection, "100001")

    assert result["description"] == "Example Hub"
    assert result["location"] == "Custom Location"
    assert result["callsign"] == "N0CALL"


def test_unknown_node_fallback(tmp_path):
    db = tmp_path / "metadata.db"
    initialize_database(db)

    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        result = resolve_node(connection, "999999999")

    assert result["node_number"] == "999999999"
    assert result["callsign"] is None


def test_directory_fetch_mocked(monkeypatch):
    import asl3_connection_logger.metadata as metadata

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            return json.dumps([SAMPLE]).encode()

    monkeypatch.setattr(
        metadata,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = fetch_node("100001")

    assert result["callsign"] == "N0CALL"


def test_directory_missing_node(monkeypatch):
    import asl3_connection_logger.metadata as metadata

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            return b"[]"

    monkeypatch.setattr(
        metadata,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    assert fetch_node("999999") is None


def test_dashboard_metadata_integration(tmp_path):
    from asl3_connection_logger.collector import process_event
    from asl3_connection_logger.web import read_dashboard

    db = tmp_path / "dashboard-metadata.db"
    initialize_database(db)

    process_event(db, 100001, 123456, "connect")

    cache_node(db, normalize_record(SAMPLE))

    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO node_metadata_overrides
                (node_number, description, location)
            VALUES (?, ?, ?)
            """,
            ("100001", "Example Hub", "Test Location"),
        )

    result = read_dashboard(db)
    session = result["sessions"][0]

    assert session["local_node"] == "100001"
    assert session["local_metadata"]["callsign"] == "N0CALL"
    assert session["local_metadata"]["description"] == "Example Hub"
    assert session["local_metadata"]["location"] == "Test Location"

    assert session["remote_node"] == "123456"
    assert session["remote_metadata"]["node_number"] == "123456"
    assert session["remote_metadata"]["callsign"] is None

    assert result["top_nodes"][0]["remote_metadata"]["node_number"] == "123456"
