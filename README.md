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
