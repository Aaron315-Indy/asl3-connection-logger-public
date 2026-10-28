# ASL3 Connection Logger

A GPLv3-licensed connection history logger for
AllStarLink 3 (ASL3).

## Purpose

Record AllStarLink node connection and disconnection
events with timestamps and session durations.

## Components

1. Backend event collector and SQLite database.
2. Read-only web dashboard with Apache2 integration.


## Installation

Tested environment: Debian 13 (Trixie) with AllStarLink 3.

Run as root on your AllStarLink server.

### 1. Install prerequisites

    apt update
    apt install -y git python3 python3-venv python3-pip apache2 curl

### 2. Clone and install

    git clone https://github.com/Aaron315-Indy/asl3-connection-logger-public.git /opt/asl3-connection-logger
    cd /opt/asl3-connection-logger
    python3 -m venv .venv
    .venv/bin/python -m pip install .

### 3. Install the connection collector

Replace 123456 with your actual AllStarLink node number.

Dry run:

    ./scripts/install.sh --node 123456 --dry-run

Install:

    ./scripts/install.sh --node 123456

The installer backs up /etc/asterisk/rpt.conf and configures
connection and disconnection callbacks.

Asterisk is not restarted or reloaded automatically.
Apply callback changes during a controlled Asterisk reload.

### 4. Install the optional dashboard

See [Web Dashboard Installation](docs/web-dashboard.md#installation).

### 5. Database location

    /var/lib/asl3-connection-logger/connections.db

## License

GNU General Public License version 3 or later.

See LICENSE.

## Web dashboard

The optional Apache2 web dashboard provides live connection
monitoring, history, statistics, filtering, and auto-refresh.

See [Web Dashboard Documentation](docs/web-dashboard.md)
for installation, configuration, security modes, API details,
and troubleshooting.
