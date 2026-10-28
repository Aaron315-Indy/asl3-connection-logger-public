"""Static safety checks for the dashboard installer."""

from pathlib import Path

INSTALLER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "install-dashboard.sh"
)


def installer():
    return INSTALLER.read_text()


def renderer():
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "render-apache-config.sh"
    ).read_text()


def test_installer_exists():
    assert INSTALLER.is_file()


def test_private_networks_are_explicit():
    source = installer()
    assert 'ALLOW_NETS="${ASL3_DASHBOARD_NETWORKS:-}"' in source
    assert "Private mode requires an IP allowlist" in source
    assert "ipaddress.ip_network" in source


def test_dashboard_binds_to_localhost():
    source = installer()
    assert "--host 127.0.0.1" in source
    assert 'render-apache-config.sh' in source
    assert "ProxyPass" in renderer()


def test_public_authentication_required():
    source = renderer()
    assert "AuthType Basic" in source
    assert "AuthUserFile" in source
    assert "Require valid-user" in source
    assert "SSLRequireSSL" in source


def test_no_certificate_provisioning():
    source = installer()
    assert "certbot" not in source.lower()
    assert "acme.sh" not in source.lower()


def test_repository_path_is_discovered():
    source = installer()
    assert 'dirname "${BASH_SOURCE[0]}"' in source


def test_public_mode_checks_requested_hostname():
    source = installer()
    assert 'check-apache-https-vhost.py' in source
    validator = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check-apache-https-vhost.py"
    ).read_text()
    assert "Public mode requires an HTTPS virtual host for" in validator


def test_public_mode_requires_https():
    source = renderer()
    assert "SSLRequireSSL" in source
    assert "AuthType Basic" in source
    assert "Require valid-user" in source


def test_rollback_remains_active_through_apache_reload():
    """Keep rollback enabled until the installation succeeds."""
    source = installer()

    rollback = source.index("trap restore_apache ERR")
    validation = source.index("apache2ctl configtest", rollback)
    startup = source.index('systemctl restart "$SERVICE"', validation)
    reload = source.index("systemctl reload apache2", startup)
    cleanup = source.index("trap - ERR", reload)

    assert rollback < validation < startup < reload < cleanup


def test_backup_cleanup_occurs_after_reload():
    """Do not delete the backup before Apache reloads."""
    source = installer()

    reload = source.index("systemctl reload apache2")
    cleanup = source.index('rm -f "$BACKUP"', reload)

    assert cleanup > reload


def test_rollback_restores_previous_configuration():
    """Verify the rollback handler retains restoration commands."""
    source = installer()

    assert 'cp -p "$BACKUP" "$CONF"' in source
    assert "trap restore_apache ERR" in source
    assert "a2disconf asl3-connection-logger" in source


def test_rollback_reloads_restored_apache_configuration():
    """Rollback must restore both the file and running Apache config."""
    source = installer()

    start = source.index("restore_apache() {")
    end = source.index("trap restore_apache ERR", start)
    rollback = source[start:end]

    assert 'cp -p "$BACKUP" "$CONF"' in rollback
    assert "apache2ctl configtest" in rollback
    assert "systemctl reload apache2" in rollback

    assert (
        rollback.index('cp -p "$BACKUP" "$CONF"')
        < rollback.index("apache2ctl configtest")
        < rollback.index("systemctl reload apache2")
    )
