# AllStarLink Node Metadata

ASL3 Connection Logger enriches connection history with node information
from the AllStarLink directory.

## Directory information

The following fields are supported:

- Node number
- Callsign
- Owner
- Location
- Frequency or node description
- Tone
- Site
- Affiliation

The `node_frequency` field may contain descriptive text rather than
a numeric frequency.

## Automatic synchronization

The metadata synchronization service discovers nodes from connection
history and locally configured overrides.

It retrieves directory information and stores it in the existing
SQLite database.

Synchronization runs separately from Asterisk and the web dashboard.

Service:

    asl3-metadata-sync.service

Timer:

    asl3-metadata-sync.timer

The timer refreshes directory information approximately every six
hours, with a randomized scheduling delay.

Check the timer:

    systemctl list-timers asl3-metadata-sync.timer

Run synchronization manually:

    systemctl start asl3-metadata-sync.service

View synchronization logs:

    journalctl -u asl3-metadata-sync.service -n 50 --no-pager

## Manual synchronization

Synchronize a particular node:

    /opt/asl3-connection-logger/.venv/bin/python \
      -m asl3_connection_logger.metadata_sync \
      --database /var/lib/asl3-connection-logger/connections.db \
      --node 100001

The command must run as a user with permission to update the database.

## Local overrides

Local overrides take precedence over directory information on a
field-by-field basis.

Supported override fields:

- callsign
- owner
- location
- frequency
- tone
- site
- affiliation
- description

A NULL override means the directory value is used. An empty string
is an explicit override and suppresses the corresponding directory value.

Example: configure a custom description and location for node 100001.

    sudo -u asterisk sqlite3 \
      /var/lib/asl3-connection-logger/connections.db \
      "INSERT INTO node_metadata_overrides
         (node_number, description, location)
       VALUES ('100001', 'Example Hub', 'Example Location')
       ON CONFLICT(node_number) DO UPDATE SET
         description=excluded.description,
         location=excluded.location;"

This example requires the sqlite3 command-line utility.

Directory synchronization never overwrites local overrides.

Remove an override:

    sudo -u asterisk sqlite3 \
      /var/lib/asl3-connection-logger/connections.db \
      "DELETE FROM node_metadata_overrides
       WHERE node_number='100001';"

## Offline operation

The dashboard reads cached SQLite metadata only.

It never contacts the AllStarLink directory while serving requests.

If directory synchronization fails, previously cached metadata and
local overrides remain available.

Unknown nodes continue to display their numeric node numbers.

## Security

The synchronization service runs as the asterisk user.

It uses systemd filesystem restrictions and requires write access
only to the logger database directory.

Administrators are responsible for configuring HTTPS separately
when exposing the dashboard publicly.
