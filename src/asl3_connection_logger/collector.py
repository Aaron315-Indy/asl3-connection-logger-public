# SPDX-License-Identifier: GPL-3.0-or-later
"""Process ASL3 connection and disconnection events."""

import sqlite3
from datetime import datetime, timezone

from .database import initialize_database


def process_event(db_path, local_node, remote_node, event_type,
                  timestamp=None, runtime_id=None):
    """Record an event and update its connection session."""

    if event_type not in ("connect", "disconnect"):
        raise ValueError("Invalid event type")

    local_node = str(local_node)
    remote_node = str(remote_node)

    if not local_node.isdigit() or not remote_node.isdigit():
        raise ValueError("Node numbers must be numeric")

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        raise ValueError("Timestamp must include timezone")

    timestamp = timestamp.astimezone(timezone.utc)
    event_time = timestamp.isoformat()

    initialize_database(db_path)

    with sqlite3.connect(db_path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")

        # Serialize concurrent callback writers.
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            INSERT INTO connection_events
                (local_node, remote_node, event_type, event_timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (local_node, remote_node, event_type, event_time),
        )

        active = connection.execute(
            """
            SELECT id, connected_at, runtime_id
            FROM connection_sessions
            WHERE local_node = ?
              AND remote_node = ?
              AND status = 'active'
            """,
            (local_node, remote_node),
        ).fetchone()

        if event_type == "connect":
            if (active is not None
                    and runtime_id is not None
                    and active[2] != runtime_id):
                # A new Asterisk runtime cannot inherit an old session.
                connection.execute(
                    """
                    UPDATE connection_sessions
                    SET status = 'interrupted',
                        disconnected_at = NULL,
                        duration_seconds = NULL
                    WHERE id = ? AND status = 'active'
                    """,
                    (active[0],),
                )
                active = None

            if active is None:
                connection.execute(
                    """
                    INSERT INTO connection_sessions
                        (local_node, remote_node, connected_at,
                         status, runtime_id)
                    VALUES (?, ?, ?, 'active', ?)
                    """,
                    (local_node, remote_node, event_time, runtime_id),
                )

        elif active is not None:
            session_id, connected_at, session_runtime = active

            # Ignore a delayed disconnect from an older runtime.
            if (runtime_id is not None
                    and session_runtime is not None
                    and session_runtime != runtime_id):
                connection.commit()
                return

            start = datetime.fromisoformat(connected_at)
            duration = max(
                0,
                round((timestamp - start).total_seconds()),
            )

            connection.execute(
                """
                UPDATE connection_sessions
                SET disconnected_at = ?,
                    duration_seconds = ?,
                    status = 'completed'
                WHERE id = ?
                """,
                (event_time, duration, session_id),
            )

        connection.commit()
