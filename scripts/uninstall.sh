#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail

RPT_CONF="/etc/asterisk/rpt.conf"
WRAPPER="/usr/local/bin/asl3-connection-event"
DB_FILE="/var/lib/asl3-connection-logger/connections.db"

NODE=""
DRY_RUN=0

usage() {
    echo "Usage: $0 --node NODE [--dry-run]"
}

while (($#)); do
    case "$1" in
        --node)
            [[ $# -ge 2 ]] || { usage; exit 1; }
            NODE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

[[ "$NODE" =~ ^[0-9]+$ ]] || {
    echo "ERROR: Valid numeric --node required"
    exit 1
}

[[ $EUID -eq 0 ]] || {
    echo "ERROR: Run as root"
    exit 1
}

[[ -f "$RPT_CONF" ]] || {
    echo "ERROR: Missing $RPT_CONF"
    exit 1
}

echo "=== ASL3 CONNECTION LOGGER UNINSTALLER ==="
echo "Node: $NODE"
echo "Dry run: $DRY_RUN"

python3 - "$RPT_CONF" "$NODE" "$WRAPPER" "$DRY_RUN" <<'PYTHON'
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])
node = sys.argv[2]
wrapper = sys.argv[3]
dry_run = sys.argv[4] == "1"

original = path.read_bytes()
text = original.decode("utf-8")

header_pattern = re.compile(
    rf"^\[{re.escape(node)}\](?:\([^)]+\))?[ \t]*$",
    re.MULTILINE,
)

matches = list(header_pattern.finditer(text))

if len(matches) != 1:
    raise SystemExit(
        f"ERROR: Expected one [{node}] section; found {len(matches)}"
    )

match = matches[0]
next_section = re.search(
    r"^\[[^\]\r\n]+\][^\r\n]*$",
    text[match.end():],
    re.MULTILINE,
)

end = (
    match.end() + next_section.start()
    if next_section else len(text)
)

section = text[match.end():end]

expected = {
    "connpgm": f"{wrapper} connect",
    "discpgm": f"{wrapper} disconnect",
}

removed = []

for key, value in expected.items():
    entries = re.findall(
        rf"^[ \t]*{key}[ \t]*=[ \t]*(.*?)[ \t]*$",
        section,
        re.MULTILINE,
    )

    if len(entries) > 1:
        raise SystemExit(
            f"ERROR: Multiple {key} entries; refusing modification"
        )

    if entries and entries[0] != value:
        raise SystemExit(
            f"ERROR: {key} belongs to another program: {entries[0]}"
        )

    if entries:
        removed.append(key)
        section = re.sub(
            rf"^[ \t]*{key}[ \t]*=[ \t]*"
            rf"{re.escape(value)}[ \t]*\r?\n",
            "",
            section,
            count=1,
            flags=re.MULTILINE,
        )

print("Callbacks found:", ", ".join(removed) if removed else "none")

if not removed:
    print("No changes necessary.")
    sys.exit(0)

updated = text[:match.end()] + section + text[end:]

if dry_run:
    print("DRY RUN: Would remove:", ", ".join(removed))
    print("No files changed.")
    sys.exit(0)

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
backup = path.with_name(
    f"{path.name}.asl3-logger-uninstall.{timestamp}.bak"
)

shutil.copy2(path, backup)
print("Backup:", backup)

fd, temp_name = tempfile.mkstemp(
    prefix=".rpt.conf.asl3-logger.",
    dir=path.parent,
)

try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(updated.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())

    shutil.copymode(path, temp_name)
    shutil.copystat(path, temp_name)
    shutil.chown(
        temp_name,
        user=path.stat().st_uid,
        group=path.stat().st_gid,
    )

    os.replace(temp_name, path)
except Exception:
    if os.path.exists(temp_name):
        os.unlink(temp_name)
    raise

print("PASS: Logger callbacks removed from node", node)
PYTHON

echo
echo "=== DATABASE PRESERVED ==="
echo "$DB_FILE"

echo "=== SHARED COMPONENTS PRESERVED ==="
echo "$WRAPPER"
echo "/opt/asl3-connection-logger"

echo
echo "Asterisk was NOT restarted or reloaded."
