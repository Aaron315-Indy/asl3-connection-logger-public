# SPDX-License-Identifier: GPL-3.0-or-later
"""AllStarLink directory metadata synchronization and resolution."""

import json
import sqlite3
from urllib.parse import urlencode
from urllib.request import urlopen

DIRECTORY_URL = (
    "https://www.allstarlink.org/nodelist/nodelist-server.php"
)

FIELDS = (
    "callsign", "owner", "location", "frequency",
    "tone", "site", "affiliation",
)


def normalize_record(record):
    """Convert a directory record into the local metadata format."""
    if not isinstance(record, dict):
        raise ValueError("Directory record must be an object")

    node = str(record.get("name", ""))
    if not node.isdigit():
        raise ValueError("Invalid directory node number")

    return {
        "node_number": node,
        "callsign": record.get("callsign") or None,
        "owner": record.get("User_ID") or None,
        "location": record.get("Location") or None,
        "frequency": record.get("node_frequency") or None,
        "tone": record.get("node_tone") or None,
        "site": record.get("SiteName") or None,
        "affiliation": record.get("Affiliation") or None,
        "last_seen": record.get("regseconds"),
    }


def fetch_node(node_number, timeout=15):
    """Retrieve one node's metadata from the AllStarLink directory."""
    node_number = str(node_number)
    if not node_number.isdigit():
        raise ValueError("Invalid node number")

    url = DIRECTORY_URL + "?" + urlencode({"s": node_number})

    with urlopen(url, timeout=timeout) as response:
        records = json.load(response)

    if not isinstance(records, list):
        raise ValueError("Unexpected directory response")

    for record in records:
        normalized = normalize_record(record)
        if normalized["node_number"] == node_number:
            return normalized

    return None


def cache_node(db_path, metadata):
    """Insert or update directory metadata without changing overrides."""
    columns = (
        "node_number", *FIELDS, "last_seen",
    )

    values = [metadata.get(column) for column in columns]

    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in (*FIELDS, "last_seen")
    )

    sql = f"""
        INSERT INTO node_metadata ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(node_number) DO UPDATE SET
            {updates},
            updated_at = CURRENT_TIMESTAMP
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute(sql, values)


def resolve_node(connection, node_number):
    """Return merged directory metadata and local overrides."""
    node_number = str(node_number)

    directory = connection.execute(
        "SELECT * FROM node_metadata WHERE node_number = ?",
        (node_number,),
    ).fetchone()

    override = connection.execute(
        "SELECT * FROM node_metadata_overrides WHERE node_number = ?",
        (node_number,),
    ).fetchone()

    result = {"node_number": node_number}

    for field in (*FIELDS, "description"):
        directory_value = (
            directory[field]
            if directory is not None and field in directory.keys()
            else None
        )
        override_value = (
            override[field]
            if override is not None and field in override.keys()
            else None
        )
        result[field] = (
            override_value
            if override_value is not None
            else directory_value
        )

    return result
