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
