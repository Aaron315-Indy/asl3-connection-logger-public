"""Exercise real backup/restore file operations with a simulated service manager.

No test installs a package, changes the host installation, or controls a service.
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
from types import SimpleNamespace
from urllib.error import HTTPError
from zipfile import ZipFile

import pytest

SPEC = importlib.util.spec_from_file_location('upgrade', Path(__file__).resolve().parents[1] / 'scripts/upgrade.py')
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


def info(release):
    return {'version': release['version'], 'commit': release['commit'],
            'build': {'type': 'release', 'dirty': release['dirty'], 'built_at': 'timestamp'}}


def exec_start(args):
    return '{ path=' + args[0] + ' ; argv[]=' + shlex.join(args) + ' ; ignore_errors=no ; }'


@pytest.fixture
def machine(tmp_path, monkeypatch):
    source, install = tmp_path / 'incoming', tmp_path / 'installed'
    root, units = tmp_path / 'backups', tmp_path / 'systemd'
    root.mkdir(mode=0o700)
    units.mkdir()
    (source / 'src/asl3_connection_logger').mkdir(parents=True)
    (source / 'src/asl3_connection_logger/_version.py').write_text('VERSION = "0.2.1"\n')
    (source / 'systemd').mkdir()
    for unit in upgrade.UNITS:
        (source / 'systemd' / unit).write_text(
            'WorkingDirectory=/opt/asl3-connection-logger\n'
            'ExecStart=/opt/asl3-connection-logger/.venv/bin/python '
            '--database ' + upgrade.DEFAULT_DB + '\nnew unit\n')
        (units / unit).write_text('previous ' + unit)
        (units / (unit + '.d')).mkdir()
        (units / (unit + '.d') / 'override.conf').write_text('administrator override')
    (install / '.venv/bin').mkdir(parents=True)
    (install / '.venv/bin/python').write_text('previous interpreter')
    (install / '.venv/previous-only').write_text('preserve this file')
    old = {'version': '0.2.0', 'commit': 'a' * 40, 'dirty': False, 'content_sha256': 'old-content'}
    marker = install / '.venv/release.json'
    marker.write_text(json.dumps(old))
    database, metadata_db = tmp_path / 'custom.db', tmp_path / 'metadata.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE history(value)')
        db.execute('INSERT INTO history VALUES (42)')
    sentinels = {}
    for name in ('apache.conf', 'authentication', 'rpt.conf', 'dashboard.conf'):
        path = tmp_path / name
        path.write_text('existing ' + name)
        sentinels[path] = path.read_bytes()
    state = SimpleNamespace(source=source, install=install, root=root, units=units,
                            database=database, metadata_db=metadata_db, marker=marker,
                            old=old, running=old.copy(), calls=[], failure=None,
                            failed_once=False, timer_active='active', timer_enabled='enabled',
                            metadata_checks=0, previous_endpoint=False, sentinels=sentinels,
                            new=None)
    def fail_once(name):
        if state.failure == name and not state.failed_once:
            state.failed_once = True
            raise RuntimeError('simulated ' + name)
    def run(*args, **kwargs):
        state.calls.append(args)
        if args[0] == 'systemd-analyze':
            return ''  # Real validation is covered by the dedicated filesystem tests.
        if args[0] == 'systemctl':
            action = args[1]
            if action == 'show':
                unit = args[2]
                prop = args[3].split('=', 1)[1]
                if prop == 'ExecStart':
                    if unit == upgrade.SERVICE:
                        return exec_start([str(install / '.venv/bin/python'), '-m',
                                           'asl3_connection_logger.web', '--database', str(database), '--port=9876'])
                    return exec_start([str(install / '.venv/bin/python'), '-m',
                                       'asl3_connection_logger.metadata_sync', '--database', str(metadata_db)])
                if prop == 'WorkingDirectory':
                    return str(install)
                if prop == 'ActiveState':
                    if unit == upgrade.SERVICE:
                        return 'active'
                    if unit == upgrade.TIMER:
                        return state.timer_active
                    state.metadata_checks += 1
                    if state.failure == 'metadata-race' and state.metadata_checks > 1:
                        return 'active'
                    return 'inactive'
                if prop == 'UnitFileState':
                    return state.timer_enabled
            if action == 'daemon-reload':
                fail_once('daemon-reload')
            if action in ('start', 'restart') and args[2] == upgrade.TIMER:
                fail_once('timer-start')
                state.timer_active = 'active'
            if action == 'stop' and args[2] == upgrade.TIMER:
                state.timer_active = 'inactive'
            if action in ('enable', 'disable'):
                state.timer_enabled = 'enabled' if action == 'enable' else 'disabled'
            if action == 'restart' and args[2] == upgrade.SERVICE:
                if state.failure == 'all-restarts':
                    raise RuntimeError('simulated all-restarts')
                fail_once('dashboard-restart')
                state.running = json.loads(marker.read_text())
            return ''
        if '-c' in args:
            release = json.loads(marker.read_text())
            return json.dumps(info(release) if 'version_info' in args[-1] else release)
        if 'wheel' in args:
            fail_once('wheel-build')
            destination = Path(args[args.index('--wheel-dir') + 1]) / 'asl3_connection_logger-0.2.1-py3-none-any.whl'
            with ZipFile(destination, 'w') as archive:
                archive.writestr('asl3_connection_logger/_version.py', 'VERSION = "0.2.1"\n')
                archive.writestr('asl3_connection_logger/build-info.json', json.dumps(
                    {'commit': 'b' * 40, 'dirty': False, 'built_at': 'new timestamp'}))
                archive.writestr('asl3_connection_logger/release.py', 'new implementation')
            state.new = upgrade.wheel_release(destination)
            return ''
        if 'pip' in args and 'install' in args:
            marker.write_text(json.dumps(state.new))
            (install / '.venv/new-only').write_text('partially installed file')
            # Simulate a live callback during the upgrade: rollback must retain it.
            with sqlite3.connect(database) as db:
                db.execute('INSERT INTO history VALUES (99)')
            fail_once('pip-install')
            if state.failure == 'installed-content':
                marker.write_text(json.dumps({**state.new, 'content_sha256': 'incorrect'}))
            return ''
        raise AssertionError(f'Unexpected command: {args}')
    def api(port, path):
        assert port == 9876
        new_running = state.running != state.old
        if state.failure == 'api-health' and new_running and path == '/health':
            return {'status': 'bad'}
        if path == '/health':
            return {'status': 'ok'}
        if path == '/api/version':
            if state.failure == 'api-version' and new_running:
                return info(state.old)
            return info(state.running)
        if path == '/api/dashboard?limit=1':
            if state.failure == 'api-data' and new_running:
                raise RuntimeError('data API unavailable')
            return {'sessions': []}
        if path == '/api/release':
            if state.failure == 'stale-process' and new_running:
                return {**state.new, 'content_sha256': 'stale-process-content'}
            if state.running == state.old and not state.previous_endpoint:
                raise HTTPError('url', 404, 'not found', {}, None)
            return state.running
        raise AssertionError(path)
    monkeypatch.setattr(upgrade, 'run', run)
    monkeypatch.setattr(upgrade, 'get_api', api)
    monkeypatch.setattr(upgrade, 'UNIT_DIR', units)
    monkeypatch.setattr(upgrade.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(upgrade.time, 'sleep', lambda _: None)
    # The protected-root permission checks have separate tests; allow unprivileged CI.
    monkeypatch.setattr(upgrade, 'protected_backup_root', lambda *args: root)
    state.perform = lambda: upgrade.upgrade(source, install, root)
    state.backup = lambda: sorted(root.glob('upgrade-*'))[-1]
    state.status = lambda: json.loads((state.backup() / 'state.json').read_text())
    state.dashboard_restarts = lambda: [args for args in state.calls if args == ('systemctl', 'restart', upgrade.SERVICE)]
    return state


def assert_preserved(machine, rolled_back=False):
    for path, data in machine.sentinels.items():
        assert path.read_bytes() == data
    for unit in upgrade.UNITS:
        assert (machine.units / (unit + '.d') / 'override.conf').read_text() == 'administrator override'
        if rolled_back:
            assert (machine.units / unit).read_text() == 'previous ' + unit
    assert not any(args[0] == 'systemctl' and any('asterisk' in arg or 'apache' in arg for arg in args[1:])
                   for args in machine.calls)
    if rolled_back:
        assert json.loads(machine.marker.read_text()) == machine.old
        assert machine.running == machine.old
        assert (machine.install / '.venv/previous-only').exists()
        assert not (machine.install / '.venv/new-only').exists()
        assert machine.timer_active == 'active'
        assert machine.timer_enabled == 'enabled'


def test_isolated_source_upgrades_installed_location_and_repeats_safely(machine):
    backup = machine.perform()
    assert machine.source != machine.install
    assert backup.parent == machine.root
    assert backup.stat().st_mode & 0o777 == 0o700
    assert machine.status()['state'] == 'complete'
    assert machine.running == machine.new
    assert len(machine.dashboard_restarts()) == 1
    assert not (machine.source / '.venv').exists()
    for unit in upgrade.UNITS:
        content = (machine.units / unit).read_text()
        assert str(machine.install) in content
        assert str(machine.source) not in content
        assert str(machine.metadata_db) in content
    assert any(args[0] == str(machine.install / '.venv/bin/python') and args[-1].endswith('.whl')
               for args in machine.calls if 'install' in args)
    assert_preserved(machine)
    machine.calls.clear()
    machine.previous_endpoint = True
    machine.perform()
    assert not machine.dashboard_restarts()
    assert len(list(machine.root.glob('upgrade-*'))) == 2


@pytest.mark.parametrize('failure', ['pip-install', 'installed-content', 'daemon-reload',
                                    'timer-start', 'dashboard-restart', 'api-health',
                                    'api-version', 'api-data', 'stale-process', 'metadata-race'])
def test_installation_and_verification_failures_automatically_restore(machine, failure):
    machine.failure = failure
    with pytest.raises(RuntimeError, match='Previous dashboard restored and verified'):
        machine.perform()
    assert machine.status()['state'] == 'rolled-back'
    assert_preserved(machine, rolled_back=True)
    assert bool(machine.dashboard_restarts()) == (failure != 'metadata-race')
    with sqlite3.connect(machine.database) as db:
        values = db.execute('SELECT value FROM history').fetchall()
    assert values == ([(42,)] if failure == 'metadata-race' else [(42,), (99,)])
    # SQLite snapshot remains historical; it was never copied over the live file.
    with sqlite3.connect(machine.backup() / 'connections.db') as db:
        assert db.execute('SELECT value FROM history').fetchall() == [(42,)]


@pytest.mark.parametrize('failure', ['sqlite-backup', 'environment-backup', 'unit-backup',
                                    'wheel-build', 'initial-journal', 'prepared-journal'])
def test_preparation_failure_never_uses_partial_backups(machine, monkeypatch, failure):
    real_snapshot, real_journal = upgrade.snapshot_unit, upgrade.journal
    if failure == 'sqlite-backup':
        monkeypatch.setattr(upgrade, 'backup_database', lambda *a: (_ for _ in ()).throw(RuntimeError('backup failed')))
    if failure == 'environment-backup':
        def partial_copy(src, dst, **kwargs):
            Path(dst).mkdir()
            (Path(dst) / 'partial').write_text('incomplete')
            raise OSError('backup space exhausted')
        monkeypatch.setattr(upgrade.shutil, 'copytree', partial_copy)
    if failure == 'unit-backup':
        def partial_unit(target, backup):
            if target.name.endswith('.timer'):
                raise OSError('unit backup failed')
            return real_snapshot(target, backup)
        monkeypatch.setattr(upgrade, 'snapshot_unit', partial_unit)
    if failure in ('initial-journal', 'prepared-journal'):
        def write_state(backup, state, **details):
            if state == ('preparing' if failure == 'initial-journal' else 'prepared'):
                raise OSError('journal failed')
            real_journal(backup, state, **details)
        monkeypatch.setattr(upgrade, 'journal', write_state)
    machine.failure = failure
    with pytest.raises(RuntimeError, match='preparation failed; installation unchanged'):
        machine.perform()
    assert machine.status()['state'] == 'preparation-failed'
    assert not machine.dashboard_restarts()
    assert not any('install' in args and 'pip' in args for args in machine.calls)
    assert not any(args[:2] == ('systemctl', 'stop') for args in machine.calls)
    assert_preserved(machine, rolled_back=True)


def test_partial_unit_update_restores_files_and_symlinks(machine, monkeypatch):
    first = machine.units / upgrade.UNITS[0]
    vendor = machine.units / 'vendor.service'
    vendor.write_text('vendor configuration')
    first.unlink()
    first.symlink_to(vendor)
    timer = machine.units / upgrade.TIMER
    timer.unlink()  # Newly created base unit must disappear on rollback.
    real_write = upgrade.atomic_write
    failed = False
    def write(path, data, mode=0o600):
        nonlocal failed
        if path == timer and not failed:
            failed = True
            raise OSError('unit write failed')
        return real_write(path, data, mode)
    monkeypatch.setattr(upgrade, 'atomic_write', write)
    with pytest.raises(RuntimeError, match='Previous dashboard restored and verified'):
        machine.perform()
    assert first.is_symlink() and first.resolve() == vendor
    assert vendor.read_text() == 'vendor configuration'
    assert not timer.exists()
    assert (machine.units / (upgrade.TIMER + '.d') / 'override.conf').exists()
    assert machine.status()['state'] == 'rolled-back'


@pytest.mark.parametrize('failure', ['restore-copy', 'restore-unit', 'all-restarts', 'rollback-api'])
def test_failed_recovery_reports_and_blocks_followup(machine, monkeypatch, failure):
    machine.failure = 'api-health'
    if failure == 'restore-copy':
        real_copy = upgrade.shutil.copytree
        def copy(src, dst, *args, **kwargs):
            if Path(src) == machine.backup() / 'venv':
                raise OSError('restore copy failed')
            return real_copy(src, dst, *args, **kwargs)
        monkeypatch.setattr(upgrade.shutil, 'copytree', copy)
    elif failure == 'restore-unit':
        monkeypatch.setattr(upgrade, 'restore_unit', lambda *a: (_ for _ in ()).throw(OSError('restore unit failed')))
    elif failure == 'all-restarts':
        machine.failure = failure
    else:
        real_verify = upgrade.verify_api
        def verify(port, expected):
            if expected['version']['version'] == machine.old['version']:
                raise RuntimeError('rollback API unavailable')
            return real_verify(port, expected)
        monkeypatch.setattr(upgrade, 'verify_api', verify)
    with pytest.raises(RuntimeError, match='Automatic rollback incomplete'):
        machine.perform()
    assert machine.status()['state'] == 'rollback-failed'
    assert machine.status()['rollback_errors']
    count = len(machine.calls)
    with pytest.raises(RuntimeError, match='Unfinished upgrade requires recovery'):
        machine.perform()
    assert len(machine.calls) == count
    assert (machine.backup() / 'ROLLBACK.txt').exists()
    assert any(args[:2] == ('systemctl', 'daemon-reload') for args in machine.calls)


@pytest.mark.parametrize('state', ['preparing', 'prepared', 'installing', 'rolling-back',
                                   'rollback-failed', 'unknown', None, [], {}])
def test_interrupted_upgrade_blocks_new_mutation(machine, state):
    backup = machine.root / 'upgrade-interrupted'
    backup.mkdir()
    upgrade.journal(backup, state, install=str(machine.install))
    with pytest.raises(RuntimeError, match='Unfinished upgrade'):
        machine.perform()
    assert not machine.calls


def test_final_database_integrity_failure_rolls_back_without_restoring_db(machine, monkeypatch):
    real_integrity = upgrade.integrity
    failed = False
    def check(path):
        nonlocal failed
        if machine.new is not None and machine.running == machine.new and not failed:
            failed = True
            raise RuntimeError('simulated final database integrity failure')
        return real_integrity(path)
    monkeypatch.setattr(upgrade, 'integrity', check)
    with pytest.raises(RuntimeError, match='Previous dashboard restored and verified'):
        machine.perform()
    assert_preserved(machine, rolled_back=True)
    with sqlite3.connect(machine.database) as db:
        assert db.execute('SELECT value FROM history').fetchall() == [(42,), (99,)]


def test_disabled_timer_state_survives_upgrade_and_rollback(machine):
    machine.timer_enabled, machine.timer_active = 'disabled', 'inactive'
    machine.failure = 'api-health'
    with pytest.raises(RuntimeError, match='Previous dashboard restored'):
        machine.perform()
    assert machine.timer_enabled == 'disabled'
    assert machine.timer_active == 'inactive'


def test_no_running_release_endpoint_is_not_accepted_for_new_release(machine, monkeypatch):
    real_api = upgrade.get_api
    def api(port, path):
        if path == '/api/release':
            raise HTTPError('url', 404, 'not found', {}, None)
        return real_api(port, path)
    monkeypatch.setattr(upgrade, 'get_api', api)
    with pytest.raises(RuntimeError, match='Running dashboard release content mismatch'):
        machine.perform()
    assert machine.status()['state'] == 'rolled-back'


def test_same_version_with_different_content_requires_new_process(machine):
    machine.old['version'] = '0.2.1'
    machine.running = machine.old.copy()
    machine.marker.write_text(json.dumps(machine.old))
    machine.previous_endpoint = True
    machine.failure = 'stale-process'
    with pytest.raises(RuntimeError, match='Running dashboard release content mismatch'):
        machine.perform()
    assert machine.status()['state'] == 'rolled-back'
    assert_preserved(machine, rolled_back=True)


def test_lock_serializes_upgrades(machine):
    with (machine.root / 'upgrade.lock').open('a') as lock:
        upgrade.fcntl.flock(lock, upgrade.fcntl.LOCK_EX | upgrade.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            machine.perform()
    assert not machine.calls


def test_existing_service_must_match_explicit_install_directory(machine, monkeypatch):
    real_args = upgrade.service_arguments
    monkeypatch.setattr(upgrade, 'service_arguments', lambda unit:
                        ['/other/.venv/bin/python'] if unit == upgrade.SERVICE else real_args(unit))
    with pytest.raises(RuntimeError, match='configured installed Python'):
        machine.perform()
    assert not list(machine.root.glob('upgrade-*'))


def test_default_install_and_cli_forwarding():
    assert upgrade.DEFAULT_INSTALL == Path('/opt/asl3-connection-logger')
    assert upgrade.DEFAULT_BACKUPS == Path('/var/backups/asl3-connection-logger')
    setup = (Path(__file__).resolve().parents[1] / 'scripts/setup.sh').read_text()
    assert 'REPO="${ASL3_INSTALL_DIR:-/opt/asl3-connection-logger}"' in setup
    assert 'exec python3 "$SOURCE/scripts/upgrade.py" "$SOURCE" "$@"' in setup
    assert setup.index('"--upgrade"') < setup.index('Interactive terminal required')
    assert 'exec python3 "$SOURCE/scripts/upgrade.py" "$SOURCE" --install-dir "$REPO"' in setup


def test_setup_upgrade_dispatch_from_isolated_checkout(tmp_path):
    source = tmp_path / 'source'
    (source / 'scripts').mkdir(parents=True)
    setup = Path(__file__).resolve().parents[1] / 'scripts/setup.sh'
    (source / 'scripts/setup.sh').write_text(setup.read_text())
    (source / 'scripts/upgrade.py').write_text('import json, sys; print(json.dumps(sys.argv[1:]))')
    result = subprocess.check_output(['bash', str(source / 'scripts/setup.sh'), '--upgrade',
                                      '--install-dir', '/custom/installed'], text=True)
    assert json.loads(result) == [str(source), '--install-dir', '/custom/installed']


def test_protected_backup_root_rejects_repository_and_symlink(tmp_path):
    source, install = tmp_path / 'source', tmp_path / 'installed'
    source.mkdir()
    install.mkdir()
    for root in (source, source / 'backups', install / 'backups'):
        with pytest.raises(RuntimeError, match='outside source and installed'):
            upgrade.protected_backup_root(root, source, install)
    link = tmp_path / 'link'
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(RuntimeError, match='symlinks'):
        upgrade.protected_backup_root(link, source, install)
    unsafe = tmp_path / 'unsafe'
    unsafe.mkdir(mode=0o755)
    with pytest.raises(RuntimeError, match='root-owned with mode 0700'):
        upgrade.protected_backup_root(unsafe, source, install)


def test_backup_includes_wal_and_metadata(tmp_path):
    source = tmp_path / 'live.db'
    with sqlite3.connect(source) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE metadata(value)')
        db.execute("INSERT INTO metadata VALUES ('preserved')")
        db.commit()
        backup = tmp_path / 'backup.db'
        upgrade.backup_database(source, backup)
        with sqlite3.connect(backup) as saved:
            assert saved.execute('SELECT * FROM metadata').fetchall() == [('preserved',)]
        db.execute("INSERT INTO metadata VALUES ('later callback')")
        db.commit()
    upgrade.integrity(source)


def test_corrupt_database_rejected(tmp_path):
    path = tmp_path / 'broken.db'
    path.write_bytes(b'corrupt database')
    with pytest.raises(sqlite3.DatabaseError):
        upgrade.backup_database(path, tmp_path / 'backup.db')


def test_failure_retains_failed_environment_outside_repositories(machine):
    machine.failure = 'api-health'
    with pytest.raises(RuntimeError, match='Previous dashboard restored'):
        machine.perform()
    failed = machine.backup() / 'failed-venv'
    assert (failed / 'new-only').exists()
    assert json.loads((failed / 'release.json').read_text()) == machine.new
    assert not list(machine.install.glob('.venv-restore-*'))


def test_backup_directory_creation_failure_is_explicit_and_does_not_mutate(machine, monkeypatch):
    monkeypatch.setattr(upgrade.tempfile, 'mkdtemp', lambda **kwargs: (_ for _ in ()).throw(OSError('no backup space')))
    with pytest.raises(OSError, match='no backup space'):
        machine.perform()
    assert not machine.dashboard_restarts()
    assert not any('pip' in args for args in machine.calls)
    assert_preserved(machine, rolled_back=True)


def test_unwritable_journal_reports_no_installation_changes(machine, monkeypatch, capsys):
    monkeypatch.setattr(upgrade, 'journal', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(RuntimeError, match='preparation failed; installation unchanged'):
        machine.perform()
    assert 'No installation changes began' in capsys.readouterr().err
    assert not machine.dashboard_restarts()
    assert not any('pip' in args for args in machine.calls)


def test_backups_reject_unrelated_git_repository(tmp_path):
    repository = tmp_path / 'other-repo'
    (repository / '.git').mkdir(parents=True)
    (repository / '.git/HEAD').write_text('ref: refs/heads/main')
    with pytest.raises(RuntimeError, match='outside every Git'):
        upgrade.protected_backup_root(repository / 'backups', tmp_path / 'source', tmp_path / 'installed')


def test_cli_uses_installed_default_independently_of_source(monkeypatch, tmp_path):
    calls = []
    monkeypatch.delenv('ASL3_INSTALL_DIR', raising=False)
    monkeypatch.setattr(upgrade.sys, 'argv', ['upgrade.py', str(tmp_path / 'incoming')])
    monkeypatch.setattr(upgrade, 'upgrade', lambda *args: calls.append(args))
    assert upgrade.main() == 0
    assert calls == [(tmp_path / 'incoming', upgrade.DEFAULT_INSTALL, upgrade.DEFAULT_BACKUPS)]


def test_service_arguments_preserve_systemd_escaped_spaces(monkeypatch):
    command = r'{ path=/opt/custom\x20install/.venv/bin/python ; argv[]=/opt/custom\x20install/.venv/bin/python --database /srv/data\x20files/history.db ; ignore_errors=no ; }'
    monkeypatch.setattr(upgrade, 'property_value', lambda *args: command)
    assert upgrade.service_arguments(upgrade.SERVICE) == [
        '/opt/custom install/.venv/bin/python', '--database', '/srv/data files/history.db']


def test_runtime_enabled_timer_remains_runtime_enabled(machine):
    machine.timer_enabled = 'enabled-runtime'
    machine.perform()
    assert ('systemctl', 'enable', '--runtime', upgrade.TIMER) in machine.calls
    assert ('systemctl', 'enable', upgrade.TIMER) not in machine.calls


def test_masked_timer_is_preserved_without_mutation(machine):
    machine.timer_enabled = 'masked'
    with pytest.raises(RuntimeError, match='Metadata units are masked'):
        machine.perform()
    assert not list(machine.root.glob('upgrade-*'))
    assert not any('pip' in args for args in machine.calls)


@pytest.mark.parametrize('failure', ['pip-install', 'api-health'])
def test_rollback_removes_new_timer_enablement_before_removing_unit(machine, failure):
    timer = machine.units / upgrade.TIMER
    timer.unlink()
    machine.timer_enabled, machine.timer_active = '', 'inactive'
    machine.failure = failure
    with pytest.raises(RuntimeError, match='Previous dashboard restored'):
        machine.perform()
    assert machine.status()['state'] == 'rolled-back'
    assert not timer.exists()
    assert machine.timer_active == 'inactive'
    assert machine.timer_enabled in ('', 'disabled')


def test_render_metadata_paths_preserves_arguments_and_sandbox_directory():
    text = ('WorkingDirectory=/opt/asl3-connection-logger\n'
            'ExecStart=/opt/asl3-connection-logger/.venv/bin/python -m asl3_connection_logger.metadata_sync '
            '--database /var/lib/asl3-connection-logger/connections.db\n'
            'ReadWritePaths=/var/lib/asl3-connection-logger\n')
    db = '/var/lib/asl3-connection-logger/archive/history with spaces.db'
    result = upgrade.render_unit(text, Path('/opt/custom install'), db).decode()
    fields = dict(line.split('=', 1) for line in result.splitlines())
    arguments = shlex.split(fields['ExecStart'])
    assert arguments[0] == '/opt/custom install/.venv/bin/python'
    assert upgrade.option(arguments, 'database', None) == db
    assert fields['WorkingDirectory'] == '/opt/custom install'
    assert shlex.split(fields['ReadWritePaths']) == ['/var/lib/asl3-connection-logger/archive']


def test_unit_permissions_restored(machine):
    first = machine.units / upgrade.UNITS[0]
    first.chmod(0o640)
    machine.failure = 'api-health'
    with pytest.raises(RuntimeError, match='Previous dashboard restored'):
        machine.perform()
    assert first.stat().st_mode & 0o777 == 0o640


def test_success_journal_failure_triggers_rollback(machine, monkeypatch):
    real_journal = upgrade.journal
    def write(backup, state, **details):
        if state == 'complete':
            raise OSError('cannot finalize success')
        return real_journal(backup, state, **details)
    monkeypatch.setattr(upgrade, 'journal', write)
    with pytest.raises(RuntimeError, match='Previous dashboard restored'):
        machine.perform()
    assert_preserved(machine, rolled_back=True)
    assert machine.status()['state'] == 'rolled-back'
    assert 'cannot finalize success' in machine.status()['upgrade_error']


def test_backup_wrong_owner_rejected(tmp_path, monkeypatch):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    real_stat = Path.stat
    def file_stat(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path == root:
            return SimpleNamespace(st_uid=12345, st_mode=result.st_mode)
        return result
    monkeypatch.setattr(Path, 'stat', file_stat)
    with pytest.raises(RuntimeError, match='root-owned with mode 0700'):
        upgrade.protected_backup_root(root, tmp_path / 'source', tmp_path / 'installed')


def test_nonroot_upgrade_never_prepares_or_mutates(machine, monkeypatch):
    monkeypatch.setattr(upgrade.os, 'geteuid', lambda: 12345)
    with pytest.raises(RuntimeError, match='as root'):
        machine.perform()
    assert not machine.calls
    assert not list(machine.root.glob('upgrade-*'))


@pytest.mark.parametrize('failure', ['pip-install', 'api-health'])
def test_failed_environment_restoration_never_restarts_or_verifies_dashboard(machine, monkeypatch, failure):
    machine.failure = failure
    def restore(install, backup):
        raise OSError('environment restoration failed')
    monkeypatch.setattr(upgrade, 'restore_environment', restore)
    checks = []
    real_verify = upgrade.verify_api
    def verify(port, expected):
        checks.append(expected)
        return real_verify(port, expected)
    monkeypatch.setattr(upgrade, 'verify_api', verify)
    with pytest.raises(RuntimeError, match='Automatic rollback incomplete') as error:
        machine.perform()
    # API failure requires one restart into the new release; pip failure requires none.
    assert len(machine.dashboard_restarts()) == (1 if failure == 'api-health' else 0)
    assert all(check['version']['version'] != machine.old['version'] for check in checks)
    assert machine.status()['state'] == 'rollback-failed'
    assert machine.status()['dashboard_verified'] is False
    assert 'dashboard restart and verification skipped' in str(error.value)
    assert 'Previous dashboard restored and verified' not in str(error.value)


@pytest.mark.parametrize('mismatch', ['version', 'release', 'missing-release'])
def test_rollback_requires_previous_version_and_release_identity(machine, monkeypatch, mismatch):
    machine.previous_endpoint = True
    machine.failure = 'pip-install'
    real_api = upgrade.get_api
    def api(port, path):
        if machine.failed_once:
            if mismatch == 'version' and path == '/api/version':
                return info(machine.new)
            if mismatch == 'release' and path == '/api/release':
                return {**machine.old, 'content_sha256': 'wrong release with same version'}
            if mismatch == 'missing-release' and path == '/api/release':
                raise HTTPError('url', 404, 'not found', {}, None)
        return real_api(port, path)
    monkeypatch.setattr(upgrade, 'get_api', api)
    with pytest.raises(RuntimeError, match='Automatic rollback incomplete') as error:
        machine.perform()
    assert machine.status()['state'] == 'rollback-failed'
    assert machine.status()['dashboard_verified'] is False
    assert 'Previous dashboard restored and verified' not in str(error.value)


def test_successful_rollback_records_verified_previous_identity(machine):
    machine.previous_endpoint = True
    machine.failure = 'api-health'
    with pytest.raises(RuntimeError, match='Previous dashboard restored and verified'):
        machine.perform()
    status = machine.status()
    assert status['state'] == 'rolled-back'
    assert status['dashboard_verified'] is True
    assert status['previous']['version'] == info(machine.old)
    assert status['previous']['release'] == machine.old


@pytest.mark.parametrize('contents', [None, '{invalid', 'null', '{}',
                                      '{"install": "relative", "state": "complete"}'])
def test_missing_or_invalid_interrupted_journal_blocks_before_preflight(machine, contents):
    previous = machine.root / 'upgrade-interrupted'
    previous.mkdir()
    if contents is not None:
        (previous / 'state.json').write_text(contents)
    with pytest.raises(RuntimeError, match='Unfinished upgrade requires recovery'):
        machine.perform()
    assert not machine.calls
    assert list(machine.root.glob('upgrade-*')) == [previous]


def test_interrupted_attempt_requires_explicit_resolution(machine):
    previous = machine.root / 'upgrade-interrupted'
    previous.mkdir()
    upgrade.journal(previous, 'prepared', install=str(machine.install))
    with pytest.raises(RuntimeError, match='Unfinished upgrade'):
        machine.perform()
    # A bare label cannot silently waive recovery.
    upgrade.journal(previous, 'resolved')
    with pytest.raises(RuntimeError, match='Unfinished upgrade'):
        machine.perform()
    assert not machine.calls
    upgrade.journal(previous, 'resolved', resolution='Operator verified installation unchanged and dashboard identity')
    backup = machine.perform()
    assert json.loads((backup / 'state.json').read_text())['state'] == 'complete'
    assert json.loads((previous / 'state.json').read_text())['state'] == 'resolved'
    assert machine.running == machine.new


def test_old_unverified_rollback_journal_requires_explicit_resolution(machine):
    previous = machine.root / 'upgrade-unverified'
    previous.mkdir()
    upgrade.journal(previous, 'rolled-back', install=str(machine.install), rollback_errors=[])
    with pytest.raises(RuntimeError, match='Unfinished upgrade'):
        machine.perform()
    assert not machine.calls


@pytest.mark.parametrize('directory', ['/opt/logger', '/opt/custom install',
                                     '/opt/quotes"and\'apostrophes', '/opt/back\\slash',
                                     '/opt/percent%name', '/opt/end ', '/opt/end\\'])
def test_working_directory_is_a_literal_absolute_systemd_path(directory):
    content = upgrade.render_unit('WorkingDirectory=/opt/asl3-connection-logger\n',
                                  Path(directory), upgrade.DEFAULT_DB).decode()
    value = content.removeprefix('WorkingDirectory=').rstrip('\n')
    suffix = '/.' if directory.endswith((' ', '\\')) else ''
    assert value == directory.replace('%', '%%') + suffix
    assert value.startswith('/')


@pytest.mark.parametrize('directory', ['/tmp/injected\n[Service]', '/tmp/injected\rvalue',
                                     '/tmp/injected\tvalue', '/tmp/injected\x00value'])
def test_working_directory_rejects_control_characters(directory):
    with pytest.raises(ValueError, match='without control characters'):
        upgrade.render_unit('WorkingDirectory=/opt/asl3-connection-logger\n',
                            Path(directory), upgrade.DEFAULT_DB)


def test_invalid_generated_units_abort_before_installing_or_stopping_services(machine, monkeypatch):
    original = upgrade.run
    def run(*args, **kwargs):
        if args[0] == 'systemd-analyze':
            raise subprocess.CalledProcessError(1, args, output='Unit configuration has fatal error')
        return original(*args, **kwargs)
    monkeypatch.setattr(upgrade, 'run', run)
    with pytest.raises(RuntimeError, match='preparation failed; installation unchanged'):
        machine.perform()
    assert machine.status()['state'] == 'preparation-failed'
    assert not any('pip' in args and 'install' in args for args in machine.calls)
    assert not any(args[:2] == ('systemctl', 'stop') for args in machine.calls)
    assert not machine.dashboard_restarts()
    assert_preserved(machine, rolled_back=True)


@pytest.mark.parametrize('directory', ['installed', 'installed with spaces',
                                     'percent%name', 'trailing '])
def test_generated_metadata_units_pass_real_systemd_verification(tmp_path, directory):
    import shutil
    import sys
    if not shutil.which('systemd-analyze'):
        pytest.skip('systemd-analyze is unavailable')
    install = tmp_path / directory
    (install / '.venv/bin').mkdir(parents=True)
    (install / '.venv/bin/python').symlink_to(sys.executable)
    database = tmp_path / 'data with spaces' / 'history.db'
    database.parent.mkdir()
    repo = Path(__file__).resolve().parents[1]
    contents = {unit: upgrade.render_unit((repo / 'systemd' / unit).read_text(), install, str(database))
                for unit in upgrade.UNITS}
    try:
        upgrade.verify_units(contents, tmp_path / 'units')
    except subprocess.CalledProcessError as error:
        pytest.fail(error.output, pytrace=False)


def test_original_quoted_working_directory_fails_real_systemd_verification(tmp_path):
    import shutil
    import sys
    if not shutil.which('systemd-analyze'):
        pytest.skip('systemd-analyze is unavailable')
    install = tmp_path / 'installed'
    (install / '.venv/bin').mkdir(parents=True)
    (install / '.venv/bin/python').symlink_to(sys.executable)
    repo = Path(__file__).resolve().parents[1]
    contents = {unit: upgrade.render_unit((repo / 'systemd' / unit).read_text(), install, upgrade.DEFAULT_DB)
                for unit in upgrade.UNITS}
    service = upgrade.UNITS[0]
    contents[service] = contents[service].replace(
        f'WorkingDirectory={install}\n'.encode(), f'WorkingDirectory="{install}"\n'.encode())
    with pytest.raises(subprocess.CalledProcessError) as error:
        upgrade.verify_units(contents, tmp_path / 'units')
    assert 'WorkingDirectory= path is not absolute' in error.value.output


@pytest.mark.parametrize('directory', ['quotes"and\'apostrophes', 'back\\slash', 'trailing\\'])
def test_literal_working_directory_special_characters_verify_with_safe_executable(tmp_path, directory):
    import shutil
    import sys
    if not shutil.which('systemd-analyze'):
        pytest.skip('systemd-analyze is unavailable')
    install = tmp_path / directory
    install.mkdir()
    repo = Path(__file__).resolve().parents[1]
    contents = {}
    for unit in upgrade.UNITS:
        template = (repo / 'systemd' / unit).read_text()
        # Isolate WorkingDirectory syntax from systemd's separate restriction on
        # quote/backslash characters in executable filenames.
        template = template.replace(str(upgrade.DEFAULT_INSTALL) + '/.venv/bin/python', sys.executable)
        contents[unit] = upgrade.render_unit(template, install, upgrade.DEFAULT_DB)
    working = next(line.split('=', 1)[1] for line in contents[upgrade.UNITS[0]].decode().splitlines()
                   if line.startswith('WorkingDirectory='))
    assert Path(working).resolve() == install.resolve()
    try:
        upgrade.verify_units(contents, tmp_path / 'units')
    except subprocess.CalledProcessError as error:
        pytest.fail(error.output, pytrace=False)


@pytest.mark.parametrize('directory', ['quotes"and\'apostrophes', 'back\\slash', 'trailing\\'])
def test_systemd_rejects_unsupported_executable_paths_without_installing_units(tmp_path, directory):
    import shutil
    import sys
    if not shutil.which('systemd-analyze'):
        pytest.skip('systemd-analyze is unavailable')
    install = tmp_path / directory
    (install / '.venv/bin').mkdir(parents=True)
    (install / '.venv/bin/python').symlink_to(sys.executable)
    repo = Path(__file__).resolve().parents[1]
    contents = {unit: upgrade.render_unit((repo / 'systemd' / unit).read_text(), install, upgrade.DEFAULT_DB)
                for unit in upgrade.UNITS}
    with pytest.raises(subprocess.CalledProcessError) as error:
        upgrade.verify_units(contents, tmp_path / 'units')
    assert 'Executable path contains special characters' in error.value.output


def test_configured_install_path_is_not_rewritten_as_a_database_directory():
    install = Path('/var/lib/asl3-connection-logger/installed app')
    db = '/srv/metadata/history.db'
    template = ('WorkingDirectory=/opt/asl3-connection-logger\n'
                'ExecStart=/opt/asl3-connection-logger/.venv/bin/python '
                '--database=/var/lib/asl3-connection-logger/connections.db\n'
                'ReadWritePaths=/var/lib/asl3-connection-logger\n')
    fields = dict(line.split('=', 1) for line in upgrade.render_unit(template, install, db).decode().splitlines())
    assert fields['WorkingDirectory'] == str(install)
    arguments = shlex.split(fields['ExecStart'])
    assert arguments == [str(install / '.venv/bin/python'), '--database=' + db]
    assert shlex.split(fields['ReadWritePaths']) == ['/srv/metadata']
