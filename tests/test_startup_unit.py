from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def test_startup_unit_template():
    template = (
        PROJECT / "systemd/asl3-connection-recovery.service.in"
    ).read_text()

    assert "After=asterisk.service" in template
    assert "PartOf=asterisk.service" in template
    assert "WantedBy=asterisk.service" in template
    assert "--node @NODE@ --apply" in template
    assert "User=asterisk" in template


def test_startup_installer_does_not_restart_asterisk():
    installer = (
        PROJECT / "scripts/install-startup-recovery.sh"
    ).read_text()

    assert "systemctl enable asl3-connection-recovery.service" in installer
    assert "systemctl restart asterisk" not in installer
    assert "systemctl reload asterisk" not in installer
