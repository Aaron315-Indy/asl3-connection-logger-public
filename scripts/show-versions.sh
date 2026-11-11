#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Read-only preflight. Run before pip replaces the installed distribution.
set -euo pipefail
SOURCE_DIR="${1:?Source directory required}"
INSTALLED_DIR="${2:-/opt/asl3-connection-logger}"
PYTHON="$INSTALLED_DIR/.venv/bin/python"
echo '=== ASL3 CONNECTION LOGGER VERSIONS ==='
if [[ -x "$PYTHON" ]]; then
    (cd / && "$PYTHON" -I -c '
from importlib.metadata import PackageNotFoundError, version
try:
    from asl3_connection_logger.version import version_label
    print("Installed version: " + version_label())
except ImportError:
    try:
        print("Installed version: " + version("asl3-connection-logger"))
    except PackageNotFoundError:
        print("Installed version: not installed")
')
else
    echo 'Installed version: not installed'
fi
PYTHONPATH="$SOURCE_DIR/src" python3 -m asl3_connection_logger --version | sed 's/^ASL3 Connection Logger /Incoming version: /'
