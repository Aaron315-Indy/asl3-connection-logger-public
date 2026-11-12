# SPDX-License-Identifier: GPL-3.0-or-later
"""Content identity captured by each dashboard process when it starts."""
import hashlib
import json
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


def release_identity():
    root = Path(__file__).resolve().parent
    info = version_info()
    return {
        'version': info['version'],
        'commit': info['commit'],
        'dirty': info['build']['dirty'],
        'content_sha256': content_digest(
            (str(path.relative_to(root)), path.read_bytes())
            for path in root.rglob('*') if path.is_file()
        ),
    }
