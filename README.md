# ASL3 Connection Logger

A GPLv3-licensed connection history logger for
AllStarLink 3 (ASL3).

## Purpose

Record AllStarLink node connection and disconnection
events with timestamps and session durations.

## Components

1. Backend event collector and SQLite database.
2. Read-only web reporting dashboard.



## Installation

ASL3 Connection Logger records AllStarLink 3 node connections
and provides a read-only web reporting dashboard.

The interactive installer is intended for:

- AllStarLink 3 Raspberry Pi appliance installations
- Custom AllStarLink 3 hubs running Debian 13

### Requirements

- A working AllStarLink 3 installation
- Debian 13 (Trixie)
- Root or sudo access
- Internet access to install required packages

### Quick installation

Open a terminal or SSH session on your AllStarLink node.

Run:

    sudo apt update
    sudo apt install -y git

Download the logger:

    sudo git clone https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /opt/asl3-connection-logger

Start the installer:

    cd /opt/asl3-connection-logger
    sudo ./scripts/setup.sh

The installer will:

1. Detect your configured AllStarLink node number.
2. Ask for confirmation.
3. Install required dependencies.
4. Configure connection and disconnection logging.
5. Preserve existing connection history.
6. Install the read-only reporting dashboard.
7. Configure Apache to serve reports at /logger/.

### Upgrading an Existing Installation

Download the latest [public release](https://github.com/Aaron315-Indy/asl3-connection-logger-public/releases/latest)
and extract it into a fresh directory **outside** `/opt/asl3-connection-logger`.
Alternatively, clone the release below, replacing `RELEASE_TAG` with its published
tag. Use a new destination if the example directory already exists.

    git clone --branch RELEASE_TAG https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /tmp/asl3-connection-logger-upgrade
    cd /tmp/asl3-connection-logger-upgrade
    sudo ./scripts/setup.sh

Keep the existing dashboard running. Answer `y` to **Upgrade existing installation?**.
The default installed application remains at `/opt/asl3-connection-logger`;
run setup from the incoming release directory. For a noninteractive upgrade,
run this instead from that same directory:

    sudo ./scripts/setup.sh --upgrade

Setup automatically creates and verifies a SQLite backup before changing the
installation. Existing history, metadata, Asterisk callbacks, Apache settings,
authentication, and dashboard configuration are preserved. The dashboard may
restart; Asterisk is never restarted or reloaded. Failures after changes begin
trigger automatic application and systemd-unit rollback; the live database is
never overwritten during ordinary rollback.

After upgrading, verify the expected release, active dashboard service, and database:

    curl --fail --silent --show-error http://127.0.0.1:8765/api/version
    sudo systemctl status --no-pager asl3-connection-dashboard.service

Check SQLite integrity read-only using the installed Python standard library:

```bash
sudo python3 - <<'PYSQL'
import sqlite3
with sqlite3.connect("file:/var/lib/asl3-connection-logger/connections.db?mode=ro", uri=True) as db:
    print(db.execute("PRAGMA integrity_check").fetchall())
PYSQL
```

Expect `[('ok',)]`. Substitute your configured port or database path if customized.
Rollback backups are retained in `/var/backups/asl3-connection-logger/upgrade-*`.
If an upgrade fails, retain the printed backup directory, inspect the error and
its `state.json` / `ROLLBACK.txt`, and **do not blindly rerun**. Resolve interrupted
or incomplete recovery first; never copy a backup over the live database.
See [detailed upgrade and recovery instructions](docs/web-dashboard.md#upgrading-an-existing-installation).

### View your reports

Open the following address in a web browser:

    http://YOUR-NODE-IP/logger/

Replace YOUR-NODE-IP with your AllStarLink node's IP address.

### Important: Dashboard access

The standard installer does not configure dashboard authentication
or restrict clients by source IP address.

Anyone who can reach the Apache web server may be able to view
connection reports.

Do not expose the dashboard directly to the public Internet
without appropriate access controls.

Hub operators requiring custom Apache access restrictions,
authentication, or HTTPS should use the advanced dashboard
installation instructions.

### Activate connection logging

The installer configures Asterisk connection and disconnection
callbacks but does not automatically reload or restart Asterisk.

Apply the changes during a controlled Asterisk reload.

Until the configuration is applied, new connection events may
not be recorded.

### Test installation without making changes

    cd /opt/asl3-connection-logger
    sudo ./scripts/setup.sh --dry-run

The dry run checks node detection and displays the installation
summary without installing packages or changing configuration.

### Check dashboard status

    systemctl status asl3-connection-dashboard.service

Check the dashboard API:

    curl http://127.0.0.1:8765/health

### Advanced installation

The existing noninteractive installers remain available:

- scripts/install.sh
- scripts/install-dashboard.sh

See [Web Dashboard Documentation](docs/web-dashboard.md)
for advanced Apache and network configuration.

## License

GNU General Public License version 3 or later.

See LICENSE.

## Web dashboard

The optional Apache2 web dashboard provides live connection
monitoring, history, statistics, filtering, and auto-refresh.

See [Web Dashboard Documentation](docs/web-dashboard.md)
for installation, configuration, security modes, API details,
and troubleshooting.

## Node metadata

Connection history can display AllStarLink directory callsigns, locations, and locally configured descriptions. Metadata is cached in SQLite and refreshed by a systemd timer.

See [Node metadata documentation](docs/node-metadata.md) for synchronization, configuration, and local overrides.

## Application version

Show the installed version and available commit identifier:

    /opt/asl3-connection-logger/.venv/bin/asl3-connection-logger --version

The equivalent module command is `.venv/bin/python -m asl3_connection_logger --version`.
The dashboard footer shows the same identity, even if reporting data fails.
Fetch public build information with:

    curl http://127.0.0.1:8765/api/version

Through Apache the endpoint is `/logger/api/version` and uses the dashboard's
existing access controls. Fields are `version`, `commit` (or null), and `build`
(`type`, `built_at` UTC or null, and `dirty`). No database access is required.
See [Release and upgrade documentation](docs/releases.md) for the authoritative
version source, development versions, archive builds and upgrade preflight.
