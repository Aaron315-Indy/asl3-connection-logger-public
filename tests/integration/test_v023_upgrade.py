"""Real v0.2.3 to v0.2.4 wheels, SQLite and HTTP; service control is a fixture.

No production service manager, node, configuration or database is accessed.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def http(port, path):
    with urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
        return json.load(response)


def history(path):
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        return {table: db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                for table in ('connection_events', 'connection_sessions')}


@pytest.fixture(scope='module')
def upgrade_sources(tmp_path_factory):
    if os.geteuid() != 0:
        pytest.skip('Real upgrade credential/backup checks require root in disposable fixtures')
    root = tmp_path_factory.mktemp('v023-upgrade')
    old, incoming = root / 'public-023', root / 'incoming'
    old.mkdir(); incoming.mkdir()
    archive = subprocess.check_output(['git', 'archive', 'v0.2.3'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(old, filter='data')
    for name in ('pyproject.toml', 'setup.py', 'README.md', 'LICENSE'):
        shutil.copy2(ROOT / name, incoming / name)
    for name in ('src', 'scripts', 'systemd'):
        shutil.copytree(ROOT / name, incoming / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info', 'build-info.json'))
    env = dict(os.environ)
    env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
    env.update(PIP_NO_INDEX='1', PIP_NO_BUILD_ISOLATION='0', PIP_NO_CACHE_DIR='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_CONFIG_FILE=os.devnull,
               PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    wheels = root / 'wheels'; wheels.mkdir()
    subprocess.check_output([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation',
                             '--no-deps', '--wheel-dir', str(wheels), str(old)],
                            cwd=root, env=env, stderr=subprocess.STDOUT)
    wheel, = wheels.glob('*.whl')
    assert wheel.name.startswith('asl3_connection_logger-0.2.3-')
    try:
        yield root, incoming, wheel, env
    finally:
        shutil.rmtree(root)


class UpgradeMachine:
    def __init__(self, root, source, env, backup_root):
        self.root, self.source, self.env = root, source, env
        self.install = root / 'installed app'
        self.units = root / 'units'; self.units.mkdir()
        self.backups = backup_root / 'backups'; self.backups.mkdir(mode=0o700)
        self.database = root / 'connections.db'
        self.python = self.install / '.venv/bin/python'
        self.upgrade = load(source / 'scripts/upgrade.py', 'integration_upgrade')
        self.upgrade.UNIT_DIR = self.units
        self.original_run = self.upgrade.run
        self.upgrade.run = self.run
        self.process = None; self.processes = []; self.starts = 0
        self.timer_active = 'inactive'; self.timer_enabled = ''
        self.failure = None; self.injected = False; self.calls = []
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]

    def python_run(self, code):
        return subprocess.check_output([str(self.python), '-c', code], cwd=self.install,
                                       env=self.env, text=True, stderr=subprocess.STDOUT).strip()

    def fields(self, unit):
        path = self.units / (unit if unit.endswith(('.service', '.timer')) else unit + '.service')
        return dict(line.split('=', 1) for line in path.read_text().splitlines()
                    if '=' in line and not line.startswith('#')) if path.exists() else {}

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == 'systemctl':
            return self.control(args)
        assert args[0] in (str(self.python), 'systemd-analyze'), args
        if args[0] == 'systemd-analyze':
            assert all(Path(p).is_relative_to(self.backups) for p in args[3:])
        result = self.original_run(*args, **kwargs)
        if args[1:5] == ('-m', 'pip', 'install', '--upgrade') and self.failure == 'pip' and not self.injected:
            self.injected = True
            # A real callback arrives AFTER the backup and package replacement.
            self.callback('777001')
            raise RuntimeError('injected failure after real pip and callback')
        return result

    def control(self, args):
        action = args[1]
        if action == 'show':
            unit, name = args[2], args[3].split('=', 1)[1]
            assert unit in (self.upgrade.SERVICE, *self.upgrade.UNITS)
            if name == 'ActiveState':
                if unit == self.upgrade.SERVICE:
                    return 'active' if self.process and self.process.poll() is None else 'inactive'
                return self.timer_active if unit == self.upgrade.TIMER else 'inactive'
            if name == 'UnitFileState': return self.timer_enabled
            if name == 'ExecStart':
                value = self.fields(unit).get('ExecStart')
                return '{ argv[]=' + value + ' ; ignore_errors=no ; }' if value else ''
            if name == 'WorkingDirectory': return str(self.install)
            raise AssertionError(args)
        if action == 'daemon-reload': return ''
        if action == 'restart':
            assert args[2] == self.upgrade.SERVICE
            self.stop()
            if self.failure == 'restart' and not self.injected:
                self.injected = True
                raise RuntimeError('injected restart failure')
            corrupt = self.failure == 'verification' and not self.injected
            self.injected |= corrupt
            self.start(corrupt=corrupt)
            return ''
        assert args[-1] == self.upgrade.TIMER, args
        wants = self.units / 'timers.target.wants'
        link = wants / self.upgrade.TIMER
        if action == 'start':
            if self.failure == 'timer' and not self.injected:
                self.injected = True
                raise RuntimeError('injected timer activation failure')
            self.timer_active = 'active'
        elif action == 'stop': self.timer_active = 'inactive'
        elif action == 'enable':
            self.timer_enabled = 'enabled'
            wants.mkdir(exist_ok=True)
            if not link.is_symlink(): link.symlink_to('../' + self.upgrade.TIMER)
        elif action == 'disable':
            self.timer_enabled = 'disabled'
            link.unlink(missing_ok=True)
        else: raise AssertionError(args)
        return ''

    def start(self, corrupt=False, bad_data=False):
        args = shlex.split(self.fields(self.upgrade.SERVICE)['ExecStart'])
        assert args[0] == str(self.python)
        if bad_data:
            code = """from asl3_connection_logger import web
original = web.DashboardHandler.do_GET
def get(self):
    if self.path.startswith('/api/dashboard'):
        return self.send_json({'error': 'injected missing data endpoint'}, 404)
    return original(self)
web.DashboardHandler.do_GET = get
web.main()
"""
            args = [str(self.python), '-c', code, *args[3:]]
        elif corrupt:
            args = [str(self.python), '-c', 'from asl3_connection_logger import web; '
                    'web.RUNNING_RELEASE = dict(web.RUNNING_RELEASE, content_sha256="0" * 64); '
                    'web.main()', *args[3:]]
        self.starts += 1
        logfile = self.root / f'http-{self.starts}.log'
        with logfile.open('wb') as log:
            self.process = subprocess.Popen(args, cwd=self.install, env=self.env,
                                            stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(self.process)
        for _ in range(100):
            if self.process.poll() is not None:
                raise AssertionError(logfile.read_text())
            try:
                assert http(self.port, '/health') == {'status': 'ok'}
                return
            except (OSError, URLError):
                time.sleep(0.1)
        raise AssertionError('disposable dashboard did not become ready')

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)

    def callback(self, remote):
        self.python_run('from asl3_connection_logger.collector import process_event; '
                        f'process_event({str(self.database)!r}, "658860", {remote!r}, "connect")')


@pytest.fixture
def v023_machine(upgrade_sources, tmp_path, external_tmp_path, monkeypatch):
    _, source, wheel, env = upgrade_sources
    # Only the current module's subprocess environment is altered for offline builds.
    for name in ('PIP_NO_INDEX', 'PIP_NO_BUILD_ISOLATION', 'PIP_NO_CACHE_DIR',
                 'PIP_DISABLE_PIP_VERSION_CHECK', 'PIP_CONFIG_FILE'):
        monkeypatch.setenv(name, env[name])
    machine = UpgradeMachine(tmp_path, source, env, external_tmp_path)
    subprocess.check_output([sys.executable, '-m', 'venv', '--system-site-packages',
                             str(machine.install / '.venv')], env=env, stderr=subprocess.STDOUT)
    subprocess.check_output([str(machine.python), '-m', 'pip', 'install', '--no-deps', str(wheel)],
                            env=env, cwd=tmp_path, stderr=subprocess.STDOUT)
    machine.python_run('from datetime import datetime, timezone; '
        'from asl3_connection_logger.collector import process_event; '
        f'p={str(machine.database)!r}; '
        'process_event(p,"658860","2000","connect",timestamp=datetime(2026,1,1,tzinfo=timezone.utc)); '
        'process_event(p,"658860","2000","disconnect",timestamp=datetime(2026,1,1,1,tzinfo=timezone.utc)); '
        'process_event(p,"1999","3000","connect")')
    machine.database.chmod(0o640)
    service = machine.units / (machine.upgrade.SERVICE + '.service')
    service.write_text('[Service]\nWorkingDirectory=' + str(machine.install) + '\nExecStart=' +
        shlex.join([str(machine.python), '-m', 'asl3_connection_logger.web', '--database',
                    str(machine.database), '--host', '127.0.0.1', '--port', str(machine.port)]) + '\n')
    service.chmod(0o640)
    (machine.units / (service.name + '.d')).mkdir()
    override = machine.units / (service.name + '.d') / 'override.conf'
    override.write_text('[Service]\nEnvironment=OPERATOR_SETTING=preserve\n'); override.chmod(0o600)
    for name in ('rpt.conf', 'apache.conf', 'auth.htpasswd', 'callback-wrapper'):
        path = tmp_path / name
        path.write_bytes(b'unchanged operator configuration'); path.chmod(0o640)
    private = machine.install / '.venv/operator-private'
    private.write_bytes(b'preserve nonpackage files, owner and permissions'); private.chmod(0o600)
    os.chown(private, 12345, 12346)
    (machine.install / '.venv/operator-link').symlink_to('operator-private')
    machine.before = history(machine.database)
    machine.db_stat = machine.database.stat()
    machine.sentinels = {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_uid, path.stat().st_gid)
                         for path in (service, override, *(tmp_path / name for name in
                                     ('rpt.conf', 'apache.conf', 'auth.htpasswd', 'callback-wrapper')))}
    keeper = sqlite3.connect(machine.database)
    keeper.execute('PRAGMA journal_mode=WAL')
    try:
        machine.start()
        yield machine
    finally:
        machine.stop(); machine.timer_active = 'inactive'
        keeper.close()
        assert all(process.poll() is not None for process in machine.processes)
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', machine.port))


def assert_history_and_configuration(machine, schema=3):
    rows = history(machine.database)
    for table, before in machine.before.items(): assert rows[table][:len(before)] == before
    after = machine.database.stat()
    assert (after.st_ino, after.st_uid, after.st_gid, after.st_mode) == (
        machine.db_stat.st_ino, machine.db_stat.st_uid, machine.db_stat.st_gid, machine.db_stat.st_mode)
    with sqlite3.connect(machine.database) as db:
        assert db.execute('SELECT version FROM schema_version').fetchone() == (schema,)
    for path, expected in machine.sentinels.items():
        info = path.stat()
        assert (path.read_bytes(), info.st_mode, info.st_uid, info.st_gid) == expected
    private = machine.install / '.venv/operator-private'
    assert private.read_bytes() == b'preserve nonpackage files, owner and permissions'
    assert (private.stat().st_uid, private.stat().st_gid, private.stat().st_mode & 0o777) == (12345, 12346, 0o600)
    assert os.readlink(machine.install / '.venv/operator-link') == 'operator-private'


@pytest.mark.parametrize('failure', [None, 'pip', 'restart', 'verification', 'timer'])
def test_real_v023_upgrade_repeat_and_verified_rollback(v023_machine, failure):
    machine = v023_machine
    previous = http(machine.port, '/api/release')
    previous_version = http(machine.port, '/api/version')
    assert previous['version'] == '0.2.3'
    assert machine.upgrade.installed_release(machine.python) == previous
    if failure:
        machine.failure = failure
        with pytest.raises(RuntimeError, match='Previous dashboard restored and verified'):
            machine.upgrade.upgrade(machine.source, machine.install, machine.backups)
        backup, = machine.backups.glob('upgrade-*')
        state = json.loads((backup / 'state.json').read_text())
        assert state['state'] == 'rolled-back' and state['dashboard_verified'] is True
        assert http(machine.port, '/api/release') == previous
        assert http(machine.port, '/api/version') == previous_version
        assert machine.upgrade.installed_release(machine.python) == previous
        assert not any((machine.units / unit).exists() for unit in machine.upgrade.UNITS)
        assert machine.timer_active == 'inactive'
        assert not (machine.units / 'timers.target.wants' / machine.upgrade.TIMER).is_symlink()
        machine.callback('777004')
        assert len(history(machine.database)['connection_events']) == (5 if failure == 'pip' else 4)
    else:
        backup = machine.upgrade.upgrade(machine.source, machine.install, machine.backups)
        state = json.loads((backup / 'state.json').read_text())
        assert state['state'] == 'complete'
        assert http(machine.port, '/api/release') == state['expected']
        assert machine.upgrade.installed_release(machine.python) == state['expected']
        assert state['expected']['version'] == machine.upgrade.version_from_source(
            (machine.source / 'src/asl3_connection_logger/_version.py').read_text())
        assert machine.process.pid != machine.processes[0].pid
        pid = machine.process.pid
        again = machine.upgrade.upgrade(machine.source, machine.install, machine.backups)
        assert json.loads((again / 'state.json').read_text())['state'] == 'complete'
        assert machine.process.pid == pid
        assert len(history(machine.database)['connection_events']) == 3
    assert history(backup / 'connections.db') == machine.before
    assert_history_and_configuration(machine, schema=3)


def test_real_v023_missing_history_api_retains_backups(v023_machine):
    machine = v023_machine
    previous = machine.upgrade.installed_release(machine.python)
    machine.stop(); machine.start(bad_data=True)
    with pytest.raises(RuntimeError) as error:
        machine.upgrade.upgrade(machine.source, machine.install, machine.backups)
    assert f'GET http://127.0.0.1:{machine.port}/api/dashboard?limit=1' in str(error.value)
    backup, = machine.backups.glob('upgrade-*')
    assert json.loads((backup / 'state.json').read_text())['state'] == 'preparation-failed'
    assert history(backup / 'connections.db') == machine.before
    assert machine.upgrade.installed_release(machine.python) == previous
    assert not any(args[1:4] == ('-m', 'pip', 'install') for args in machine.calls)
    assert_history_and_configuration(machine)
