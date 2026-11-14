# Database Schema

ASL3 Connection Logger uses SQLite.

## connection_events

Stores every callback event, including duplicate events
and unmatched disconnects.

Fields:
- id: unique event ID
- local_node: local ASL3 node
- remote_node: connected remote node
- event_type: connect or disconnect
- event_timestamp: UTC timestamp
- received_at: SQLite insertion timestamp

## connection_sessions

Stores connection sessions.

Fields:
- id: unique session ID
- local_node: local ASL3 node
- remote_node: connected remote node
- connected_at: UTC connection timestamp
- disconnected_at: UTC disconnection timestamp
- duration_seconds: calculated duration
- status: active, completed, or interrupted

## Timestamp Handling

Event timestamps are stored in UTC.

Reporting applications should convert timestamps into
the user's configured timezone.

## Database Location

Default:
/var/lib/asl3-connection-logger/connections.db

## Schema Version

Current schema version: 3. Version 2 added session runtime IDs; version 3 adds
cached metadata and metadata overrides. Database initialization migrates older
schema markers transactionally and records version 3 after successful migration.

Schema migration capability does not establish application upgrade support.
Connection Logger v0.2.4 rejects v0.1.0 installations before migration; see
[supported upgrade starting points](releases.md#supported-upgrade-starting-points).
