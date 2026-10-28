# SPDX-License-Identifier: GPL-3.0-or-later
"""Identify the current Asterisk process runtime."""

from pathlib import Path
import subprocess


def get_runtime_id():
    """Return a stable identifier for the running Asterisk instance."""

    boot_id = Path(
        "/proc/sys/kernel/random/boot_id"
    ).read_text().strip()

    result = subprocess.run(
        ["systemctl", "show", "asterisk",
         "-p", "MainPID", "--value"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )

    pid = int(result.stdout.strip())

    if pid <= 0:
        raise RuntimeError("Asterisk is not running")

    stat = Path(f"/proc/{pid}/stat").read_text()

    # The command name is enclosed in parentheses and may contain spaces.
    fields = stat[stat.rfind(")") + 2:].split()

    # Linux /proc/PID/stat field 22 is process start time.
    start_ticks = fields[19]

    return f"{boot_id}:{start_ticks}"


def get_stable_runtime_id():
    """Reject a runtime that changes during inspection."""
    first = get_runtime_id()
    second = get_runtime_id()

    if first != second:
        raise RuntimeError(
            "Asterisk restarted during runtime identification"
        )

    return first
