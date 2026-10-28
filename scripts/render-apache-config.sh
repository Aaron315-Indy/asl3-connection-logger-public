#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?Specify private or public}"
NODE="${2:?Specify node number}"
HOSTNAME="${3:?Specify hostname}"
ALLOW_NETS="${4:-}"
PORT=8765
AUTHFILE="/etc/apache2/asl3-connection-logger.htpasswd"

[[ "$MODE" == private || "$MODE" == public ]] || exit 2
[[ "$NODE" =~ ^[0-9]+$ ]] || exit 2

if [[ "$MODE" == private ]]; then
    python3 - "$ALLOW_NETS" <<'PY' >&2
import ipaddress
import sys

networks = sys.argv[1].split()
if not networks:
    raise SystemExit("Private mode requires an IP allowlist")

for network in networks:
    ipaddress.ip_network(network, strict=False)
PY
fi

cat <<EOF2
# ASL3 Connection Logger
# Node: $NODE
# Mode: $MODE
# Hostname: $HOSTNAME

ProxyPass        /logger/ http://127.0.0.1:$PORT/
ProxyPassReverse /logger/ http://127.0.0.1:$PORT/

<Location "/logger/">
EOF2

if [[ "$MODE" == private ]]; then
    echo "    Require ip $ALLOW_NETS"
else
    cat <<EOF2
    SSLRequireSSL
    AuthType Basic
    AuthName "ASL3 Connection Logger"
    AuthUserFile $AUTHFILE
    Require valid-user
EOF2
fi

echo '</Location>'
