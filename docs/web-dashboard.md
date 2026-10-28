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
