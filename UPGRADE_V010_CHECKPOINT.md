# Current pause: v0.2.4 release validation, 2026-11-13

The user requested a pause with checkpoint. Read this section first; older notes
below are historical and contain obsolete workspace paths and Git state.

- Durable checkout: `/opt/asl3-connection-logger-release-v024`.
- HEAD: `2eba917f73f1a3db9f673cc0ef186ea0471f186a`. Git was clean on resume.
  This checkpoint is the only change made during this session. No code changes.
- `/tmp/asl3-v021` was lost after reboot. Do not use or recreate it as the
  development workspace.
- Preserve existing databases and backups. Do not modify Asterisk, production
  systems, or published AllStarLink source. No push, publish, tag, or deployment
  without authorization. No installation or service changes were made.

## Missing service investigation completed before any changes

Read-only systemd inspection found `asl3-connection-logger.service` not-found,
but `asl3-connection-dashboard.service` loaded and active, with its base unit at
`/etc/systemd/system/asl3-connection-dashboard.service` and installed Python at
`/opt/asl3-connection-logger/.venv/bin/python`.

The package name was mistaken for the service name: current and public v0.1.0
(`bbb8809`) dashboard installers use `SERVICE="asl3-connection-dashboard"`;
the upgrader uses the same name. Repository/history searches found no installer
for `asl3-connection-logger.service`. Logging runs through the event callback
(`scripts/asl3-connection-event` / `scripts/asl3-event-hook`), not a daemon with
that name. There is no evidence of upgrade tests deleting an expected logger
unit. Do not install a replacement unit or change services to address this name.
Actual systemd service control remains outside disposable integration coverage.

## Validation evidence and interruption

- Existing retained report `/var/tmp/asl3-logger-tests/v024-isolated-results.xml`:
  **264 passed**, zero failures/errors/skips, 824.983 seconds, Nov 12.
  Its `candidate-provenance.json` identifies a dirty 0.2.4 candidate based on
  `9efb54e`, not an exact clean build of `2eba917`. Preserve both files.
- Fresh full-suite run used `TMPDIR=/var/tmp/asl3-logger-tests`, basetemp
  `pytest-v024-resume-2eba917`. A daemon restart interrupted it after at least
  11 passing progress dots; no completed XML report exists. Do not claim it passed.
- Restart left disposable dashboard PID 6252 orphaned. Its exact executable
  under that test directory was checked before SIGTERM; it was stopped.
- Recovery run used basetemp `pytest-v024-resume-2eba917-recovery` and report
  `/var/tmp/asl3-logger-tests/v024-resume-2eba917-recovery.xml`. User pause stopped
  it with Ctrl-C: XML records **8 tests**, zero failures/errors/skips, but the
  suite is INCOMPLETE. Interruption caused pytest teardown KeyboardInterrupt /
  stash KeyError; process exit was 1. This is not a completed release result.
- Final host process inspection found only installed dashboard PID 635 and node
  watcher PID 996 among Python processes, with no remaining disposable Python
  dashboard or pytest process. Neither installed process was changed.
- Interrupted test trees/evidence were preserved. Do not reuse their basetemp
  paths: pytest may delete prior contents. Pick a fresh suffix on next resume.
- `git diff --check` passed before this checkpoint update.
- Exact-HEAD local artifact build was proposed but the tool call was aborted by
  the daemon restart. `/var/tmp/asl3-logger-tests/release-2eba917` does not exist;
  no new source archive, wheel, or sdist was built by that command.

## Next resume

1. Read this checkpoint and inspect Git/process state before repeating actions.
2. Finish full suite in a NEW disposable directory with
   `TMPDIR=/var/tmp/asl3-logger-tests PYTHONDONTWRITEBYTECODE=1 python3 -m pytest
   -q --tb=short --basetemp=/var/tmp/asl3-logger-tests/pytest-v024-resume-NEXT
   -o cache_dir=/var/tmp/asl3-logger-tests/pytest-cache-resume
   --junitxml=/var/tmp/asl3-logger-tests/v024-resume-NEXT.xml`.
   Escalation is needed for `/var/tmp` writes, localhost fixtures and unit
   verification. Integration service control is strictly a fixture.
3. Prioritize existing real v0.1.0/v0.2.3 wheel/HTTP/SQLite upgrade, repeat and
   rollback validation over new test infrastructure. That implementation is
   already committed at HEAD; do not repeat completed implementation work.
4. If needed, build local source/wheel/sdist artifacts from exact committed HEAD
   with `scripts/build-release.py`, keeping them under the requested temp root
   and recording provenance. Do not install, tag, push, publish, or deploy.
5. Record final results and limits; run `git diff --check`. Stop for release
   authorization, without making production changes.

# Historical completion: transactional v0.1.0 upgrade compatibility

Resumed at the user's request and completed without committing or deploying.
The original pause notes below are retained as investigation history; see the
completion record at the end for current results.

## Workspace and restrictions

- Development checkout: `/tmp/asl3-v021` on node658860.
- Branch: `feature/v0.2.1-installer`.
- HEAD at pause: `4da78141b51e5298dc63fa6f12cef64c42b53fe5`.
- Current stable version in the checkout and local tag `v0.2.3`: 0.2.3.
- Do not access W9SEM-Hub, its services, configuration, or database.
- Do not modify `/opt`, production units, Apache, Asterisk, or production data.
- Do not modify published AllStarLink source, restart production services, commit,
  push, tag, merge private history, or publish a release.
- Never use `set -e` in interactive SSH commands.
- All implementation changes below are saved and uncommitted. No upgrade is running.

## Original task

Investigate and implement a transactional upgrade from an installed
`asl3-connection-logger 0.1.0` to the current stable application, including genuine
legacy packaging/HTTP/schema fixtures, backups before modifying installed files,
configuration/ownership/permission/history preservation, verified automatic
rollback without restoring a database file, documentation and the full test suite.

W9SEM-Hub evidence supplied by the user: active legacy dashboard; package 0.1.0;
installed at `/opt/asl3-connection-logger`; database
`/var/lib/asl3-connection-logger/connections.db`, 131072 bytes; `/api/version` and
`/api/release` return 404; current upgrade reports generic HTTP 404 before any
backup directory is found. W9SEM-Hub has NOT been contacted.

## Investigation so far

The old stable upgrader's `dashboard_state()` calls these endpoints in order:
1. `/health`
2. `/api/version`
3. `/api/dashboard?limit=1`
4. `/api/release`

It performs that preflight before creating a backup. A 404 at `/health` OR
`/api/version` therefore used to abort with an ambiguous message and no backup.
The supplied production evidence alone does not establish the exact failing
request. Do NOT claim that W9SEM-Hub's failing request has been observed.

Local Git source inspection establishes that public 0.1.0 has `/health` and
`/api/dashboard` but neither identity endpoint. The expected reproduction against
that actual source is `/health` -> 200, `/api/version` -> 404. Still reproduce
this with a real disposable process and captured request sequence before the
final report. The current error path now includes the exact request URL.

Relevant local public source history (read with `git show`/`git archive`, never
modify or merge historical trees):
- `2d0eebe`: initial public release, static pyproject version 0.1.0, schema 2;
  early packaging lacks static package-data declarations.
- `17d2d6c`: still 0.1.0; fixes inclusion of HTML/CSS/JS package data.
- `bbb8809`: still 0.1.0, latest useful public legacy dashboard/installer fixture
  before later multi-node and version/metadata changes. Suitable for a genuine
  old wheel with packaged dashboard resources.
- `v0.2.3`: current stable source for comparison and old failing upgrader.

Legacy 0.1.0 has:
- No `asl3_connection_logger.version` or `.release` modules/build identity.
- Static distribution version from importlib.metadata.
- Schema 2, connection events/sessions and runtime_id; no metadata tables.
- No metadata-sync service/timer.
- Dashboard service uses installed `.venv/bin/python -m ...web`, localhost:8765,
  asl3logger-web/asterisk identity and existing systemd hardening.
- Existing callbacks import collector from installed venv; those files should
  remain untouched. Apache/authentication/drop-ins also remain untouched.

Critical rollback constraint: the original 0.1.0 collector rejects schema 3.
The implementation now retains the schema-2 marker for existing schema-2 DBs,
adding metadata tables only. Brand-new databases still use schema 3. This keeps
original callbacks operational after environment rollback without copying an old
SQLite snapshot over newly recorded events. Validate this with the REAL 0.1.0
collector after rollback, not just SQL inspection.

## Changes already implemented

`scripts/upgrade.py`:
- `installed_version()` falls back to distribution metadata ONLY for genuine
  0.1.0 missing its historical version module; modern missing modules fail.
- `installed_release()` fingerprints legacy package files when genuine 0.1.0
  lacks the release module; modern release verification remains strict.
- `get_api()` prints the URL and includes it in HTTPError messages.
- `dashboard_state(..., legacy_version=...)` permits missing health/identity
  endpoints only for known 0.1.0; requires a valid history API in all cases.
  Stores legacy capability flags for rollback verification. Modern releases do
  not receive this fallback.
- Effective service command/DB/port still determine the installed target.
- SQLite backup, full environment backup, dashboard+metadata base-unit snapshots,
  and drop-in reference copies precede HTTP capability checks and pip installation.
- `copy_environment()` copies and verifies all bytes, symlinks, owners/groups and
  permission modes (also used to restore the environment).
- New optional metadata-unit handling tolerates only explicit unit-not-found
  errors, not bus/permission errors or a missing dashboard service.
- Legacy DB migration runs incoming initializer as the DB file owner/group,
  checks permission/ownership retention and integrity, and precedes new dashboard
  verification. Metadata timer activation occurs after dashboard verification.
- Rollback restores environment/units; verifies legacy package metadata/content
  before restarting; uses original capabilities and data API to verify the old
  dashboard. A failed restoration still prevents dashboard restart.
- Missing legacy metadata units and original timer state are restored on failure.
- No SQLite file restore is performed; additive metadata tables can remain.

`src/asl3_connection_logger/database.py`:
- Existing schema-2 databases retain marker 2 while metadata tables are added;
  new DBs remain schema 3. This is intentional rollback compatibility.

`tests/test_migration.py`:
- Updated schema-2 migration expectation to marker 2 with metadata tables.

`tests/test_upgrade.py`:
- Added legacy missing identity/health/metadata-unit upgrade/rollback simulations.
- Added exact URL HTTP error tests and modern missing endpoint fail-closed tests
  that ensure verified backups exist before the error.
- Added ownership/mode/symlink copy tests and optional-unit error discrimination.

## Tests run

1. `python3 -m pytest tests/test_upgrade.py tests/test_migration.py -q --tb=short`
   outside sandbox: **99 passed in 7.05s** at the earlier implementation state.
2. Latest `python3 -m pytest tests/test_upgrade.py -q --tb=short`
   outside sandbox: **105 passed in 6.82s** with all added upgrade unit tests.
3. `git diff --check`: passed at pause.

The ordinary sandbox cannot run systemd-analyze verification: SO_PASSCRED fails
with Operation not permitted. Use the already approved escalation for
`python3 -m pytest`; these tests use temporary unit files and mocked service
control. No production service commands have been executed.

## Remaining work (do not skip)

1. Review the current diff for transaction/compatibility edge cases.
2. Add committed-to-the-working-tree (NOT Git committed) real legacy integration
   tests under `tests/integration/`, using actual v0.1.0 source from local Git,
   real locally built wheels, temporary venvs/SQLite/HTTP processes, and a STRICT
   disposable systemctl fixture. Never invoke real systemctl service control.
3. Reproduce the exact ORIGINAL failing URL with `v0.2.3`'s dashboard_state()
   against a genuine public 0.1.0 process and record `/health` and version statuses.
4. Test successful legacy upgrade to incoming 0.2.3, repeated upgrade, missing
   metadata units, strict new version/release hash verification and valid units.
5. Inject failure after real pip installation (and append a callback event after
   the snapshot), restart failure, and new release/API verification failure.
   Verify original package and service files, modes/UID/GID, drop-ins, timer state
   and history return; invoke the actual old collector AFTER rollback to prove
   schema-2 compatibility. Never overwrite or restore the DB file.
6. Test migration failure and missing/broken history API fail safely with backups.
7. Ensure every temporary process is stopped/reaped and ports/trees are cleaned.
8. Update README.md, docs/releases.md and docs/web-dashboard.md concisely to list
   supported starting versions and explain legacy verification/migration/rollback.
   Record source comparison/root cause in a durable investigation doc if useful.
9. Run the COMPLETE suite, fix failures, run git diff --check and report honest
   limits: no production access, legacy has no HTTP code identity, service manager
   is a fixture, current-stable tests use an incoming working-tree wheel.
10. Final report: root cause (distinguish proven local reproduction from the
    unobserved production request), proposed/implemented fix, diff summary and
    test results. STOP without commits, tags, pushes or release publication.

A prior standalone v0.2.0 integration harness exists at
`/tmp/test_asl3_upgrade_disposable.py` and can be consulted for fixture structure;
it is NOT a legacy test and should not be cited as evidence for this task.
Prefer placing the new regression tests in this development repository.

## Resume

Tell Codex: "Resume the v0.1.0 upgrade task using UPGRADE_V010_CHECKPOINT.md."
Read this checkpoint and the current diff, then continue the remaining work.

## Completion record

- Full suite: **262 passed in 351.44s**, zero failures/errors/skips.
- Eight real legacy integration cases passed: public 0.1.0 request-sequence
  reproduction; actual upgrade/repeat; pip/restart/identity/SQL-migration/timer
  rollback failures; broken history API; database-owner credential migration.
- The original collector successfully logged after every injected rollback.
- All 16 disposable dashboard processes exited/reaped; fixture ports rebound.
  Seven per-case installation/DB/backup trees, source trees and owner fixture
  trees were removed. No production services, files or databases were touched.
- Source comparison, limits and evidence are documented in docs/legacy-upgrade.md.
- README.md, docs/releases.md and docs/web-dashboard.md document starting versions.
- Results: .pytest_cache/legacy-upgrade-results.xml and
  .pytest_cache/legacy-upgrade-summary.json (local, ignored test artifacts).
- All saved implementation changes remain uncommitted. No commit, push, tag,
  production upgrade or deployment was performed. The immutable v0.2.3 tag is
  unchanged; tests used the incoming working-tree build.
