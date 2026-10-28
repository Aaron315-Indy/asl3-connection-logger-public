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

Initial schema version: 1

Database migrations are not yet implemented.
