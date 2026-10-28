"""Apache HTTPS virtual-host inventory validation."""

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check-apache-https-vhost.py"
)

spec = importlib.util.spec_from_file_location("apache_vhost_check", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

has_https_vhost = module.has_https_vhost


def test_simple_https_vhost():
    output = "*:443 example.org (/etc/apache2/sites-enabled/ssl.conf:1)"
    assert has_https_vhost(output, "example.org")


def test_name_based_https_vhost():
    output = """
*:443 is a NameVirtualHost
         default server first.org (/etc/apache2/sites-enabled/a.conf:1)
         port 443 namevhost first.org (/etc/apache2/sites-enabled/a.conf:1)
         port 443 namevhost second.org (/etc/apache2/sites-enabled/b.conf:1)
"""
    assert has_https_vhost(output, "second.org")


def test_http_only_rejected():
    output = "*:80 example.org (/etc/apache2/sites-enabled/default.conf:1)"
    assert not has_https_vhost(output, "example.org")


def test_wrong_hostname_rejected():
    output = "*:443 example.org (/etc/apache2/sites-enabled/ssl.conf:1)"
    assert not has_https_vhost(output, "other.org")


def test_https_alias():
    output = """
*:443 is a NameVirtualHost
         port 443 namevhost example.org (/etc/apache2/sites-enabled/ssl.conf:1)
                 alias dashboard.example.org
"""
    assert has_https_vhost(output, "dashboard.example.org")
