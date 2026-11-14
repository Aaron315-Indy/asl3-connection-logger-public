# v0.1.0 upgrades are unsupported

Connection Logger v0.2.4 formally discontinues v0.1.0 upgrade support. The former
legacy upgrade workflow and its compatibility fixtures have been removed.

The upgrader reads installed distribution metadata first and rejects v0.1.0 with
a clear error before importing modern identity modules, probing HTTP, creating
an upgrade snapshot, changing installed files or attempting a database migration.
Do not relabel the package or schema version or bypass the preflight checks.
Preserve existing databases and backups. No automated v0.1.0 migration is provided.

Stable v0.2.x upgrades remain supported, with direct v0.2.3 → v0.2.4,
repeat-upgrade and rollback regression coverage. Protected backup checks and the
rule against restoring a database over live callback history remain in place.

See [supported starting points](releases.md#supported-upgrade-starting-points)
and [upgrade and recovery instructions](web-dashboard.md#upgrading-an-existing-installation).
