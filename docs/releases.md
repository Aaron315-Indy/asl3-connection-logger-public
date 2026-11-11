# Versioning and releases

The authoritative Semantic Versioning source is
`src/asl3_connection_logger/_version.py:VERSION`. Packaging reads this same
constant. The historical installed and initial public version was 0.1.0;
the current release is 0.2.0. Development versions use an X.Y.Z-dev suffix
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

The interactive installer prints installed and incoming identity before its
confirmation and before pip runs. Noninteractive installers print the same
preflight before changes; when upgrading manually, run this *before* pip:

    ./scripts/show-versions.sh /opt/asl3-connection-logger
    /opt/asl3-connection-logger/.venv/bin/python -m pip install /path/to/source

Use an extracted incoming source directory as the first argument when staging
an upgrade separately. The installed environment defaults to
`/opt/asl3-connection-logger`; an optional second argument overrides that path. Preserve `/var/lib/asl3-connection-logger`,
existing hooks and configuration. Do not uninstall or reinitialize the database
to upgrade. Version checks and `/api/version` never open the database.
