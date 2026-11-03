from pathlib import Path
import subprocess

SETUP = Path(__file__).resolve().parents[1] / "scripts/setup.sh"


def test_node_menu_uses_real_newlines():
    source = SETUP.read_text()

    assert r"printf '  %d) %s\n'" in source
    assert r"printf '  %d) %s\\n'" not in source

    result = subprocess.run(
        ["bash", "-c", "printf '  %d) %s\\n' 1 651861"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == "  1) 651861\n"
