#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail

REPO="/opt/asl3-connection-logger"
RPT_CONF="/etc/asterisk/rpt.conf"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" && $# -eq 1 ]]; then
    DRY_RUN=1
elif (($#)); then
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
fi

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || die "Run as root."
[[ -t 0 ]] || die "Interactive terminal required."
[[ -f "$RPT_CONF" ]] || die "AllStarLink configuration missing."
[[ -f "$REPO/scripts/install.sh" ]] || die "Collector installer missing."
[[ -f "$REPO/scripts/install-dashboard.sh" ]] || die "Dashboard installer missing."

echo
echo "========================================"
echo "     ASL3 CONNECTION LOGGER SETUP"
echo "========================================"
echo

mapfile -t NODES < <(
    python3 - "$RPT_CONF" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()

nodes = re.findall(
    r'^\[([0-9]+)\](?:\([^)]+\))?\s*$',
    text,
    re.MULTILINE
)

for node in dict.fromkeys(nodes):
    print(node)
PY
)

((${#NODES[@]})) || die "No AllStarLink nodes detected."

if ((${#NODES[@]} == 1)); then
    NODE="${NODES[0]}"
    echo "Detected AllStarLink node: $NODE"
else
    echo "Available AllStarLink nodes:"
    for i in "${!NODES[@]}"; do
        printf '  %d) %s\n' "$((i+1))" "${NODES[$i]}"
    done

    while true; do
        read -r -p "Select node [1-${#NODES[@]}]: " CHOICE
        if [[ "$CHOICE" =~ ^[1-9][0-9]*$ ]] &&
           ((CHOICE <= ${#NODES[@]})); then
            NODE="${NODES[$((CHOICE-1))]}"
            break
        fi
        echo "Invalid selection."
    done
fi

echo
echo "This installer will:"
echo "  - Install the connection logger"
echo "  - Configure connection/disconnection callbacks"
echo "  - Preserve existing connection history"
echo "  - Install the read-only reporting dashboard"
echo "  - Configure Apache at /logger/"
echo
echo "Dashboard access will not require a password."
echo "Apache will not restrict dashboard access by client IP."
echo "Use only where web access is already appropriately restricted."
echo
echo "Asterisk will NOT be restarted automatically."
echo

if ((DRY_RUN)); then
    echo "Mode: DRY RUN"
fi

read -r -p "Proceed? [y/N]: " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

if ((DRY_RUN)); then
    echo
    echo "DRY RUN COMPLETE: No changes made."
    exit 0
fi

echo
echo "=== INSTALLING REQUIREMENTS ==="

apt-get update
apt-get install -y \
    python3 python3-venv python3-pip \
    apache2 apache2-utils curl

echo
echo "=== PYTHON ENVIRONMENT ==="

if [[ ! -x "$REPO/.venv/bin/python" ]]; then
    python3 -m venv "$REPO/.venv"
fi

"$REPO/.venv/bin/python" -m pip install "$REPO"

echo
echo "=== VALIDATING COLLECTOR ==="

"$REPO/scripts/install.sh" --node "$NODE" --dry-run

echo
echo "=== INSTALLING COLLECTOR ==="

"$REPO/scripts/install.sh" --node "$NODE"

echo
echo "=== INSTALLING DASHBOARD ==="

"$REPO/scripts/install-dashboard.sh" \
    --node "$NODE" \
    --mode private \
    --allow-networks "0.0.0.0/0 ::/0"

echo
echo "========================================"
echo "       INSTALLATION COMPLETE"
echo "========================================"
echo
echo "AllStarLink node: $NODE"
echo "Database: /var/lib/asl3-connection-logger/connections.db"

SERVER_IP="$(hostname -I | awk '{print $1}')"
echo "Dashboard: http://${SERVER_IP:-YOUR-NODE-IP}/logger/"

echo
echo "IMPORTANT: Apply Asterisk callback changes"
echo "during a controlled Asterisk reload."
echo
