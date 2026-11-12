# ASL3 Connection Logger — Web Dashboard

## Overview

The web dashboard displays AllStarLink 3 connection activity.

You can view:

- Currently connected nodes
- Connection and disconnection history
- Session durations
- Completed and interrupted connections
- Most frequently connected remote nodes
- Connection statistics
- Reports filtered by node, status, or date

The dashboard is read-only. It does not control Asterisk.

## Installation

The dashboard is installed automatically by the standard
ASL3 Connection Logger installer.

On your AllStarLink 3 system:

    sudo apt update
    sudo apt install -y git
    sudo git clone https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /opt/asl3-connection-logger
    cd /opt/asl3-connection-logger
    sudo ./scripts/setup.sh

The installer detects your AllStarLink node number and
configures the logger and dashboard.

If the logger is already installed, see the main README
before rerunning the installer.

## Viewing Reports

Open a web browser and visit:

    http://YOUR-NODE-IP/logger/

Replace YOUR-NODE-IP with the IP address of your
AllStarLink node.

The dashboard refreshes automatically and allows you
to filter connection history.

## Activating Connection Logging

The installer configures Asterisk connection and
disconnection callbacks.

It does not restart or reload Asterisk automatically.

Apply the callback changes during a controlled Asterisk
reload before expecting new connection events.

## Checking Dashboard Status

Check the dashboard service:

    systemctl status asl3-connection-dashboard.service

Check the dashboard API:

    curl http://127.0.0.1:8765/health

Check Apache:

    systemctl status apache2

## Troubleshooting

### Dashboard does not load

Verify the dashboard and Apache services are running.

    systemctl status asl3-connection-dashboard.service
    systemctl status apache2

### Dashboard loads but shows no connections

Verify that Asterisk has applied the new callback
configuration.

Connection history appears after connections and
disconnections have been recorded.

### Dashboard returns an error

Check the dashboard logs:

    journalctl -u asl3-connection-dashboard.service -n 50 --no-pager

Check Apache logs:

    journalctl -u apache2 -n 50 --no-pager

## Security

The standard interactive installer does not configure
dashboard authentication or restrict client source IPs.

Anyone who can reach the Apache web server may be able
to view connection reports.

Do not expose the dashboard directly to the public
Internet without appropriate access controls.

## Advanced Configuration

Hub operators can use the noninteractive installers
for custom configurations:

- scripts/install.sh
- scripts/install-dashboard.sh

These support explicit node selection and private
network restrictions.

The dashboard's local API listens on:

    127.0.0.1:8765

Apache provides access under:

    /logger/

## License

GNU General Public License version 3 or later.

The local-node filter initially contains the lowest numeric node section in
`/etc/asterisk/rpt.conf` (including local `#include` and `#tryinclude` files).
Numeric template sections are excluded. If configuration is unavailable or has
no local nodes, the filter starts empty. You can enter another local node or
clear the field to show all nodes; refreshing does not restore the default.

### Upgrading an existing installation

Keep the incoming public release in a separate checkout or extracted release
folder. From that folder run `sudo scripts/setup.sh` and choose the upgrade
prompt, or run `sudo scripts/setup.sh --upgrade` without a terminal. The installed
application remains at `/opt/asl3-connection-logger`; setup installs the incoming
wheel into that installation's existing `.venv`. It does not redirect services
to the source checkout or replace installed hooks. For an explicitly customized
installation use `--upgrade --install-dir /your/installed/path` or set
`ASL3_INSTALL_DIR` (pass it through sudo if needed).

Setup validates the effective dashboard command, installed version, running
version, health and data API before making changes. It preserves custom database
and port arguments, resolves relative database paths against the service working
directory, and preserves independently configured metadata database paths.
Unresolved systemd argument substitutions and masked metadata units require
operator resolution before upgrade. A running metadata job must finish before
upgrading. The metadata timer is paused during installation and its previous
active/enabled state is preserved. Only the dashboard service can be restarted;
Asterisk and Apache are never restarted or reloaded.

Backups live outside Git at `/var/backups/asl3-connection-logger/upgrade-*`, beneath
a root-owned directory with mode 0700. An optional `--backup-root` selects another
persistent, root-controlled location outside any repository. Ensure sufficient
disk space for the database snapshot, the complete old environment, and the new
wheel. Backups contain a verified SQLite backup (including committed WAL data),
the previous Python environment, metadata unit files or symlink information,
`units.json`, `state.json`, and recovery instructions in `ROLLBACK.txt`.

Setup finishes backup preparation and builds and inspects the incoming wheel
before changing installed state. Both rendered metadata units must pass
`systemd-analyze verify` in the backup staging directory before the timer is
paused or packages are installed. `WorkingDirectory=` uses a literal absolute
path; command arguments and path lists retain their separate quoting rules.
Paths containing control characters are refused. systemd also rejects quote or
backslash characters in executable filenames; such installation paths fail static
verification before any installed state changes. It checks installed package content against that
wheel and checks the running dashboard's `/api/release` identity against it.
This endpoint captures version, commit, dirty flag, and package content hash when
the dashboard process starts, so an old process cannot pass verification merely
by reading a newly installed version file. Health, `/api/version`, the data API,
and live database integrity are also checked. Repeating the same release is safe;
build timestamps alone do not require a dashboard restart.

On installation or verification failure, setup automatically restores the complete
previous environment at its original path, restores metadata unit files and
symlinks without touching drop-ins, restores timer state, and restarts and verifies
the previous dashboard when the environment may have changed. If environment
restoration fails, dashboard restart and verification are skipped and rollback
is reported incomplete. Successful rollback requires matching the previous
version API identity and captured release identity (the legacy v0.2.0 API
provides version, commit, and dirty flag without a content endpoint). It retains the
failed environment in the protected backup directory for diagnosis. Apache settings, authentication,
Asterisk callbacks, dashboard settings, metadata, and the live database are
preserved. Ordinary rollback never writes or restores the live SQLite database:
callbacks may have recorded events after the snapshot.

`state.json` distinguishes preparation failures (no installation changes), verified
success, verified rollback, and incomplete rollback. Every unfinished journal,
including interrupted preparation, and missing or malformed journals block new
upgrades before preflight. Rollback records `dashboard_verified: true` only after
verification succeeds; older rollback journals without that evidence also block
upgrades. After manual recovery and dashboard version/release verification, root
may explicitly record `state: "resolved"` and a nonempty `resolution` note in the
journal. Retain the journal rather than deleting it to bypass the guard. On any
failure setup exits unsuccessfully and prints the backup location. If automatic
recovery is incomplete, use `ROLLBACK.txt` and the manifest to restore the original
environment and unit/timer state and verify the dashboard. Retain all backups and
the failed environment until recovery is verified. Database disaster recovery is
a separate maintenance operation; never copy a snapshot over the live database.
