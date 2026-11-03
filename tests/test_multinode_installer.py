"""Regression checks for multi-node installation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = (ROOT / "scripts/install.sh").read_text()
SETUP = (ROOT / "scripts/setup.sh").read_text()


def test_collector_supports_multiple_nodes():
    assert '"--nodes"' in COLLECTOR
    assert 'NODES+=("$1")' in COLLECTOR
    assert '"$0" --node "$node" --dry-run' in COLLECTOR
    assert '"$0" --node "$node"' in COLLECTOR


def test_collector_validates_before_installing():
    validation = COLLECTOR.index('for node in "${NODES[@]}"; do')
    installation = COLLECTOR.index(
        'for node in "${NODES[@]}"; do', validation + 1
    )
    assert validation < installation


def test_setup_offers_all_nodes():
    assert 'echo "  0) All nodes"' in SETUP
    assert 'SELECTED_NODES=("${NODES[@]}")' in SETUP


def test_setup_installs_collector_for_selected_nodes():
    assert (
        '"$REPO/scripts/install.sh" --nodes '
        '"${SELECTED_NODES[@]}" --dry-run'
    ) in SETUP

    assert (
        '"$REPO/scripts/install.sh" --nodes '
        '"${SELECTED_NODES[@]}"'
    ) in SETUP


def test_dashboard_installed_once():
    assert SETUP.count(
        '"$REPO/scripts/install-dashboard.sh" \\'
    ) == 1


def test_no_automatic_asterisk_restart():
    assert "systemctl restart asterisk" not in COLLECTOR
    assert "systemctl restart asterisk" not in SETUP
