# SPDX-License-Identifier: GPL-3.0-or-later
"""Synchronize connected-node metadata from the AllStarLink directory."""

import argparse
import logging
import sqlite3
import sys
import time

from .database import initialize_database
from .metadata import cache_node, fetch_node

LOG = logging.getLogger(__name__)


def discover_nodes(db_path):
    """Find distinct local and remote nodes in connection history."""
    with sqlite3.connect(db_path) as db:
        rows = db.execute("""
            SELECT local_node AS node FROM connection_sessions
            UNION
            SELECT remote_node AS node FROM connection_sessions
            UNION
            SELECT node_number AS node FROM node_metadata_overrides
        """).fetchall()

    return sorted({
        str(row[0])
        for row in rows
        if row[0] is not None and str(row[0]).isdigit()
    })


def sync_nodes(db_path, nodes=None, timeout=10, delay=0.25):
    """Fetch and cache metadata; preserve existing cache on failures."""
    if nodes is None:
        nodes = discover_nodes(db_path)

    results = {
        "updated": 0,
        "missing": 0,
        "failed": 0,
    }

    for index, node in enumerate(nodes):
        node = str(node)

        if not node.isdigit():
            LOG.warning("Skipping invalid node: %r", node)
            results["failed"] += 1
            continue

        if index and delay:
            time.sleep(delay)

        try:
            record = fetch_node(node, timeout=timeout)

            if record is None:
                LOG.info("Node %s not found in directory", node)
                results["missing"] += 1
                continue

            cache_node(db_path, record)
            LOG.info("Updated node %s (%s)", node, record["callsign"])
            results["updated"] += 1

        except Exception as exc:
            LOG.warning("Failed to update node %s: %s", node, exc)
            results["failed"] += 1

    return results


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Synchronize AllStarLink node directory metadata"
    )
    parser.add_argument(
        "--database",
        required=True,
        help="SQLite connection logger database",
    )
    parser.add_argument(
        "--node",
        action="append",
        help="Specific node to synchronize (repeatable)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay between directory requests",
    )

    args = parser.parse_args(argv)

    if args.timeout <= 0 or args.delay < 0:
        parser.error("timeout must be positive and delay nonnegative")

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    initialize_database(args.database)

    results = sync_nodes(
        args.database,
        nodes=args.node,
        timeout=args.timeout,
        delay=args.delay,
    )

    print(
        f"Updated: {results['updated']}, "
        f"Missing: {results['missing']}, "
        f"Failed: {results['failed']}"
    )

    return 1 if results["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
