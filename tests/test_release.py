from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from asl3_connection_logger import web
from asl3_connection_logger.release import content_digest


def test_running_release_is_captured_once(monkeypatch):
    expected = web.RUNNING_RELEASE.copy()
    monkeypatch.setattr(web, 'release_identity', lambda: {'content_sha256': 'newly installed files'})
    handler = object.__new__(web.DashboardHandler)
    handler.path = '/api/release'
    values = []
    handler.send_json = lambda value: values.append(value)
    handler.do_GET()
    assert values == [expected]
    assert len(expected['content_sha256']) == 64


def test_content_identity_changes_with_code_but_not_build_time():
    def entries(timestamp='first', code=b'old code'):
        return [('_version.py', b'VERSION = "0.2.1"'), ('web.py', code),
                ('build-info.json', json.dumps({'commit': 'a' * 40, 'built_at': timestamp}).encode())]
    assert content_digest(entries()) == content_digest(entries('second'))
    assert content_digest(entries()) != content_digest(entries(code=b'new code'))
    assert content_digest(entries()) == content_digest(entries() + [('__pycache__/web.pyc', b'ignored')])


def test_wheel_identity_matches_installed_hash(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('upgrade_release_test', Path(__file__).resolve().parents[1] / 'scripts/upgrade.py')
    upgrade = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upgrade)
    entries = [('_version.py', b'VERSION = "0.2.1"'), ('web.py', b'code'),
               ('build-info.json', json.dumps({'commit': 'a' * 40, 'dirty': False, 'built_at': 'time'}).encode())]
    wheel = tmp_path / 'release.whl'
    with ZipFile(wheel, 'w') as archive:
        for name, data in entries:
            archive.writestr('asl3_connection_logger/' + name, data)
    assert upgrade.wheel_release(wheel) == {'version': '0.2.1', 'commit': 'a' * 40,
                                           'dirty': False, 'content_sha256': content_digest(entries)}


def test_source_checkout_and_unrelated_distribution_keep_strict_file_scan(tmp_path, monkeypatch):
    from asl3_connection_logger import release
    package = tmp_path / 'source/asl3_connection_logger'
    package.mkdir(parents=True)
    (package / 'code.py').write_bytes(b'code')
    (package / 'code.py.bak').write_bytes(b'backup without known wheel ownership')
    unrelated = type('OtherDistribution', (), {'locate_file': lambda self, name: tmp_path / name})()
    monkeypatch.setattr(release, 'distribution', lambda name: unrelated)
    assert release._installed_files(package) is None
    assert dict(release.application_entries(package)) == {
        'code.py': b'code', 'code.py.bak': b'backup without known wheel ownership'}


def test_invalid_record_paths_are_rejected(tmp_path):
    import pytest
    from asl3_connection_logger.release import application_entries
    for name in ('../outside.py', '/outside.py'):
        with pytest.raises(ValueError, match='Invalid application path'):
            list(application_entries(tmp_path, {name}))


def test_raw_record_retains_missing_owned_backup_entries(tmp_path, monkeypatch):
    import pytest
    from asl3_connection_logger import release
    package = tmp_path / 'asl3_connection_logger'
    package.mkdir()
    (package / 'code.py').write_bytes(b'code')

    class WheelDistribution:
        def locate_file(self, name):
            return package

        def read_text(self, name):
            return {'WHEEL': 'Wheel-Version: 1.0\n', 'RECORD':
                    'asl3_connection_logger/code.py,,\n'
                    'asl3_connection_logger/static/owned.html.bak,,\n'}.get(name)

        @property
        def files(self):
            raise AssertionError('Do not use a metadata API that filters missing files')

    monkeypatch.setattr(release, 'distribution', lambda name: WheelDistribution())
    owned = release._installed_files(package)
    assert owned == {'code.py', 'static/owned.html.bak'}
    with pytest.raises(FileNotFoundError):
        list(release.application_entries(package, owned))
