# SPDX-License-Identifier: GPL-3.0-or-later
"""Read chan_echolink's local directory without contacting external services."""

import ipaddress
import logging
import re
import subprocess

LOG = logging.getLogger(__name__)
ECHOLINK_OFFSET = 3_000_000


def parse_directory(output):
    """Return logger-node records from ID|callsign|IP directory rows.

    CLI headers and malformed rows are ignored. An unrecognized/empty dump is
    a failure, so CLI error text (including a missing module) is never cached.
    """
    records = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            continue
        identity, callsign, address = parts
        if not re.fullmatch(r"[0-9]+", identity):
            LOG.warning("Skipping invalid EchoLink directory ID")
            continue
        try:
            numeric_id = int(identity)
        except ValueError:
            LOG.warning("Skipping unrepresentable EchoLink directory ID")
            continue
        if numeric_id == 0:
            LOG.warning("Skipping invalid EchoLink directory ID")
            continue
        if not re.fullmatch(r"[A-Za-z0-9*][A-Za-z0-9*/-]{0,31}", callsign):
            LOG.warning("Skipping invalid EchoLink directory callsign")
            continue
        try:
            ipaddress.IPv4Address(address)
        except ValueError:
            LOG.warning("Skipping invalid EchoLink directory address")
            continue
        node = str(ECHOLINK_OFFSET + numeric_id)
        records[node] = {"node_number": node, "callsign": callsign}

    if not records:
        raise ValueError("EchoLink directory unavailable or contains no valid records")
    return records


def fetch_directory(timeout=10):
    """Execute the read-only Asterisk CLI command once, with a bounded wait."""
    result = subprocess.run(
        ["asterisk", "-rx", "echolink dbdump"],
        capture_output=True, text=True, timeout=timeout, check=True,
    )
    return parse_directory(result.stdout)
