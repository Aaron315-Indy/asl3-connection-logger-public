# Changelog

## [Unreleased]

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
