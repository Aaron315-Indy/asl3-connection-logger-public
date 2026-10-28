"""Test Apache configuration produced by the actual renderer."""

import subprocess
from pathlib import Path

RENDERER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "render-apache-config.sh"
)


def render(mode, networks=""):
    return subprocess.run(
        [
            "bash",
            str(RENDERER),
            mode,
            "100001",
            "node.example.org",
            networks,
        ],
        capture_output=True,
        text=True,
    )


def test_private_configuration():
    result = render("private", "192.0.2.0/24 198.51.100.0/24")
    assert result.returncode == 0
    assert "Require ip 192.0.2.0/24 198.51.100.0/24" in result.stdout
    assert "SSLRequireSSL" not in result.stdout
    assert "AuthType Basic" not in result.stdout


def test_private_requires_allowlist():
    result = render("private")
    assert result.returncode != 0


def test_private_rejects_invalid_network():
    result = render("private", "not-a-network")
    assert result.returncode != 0


def test_public_configuration():
    result = render("public")
    assert result.returncode == 0
    assert "SSLRequireSSL" in result.stdout
    assert "AuthType Basic" in result.stdout
    assert "Require valid-user" in result.stdout
    assert "AuthUserFile /etc/apache2/asl3-connection-logger.htpasswd" in result.stdout


def test_invalid_mode():
    assert render("invalid").returncode != 0


def test_proxy_stays_on_localhost():
    for mode, networks in (
        ("private", "127.0.0.1/32"),
        ("public", ""),
    ):
        result = render(mode, networks)
        assert result.returncode == 0
        assert "http://127.0.0.1:8765/" in result.stdout
