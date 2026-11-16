"""Local EchoLink directory and dashboard API regression tests."""
import json
import sqlite3
import subprocess
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest

from asl3_connection_logger import echolink, metadata_sync
from asl3_connection_logger.collector import process_event
from asl3_connection_logger.database import initialize_database
from asl3_connection_logger.metadata import cache_node
from asl3_connection_logger.web import DashboardHandler

DUMP = """EchoLink directory
930729|KC9MCC-R|135.131.11.62
123456|N0CALL-L|192.0.2.1
000001|*TEST*|192.0.2.2
invalid|BAD|192.0.2.3
12||192.0.2.4
13|N0BAD|999.1.1.1
14|N0BAD|192.0.2.4|extra
"""


def test_parse_directory():
    records = echolink.parse_directory(DUMP)
    assert set(records) == {'3930729', '3123456', '3000001'}
    assert records['3930729'] == {
        'node_number': '3930729', 'callsign': 'KC9MCC-R'}


@pytest.mark.parametrize('output', ['', "No such command 'echolink dbdump'", 'junk|bad|row'])
def test_unavailable_directory(output):
    with pytest.raises(ValueError):
        echolink.parse_directory(output)


def test_cli(monkeypatch):
    def run(args, **kwargs):
        assert args == ['asterisk', '-rx', 'echolink dbdump']
        assert kwargs == dict(capture_output=True, text=True, timeout=7, check=True)
        return subprocess.CompletedProcess(args, 0, stdout=DUMP)
    monkeypatch.setattr(echolink.subprocess, 'run', run)
    assert echolink.fetch_directory(timeout=7)['3930729']['callsign'] == 'KC9MCC-R'


@pytest.mark.parametrize('error', [
    FileNotFoundError('asterisk'), subprocess.TimeoutExpired('asterisk', 1),
    subprocess.CalledProcessError(1, 'asterisk'),
    ValueError('No such command: echolink dbdump'),
])
def test_failure_preserves_cache_and_allstar(tmp_path, monkeypatch, error):
    db = tmp_path / 'test.db'
    initialize_database(db)
    cache_node(db, {'node_number': '3930729', 'callsign': 'CACHED'})
    calls = []
    def fail(timeout):
        calls.append(timeout)
        raise error
    monkeypatch.setattr(metadata_sync, 'fetch_directory', fail)
    monkeypatch.setattr(metadata_sync, 'fetch_node', lambda node, timeout: {
        'node_number': node, 'callsign': 'ALLSTAR'})
    result = metadata_sync.sync_nodes(db, ['3930729', '3123456', '100001'], delay=0)
    assert result == dict(updated=1, missing=0, failed=2)
    assert calls == [10]
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT callsign FROM node_metadata WHERE node_number='3930729'").fetchone()[0] == 'CACHED'
        assert connection.execute("SELECT callsign FROM node_metadata WHERE node_number='100001'").fetchone()[0] == 'ALLSTAR'


def test_existing_sessions_resolve_through_http_api(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    process_event(db, 100001, 3930729, 'connect')
    process_event(db, 100001, 3930729, 'disconnect')
    process_event(db, 100001, 3123456, 'connect')
    with sqlite3.connect(db) as connection:
        history = connection.execute('SELECT * FROM connection_sessions').fetchall()
        connection.execute("INSERT INTO node_metadata_overrides (node_number, callsign) VALUES ('3123456', 'MANUAL')")
    calls = []
    def fetch(timeout):
        calls.append(timeout)
        return echolink.parse_directory(DUMP)
    monkeypatch.setattr(metadata_sync, 'fetch_directory', fetch)
    monkeypatch.setattr(metadata_sync, 'fetch_node', lambda node, timeout: {
        'node_number': node, 'callsign': 'ALLSTAR'})
    assert metadata_sync.sync_nodes(db, delay=0) == dict(updated=3, missing=0, failed=0)
    assert calls == [10]
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT * FROM connection_sessions').fetchall() == history
    handler = type('TestHandler', (DashboardHandler,), {'database': str(db)})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/dashboard') as response:
            data = json.load(response)
        sessions = {row['remote_node']: row for row in data['sessions']}
        assert sessions['3930729']['remote_metadata']['callsign'] == 'KC9MCC-R'
        assert sessions['3123456']['remote_metadata']['callsign'] == 'MANUAL'
        assert sessions['3930729']['local_metadata']['callsign'] == 'ALLSTAR'
        top = {row['remote_node']: row for row in data['top_nodes']}
        assert top['3930729']['remote_metadata']['callsign'] == 'KC9MCC-R'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_missing_entry_preserves_cache_and_original_key(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    initialize_database(db)
    cache_node(db, {'node_number': '3999999', 'callsign': 'CACHED'})
    monkeypatch.setattr(metadata_sync, 'fetch_directory', lambda timeout: echolink.parse_directory(DUMP))
    assert metadata_sync.sync_nodes(db, ['03930729', '3999999'], delay=0) == dict(updated=1, missing=1, failed=0)
    with sqlite3.connect(db) as connection:
        assert dict(connection.execute('SELECT node_number, callsign FROM node_metadata')) == {
            '03930729': 'KC9MCC-R', '3999999': 'CACHED'}


def test_non_echolink_nodes_keep_allstar_resolution(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    initialize_database(db)
    def unexpected(timeout):
        pytest.fail('EchoLink CLI should not run for AllStarLink nodes')
    monkeypatch.setattr(metadata_sync, 'fetch_directory', unexpected)
    monkeypatch.setattr(metadata_sync, 'fetch_node', lambda node, timeout: {
        'node_number': node, 'callsign': 'ALLSTAR'})
    assert metadata_sync.sync_nodes(db, ['100001', '3000000'], delay=0) == dict(updated=2, missing=0, failed=0)


def test_variable_length_ids(tmp_path, monkeypatch):
    dump = "1|N0ONE|192.0.2.1\n12|N0TWO|192.0.2.2\n1234567|N0LONG|192.0.2.3"
    records = echolink.parse_directory(dump)
    assert set(records) == {'3000001', '3000012', '4234567'}
    db = tmp_path / 'variable.db'
    initialize_database(db)
    monkeypatch.setattr(metadata_sync, 'fetch_directory', lambda timeout: records)
    assert metadata_sync.sync_nodes(db, list(records), delay=0) == dict(updated=3, missing=0, failed=0)


@pytest.mark.parametrize('row', [
    '0|ZERO|192.0.2.1', '-1|NEGATIVE|192.0.2.1',
    '１２|UNICODE|192.0.2.1', '12|CALL SIGN|192.0.2.1',
    '12|N0BAD|not-an-ip', '12|N0BAD|192.0.2.1|extra',
    '9' * 5000 + '|HUGE|192.0.2.1',
])
def test_malformed_rows_do_not_discard_good_records(row):
    assert echolink.parse_directory(row + '\n100016|DW3XFA|44.31.169.232') == {
        '3100016': {'node_number': '3100016', 'callsign': 'DW3XFA'}}
