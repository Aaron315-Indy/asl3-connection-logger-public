# Versioning and releases

The authoritative Semantic Versioning source is
`src/asl3_connection_logger/_version.py:VERSION`. Packaging reads this same
constant. The historical installed and initial public version was 0.1.0;
release 0.2.4 formally discontinues v0.1.0 upgrade support. Development versions use
an X.Y.Z-dev suffix
plus the commit and dirty indicator. Python package metadata normalizes
development suffixes to PEP 440.
The application consistently displays the original SemVer spelling.

Before a release, set VERSION to the approved X.Y.Z, update CHANGELOG, run
`.venv/bin/python -m pytest`, and commit. After approval, tag that commit
`vX.Y.Z`. Do not publish or push without approval. Begin subsequent development
with an appropriate `X.Y.Z-dev` version. A version change does not change the
SQLite schema version.

Create a local source release archive from committed HEAD:

    python3 scripts/build-release.py /tmp/asl3-connection-logger.tar.gz

This excludes all uncommitted changes and includes build-info.json containing
commit, UTC build time and dirty=false. It needs no Git at installation or
runtime. Raw GitHub/git archive exports preserve VERSION but lack frozen
commit/build time; those fields honestly report null. Prefer the stamped
archive. Wheels and sdists also freeze provenance automatically during build:

    .venv/bin/python -m build

Development checkouts report the current HEAD and whether the tree is dirty.
Installed packages report their frozen build identity. If Git is unavailable,
the application version remains available and commit is null. The API includes
only version, commit, and build type, timestamp and dirty flag. It excludes
hostnames, paths, remotes, environment variables and credentials.

The supported upgrade entry point is `scripts/setup.sh` from the incoming public
release checkout or extracted source folder:

    sudo scripts/setup.sh --upgrade

The source directory is independent of the installed application, which defaults
to `/opt/asl3-connection-logger`. For an explicitly customized installation use
`--install-dir /your/installed/path`. Interactive setup also offers the upgrade
when it detects that installed environment. Use `scripts/show-versions.sh` for
read-only version inspection; direct pip installation bypasses the supported
backup, rollback, and verification workflow.

The upgrade builds an incoming wheel, backs up the live SQLite database with its
backup API, and saves the complete old environment and metadata units in the
root-protected `/var/backups/asl3-connection-logger` directory outside Git.
Failures after installation begins trigger automatic application and unit
rollback, followed by verification of the restored dashboard. The live database
is never overwritten during rollback. Unfinished recovery blocks later upgrades.
See [dashboard upgrade instructions](web-dashboard.md#upgrading-an-existing-installation)
for state files, custom paths, configuration preservation and recovery details.

The dashboard's `/api/release` endpoint reports a process-start snapshot of its
release identity and package content hash, excluding build timestamps from the
hash. Upgrade verification requires that snapshot to match the incoming wheel;
checking `/api/version` or the installed Python package alone is insufficient.
The old public v0.2.0 dashboard can be restored without this new endpoint.
Version endpoints do not open the database.

Installed content verification reads the wheel's raw `RECORD` manifest so that
missing owned files fail verification. Untracked `.bak` maintenance files left
inside the package by earlier installations do not describe the release and are
excluded from the installed digest. A `.bak` file actually shipped in the wheel
is always checked. All other unexpected code or resource files still affect the
digest; this is not a manifest-only allowlist. Source checkouts without matching
installed-wheel ownership metadata retain the strict directory scan.

### Supported upgrade starting points

Direct upgrades support stable v0.2.x installations, including v0.2.3 → v0.2.4
and repeated v0.2.4 upgrades. **v0.1.0 is unsupported.** Other versions outside
the stable v0.2.x series are also refused. Installed distribution metadata is
checked before importing application identity modules, probing HTTP, creating an
upgrade snapshot or changing installed files. An unsupported version receives a
clear error; no database migration is attempted.

Supported installations require a healthy dashboard with `/health`,
`/api/version` and a working history API. `/api/release` is required except for
public v0.2.0, which predates that endpoint. The incoming v0.2.4 installation
always requires strict version and release-content verification. HTTP diagnostics
identify the exact URL. SQLite/environment backups and unit snapshots precede
HTTP checks and package installation for supported upgrades.

The v0.1.0-specific package fingerprints, missing-endpoint fallbacks, owner-run
migration and rollback capability checks have been removed. Database initialization
uses schema 3; the old schema-2 marker is no longer retained for v0.1.0 callbacks.
This does not authorize a v0.1.0 application upgrade. Do not relabel package or
database versions, bypass preflight, or install over an unsupported installation.
Preserve its history and backups; v0.2.4 provides no automated v0.1.0 migration.

The disposable integration tests build the actual v0.2.3 wheel directly and check
upgrade/repeat behavior and rollback after pip installation, dashboard restart,
release identity or timer activation failures. Original history, post-backup
callback events, configuration, ownership, permissions and timer state remain
verified. Rollback never restores a database snapshot over the live database.

### v0.2.4 installation requirements and final validation

Use an ASL3 host with Python 3.11 or newer, Python venv/pip, systemd (including
`systemd-analyze`), Apache, curl, and the existing `asterisk` account. Setup needs
root and an interactive terminal for fresh installation; `--upgrade` works
noninteractively. Fresh collector/setup installation uses
`/opt/asl3-connection-logger`. Upgrades support explicitly configured existing
paths. Unit rendering preserves spaces, percent signs and trailing spaces.
Installation paths containing single/double quotes, backslashes or control
characters are rejected before preparation or installation changes: systemd
cannot accept these executable filenames. Choose a supported installation path;
the installer does not redirect executables or bypass unit verification.
The fresh dashboard service now shares the upgrade renderer and must pass
`systemd-analyze verify` before it is installed.

Upgrade requires healthy existing APIs, an idle metadata job, unmasked metadata
units, sufficient backup disk space and root-controlled backup ancestors. Keep
all recovery journals and backups until the release has been accepted. Automatic
rollback restores the previous application and units, verifies the old dashboard,
and preserves live history; incomplete rollback requires manual recovery using
the saved instructions. No published AllStarLink source is modified. Fresh setup
configures supported callbacks; upgrades never reload Asterisk or Apache.

The supplied pre-change unrestricted host result was **117 passed, 3 failed**
(366.82 seconds), including all six v0.2.3 upgrade integration cases passing.
That result is historical evidence, not validation of the final changed tree.
Local targeted review passed 166 tests in 174.03 seconds covering upgrade safety,
installer checks, migrations, dashboard reads, versioning and release identity.
The focused systemd run passed 10 cases, and the final path/renderer checks passed
5 cases. A disposable dashboard process also served the homepage, health, version
0.2.4, release and history APIs successfully without changing its database bytes.
These runs do not replace the six real-wheel upgrade integration cases on the
final unrestricted host run; those cases were not rerun during this review.
Final unrestricted host validation is still required before a release GO.
Use `/var/tmp` for all temporary fixtures, including rollback fixtures. From an
unrestricted root SSH shell with pytest and build dependencies installed, run:

```sh
cd /opt/asl3-connection-logger-release-v024 && sudo env TMPDIR=/var/tmp ASL3_TEST_EXTERNAL_TMPDIR=/var/tmp python3 -m pytest -q --basetemp="$(mktemp -d /var/tmp/asl3-v024-host-XXXXXX)" --junitxml=/var/tmp/asl3-v024-host-results.xml
```

Tests use disposable databases and service-control fixtures. Do not run installers
against operational services or databases as part of this validation. Public
dashboard mode still requires administrator-managed HTTPS and authentication;
default fresh setup allows all client networks, so restrict web access externally
or select a private allowlist as documented in the dashboard guide.
