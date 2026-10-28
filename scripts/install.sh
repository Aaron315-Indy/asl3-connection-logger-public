#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail

INSTALL_DIR="/opt/asl3-connection-logger"
DB_DIR="/var/lib/asl3-connection-logger"
DB_FILE="$DB_DIR/connections.db"
RPT_CONF="/etc/asterisk/rpt.conf"
WRAPPER="/usr/local/bin/asl3-connection-event"

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

[[ -f "$INSTALL_DIR/scripts/asl3-event-hook" ]] || {
    echo "ERROR: Logger source missing"
    exit 1
}

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || {
    echo "ERROR: Python environment missing"
    exit 1
}

id asterisk >/dev/null 2>&1 || {
    echo "ERROR: Asterisk account missing"
    exit 1
}

echo "=== ASL3 CONNECTION LOGGER INSTALLER ==="
echo "Node: $NODE"
echo "Install directory: $INSTALL_DIR"
echo "Database: $DB_FILE"
echo "Dry run: $DRY_RUN"

# Verify the requested node section exists exactly once.
python3 - "$RPT_CONF" "$NODE" <<'PY'
import re
import sys
from pathlib import Path

config = Path(sys.argv[1]).read_text()
node = sys.argv[2]

matches = re.findall(
    rf"^\[{re.escape(node)}\](?:\([^)]+\))?\s*$",
    config,
    re.MULTILINE,
)

if len(matches) != 1:
    raise SystemExit(
        f"ERROR: Expected one node section [{node}], found {len(matches)}"
    )
PY

# Validate existing callbacks before changing anything.
python3 - "$RPT_CONF" "$NODE" "$WRAPPER" <<'PY'
import re
import sys
from pathlib import Path

path, node, wrapper = sys.argv[1:]
text = Path(path).read_text()

header = re.compile(
    rf"^\[{re.escape(node)}\](?:\([^)]+\))?\s*$",
    re.MULTILINE,
)

match = header.search(text)
if not match:
    raise SystemExit("ERROR: Node section not found")

next_section = re.search(
    r"^\[[^\]]+\]",
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

for key, value in expected.items():
    entries = re.findall(
        rf"^\s*{key}\s*=\s*(.*?)\s*$",
        section,
        re.MULTILINE,
    )

    if len(entries) > 1:
        raise SystemExit(f"ERROR: Duplicate {key} settings")

    if entries and entries[0] != value:
        raise SystemExit(
            f"ERROR: Conflicting {key}: {entries[0]}"
        )

print("PASS: Callback configuration safe")
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo
    echo "DRY RUN COMPLETE"
    echo "No files changed."
    exit 0
fi

echo "=== BACKUP ASTERISK CONFIGURATION ==="
BACKUP="${RPT_CONF}.asl3-logger.$(date +%Y%m%d-%H%M%S).bak"
cp -a "$RPT_CONF" "$BACKUP"
echo "Backup: $BACKUP"

echo "=== INSTALL CALLBACK WRAPPER ==="
install -m 755 \
    "$INSTALL_DIR/scripts/asl3-connection-event" \
    "$WRAPPER"

echo "=== INITIALIZE DATABASE ==="
install -d -o asterisk -g asterisk -m 750 "$DB_DIR"

runuser -u asterisk -- \
    "$INSTALL_DIR/.venv/bin/python" -c \
    "from asl3_connection_logger.database import initialize_database; initialize_database('$DB_FILE')"

echo "=== CONFIGURE NODE CALLBACKS ==="
python3 - "$RPT_CONF" "$NODE" "$WRAPPER" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
node = sys.argv[2]
wrapper = sys.argv[3]

text = path.read_text()

pattern = re.compile(
    rf"^(\[{re.escape(node)}\](?:\([^)]+\))?\s*)$",
    re.MULTILINE,
)

match = pattern.search(text)
if not match:
    raise SystemExit("ERROR: Node section missing")

next_section = re.search(
    r"^\[[^\]]+\]",
    text[match.end():],
    re.MULTILINE,
)

end = (
    match.end() + next_section.start()
    if next_section else len(text)
)

section = text[match.end():end]

additions = []

for key, event in (
    ("connpgm", "connect"),
    ("discpgm", "disconnect"),
):
    if not re.search(
        rf"^\s*{key}\s*=",
        section,
        re.MULTILINE,
    ):
        additions.append(f"{key} = {wrapper} {event}")

if additions:
    insertion = "\n" + "\n".join(additions)
    text = text[:match.end()] + insertion + text[match.end():]
    path.write_text(text)

print("PASS: Callback settings configured")
PY

echo
echo "=== INSTALLATION COMPLETE ==="
echo "Node: $NODE"
echo "Backup: $BACKUP"
echo "Database preserved: $DB_FILE"
echo
echo "Asterisk was NOT restarted or reloaded."
echo "Apply callback changes during a controlled Asterisk reload."
