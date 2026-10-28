#!/usr/bin/env bash
set -euo pipefail

MODE=""
NODE=""
ALLOW_NETS="${ASL3_DASHBOARD_NETWORKS:-}"
HOSTNAME="$(hostname -f)"
PORT=8765
SERVICE="asl3-connection-dashboard"
CONF="/etc/apache2/conf-available/asl3-connection-logger.conf"
AUTHFILE="/etc/apache2/asl3-connection-logger.htpasswd"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while (($#)); do
    case "$1" in
        --mode) MODE="${2:?}"; shift 2 ;;
        --node) NODE="${2:?}"; shift 2 ;;
        --hostname) HOSTNAME="${2:?}"; shift 2 ;;
        --allow-networks) ALLOW_NETS="${2:?}"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

[[ "$EUID" -eq 0 ]] || {
    echo "Run as root" >&2
    exit 1
}

[[ "$MODE" == private || "$MODE" == public ]] || {
    echo "Specify --mode private or --mode public" >&2
    exit 2
}

[[ "$NODE" =~ ^[0-9]+$ ]] || {
    echo "Specify a numeric --node" >&2
    exit 2
}

[[ -f "$REPO/src/asl3_connection_logger/web.py" ]] || {
    echo "Dashboard backend missing" >&2
    exit 1
}

[[ -f "$REPO/src/asl3_connection_logger/static/index.html" ]] || {
    echo "Dashboard frontend missing" >&2
    exit 1
}

# Validate allowlisted IPv4/IPv6 networks before writing Apache config.
if [[ "$MODE" == private ]]; then
    python3 - "$ALLOW_NETS" <<'PY'
import ipaddress
import sys
networks = sys.argv[1].split()
if not networks:
    raise SystemExit("Private mode requires an IP allowlist")
for network in networks:
    ipaddress.ip_network(network, strict=False)
print("Private networks:", ", ".join(networks))
PY
fi

# Public mode requires an existing HTTPS virtual host and certificate.
if [[ "$MODE" == public ]]; then
    apache2ctl -M 2>/dev/null | grep -q 'ssl_module' || {
        echo "Public mode requires Apache mod_ssl" >&2
        exit 1
    }
    # Require the configured hostname in an HTTPS virtual host.
    # Certificate provisioning and renewal remain administrator-managed.
    python3 "$REPO/scripts/check-apache-https-vhost.py" "$HOSTNAME" || exit 1
    command -v htpasswd >/dev/null || {
        echo "Install apache2-utils first" >&2
        exit 1
    }
fi

echo "=== CREATE SERVICE USER ==="
if ! id asl3logger-web >/dev/null 2>&1; then
    useradd --system --no-create-home \
        --shell /usr/sbin/nologin \
        --gid asterisk asl3logger-web
fi

echo "=== INSTALL SYSTEMD SERVICE ==="
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=ASL3 Connection Logger Web Dashboard
After=network.target

[Service]
Type=simple
User=asl3logger-web
Group=asterisk
WorkingDirectory=$REPO
ExecStart=$REPO/.venv/bin/python -m asl3_connection_logger.web --host 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

echo "=== PREPARE APACHE ==="
a2enmod proxy proxy_http headers

if [[ "$MODE" == public ]]; then
    echo "=== APACHE AUTHENTICATION ==="
    if [[ ! -f "$AUTHFILE" ]]; then
        echo "Create dashboard administrator password:"
        htpasswd -B -c "$AUTHFILE" admin
    else
        echo "Using existing password file: $AUTHFILE"
    fi
    chown root:www-data "$AUTHFILE"
    chmod 640 "$AUTHFILE"
fi

# Backup existing config so Apache can be restored if validation fails.
BACKUP="$(mktemp)"
HAD_CONF=0
if [[ -f "$CONF" ]]; then
    cp -p "$CONF" "$BACKUP"
    HAD_CONF=1
fi

restore_apache() {
    echo "Restoring previous Apache configuration..." >&2
    if [[ "$HAD_CONF" == 1 ]]; then
        cp -p "$BACKUP" "$CONF"
    else
        a2disconf asl3-connection-logger >/dev/null 2>&1 || true
        rm -f "$CONF"
    fi
    if apache2ctl configtest >&2; then
        systemctl reload apache2 >&2 || true
    else
        echo "WARNING: Restored Apache configuration failed validation" >&2
    fi
}
trap restore_apache ERR

echo "=== WRITE APACHE CONFIGURATION ==="
"$REPO/scripts/render-apache-config.sh" \
    "$MODE" "$NODE" "$HOSTNAME" "$ALLOW_NETS" > "$CONF"

a2enconf asl3-connection-logger

echo "=== VALIDATE APACHE ==="
apache2ctl configtest

echo "=== START DASHBOARD ==="
systemctl daemon-reload
systemctl enable --now "$SERVICE"
systemctl restart "$SERVICE"

echo "=== WAIT FOR DASHBOARD API ==="
READY=0

for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 2 \
        "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [[ "$READY" -ne 1 ]]; then
    echo "Dashboard API did not become ready" >&2
    journalctl -u "$SERVICE" -n 30 --no-pager >&2
    exit 1
fi

echo "Dashboard API ready"

echo "=== RELOAD APACHE ==="
systemctl reload apache2

echo "=== VERIFY DASHBOARD ==="
systemctl is-active "$SERVICE"
systemctl is-active apache2

echo
echo "=== LISTENING SOCKET ==="
ss -ltnp "( sport = :$PORT )"

echo
# Installation succeeded; rollback is no longer necessary.
trap - ERR
rm -f "$BACKUP"

echo "=== INSTALLATION COMPLETE ==="
echo "Mode: $MODE"
echo "Dashboard: http://$HOSTNAME/logger/"
echo "API: http://127.0.0.1:$PORT/api/dashboard"
echo "Note: access depends on Apache authorization and HTTPS configuration."
