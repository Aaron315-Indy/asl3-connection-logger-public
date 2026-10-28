# ASL3 Connection Logger — Web Dashboard

## Overview

The web dashboard provides read-only reporting for AllStarLink 3
connection activity stored in SQLite.

Features:

- Current connections
- Connection history
- Completed and interrupted sessions
- Connection duration statistics
- Most frequently connected remote nodes
- Local and remote node filtering
- Status filtering
- UTC connection-start date filtering
- Automatic refresh (15, 30, or 60 seconds)
- Responsive dark interface

The dashboard does not control Asterisk or modify connection records.

## Requirements

- Debian 13 (Trixie)
- AllStarLink 3
- Apache2
- Python virtual environment from the main project
- Existing ASL3 Connection Logger installation
- Root access for installation

TLS certificate issuance and renewal are outside this project's scope.
Administrators are responsible for configuring HTTPS when required.

The installer uses Apache2 as a reverse proxy. No additional
web server is required.

## Architecture

Browser
  |
  | HTTP or HTTPS
  v
Apache2 /logger/
  |
  | Reverse proxy
  v
127.0.0.1:8765
  |
  v
Python read-only API
  |
  v
SQLite connection database

The Python service listens only on localhost.


## Installation

Complete the [main installation](../README.md#installation) first.

### 1. Install Apache prerequisites

Run as root:

    apt update
    apt install -y apache2 apache2-utils curl

### 2. Install the private dashboard

    cd /opt/asl3-connection-logger

Replace 123456 with your actual AllStarLink node number.

Replace 192.0.2.0/24 with your actual permitted LAN or VPN
network. The addresses below are documentation examples.

    ./scripts/install-dashboard.sh --node 123456 --mode private --allow-networks "192.0.2.0/24"

For multiple networks:

    ./scripts/install-dashboard.sh --node 123456 --mode private --allow-networks "192.0.2.0/24 198.51.100.0/24"

### 3. Verify installation

    systemctl status asl3-connection-dashboard.service
    apache2ctl configtest
    curl --fail http://127.0.0.1:8765/health

Open the dashboard at:

    http://YOUR-SERVER-IP/logger/

Your browser's source IP must be within an allowed network.

### What the installer configures

- Dedicated service account: asl3logger-web
- systemd service: asl3-connection-dashboard.service
- Apache2 reverse proxy under /logger/
- Network-based authorization for private mode
- Local API listening on 127.0.0.1:8765

The installer can be rerun.

## Authentication modes

### Private

Private mode requires no username or password.

Apache restricts access to the configured source networks.

No networks are allowed by default. Administrators must
explicitly supply an allowlist with `--allow-networks` or the
`ASL3_DASHBOARD_NETWORKS` environment variable.

Private mode does not automatically make the server private.
Ensure the allowlist reflects the networks from which Apache
actually receives client connections.

### Public

Public mode is intended to use Apache Basic Authentication
over HTTPS.

The installer includes preliminary support for:

    ./scripts/install-dashboard.sh \
      --node 123456 \
      --mode public

**Public mode is not yet approved for deployment.**

Before enabling it, validate the HTTPS virtual host, certificate
hostname, authentication enforcement, and HTTP-to-HTTPS behavior.

Do not expose Basic Authentication over plaintext HTTP.

## URLs

Example private dashboard:

    http://192.0.2.10/logger/

Configured hostname:

    node.example.org

The hostname's HTTPS URL requires a valid certificate and
a correctly configured Apache HTTPS virtual host.

## API

Health endpoint:

    http://127.0.0.1:8765/health

Dashboard endpoint:

    http://127.0.0.1:8765/api/dashboard

Supported query parameters:

| Parameter | Description |
|-----------|-------------|
| node | Local node number |
| remote | Remote node number |
| status | active, completed, interrupted |
| from | Start date, YYYY-MM-DD |
| to | End date, YYYY-MM-DD |
| limit | Maximum returned sessions, capped at 500 |

Date filters apply to the connection start date in UTC.

Statistics are calculated over all matching sessions, not
only the limited set returned in the history table.

## Service management

Check status:

    systemctl status asl3-connection-dashboard.service

Restart dashboard:

    systemctl restart asl3-connection-dashboard.service

View logs:

    journalctl -u asl3-connection-dashboard.service -n 100 --no-pager

The dashboard service is independent of Asterisk.

## Apache2 configuration

Configuration file:

    /etc/apache2/conf-available/asl3-connection-logger.conf

Enabled through:

    /etc/apache2/conf-enabled/asl3-connection-logger.conf

Check Apache syntax:

    apache2ctl configtest

Reload Apache:

    systemctl reload apache2

The installer does not replace the existing AllStarLink
Apache virtual host.

## Troubleshooting

### Dashboard unavailable

Check:

    systemctl status asl3-connection-dashboard.service

    ss -ltnp '( sport = :8765 )'

    curl http://127.0.0.1:8765/health

### HTTP 403

Check the private-mode source IP allowlist.

If accessing through a VPN or reverse proxy, verify the
source address Apache actually sees.

### HTTP 503 from the API

Verify that the web service account can read the SQLite
database and traverse its parent directory.

The database must remain protected from unauthorized writes.

### Apache proxy errors

Check:

    apache2ctl configtest

    journalctl -u apache2 -n 100 --no-pager

### Date filters

Dates use YYYY-MM-DD and are interpreted against the
UTC connection-start date.

## Development

Run tests:

    cd /opt/asl3-connection-logger
    .venv/bin/python -m pytest -q

Check syntax:

    .venv/bin/python -m compileall -q src/asl3_connection_logger

## License

GPL-3.0-or-later.
