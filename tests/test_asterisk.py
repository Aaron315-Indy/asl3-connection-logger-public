import pytest

from asl3_connection_logger.asterisk import (
    parse_stats,
    parse_lstats,
)


def test_empty_stats():
    output = """
******** NODE 100001 STATISTICS ********
Nodes currently connected to us..................: <NONE>
"""
    assert parse_stats(output, "100001") == set()


def test_invalid_stats():
    with pytest.raises(ValueError):
        parse_stats("", "100001")


def test_empty_links():
    output = """NODE      PEER                RECONNECTS  DIRECTION  CONNECT TIME        CONNECT STATE
----      ----                ----------  ---------  ------------        -------------
"""
    assert parse_lstats(output, "100001") == set()


def test_invalid_links():
    with pytest.raises(ValueError):
        parse_lstats("", "100001")


def test_invalid_remote_node():
    output = """NODE      PEER                RECONNECTS  DIRECTION  CONNECT TIME        CONNECT STATE
----      ----                ----------  ---------  ------------        -------------
INVALID   203.0.113.97        0           OUT        00:00:30            ESTABLISHED
"""
    with pytest.raises(ValueError):
        parse_lstats(output, "100001")


def test_real_established_connection():
    output = """NODE      PEER                RECONNECTS  DIRECTION  CONNECT TIME        CONNECT STATE
----      ----                ----------  ---------  ------------        -------------
100002    203.0.113.97        0           IN         00:00:18:154        ESTABLISHED
"""
    assert parse_lstats(output, "100001") == {"100002"}
