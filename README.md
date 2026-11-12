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
- A root shell (`sudo -i` if needed)
- Internet access to install required packages

### Quick Installation

Open a root terminal or SSH session on your AllStarLink node. For a **new**
installation, run the block below. For an existing installation, use the upgrade
instructions in the next section.

```bash
apt update &&
apt install -y git &&
git clone --single-branch --branch main https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /opt/asl3-connection-logger &&
(
    cd /opt/asl3-connection-logger &&
    ./scripts/setup.sh
)
```

The installer will:

1. Detect your configured AllStarLink node number.
2. Ask for confirmation.
3. Install required dependencies.
4. Configure connection and disconnection logging.
5. Preserve existing connection history.
6. Install the read-only reporting dashboard.
7. Configure Apache to serve reports at /logger/.

### Upgrading an Existing Installation

Public `main` tracks the latest stable release. Immutable `vX.Y.Z` tags identify
specific releases; see [release details](docs/releases.md) for tagged builds.

Run this block **as root in an interactive terminal** on Debian 13 or ASL3.
Keep the existing dashboard running. The incoming checkout is separate from the
default installed application at `/opt/asl3-connection-logger`.

```bash
(
    if [ -e /tmp/asl3-connection-logger-upgrade ] || [ -L /tmp/asl3-connection-logger-upgrade ]; then
        printf '%s\n' 'Checkout already exists; inspect or preserve it as described below before retrying.' >&2
        exit 1
    fi
    git clone --single-branch --branch main https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /tmp/asl3-connection-logger-upgrade &&
    cd /tmp/asl3-connection-logger-upgrade &&
    ./scripts/setup.sh
)
```

Answer `y` to **Upgrade existing installation?**. If the checkout already exists,
the block stops without changing it. Inspect it first; to preserve it intact,
including local changes, run this separate block and then repeat the upgrade
block above. The saved location is printed; keep it until verification succeeds.

```bash
asl3_saved_checkout=$(mktemp -d /tmp/asl3-connection-logger-upgrade.saved.XXXXXX) &&
mv -v -- /tmp/asl3-connection-logger-upgrade "$asl3_saved_checkout/"
```

For noninteractive operation, use `--upgrade` instead of the final setup command
in the main block. From a freshly prepared checkout, the supported command is:

```bash
(cd /tmp/asl3-connection-logger-upgrade && ./scripts/setup.sh --upgrade)
```

Setup automatically creates and verifies a SQLite backup and preserves history,
metadata, callbacks, Apache settings, authentication, and dashboard configuration.
The dashboard may restart; Asterisk is never restarted or reloaded. Failures after
changes begin trigger automatic application and unit rollback. Ordinary rollback
never overwrites the live database.

After success, check the expected release in `/api/version`, an `active (running)`
dashboard service, and SQLite integrity. These commands use the default port and
database path; adjust them only if your installation uses custom settings.

```bash
curl --fail --silent --show-error http://127.0.0.1:8765/api/version
systemctl status --no-pager asl3-connection-dashboard.service
python3 - <<'PYSQL'
import sqlite3
from contextlib import closing
uri = "file:/var/lib/asl3-connection-logger/connections.db?mode=ro"
with closing(sqlite3.connect(uri, uri=True)) as db:
    print(db.execute("PRAGMA integrity_check").fetchall())
PYSQL
```

Expect `[('ok',)]`. Read-only mode refuses a missing database instead of creating
one. Rollback backups remain under `/var/backups/asl3-connection-logger/upgrade-*`.
On failure, retain the backup, inspect the error, `state.json`, and `ROLLBACK.txt`,
and **do not blindly rerun**. Interrupted or incomplete recovery must be resolved
before another upgrade. Follow the [upgrade and recovery instructions](docs/web-dashboard.md#upgrading-an-existing-installation);
never restore a snapshot over the live database.

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
    ./scripts/setup.sh --dry-run

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
