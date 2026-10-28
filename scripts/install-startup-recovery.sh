#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

NODE="${1:-}"
PROJECT="/opt/asl3-connection-logger"
TEMPLATE="$PROJECT/systemd/asl3-connection-recovery.service.in"
UNIT="/etc/systemd/system/asl3-connection-recovery.service"

if [[ ! "$NODE" =~ ^[0-9]+$ ]]; then
    echo "Usage: $0 NODE" >&2
    exit 1
fi

if (( EUID != 0 )); then
    echo "ERROR: Run as root" >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: Missing service template" >&2
    exit 1
fi

if [[ ! -x "$PROJECT/.venv/bin/python" ]]; then
    echo "ERROR: Missing Python environment" >&2
    exit 1
fi

if [[ ! -f "$PROJECT/scripts/asl3-startup-recover" ]]; then
    echo "ERROR: Missing recovery program" >&2
    exit 1
fi

if ! id asterisk >/dev/null 2>&1; then
    echo "ERROR: Missing asterisk account" >&2
    exit 1
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

sed "s/@NODE@/$NODE/g" "$TEMPLATE" > "$TMP"

systemd-analyze verify "$TMP" 2>&1 || {
    echo "ERROR: systemd validation failed" >&2
    exit 1
}

install -m 0644 "$TMP" "$UNIT"
systemctl daemon-reload
systemctl enable asl3-connection-recovery.service

echo "Installed and enabled recovery for node $NODE"
echo "Asterisk was NOT restarted."
echo "Recovery was NOT executed."
