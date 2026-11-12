#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Transactional upgrades from a source checkout into an existing installation."""
import argparse
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

SERVICE = 'asl3-connection-dashboard'
TIMER = 'asl3-metadata-sync.timer'
UNITS = ('asl3-metadata-sync.service', TIMER)
DEFAULT_INSTALL = Path('/opt/asl3-connection-logger')
DEFAULT_BACKUPS = Path('/var/backups/asl3-connection-logger')
DEFAULT_DB = '/var/lib/asl3-connection-logger/connections.db'
UNIT_DIR = Path('/etc/systemd/system')
FINISHED = {'complete', 'rolled-back', 'preparation-failed', 'resolved'}


def run(*args, cwd='/'):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    return subprocess.check_output(args, cwd=cwd, env=env, text=True,
                                   stderr=subprocess.STDOUT).strip()


def integrity(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError(f'Database integrity check failed: {path}')


def backup_database(source, destination):
    # The only SQLite write performed by the upgrader is to this backup file.
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as db:
        with sqlite3.connect(destination) as backup:
            db.backup(backup)
    integrity(destination)
    integrity(source)


def atomic_write(path, data, mode=0o600):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def journal(backup, state, **details):
    path = backup / 'state.json'
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(details, state=state)
    atomic_write(path, json.dumps(existing, indent=2).encode())


def version_from_source(text):
    for statement in ast.parse(text).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'VERSION'
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise RuntimeError('Application version missing')


def wheel_release(wheel):
    # The wheel defines application-owned files. Installed release_identity uses
    # RECORD to distinguish unowned .bak debris; every file shipped here is hashed.
    # Use the same content_digest rules without importing incoming code.
    prefix = 'asl3_connection_logger/'
    with ZipFile(wheel) as archive:
        entries = sorted((name[len(prefix):], archive.read(name))
                         for name in archive.namelist()
                         if name.startswith(prefix) and not name.endswith('/'))
    files = dict(entries)
    stamp = json.loads(files['build-info.json'])
    digest = hashlib.sha256()
    for name, data in entries:
        if '__pycache__' in Path(name).parts or name.endswith('.pyc'):
            continue
        if name == 'build-info.json':
            normalized = json.loads(data)
            normalized.pop('built_at', None)
            data = json.dumps(normalized, sort_keys=True).encode()
        digest.update(name.encode() + b'\0' + data + b'\0')
    return {'version': version_from_source(files['_version.py'].decode()),
            'commit': stamp.get('commit'), 'dirty': bool(stamp.get('dirty', False)),
            'content_sha256': digest.hexdigest()}


def installed_version(python):
    return json.loads(run(str(python), '-c',
                          'import json; from asl3_connection_logger.version import version_info; '
                          'print(json.dumps(version_info()))'))


def installed_release(python):
    return json.loads(run(str(python), '-c',
                          'import json; from asl3_connection_logger.release import release_identity; '
                          'print(json.dumps(release_identity()))'))


def get_api(port, path):
    with urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
        return json.load(response)


def public_identity(info):
    return {'version': info['version'], 'commit': info.get('commit'),
            'dirty': info['build']['dirty']}


def dashboard_state(port):
    if get_api(port, '/health').get('status') != 'ok':
        raise RuntimeError('Dashboard health check failed')
    version = get_api(port, '/api/version')
    get_api(port, '/api/dashboard?limit=1')
    try:
        release = get_api(port, '/api/release')
    except HTTPError as error:
        if error.code != 404:
            raise
        release = None  # Public v0.2.0 does not have this endpoint.
    return {'version': version, 'release': release}


def verify_api(port, expected):
    last_error = None
    for attempt in range(30):
        try:
            actual = dashboard_state(port)
            if public_identity(actual['version']) != public_identity(expected['version']):
                raise RuntimeError('Dashboard version API identity mismatch')
            if actual['release'] != expected['release']:
                raise RuntimeError('Running dashboard release content mismatch')
            return
        except Exception as error:
            last_error = error
            if attempt < 29:
                time.sleep(1)
    raise RuntimeError(f'Dashboard verification failed: {last_error}')


def property_value(unit, name):
    return run('systemctl', 'show', unit, '--property=' + name, '--value')


def service_arguments(unit):
    command = property_value(unit, 'ExecStart')
    match = re.search(r'argv\[\]=(.*?)\s+;', command)
    if not match:
        raise RuntimeError(f'Cannot parse effective ExecStart for {unit}')
    lexer = shlex.shlex(match[1], posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    lexer.escape = ''  # Preserve systemd \xNN escapes until tokenization finishes.
    args = list(lexer)
    args = [re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)), arg)
            for arg in args]
    if any('$' in arg or '%' in arg for arg in args):
        raise RuntimeError(f'Unresolved systemd substitutions in {unit}; use explicit arguments')
    return args


def option(args, name, default):
    for index, arg in enumerate(args):
        if arg == '--' + name:
            if index + 1 == len(args):
                raise RuntimeError(f'Missing --{name} argument')
            return args[index + 1]
        if arg.startswith('--' + name + '='):
            return arg.split('=', 1)[1]
    return default


def render_unit(text, install, metadata_db):
    """Render each setting using its own systemd parsing rules."""
    substitutions = {str(DEFAULT_INSTALL): str(install), DEFAULT_DB: metadata_db,
                     str(Path(DEFAULT_DB).parent): str(Path(metadata_db).parent)}
    pattern = re.compile('|'.join(re.escape(path) for path in sorted(substitutions, key=len, reverse=True)))

    def replace(value):
        # Substitute template paths once: configured paths can themselves live
        # under the default data directory and must not be rewritten again.
        return pattern.sub(lambda match: substitutions[match[0]], value)

    def quote(value, command=False):
        value = value.replace('%', '%%')
        if command:
            value = value.replace('$', '$$')
        return json.dumps(value, ensure_ascii=False)

    lines = []
    for line in text.splitlines():
        key, separator, value = line.partition('=')
        if separator and key == 'WorkingDirectory':
            # This setting consumes one literal path, not a shell-style word.
            # Quotes become part of the path and would make it nonabsolute.
            path = replace(value)
            if not Path(path).is_absolute() or any(ord(char) < 32 or ord(char) == 127 for char in path):
                raise ValueError('WorkingDirectory must be an absolute path without control characters')
            # Keep trailing spaces and a literal final backslash away from the
            # unit parser's whitespace trimming and line-continuation syntax.
            if path != path.rstrip() or path.endswith('\\'):
                path += '/.'
            line = key + '=' + path.replace('%', '%%')
        elif separator and key in ('ExecStart', 'ReadWritePaths'):
            args = shlex.split(value)
            line = key + '=' + ' '.join(quote(replace(arg), command=key == 'ExecStart') for arg in args)
        lines.append(line)
    return ('\n'.join(lines) + '\n').encode()


def verify_units(contents, directory):
    """Validate staged units without loading or changing installed systemd units."""
    directory.mkdir()
    paths = []
    for unit, content in contents.items():
        path = directory / unit
        atomic_write(path, content, 0o644)
        paths.append(str(path))
    run('systemd-analyze', 'verify', '--man=no', *paths)


def snapshot_unit(target, backup):
    if target.is_symlink():
        info = target.lstat()
        return {'kind': 'symlink', 'link': os.readlink(target), 'uid': info.st_uid, 'gid': info.st_gid}
    if target.exists():
        shutil.copy2(target, backup / target.name)
        info = target.stat()
        return {'kind': 'file', 'mode': stat.S_IMODE(info.st_mode),
                'uid': info.st_uid, 'gid': info.st_gid}
    return {'kind': 'absent'}


def restore_unit(target, backup, saved):
    if saved['kind'] == 'file':
        atomic_write(target, (backup / target.name).read_bytes(), saved['mode'])
        os.chown(target, saved['uid'], saved['gid'])
    elif saved['kind'] == 'symlink':
        temporary = target.with_name('.' + target.name + '.restore')
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(saved['link'])
        temporary.replace(target)
        os.lchown(target, saved['uid'], saved['gid'])
    else:
        # Remove only the base unit created by this transaction; leave drop-ins alone.
        target.unlink(missing_ok=True)


def restore_environment(install, backup):
    # Prepare the complete replacement before moving the failed environment aside.
    staging = Path(tempfile.mkdtemp(prefix='.venv-restore-', dir=install))
    shutil.copytree(backup / 'venv', staging / 'venv', symlinks=True)
    live = install / '.venv'
    failed = staging / 'failed-venv'
    live.rename(failed)
    try:
        (staging / 'venv').rename(live)
    except Exception:
        failed.rename(live)
        raise
    # The failed environment is diagnostic material too: retain it outside Git.
    # shutil.move also supports backups on a different filesystem. The working
    # environment is already restored if moving diagnostic material fails.
    shutil.move(str(failed), str(backup / 'failed-venv'))
    staging.rmdir()


def apply_timer(saved, new_install=False):
    enabled = saved['enabled']
    if enabled == 'enabled-runtime' and not new_install:
        run('systemctl', 'enable', '--runtime', TIMER)
    elif enabled == 'enabled' or new_install:
        run('systemctl', 'enable', TIMER)
    elif enabled in ('disabled', '', 'not-found'):
        run('systemctl', 'disable', TIMER)
    if saved['active'] == 'active' or new_install:
        run('systemctl', 'start', TIMER)
    else:
        run('systemctl', 'stop', TIMER)


def rollback(install, backup, manifest):
    errors = []
    def attempt(label, action):
        try:
            action()
            return True
        except Exception as error:
            errors.append(f'{label}: {error}')
            return False
    attempt('journal', lambda: journal(backup, 'rolling-back', upgrade_error=manifest.get('upgrade_error')))
    if manifest['timer']['active'] == 'active' or manifest.get('timer_applied'):
        attempt('stop timer', lambda: run('systemctl', 'stop', TIMER))
    if manifest.get('timer_applied') and manifest['timer']['enabled'] in ('', 'not-found'):
        # Remove newly created enablement links while the new base unit exists.
        attempt('disable newly added timer', lambda: run('systemctl', 'disable', TIMER))
    environment_restored = True
    if manifest.get('environment_mutated'):
        environment_restored = attempt('restore Python environment', lambda: restore_environment(install, backup))
    for unit, saved in manifest['units'].items():
        attempt('restore ' + unit, lambda unit=unit, saved=saved:
                restore_unit(UNIT_DIR / unit, backup, saved))
    attempt('reload systemd units', lambda: run('systemctl', 'daemon-reload'))
    if manifest['timer']['enabled'] or manifest['units'][TIMER]['kind'] != 'absent':
        attempt('restore timer state', lambda: apply_timer(manifest['timer']))
    # A failed pip installation can leave lazy imports inconsistent even if the
    # original dashboard process never stopped. Restart against the restored venv.
    dashboard_verified = False
    dashboard_ready = environment_restored
    if not environment_restored:
        errors.append('dashboard restart and verification skipped: Python environment restoration failed')
    elif manifest.get('environment_mutated'):
        dashboard_ready = attempt('restore dashboard', lambda: run('systemctl', 'restart', SERVICE))
    if dashboard_ready:
        dashboard_verified = attempt('verify restored dashboard',
                                     lambda: verify_api(manifest['port'], manifest['previous']))
    elif environment_restored:
        errors.append('dashboard verification skipped: dashboard restart failed')
    attempt('verify database (read only)', lambda: integrity(manifest['database']))
    if not dashboard_verified and not errors:
        errors.append('previous dashboard version and release identity were not verified')
    journal(backup, 'rollback-failed' if errors else 'rolled-back',
            rollback_errors=errors, dashboard_verified=dashboard_verified)
    if errors:
        raise RuntimeError('Automatic rollback incomplete: ' + '; '.join(errors))


def protected_backup_root(root, source, install):
    root = Path(root).absolute()
    if root != root.resolve():
        raise RuntimeError('Backup directory must not contain symlinks')
    for repository in (source, install):
        if root == repository or repository in root.parents:
            raise RuntimeError('Rollback backups must be outside source and installed repositories')
    if any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file()
           for parent in (root, *root.parents)):
        raise RuntimeError('Rollback backups must be outside every Git repository')
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('Backup directory must be root-owned with mode 0700')
    for parent in root.parents:
        info = parent.stat()
        if info.st_uid != 0 or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise RuntimeError('Backup directory ancestors must be controlled by root')
    return root


def check_previous_attempts(root, install):
    """Fail closed on interrupted or unreadable journals before any upgrade work."""
    for backup in sorted(root.glob('upgrade-*')):
        if not backup.is_dir():
            continue
        path = backup / 'state.json'
        try:
            state = json.loads(path.read_text())
            if not isinstance(state, dict) or not isinstance(state.get('install'), str):
                raise ValueError('journal is missing its installation identity')
            if not Path(state['install']).is_absolute():
                raise ValueError('journal installation path is not absolute')
        except (OSError, ValueError) as error:
            raise RuntimeError(f'Unfinished upgrade requires recovery: {path} ({error})') from error
        if Path(state['install']).resolve() != install:
            continue
        finished = isinstance(state.get('state'), str) and state['state'] in FINISHED
        if state.get('state') == 'rolled-back':
            finished = state.get('dashboard_verified') is True and state.get('rollback_errors') == []
        elif state.get('state') == 'resolved':
            finished = isinstance(state.get('resolution'), str) and bool(state['resolution'].strip())
        if not finished:
            raise RuntimeError(f'Unfinished upgrade requires recovery or explicit resolution: {path}')


def upgrade(source, install=DEFAULT_INSTALL, backup_root=DEFAULT_BACKUPS):
    if os.geteuid() != 0:
        raise RuntimeError('Run setup.sh --upgrade as root')
    source, install = Path(source).resolve(), Path(install).resolve()
    root = protected_backup_root(backup_root, source, install)
    with (root / 'upgrade.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_previous_attempts(root, install)
        return perform_upgrade(source, install, root)


def perform_upgrade(source, install, root):
    python = install / '.venv/bin/python'
    if not python.is_file() or (install / '.venv').is_symlink():
        raise RuntimeError('Existing, nonsymlink Python environment required')
    incoming = version_from_source((source / 'src/asl3_connection_logger/_version.py').read_text())
    arguments = service_arguments(SERVICE)
    if not arguments or Path(arguments[0]) != python:
        raise RuntimeError('Dashboard ExecStart does not use the configured installed Python environment')
    database = Path(option(arguments, 'database', DEFAULT_DB))
    if not database.is_absolute():
        working = property_value(SERVICE, 'WorkingDirectory')
        if not working or not Path(working).is_absolute():
            raise RuntimeError('Cannot resolve dashboard database relative to WorkingDirectory')
        database = Path(working) / database
    if not database.is_file():
        raise RuntimeError('Existing dashboard database missing')
    port = int(option(arguments, 'port', '8765'))
    if property_value(SERVICE, 'ActiveState') != 'active':
        raise RuntimeError('Dashboard must be active before upgrading')
    if property_value(UNITS[0], 'ActiveState') in ('active', 'activating'):
        raise RuntimeError('Metadata synchronization is running; retry after it finishes')
    previous = dashboard_state(port)
    installed = installed_version(python)
    if public_identity(previous['version']) != public_identity(installed):
        raise RuntimeError('Running dashboard differs from installed application; resolve before upgrading')
    if previous['release'] is not None and installed_release(python) != previous['release']:
        raise RuntimeError('Running dashboard content differs from installed environment')
    print(f'Installed: {installed["version"]}; incoming: {incoming}', flush=True)
    timer = {'active': property_value(TIMER, 'ActiveState'),
             'enabled': property_value(TIMER, 'UnitFileState')}
    if timer['enabled'] in ('masked', 'masked-runtime') or (UNIT_DIR / UNITS[0]).is_symlink() and (UNIT_DIR / UNITS[0]).resolve() == Path('/dev/null'):
        raise RuntimeError('Metadata units are masked; resolve this explicitly before upgrading')
    metadata_args = service_arguments(UNITS[0]) if property_value(UNITS[0], 'ExecStart') else []
    metadata_db = option(metadata_args, 'database', DEFAULT_DB if metadata_args else str(database))
    # Preserve independently configured metadata DB settings, including relative paths.
    if not Path(metadata_db).is_absolute():
        working = property_value(UNITS[0], 'WorkingDirectory')
        if not working or not Path(working).is_absolute():
            raise RuntimeError('Cannot resolve metadata database WorkingDirectory')
        metadata_db = str(Path(working) / metadata_db)
    contents = {unit: render_unit((source / 'systemd' / unit).read_text(), install, metadata_db)
                for unit in UNITS}
    backup = Path(tempfile.mkdtemp(prefix='upgrade-', dir=root))
    mutation_started = False
    manifest = {'install': str(install), 'source': str(source), 'database': str(database),
                'port': port, 'previous': previous, 'timer': timer, 'units': {},
                'environment_mutated': False}
    print(f'Rollback backup: {backup}', flush=True)
    try:
        journal(backup, 'preparing', **manifest)
        atomic_write(backup / 'ROLLBACK.txt', (
            f'Installation: {install}\nDatabase (never restored automatically): {database}\n'
            'Read state.json first. A preparation-failed attempt made no installation changes.\n'
            'A rolled-back attempt restored and verified the previous dashboard.\n'
            'For rollback-failed or ANY interrupted attempt, retain\n'
            'this directory and the failed environment. Restore venv to the ORIGINAL .venv\n'
            'path, preserving the failed environment; use units.json to restore base units\n'
            '(including saved symlinks) without touching drop-ins. Run systemctl daemon-reload,\n'
            'restore the recorded timer state, restart asl3-connection-dashboard, and verify\n'
            'its APIs. Do not restore connections.db over the live database: callbacks can\n'
            'have added events since backup. Do not restart or reload Asterisk or Apache.\n'
            'After explicit manual recovery and dashboard version/release verification,\n'
            'record state=resolved and a nonempty resolution note in state.json.\n'
            'Do not delete the journal to bypass the interrupted-upgrade guard.\n'
        ).encode())
        backup_database(database, backup / 'connections.db')
        shutil.copytree(install / '.venv', backup / 'venv', symlinks=True)
        for unit in UNITS:
            manifest['units'][unit] = snapshot_unit(UNIT_DIR / unit, backup)
        atomic_write(backup / 'units.json', json.dumps(manifest['units'], indent=2).encode())
        wheels = backup / 'wheels'
        wheels.mkdir()
        run(str(python), '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels), str(source))
        wheel, = wheels.glob('asl3_connection_logger-*.whl')
        release = wheel_release(wheel)
        if release['version'] != incoming:
            raise RuntimeError('Built wheel version differs from incoming source')
        verify_units(contents, backup / 'units-verify')
        journal(backup, 'prepared', **manifest, expected=release)
        # Record mutation intent before the first installed-state change. A crash
        # here blocks subsequent upgrades until the operator resolves this state.
        journal(backup, 'installing')
        mutation_started = True
        if timer['active'] == 'active':
            run('systemctl', 'stop', TIMER)
        if property_value(UNITS[0], 'ActiveState') in ('active', 'activating'):
            raise RuntimeError('Metadata synchronization started during preparation; retry later')
        manifest['environment_mutated'] = True
        journal(backup, 'installing', environment_mutated=True)
        run(str(python), '-m', 'pip', 'install', '--upgrade', '--force-reinstall', str(wheel))
        if installed_release(python) != release:
            raise RuntimeError('Installed application content differs from incoming wheel')
        changed_units = False
        for unit, content in contents.items():
            target = UNIT_DIR / unit
            if not target.is_file() or target.read_bytes() != content:
                atomic_write(target, content, 0o644)
                changed_units = True
        if changed_units:
            run('systemctl', 'daemon-reload')
        manifest['timer_applied'] = True
        journal(backup, 'installing', timer_applied=True)
        apply_timer(timer, new_install=manifest['units'][TIMER]['kind'] == 'absent'
                    and not timer['enabled'])
        if previous['release'] != release:
            run('systemctl', 'restart', SERVICE)
        expected = {'version': installed_version(python), 'release': release}
        verify_api(port, expected)
        integrity(database)
        journal(backup, 'complete')
    except Exception as error:
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        if mutation_started:
            manifest['upgrade_error'] = str(error)
            try:
                rollback(install, backup, manifest)
            except Exception as recovery:
                raise RuntimeError(f'Upgrade failed: {error}. {recovery}. Recovery instructions: {backup}') from error
            raise RuntimeError(f'Upgrade failed: {error}. Previous dashboard restored and verified. Backup: {backup}') from error
        try:
            journal(backup, 'preparation-failed', error=str(error), **manifest)
        except Exception as state_error:
            print(f'Could not record preparation failure: {state_error}. No installation changes began.', file=sys.stderr)
        raise RuntimeError(f'Upgrade preparation failed; installation unchanged: {error}. Backup: {backup}') from error
    print(f'Upgrade verified: {incoming}. Backup retained at {backup}')
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--install-dir', type=Path,
                        default=Path(os.environ.get('ASL3_INSTALL_DIR', str(DEFAULT_INSTALL))))
    parser.add_argument('--backup-root', type=Path, default=DEFAULT_BACKUPS)
    args = parser.parse_args()
    try:
        upgrade(args.source, args.install_dir, args.backup_root)
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
