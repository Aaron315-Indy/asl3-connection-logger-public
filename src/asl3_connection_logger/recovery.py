# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconcile recorded sessions with confirmed live connections."""

import sqlite3

from .database import initialize_database


def reconcile_sessions(db_path, local_node, connected_nodes,
                       dry_run=True, runtime_id=None, snapshot_started_at=None,
                       runtime_guard=None):
    """Mark missing active sessions as interrupted.

    connected_nodes must be an authoritative snapshot of currently
    connected remote nodes. Never pass an unverified or failed query.
    """

    local_node = str(local_node)

    if not local_node.isdigit():
        raise ValueError("Local node must be numeric")

    connected_nodes = {str(node) for node in connected_nodes}

    if not all(node.isdigit() for node in connected_nodes):
        raise ValueError("Connected nodes must be numeric")

    initialize_database(db_path)

    with sqlite3.connect(db_path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("BEGIN IMMEDIATE")

        active = connection.execute(
            """
            SELECT id, remote_node, runtime_id, connected_at
            FROM connection_sessions
            WHERE local_node = ?
              AND status = 'active'
            """,
            (local_node,),
        ).fetchall()

        interrupted = []

        for session_id, remote_node, session_runtime, connected_at in active:
            stale_runtime = (
                runtime_id is not None
                and session_runtime is not None
                and session_runtime != runtime_id
            )

            # A session created after the snapshot began must not
            # be interrupted merely because it was absent from
            # the earlier Asterisk connection listing.
            created_after_snapshot = (
                snapshot_started_at is not None
                and connected_at > snapshot_started_at
            )

            if stale_runtime or (
                not created_after_snapshot
                and remote_node not in connected_nodes
            ):
                interrupted.append((session_id, remote_node))

        if not dry_run:
            # Validate the snapshot while holding the SQLite write lock.
            if runtime_guard is not None:
                runtime_guard()

            connection.executemany(
                """
                UPDATE connection_sessions
                SET status = 'interrupted',
                    disconnected_at = NULL,
                    duration_seconds = NULL
                WHERE id = ?
                  AND status = 'active'
                """,
                [(session_id,) for session_id, _ in interrupted],
            )

            connection.commit()

        return interrupted
