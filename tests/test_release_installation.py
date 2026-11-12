"""Real wheel/venv regression for untracked backups left behind by pip upgrades.

No services or databases are used. Builds and installations are entirely local
and offline, and both disposable environments are removed after the tests.
"""
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from asl3_connection_logger.release import content_digest
from asl3_connection_logger.version import version_info

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release_install_upgrade', ROOT / 'scripts/upgrade.py')
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


@pytest.fixture(scope='module', params=[False, True], ids=['normal-wheel', 'wheel-owned-backup'])
def installed_wheel(request):
    with tempfile.TemporaryDirectory(prefix='asl3-release-install-') as directory:
        root = Path(directory)
        source = root / 'source'
        source.mkdir()
        for name in ('setup.py', 'pyproject.toml', 'README.md', 'LICENSE'):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / 'src/asl3_connection_logger', source / 'src/asl3_connection_logger',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'build-info.json'))
        identity = version_info()
        (source / 'src/asl3_connection_logger/build-info.json').write_text(json.dumps({
            'commit': identity['commit'], 'dirty': identity['build']['dirty'],
            'built_at': '2026-11-12T00:00:00+00:00'}))
        if request.param:
            # A backup explicitly shipped in the wheel must still be checked.
            (source / 'src/asl3_connection_logger/static/packaged.html.bak').write_text('owned resource')
            config = source / 'pyproject.toml'
            config.write_text(config.read_text().replace('"static/*.html",', '"static/*.html", "static/*.bak",'))
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env.update(PYTHONDONTWRITEBYTECODE='1', PIP_CONFIG_FILE=os.devnull,
                   PIP_NO_INDEX='1', PIP_NO_CACHE_DIR='1', PIP_DISABLE_PIP_VERSION_CHECK='1')

        def run(*args, cwd=root):
            return subprocess.check_output([str(arg) for arg in args], cwd=cwd, env=env,
                                           text=True, stderr=subprocess.STDOUT).strip()

        run(sys.executable, 'setup.py', 'bdist_wheel', cwd=source)
        wheel, = (source / 'dist').glob('*.whl')
        expected = upgrade.wheel_release(wheel)
        run(sys.executable, '-m', 'venv', root / 'venv')
        python = root / 'venv/bin/python'
        site = Path(run(python, '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'))
        package = site / 'asl3_connection_logger'
        orphan = package / 'static/index.html.bak'
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'preexisting unowned homepage backup; not part of application\n')
        run(python, '-m', 'pip', 'install', '--no-deps', wheel)
        assert orphan.read_bytes().startswith(b'preexisting unowned')
        loaded = Path(run(python, '-c', 'import asl3_connection_logger; print(asl3_connection_logger.__file__)'))
        assert loaded == package / '__init__.py'
        record, = site.glob('asl3_connection_logger-*.dist-info/RECORD')
        assert not any(row[0] == 'asl3_connection_logger/static/index.html.bak'
                       for row in csv.reader(record.read_text().splitlines()))
        with ZipFile(wheel) as archive:
            names = sorted(name.removeprefix('asl3_connection_logger/') for name in archive.namelist()
                           if name.startswith('asl3_connection_logger/') and not name.endswith('/'))

        def actual():
            return json.loads(run(python, '-c',
                'import json; from asl3_connection_logger.release import release_identity; '
                'print(json.dumps(release_identity()))'))

        assert actual() == expected
        print(f'\nReal {request.node.name} ({request.param=}): '
              f'wheel digest={expected["content_sha256"]}; installed digest={actual()["content_sha256"]}')
        yield SimpleNamespace(root=root, package=package, record=record, expected=expected,
                              orphan=orphan, names=names, actual=actual, run=run, python=python)


def test_real_wheel_matches_despite_preexisting_unowned_backup(installed_wheel):
    fixture = installed_wheel
    # Reproduce the old algorithm's mismatch with precisely the same installed tree.
    old_digest = content_digest((path.relative_to(fixture.package).as_posix(), path.read_bytes())
                                for path in fixture.package.rglob('*') if path.is_file())
    assert old_digest != fixture.expected['content_sha256']
    assert fixture.actual() == fixture.expected
    original = fixture.orphan.read_bytes()
    try:
        fixture.orphan.write_bytes(b'another unowned maintenance backup')
        assert fixture.actual() == fixture.expected
    finally:
        fixture.orphan.write_bytes(original)


def test_every_wheel_owned_file_is_checked_for_modification(installed_wheel):
    fixture = installed_wheel
    for name in fixture.names:
        path = fixture.package / name
        original = path.read_bytes()
        try:
            if name == 'build-info.json':
                stamp = json.loads(original)
                stamp['dirty'] = not stamp['dirty']
                path.write_text(json.dumps(stamp))
            else:
                path.write_bytes(original + b'\n# integrity regression modification\n')
            assert fixture.actual()['content_sha256'] != fixture.expected['content_sha256'], name
        finally:
            path.write_bytes(original)
    assert fixture.actual() == fixture.expected


def test_every_wheel_owned_file_is_required_even_if_missing(installed_wheel):
    fixture = installed_wheel
    for name in fixture.names:
        path = fixture.package / name
        original = path.read_bytes()
        try:
            path.unlink()
            with pytest.raises(subprocess.CalledProcessError):
                fixture.actual()
        finally:
            path.write_bytes(original)
    assert fixture.actual() == fixture.expected


@pytest.mark.parametrize('name', ['unexpected.py', 'static/unexpected.js', 'static/unexpected.html'])
def test_unexpected_application_files_still_change_installed_digest(installed_wheel, name):
    fixture = installed_wheel
    path = fixture.package / name
    try:
        path.write_bytes(b'unexpected application content')
        assert fixture.actual()['content_sha256'] != fixture.expected['content_sha256']
    finally:
        path.unlink()
    assert fixture.actual() == fixture.expected


def test_missing_record_fails_closed(installed_wheel):
    fixture = installed_wheel
    original = fixture.record.read_bytes()
    try:
        fixture.record.unlink()
        with pytest.raises(subprocess.CalledProcessError) as error:
            fixture.actual()
        assert 'Installed application RECORD is missing' in error.value.output
    finally:
        fixture.record.write_bytes(original)
    assert fixture.actual() == fixture.expected


def test_record_is_not_an_allowlist_that_hides_unexpected_code(installed_wheel):
    fixture = installed_wheel
    code = fixture.package / 'web.py'
    original_code, original_record = code.read_bytes(), fixture.record.read_bytes()
    try:
        fixture.record.write_text(''.join(line for line in original_record.decode().splitlines(keepends=True)
                                          if not line.startswith('asl3_connection_logger/web.py,')))
        code.write_bytes(original_code + b'\n# unlisted modification must still be detected\n')
        assert fixture.actual()['content_sha256'] != fixture.expected['content_sha256']
    finally:
        code.write_bytes(original_code)
        fixture.record.write_bytes(original_record)
    assert fixture.actual() == fixture.expected
