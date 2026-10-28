# SPDX-License-Identifier: GPL-3.0-or-later
"""Conservative recovery after an Asterisk process restart."""

import sqlite3

from .database import initialize_database
from .runtime import get_stable_runtime_id


def recover_previous_runtimes(db_path, local_node, dry_run=True):
    """Interrupt only sessions belonging to older Asterisk runtimes."""

    local_node = str(local_node)
    if not local_node.isdigit():
        raise ValueError("Local node must be numeric")

    expected_runtime = get_stable_runtime_id()
    initialize_database(db_path)

    with sqlite3.connect(db_path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("BEGIN IMMEDIATE")

        # Verify the runtime again while holding the write lock.
        if get_stable_runtime_id() != expected_runtime:
            raise RuntimeError("Asterisk runtime changed during recovery")

        rows = connection.execute(
            """
            SELECT id, remote_node
            FROM connection_sessions
            WHERE local_node = ?
              AND status = 'active'
              AND runtime_id IS NOT NULL
              AND runtime_id != ?
            ORDER BY id
            """,
            (local_node, expected_runtime),
        ).fetchall()

        if not dry_run:
            connection.executemany(
                """
                UPDATE connection_sessions
                SET status = 'interrupted',
                    disconnected_at = NULL,
                    duration_seconds = NULL
                WHERE id = ?
                  AND status = 'active'
                """,
                [(session_id,) for session_id, _ in rows],
            )
            connection.commit()

        return rows
