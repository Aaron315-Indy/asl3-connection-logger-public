# ASL3 Connection Logger

A GPLv3-licensed connection history logger for
AllStarLink 3 (ASL3).

## Purpose

Record AllStarLink node connection and disconnection
events with timestamps and session durations.

## Components

1. Backend event collector and SQLite database.
2. Web-based reporting interface (planned).

## Development Status

Version 0.1.0 — Initial development.

## Supported Environment

- Debian GNU/Linux 13 (Trixie)
- AllStarLink 3
- Python 3.13+
- SQLite 3

## License

GNU General Public License version 3 or later.

See LICENSE.

## Web dashboard

The optional Apache2 web dashboard provides live connection
monitoring, history, statistics, filtering, and auto-refresh.

See [Web Dashboard Documentation](docs/web-dashboard.md)
for installation, configuration, security modes, API details,
and troubleshooting.
