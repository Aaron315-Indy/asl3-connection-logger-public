"""Local simulation checks for the live-only verification runner."""
import importlib.util
from pathlib import Path
import socket
import subprocess

import pytest

from asl3_connection_logger import metadata_sync

RUNNER = Path(__file__).resolve().parents[1] / 'scripts/echolink-verification/verify.py'
spec = importlib.util.spec_from_file_location('live_verify', RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

DUMP = '100016|DW3XFA|44.31.169.232\n930729|KC9MCC-R|135.131.11.62\n1|N0TEST|192.0.2.1\n1234567|N0LONG|192.0.2.2\n'


def test_runner_simulated_success(monkeypatch, capsys):
    def command(args, **kwargs):
        assert args == ['asterisk', '-rx', 'echolink dbdump']
        return subprocess.CompletedProcess(args, 0, stdout=DUMP)
    monkeypatch.setattr(runner.subprocess, 'run', command)
    monkeypatch.setattr(metadata_sync, 'fetch_node', lambda node, timeout: {
        'node_number': node, 'callsign': 'ASL-LIVE-SIMULATION'})
    assert runner.main(['--expected-host', socket.gethostname().split('.')[0]]) == 0
    output = capsys.readouterr().out
    assert 'PASS overall live verification' in output
    assert 'DW3XFA' in output and 'KC9MCC-R' in output
    assert '3100016' in output and '3930729' in output


@pytest.mark.parametrize('output', ["No such command 'echolink dbdump'", '', DUMP.splitlines()[0]])
def test_runner_fails_closed_and_cleans_up(monkeypatch, capsys, output):
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout=output))
    before = set(Path('/var/tmp').glob('asl3-v025-live-*'))
    assert runner.main(['--expected-host', socket.gethostname().split('.')[0]]) == 1
    captured = capsys.readouterr()
    assert 'FAIL live verification' in captured.err
    assert 'PASS overall' not in captured.out
    assert set(Path('/var/tmp').glob('asl3-v025-live-*')) == before


def test_runner_cli_failure(monkeypatch, capsys):
    def command(*args, **kwargs):
        raise subprocess.TimeoutExpired('asterisk', 30)
    monkeypatch.setattr(runner.subprocess, 'run', command)
    assert runner.main(['--expected-host', socket.gethostname().split('.')[0]]) == 1
    assert 'TimeoutExpired' in capsys.readouterr().err
