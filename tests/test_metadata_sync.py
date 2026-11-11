"""Tests for AllStarLink directory synchronization."""

import sqlite3

from asl3_connection_logger.database import initialize_database
from asl3_connection_logger.metadata_sync import discover_nodes, sync_nodes


def test_discover_nodes(tmp_path):
    db = tmp_path / "nodes.db"
    initialize_database(db)

    with sqlite3.connect(db) as connection:
        connection.execute("""
            INSERT INTO connection_sessions
                (local_node, remote_node, connected_at, status)
            VALUES ('100001', '100002', CURRENT_TIMESTAMP, 'active')
        """)
        connection.execute("""
            INSERT INTO node_metadata_overrides
                (node_number, description)
            VALUES ('123456', 'Custom Node')
        """)

    assert discover_nodes(db) == ["100001", "100002", "123456"]


def test_sync_success(tmp_path, monkeypatch):
    import asl3_connection_logger.metadata_sync as sync

    db = tmp_path / "nodes.db"
    initialize_database(db)

    monkeypatch.setattr(
        sync,
        "fetch_node",
        lambda node, timeout: {
            "node_number": node,
            "callsign": "N0CALL",
            "location": "Example Location",
        },
    )

    result = sync_nodes(db, nodes=["100001"], delay=0)

    assert result == {"updated": 1, "missing": 0, "failed": 0}

    with sqlite3.connect(db) as connection:
        callsign = connection.execute("""
            SELECT callsign FROM node_metadata
            WHERE node_number = '100001'
        """).fetchone()[0]

    assert callsign == "N0CALL"


def test_sync_missing_node(tmp_path, monkeypatch):
    import asl3_connection_logger.metadata_sync as sync

    db = tmp_path / "nodes.db"
    initialize_database(db)

    monkeypatch.setattr(
        sync,
        "fetch_node",
        lambda node, timeout: None,
    )

    result = sync_nodes(db, nodes=["999999"], delay=0)

    assert result == {"updated": 0, "missing": 1, "failed": 0}


def test_sync_failure_preserves_cache(tmp_path, monkeypatch):
    import asl3_connection_logger.metadata_sync as sync

    db = tmp_path / "nodes.db"
    initialize_database(db)

    with sqlite3.connect(db) as connection:
        connection.execute("""
            INSERT INTO node_metadata (node_number, callsign)
            VALUES ('100001', 'N0CALL')
        """)

    def fail_fetch(node, timeout):
        raise TimeoutError("Directory unavailable")

    monkeypatch.setattr(sync, "fetch_node", fail_fetch)

    result = sync_nodes(db, nodes=["100001"], delay=0)

    assert result == {"updated": 0, "missing": 0, "failed": 1}

    with sqlite3.connect(db) as connection:
        callsign = connection.execute("""
            SELECT callsign FROM node_metadata
            WHERE node_number = '100001'
        """).fetchone()[0]

    assert callsign == "N0CALL"


def test_sync_invalid_node(tmp_path):
    db = tmp_path / "nodes.db"
    initialize_database(db)

    result = sync_nodes(db, nodes=["invalid"], delay=0)

    assert result == {"updated": 0, "missing": 0, "failed": 1}
