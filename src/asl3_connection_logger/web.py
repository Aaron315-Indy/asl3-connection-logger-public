# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only HTTP API for the ASL3 Connection Logger."""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

DEFAULT_DB = "/var/lib/asl3-connection-logger/connections.db"


def read_dashboard(db_path, node="", status="", remote="", limit=100, date_from="", date_to=""):
    """Return connection history and statistics without writing to SQLite."""
    limit = max(1, min(int(limit), 500))

    if node and not node.isdigit():
        raise ValueError("Invalid local node")
    if remote and not remote.isdigit():
        raise ValueError("Invalid remote node")
    if status and status not in ("active", "completed", "interrupted"):
        raise ValueError("Invalid session status")

    for value in (date_from, date_to):
        if value:
            datetime.strptime(value, "%Y-%m-%d")

    if date_from and date_to and date_from > date_to:
        raise ValueError("Start date must not exceed end date")

    uri = Path(db_path).resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")

        filters = []
        params = []

        for column, value in (
            ("local_node", node),
            ("remote_node", remote),
            ("status", status),
        ):
            if value:
                filters.append(f"{column} = ?")
                params.append(value)

        if date_from:
            filters.append("substr(connected_at, 1, 10) >= ?")
            params.append(date_from)
        if date_to:
            filters.append("substr(connected_at, 1, 10) <= ?")
            params.append(date_to)

        where = " WHERE " + " AND ".join(filters) if filters else ""

        rows = db.execute(
            """
            SELECT id, local_node, remote_node, connected_at,
                   disconnected_at, duration_seconds, status, runtime_id
            FROM connection_sessions
            """
            + where
            + " ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()

        counts = db.execute(
            "SELECT status, COUNT(*) AS total FROM connection_sessions"
            + where
            + " GROUP BY status",
            params,
        ).fetchall()

        duration = db.execute(
            """
            SELECT AVG(duration_seconds) AS average_seconds,
                   MAX(duration_seconds) AS longest_seconds
            FROM connection_sessions
            """
            + where,
            params,
        ).fetchone()

        popular = db.execute(
            """
            SELECT remote_node, COUNT(*) AS connections
            FROM connection_sessions
            """
            + where
            + " GROUP BY remote_node ORDER BY connections DESC LIMIT 10",
            params,
        ).fetchall()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sessions": [dict(row) for row in rows],
        "counts": {row["status"]: row["total"] for row in counts},
        "average_seconds": duration["average_seconds"],
        "longest_seconds": duration["longest_seconds"],
        "top_nodes": [dict(row) for row in popular],
    }


class DashboardHandler(BaseHTTPRequestHandler):
    database = DEFAULT_DB

    def do_GET(self):
        parsed = urlsplit(self.path)

        if parsed.path == "/":
            return self.send_homepage()

        if parsed.path == "/health":
            return self.send_json({"status": "ok"})

        if parsed.path != "/api/dashboard":
            return self.send_json({"error": "Not found"}, 404)

        try:
            query = parse_qs(parsed.query)
            result = read_dashboard(
                self.database,
                node=query.get("node", [""])[0],
                status=query.get("status", [""])[0],
                remote=query.get("remote", [""])[0],
                limit=query.get("limit", ["100"])[0],
                date_from=query.get("from", [""])[0],
                date_to=query.get("to", [""])[0],
            )
            self.send_json(result)
        except (ValueError, TypeError):
            self.send_json({"error": "Invalid filter"}, 400)
        except sqlite3.Error:
            self.send_json({"error": "Database unavailable"}, 503)

    def send_homepage(self):
        from importlib.resources import files

        page = (
            files("asl3_connection_logger")
            .joinpath("static/index.html")
            .read_bytes()
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def send_json(self, value, status=200):
        payload = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=DEFAULT_DB)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {"database": args.database},
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"ASL3 dashboard API listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
