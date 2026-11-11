# SPDX-License-Identifier: GPL-3.0-or-later
"""Public build identity; never reports paths, users, remotes or environment."""
import json
import re
import subprocess
from pathlib import Path

from ._version import VERSION


def version_info():
    package = Path(__file__).resolve().parent
    stamp = package / "build-info.json"
    if stamp.is_file():
        data = json.loads(stamp.read_text())
        commit = data.get("commit")
        if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid build commit")
        return {
            "version": VERSION,
            "commit": commit,
            "build": {
                "type": "development" if "-" in VERSION else "release",
                "built_at": data.get("built_at"),
                "dirty": bool(data.get("dirty", False)),
            },
        }

    root = package.parent.parent
    commit = None
    dirty = False
    # Only inspect our own checkout, never an enclosing or unrelated repository.
    if (root / ".git").exists():
        try:
            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(root), *args],
                    stderr=subprocess.DEVNULL, timeout=2, text=True,
                ).strip()
            commit = git("rev-parse", "HEAD")
            dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
        except (OSError, subprocess.SubprocessError):
            commit = None
    return {
        "version": VERSION,
        "commit": commit,
        "build": {"type": "development" if "-" in VERSION else "release",
                  "built_at": None, "dirty": dirty},
    }


def version_label(info=None):
    info = version_info() if info is None else info
    label = info["version"]
    if info["commit"]:
        label += " (" + info["commit"][:12] + (" dirty" if info["build"]["dirty"] else "") + ")"
    return label
