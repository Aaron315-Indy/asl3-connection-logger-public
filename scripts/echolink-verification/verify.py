"""Isolated live verification; only standard-library dependencies."""
import argparse
import json
import logging
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from asl3_connection_logger.echolink import parse_directory
from asl3_connection_logger.metadata import resolve_node
from asl3_connection_logger.metadata_sync import sync_nodes
from asl3_connection_logger.collector import process_event
from asl3_connection_logger.web import DashboardHandler


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def api_rows(server):
    with urlopen(f'http://127.0.0.1:{server.server_port}/api/dashboard', timeout=10) as response:
        require(response.status == 200, 'dashboard HTTP status')
        return json.load(response)


def check_api(server, entries, allstar, override=False):
    payload = api_rows(server)
    sessions = {row['remote_node']: row for row in payload['sessions']}
    top = {row['remote_node']: row for row in payload['top_nodes']}
    for index, entry in enumerate(entries):
        node = entry['node_number']
        expected = 'VERIFY-OVERRIDE' if override and index == 0 else entry['callsign']
        require(sessions[node]['remote_metadata']['callsign'] == expected,
                f'dashboard session callsign mismatch: {node}')
        require(top[node]['remote_metadata']['callsign'] == expected,
                f'dashboard top-nodes callsign mismatch: {node}')
        require(sessions[node]['local_metadata']['callsign'] == allstar,
                'dashboard AllStarLink resolution mismatch')


def verify(db, args):
    # Query live CLI directly. There is deliberately no fixture/fallback option.
    result = subprocess.run(['asterisk', '-rx', 'echolink dbdump'],
                            check=True, capture_output=True, text=True,
                            timeout=args.timeout)
    try:
        directory = parse_directory(result.stdout)
    except ValueError as exc:
        raise RuntimeError(f"{exc}; CLI stdout={result.stdout[:300]!r}; "
                           f"stderr={result.stderr[:300]!r}") from exc
    # Build expectations independently from the raw IDs, not the parser's keys.
    candidates = {}
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split('|')]
        if len(parts) != 3 or not parts[0].isascii() or not parts[0].isdigit():
            continue
        try:
            identity = int(parts[0])
        except ValueError:
            continue
        node = str(3_000_000 + identity)
        if identity > 0 and node in directory:
            require(directory[node]['callsign'] == parts[1], 'raw callsign mismatch')
            candidates[node] = dict(echolink_id=parts[0], node_number=node,
                                    callsign=parts[1])
    require(len(candidates) >= 3, f'need 3 actual entries; found {len(candidates)}')
    preferred = ['3100016', '3930729']
    selected = sorted(candidates, key=lambda n: (n not in preferred, int(n)))[:3]
    entries = [candidates[node] for node in selected]
    print(f'PASS live directory: {len(directory)} valid entries', flush=True)
    for entry in entries:
        print('LIVE selected ' + json.dumps(entry, sort_keys=True), flush=True)

    # Seed new test history only; no installed database is opened or copied.
    for entry in entries:
        process_event(db, args.allstar_node, entry['node_number'], 'connect')
    with sqlite3.connect(db) as connection:
        history = connection.execute('SELECT * FROM connection_sessions').fetchall()
        events = connection.execute('SELECT * FROM connection_events').fetchall()
    expected = dict(updated=4, missing=0, failed=0)
    actual = sync_nodes(db, timeout=args.timeout, delay=0)
    require(actual == expected, f'live metadata sync failed: {actual}; expected {expected}')
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        for entry in entries:
            node = entry['node_number']
            cached = connection.execute('SELECT callsign FROM node_metadata WHERE node_number=?', (node,)).fetchone()
            require(cached is not None and cached[0] == entry['callsign'],
                    f'cache mismatch: {node}; directory may have changed during test')
            require(resolve_node(connection, node)['callsign'] == entry['callsign'],
                    f'resolver mismatch: {node}')
        allstar = resolve_node(connection, args.allstar_node)['callsign']
        require(bool(allstar), f'AllStarLink {args.allstar_node} has no live callsign')

    class QuietHandler(DashboardHandler):
        database = str(db)
        def log_message(self, *unused):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        check_api(server, entries, allstar)
        print('PASS dashboard HTTP API: sessions and top_nodes (loopback, temporary port)', flush=True)
        with sqlite3.connect(db) as connection:
            connection.execute('INSERT INTO node_metadata_overrides (node_number, callsign) VALUES (?, ?)',
                               (entries[0]['node_number'], 'VERIFY-OVERRIDE'))
            connection.execute('INSERT INTO node_metadata_overrides (node_number, location) VALUES (?, ?)',
                               (args.allstar_node, 'VERIFY-LOCATION'))
        actual = sync_nodes(db, timeout=args.timeout, delay=0)
        require(actual == expected, f'repeated live sync failed: {actual}')
        with sqlite3.connect(db) as connection:
            connection.row_factory = sqlite3.Row
            require(resolve_node(connection, entries[0]['node_number'])['callsign'] == 'VERIFY-OVERRIDE',
                    'EchoLink manual override lost')
            merged = resolve_node(connection, args.allstar_node)
            require(merged['callsign'] == allstar and merged['location'] == 'VERIFY-LOCATION',
                    'AllStarLink field override or directory callsign lost')
            require([tuple(row) for row in connection.execute('SELECT * FROM connection_sessions')] == history,
                    'connection history changed during synchronization')
            require([tuple(row) for row in connection.execute('SELECT * FROM connection_events')] == events,
                    'connection events changed during synchronization')
        check_api(server, entries, allstar, override=True)
        payload = api_rows(server)
        require(all(row['local_metadata']['location'] == 'VERIFY-LOCATION' for row in payload['sessions']),
                'AllStarLink location override absent from API')
        for entry in entries:
            print('PASS EchoLink ' + json.dumps(entry, sort_keys=True), flush=True)
        print(f'PASS live AllStarLink: node={args.allstar_node} callsign={allstar}', flush=True)
        print('PASS manual overrides survive repeated sync; session/event history unchanged', flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-host', default='node651861')
    parser.add_argument('--allstar-node', default='651861')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args(argv)
    require(args.timeout > 0, 'timeout must be positive')
    require(args.allstar_node.isascii() and args.allstar_node.isdigit()
            and 0 < int(args.allstar_node) <= 3_000_000, 'invalid AllStarLink node')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    try:
        host = socket.gethostname().split('.')[0]
        require(host == args.expected_host, f'host mismatch: actual={host}, expected={args.expected_host}')
        print(f'Verifying on {host}; bundled code only; installed logger is not imported', flush=True)
        with tempfile.TemporaryDirectory(prefix='asl3-v025-live-', dir='/var/tmp') as temporary:
            try:
                verify(Path(temporary) / 'verification.sqlite', args)
            finally:
                print('Removing disposable database and temporary directory', flush=True)
        print('PASS cleanup; PASS overall live verification', flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            print(f'CLI stderr={exc.stderr!r}; stdout={exc.stdout!r}', file=sys.stderr)
        print(f'FAIL live verification: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
