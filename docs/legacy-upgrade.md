# Upgrading the public v0.1.0 installation

This investigation uses local public source history and disposable installations.
W9SEM-Hub was not contacted or modified. Its reported generic HTTP 404 alone does
not identify the failed request; an active service and the two identity-endpoint
404s do not establish the status of `/health` or the history API.

## Source comparison

| Area | Public v0.1.0 | v0.2.3 |
| --- | --- | --- |
| Packaging | Static distribution version; no version/release modules | Version module and frozen build identity |
| HTTP | `/health` and `/api/dashboard`; identity endpoints return 404 | Health, history, version, and process-start release identity |
| SQLite | Schema 2: events, sessions, runtime IDs | Schema 3 adds metadata cache and override tables |
| Dashboard service | Installed venv, localhost port 8765, existing service user/hardening | Same service and deployment paths |
| Periodic metadata | No metadata units | Metadata-sync service and timer |
| Integration | Existing callbacks, Apache/authentication and configuration | Preserved by upgrades; fresh-install procedures are not rerun |

The public initial release is commit `2d0eebe`. Commit `17d2d6c` fixes static asset
packaging while retaining package version 0.1.0. The integration fixture builds
public commit `bbb8809`, which includes that packaging fix and the original
schema-2 dashboard, not a newly implemented imitation of it.

## Root cause and reproduction

The v0.2.3 upgrader probes `/health`, then `/api/version`, then the history API,
then `/api/release`. This happens before backup creation. Against the real public
v0.1.0 fixture, the recorded sequence is **GET `/health` -> 200**, then **GET
`/api/version` -> 404**; the exception prevents the later requests and no upgrade
backup exists. This proves the local public-source reproduction, not the
unobserved production request. The corrected diagnostics include the exact URL,
so a health, identity, or history API failure can be distinguished.

Ignoring that first exception would not suffice: the legacy package lacks
`version_info()`, lacks the metadata tables/units, and its collector rejects a
schema-3 marker. A naive upgrade could therefore break rollback logging even if
the old environment were restored successfully.

## Compatibility and transaction boundary

The upgrader recognizes 0.1.0 from installed distribution metadata. It snapshots
and verifies SQLite with the backup API, the complete Python environment with
owners/groups/modes/symlinks, dashboard and metadata base units, and reference
copies of their drop-ins before HTTP probing or package replacement. Existing
Apache/authentication, callback wrappers, source configuration and drop-ins are
not rewritten. Missing optional metadata units are distinguished from a service
manager or permissions failure.

Only known v0.1.0 receives the missing-endpoint fallback. It still needs a working
history API. Its package fingerprint and original endpoint capabilities are
recorded for recovery. Incoming packages always require wheel/content equality,
a healthy data API, and matching running version/release identity. A legacy
server cannot expose an HTTP content attestation; this limitation is explicit.

Metadata tables are created atomically using the database file's owner/group.
Existing events/sessions, IDs, status, timestamps and durations are not rewritten.
Existing schema-2 databases retain marker 2, including subsequent collector and
metadata-sync initialization. Brand-new databases still use marker 3. This
additive compatibility preserves the ability to run original v0.1.0 callbacks
after rollback. Extra metadata tables may remain; rollback does not drop tables,
replace the live database, or discard events recorded after the snapshot.

On failure after mutation begins, the old environment and units are restored;
legacy package content/version is checked before restarting the dashboard. Failed
environment restoration prevents restart. Recovery succeeds only after the old
HTTP capabilities and history API and database integrity have been verified.
Interrupted or incomplete recovery remains recorded and blocks another upgrade.
The timer is activated only after the new dashboard has passed verification.

## Regression coverage and limits

`tests/integration/test_legacy_upgrade.py` builds actual old and incoming wheels,
installs disposable virtual environments, creates an original schema-2 database,
and runs real localhost dashboard processes. Only service control and unit-file
locations are fixtures. The tests cover the original 404, successful/repeated
upgrade, metadata-unit installation, post-pip events, restart/identity/SQL-migration/
timer failures, restored ownership/modes/configuration, and actual old collector
writes after rollback. A separate migration runs with an unprivileged numeric
UID/GID to verify database-owner credentials. A broken legacy history endpoint
must fail with its exact URL and retained backups.

Static metadata units use real `systemd-analyze verify`. No production systemd
manager or Asterisk is controlled, and no metadata directory requests are made.
The incoming wheel is built from the uncommitted development source reporting
0.2.3; it does not replace or retag the immutable published v0.2.3 release.
