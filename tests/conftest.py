"""Disposable backup locations independent of pytest's repository-local temp root."""
import os
from pathlib import Path
import tempfile

import pytest


@pytest.fixture
def external_tmp_path():
    # Rollback backups deliberately cannot live beneath any Git repository.
    # Keep reports, source builds and the ordinary pytest temp tree in TMPDIR;
    # only fixtures that exercise real backup guards use this separate root.
    base = Path(os.environ.get('ASL3_TEST_EXTERNAL_TMPDIR', '/var/tmp'))
    if not base.is_absolute():
        pytest.fail('ASL3_TEST_EXTERNAL_TMPDIR must be an absolute directory')
    base = base.resolve(strict=True)
    if any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file()
           for parent in (base, *base.parents)):
        pytest.fail('ASL3_TEST_EXTERNAL_TMPDIR must be outside every Git repository')
    with tempfile.TemporaryDirectory(prefix='asl3-backup-test-', dir=base) as directory:
        yield Path(directory)
