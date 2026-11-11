# SPDX-License-Identifier: GPL-3.0-or-later
"""Freeze public provenance into wheels, including wheels built from an sdist."""
import json
import sys
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

sys.path.insert(0, str(Path(__file__).parent / "src"))
from asl3_connection_logger.version import version_info
from datetime import datetime, timezone


def stamp(destination):
    info = version_info()
    data = {"commit": info["commit"], "dirty": info["build"]["dirty"],
            "built_at": info["build"]["built_at"] or datetime.now(timezone.utc).isoformat()}
    Path(destination).write_text(json.dumps(data) + "\n")


class BuildPy(build_py):
    def run(self):
        super().run()
        stamp(Path(self.build_lib) / "asl3_connection_logger/build-info.json")


class Sdist(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        stamp(Path(base_dir) / "src/asl3_connection_logger/build-info.json")


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist})
