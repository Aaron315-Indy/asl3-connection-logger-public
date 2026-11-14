# Upgrade validation

Keep pytest's temporary tree, build files and reports in the ignored persistent
`.validation-tmp` directory. Set `TMPDIR`, `TMP` and `TEMP` to its absolute path,
and set `--basetemp`, `cache_dir` and `--junitxml` beneath a fresh run directory.
Check available space first; do not put the complete suite on a small `/tmp` tmpfs.

Tests that exercise the real protected-backup checks use an independent
`external_tmp_path` fixture. It defaults to `/var/tmp` and creates a private,
unique directory that is removed at teardown. Set `ASL3_TEST_EXTERNAL_TMPDIR` to
an existing absolute directory outside every Git repository to override it.
This setting moves only those backup fixtures; reports and other test files
remain under the repository-local run directory. Choose a location with enough
space for the disposable environment backups and rollback diagnostics.

Run targeted upgrade tests before the full suite:

```bash
validation_root=$(mktemp -d "$PWD/.validation-tmp/v024-targeted-XXXXXXXX")
export TMPDIR="$validation_root" TMP="$validation_root" TEMP="$validation_root"
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    tests/test_upgrade.py tests/test_migration.py tests/integration/test_v023_upgrade.py \
    -q --tb=short --basetemp="$validation_root/tests" \
    -o cache_dir="$validation_root/cache" --junitxml="$validation_root/results.xml"
```

The integration tests use disposable service-control fixtures and must never
control installed services. Real HTTP sockets, systemd static verification and
numeric fixture ownership changes still need an environment that permits those
operations. Do not mock or skip verification to conceal environment restrictions.
