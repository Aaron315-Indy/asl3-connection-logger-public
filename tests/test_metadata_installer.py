"""Regression tests for metadata synchronization installation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install.sh"
SERVICE = ROOT / "systemd/asl3-metadata-sync.service"
TIMER = ROOT / "systemd/asl3-metadata-sync.timer"


def test_installer_installs_metadata_units():
    script = INSTALLER.read_text()

    assert 'systemd/asl3-metadata-sync.service' in script
    assert 'systemd/asl3-metadata-sync.timer' in script
    assert "systemctl daemon-reload" in script
    assert "systemctl enable --now asl3-metadata-sync.timer" in script


def test_metadata_service_runs_as_asterisk():
    service = SERVICE.read_text()

    assert "Type=oneshot" in service
    assert "User=asterisk" in service
    assert "Group=asterisk" in service
    assert "asl3_connection_logger.metadata_sync" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/var/lib/asl3-connection-logger" in service


def test_metadata_timer_configuration():
    timer = TIMER.read_text()

    assert "OnUnitActiveSec=6h" in timer
    assert "Persistent=true" in timer
    assert "Unit=asl3-metadata-sync.service" in timer


def test_installer_dry_run_precedes_metadata_install():
    script = INSTALLER.read_text()

    assert script.index('if [[ "$DRY_RUN" -eq 1 ]]') < script.index(
        'echo "=== INSTALL METADATA SYNCHRONIZATION ==="'
    )
