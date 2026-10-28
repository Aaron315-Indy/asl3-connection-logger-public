#!/usr/bin/env python3
"""Validate that Apache declares an HTTPS virtual host for a hostname."""

import re
import subprocess
import sys


def has_https_vhost(output: str, hostname: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    in_https = False

    for line in output.splitlines():
        stripped = line.strip()

        # Examples:
        # *:443 example.org (/etc/apache2/sites-enabled/ssl.conf:1)
        # 10.0.0.1:443 is a NameVirtualHost
        # port 443 namevhost example.org (...)
        # port 80 namevhost example.org (...)
        if re.match(r"^\S+:443\s", stripped):
            in_https = True
            match = re.match(r"^\S+:443\s+(\S+)", stripped)
            if match and match.group(1).lower().rstrip(".") == hostname:
                return True
            continue

        match = re.match(
            r"^port\s+(\d+)\s+(?:default server|namevhost)\s+(\S+)",
            stripped,
            re.IGNORECASE,
        )
        if match:
            port, name = match.groups()
            if port == "443" and name.lower().rstrip(".") == hostname:
                return True
            continue

        if stripped.startswith("alias "):
            alias = stripped[6:].lower().rstrip(".")
            if in_https and alias == hostname:
                return True

        if re.match(r"^\S+:\d+\s", stripped):
            in_https = False

    return False


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check-apache-https-vhost.py HOSTNAME", file=sys.stderr)
        return 2

    result = subprocess.run(
        ["apache2ctl", "-S"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Cannot inspect Apache virtual hosts", file=sys.stderr)
        return 1

    if not has_https_vhost(
        result.stdout + result.stderr,
        sys.argv[1],
    ):
        print(
            f"Public mode requires an HTTPS virtual host for {sys.argv[1]}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
