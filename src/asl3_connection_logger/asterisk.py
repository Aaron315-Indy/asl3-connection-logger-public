# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and validate live AllStarLink connection state."""

import re
import subprocess


def parse_stats(output, node):
    expected = f"NODE {node} STATISTICS"

    if expected not in output:
        raise ValueError("Asterisk node statistics unavailable")

    match = re.search(
        r"^Nodes currently connected to us\.+:\s*(.*)$",
        output,
        re.MULTILINE,
    )

    if not match:
        raise ValueError("Missing connected-nodes field")

    value = match.group(1).strip()

    if value == "<NONE>":
        return set()

    # Do not guess at an unfamiliar output format.
    if not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", value):
        raise ValueError(
            f"Unrecognized connected-nodes format: {value}"
        )

    return set(re.findall(r"\d+", value))


def parse_lstats(output, node):
    lines = [line.strip() for line in output.splitlines()
             if line.strip()]

    if len(lines) < 2:
        raise ValueError("Missing link-status table")

    header = lines[0].split()

    if header[:2] != ["NODE", "PEER"]:
        raise ValueError("Invalid link-status header")

    if "CONNECT" not in lines[0] or "STATE" not in lines[0]:
        raise ValueError("Incomplete link-status header")

    if not re.fullmatch(r"[-\s]+", lines[1]):
        raise ValueError("Invalid link-status separator")

    connected = set()

    for line in lines[2:]:
        fields = line.split()

        if len(fields) < 2:
            raise ValueError("Malformed link-status row")

        if not fields[0].isdigit():
            raise ValueError("Invalid remote node in link table")

        if len(fields) != 6:
            raise ValueError("Incomplete link-status row")

        if fields[3] not in ("IN", "OUT"):
            raise ValueError("Invalid connection direction")

        if fields[-1] != "ESTABLISHED":
            raise ValueError("Connection is not established")

        connected.add(fields[0])

    return connected


def query_asterisk(node):
    def run(command):
        result = subprocess.run(
            ["asterisk", "-rx", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Asterisk command failed: {command}"
            )

        if result.stderr.strip():
            raise RuntimeError(
                f"Asterisk reported an error: {result.stderr}"
            )

        return result.stdout

    stats = parse_stats(run(f"rpt stats {node}"), node)
    links = parse_lstats(run(f"rpt lstats {node}"), node)

    if stats != links:
        raise RuntimeError(
            f"Asterisk reports disagree: stats={stats}, links={links}"
        )

    return stats
