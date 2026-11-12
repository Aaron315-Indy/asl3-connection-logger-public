# SPDX-License-Identifier: GPL-3.0-or-later
"""Content identity captured by each dashboard process when it starts."""
import csv
import hashlib
import json
from importlib.metadata import PackageNotFoundError, distribution
from io import StringIO
from pathlib import Path

from .version import version_info


def content_digest(entries):
    """Hash package files consistently for wheels and installed packages."""
    digest = hashlib.sha256()
    for name, data in sorted(entries):
        if '__pycache__' in Path(name).parts or name.endswith('.pyc'):
            continue
        if name == 'build-info.json':
            stamp = json.loads(data)
            stamp.pop('built_at', None)
            data = json.dumps(stamp, sort_keys=True).encode()
        digest.update(name.encode() + b'\0' + data + b'\0')
    return digest.hexdigest()


def _installed_files(root):
    """Use ownership only from the wheel distribution containing this package."""
    try:
        installed = distribution('asl3-connection-logger')
    except PackageNotFoundError:
        return None
    if Path(installed.locate_file('asl3_connection_logger')).resolve() != root:
        return None  # A source checkout must not borrow another installation's manifest.
    if installed.read_text('WHEEL') is None:
        return None  # Source/egg-info metadata is not an installed wheel RECORD.
    # Read RECORD directly: importlib.metadata.files can filter out missing
    # files, which would silently lose ownership information for deleted assets.
    record = installed.read_text('RECORD')
    if record is None:
        raise RuntimeError('Installed application RECORD is missing')
    prefix = 'asl3_connection_logger/'
    files = set()
    for row in csv.reader(StringIO(record), strict=True):
        if len(row) != 3:
            raise ValueError('Invalid installed application RECORD')
        if row[0].startswith(prefix):
            files.add(row[0][len(prefix):])
    if not files:
        raise RuntimeError('Installed application RECORD contains no application files')
    return files


def application_entries(root, recorded_files=None):
    """Retain all application files, excluding only unowned .bak maintenance files.

    RECORD is not a hash allowlist: unexpected code/resources still contribute
    to the digest, and recorded files must be read even when they are missing.
    A .bak shipped in the wheel remains application content and is checked too.
    Source checkouts without wheel ownership metadata retain the strict scan.
    """
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    names = actual
    if recorded_files is not None:
        names = set(recorded_files) | {name for name in actual if not name.endswith('.bak')}
    for name in sorted(names):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid application path in installed RECORD')
        if '__pycache__' in relative.parts or name.endswith('.pyc'):
            continue
        yield name, (root / relative).read_bytes()


def release_identity():
    root = Path(__file__).resolve().parent
    info = version_info()
    return {
        'version': info['version'],
        'commit': info['commit'],
        'dirty': info['build']['dirty'],
        'content_sha256': content_digest(application_entries(root, _installed_files(root))),
    }
