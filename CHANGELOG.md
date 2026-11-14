# Changelog

## 0.2.4

- Discontinue v0.1.0 upgrade support. Reject unsupported installed versions with
  a clear error before HTTP probing, package installation or database migration.
- Remove v0.1.0 identity/endpoint fallbacks, migration and rollback compatibility,
  historical package fixtures, and schema-2 marker retention.
- Maintain v0.2.3 → v0.2.4 upgrade, repeat-upgrade and rollback coverage using
  real v0.2.3 wheels, HTTP and SQLite with disposable service-control fixtures.
- Preserve verified environment ownership/modes, protected backups outside Git,
  exact HTTP error URLs and the live database during rollback.

## 0.2.2

- Match wheel and installed content digests despite untracked `.bak` leftovers;
  retain verification of owned, modified, missing, and unexpected application files.

## 0.2.1

- Default the dashboard local-node input to the lowest locally configured node
  numbered 2000 or greater across multi-node installations. Leave the default
  blank for private-only configurations and retain manual and empty filters.
- Add interactive and noninteractive setup upgrades with verified SQLite backups,
  environment and metadata timer updates, process release verification, and
  automatic rollback of the previous environment and units on failure.
- Separate incoming source from installed paths and keep protected persistent
  rollback backups outside Git; never overwrite the live database during rollback.
  Preserve existing configuration and never reload or restart Asterisk.
- Render systemd working directories as literal paths and validate generated
  metadata service/timer units before changing the installed environment.


## [0.2.0] — 2026-11-11

### Added
- Cached node metadata, local overrides, and periodic directory synchronization.
- Dashboard metadata labels with correctly rendered newlines.
- One SemVer application version source with distinct development identity.
- Installed dashboard footer, CLI --version, and GET /api/version.
- Installer installed/incoming version preflight before package replacement.
- Frozen commit and build provenance for wheels, sdists and source archives.
- Automated version, packaging and HTTP tests; release/upgrade documentation.

## [0.1.0] — existing public baseline

The initial public commit (2d0eebe) and subsequent installed package declared
0.1.0. No version tags were present in the inspected local history.
The original development notes follow; their limitations describe that earlier
stage and are not a statement of current feature support.


### Added
- SQLite connection event database
- Connection session tracking
- UTC event timestamps
- Session duration calculation
- ASL3 connection/disconnection callback
- Automated database and collector tests
- Initial GPLv3 project structure

### Verified
- Debian 13 Trixie
- ASL3 3.10.8 / Asterisk 22.10.1
- Python 3.13
- Real connection/disconnection on development node 123456

### Known Limitations
- Reboot reconciliation not implemented
- Database migrations not implemented
- Reporting API not implemented
- Web frontend not implemented
