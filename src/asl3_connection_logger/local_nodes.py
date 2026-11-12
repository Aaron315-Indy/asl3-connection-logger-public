# SPDX-License-Identifier: GPL-3.0-or-later
"""Read local node sections, never directory entries or connection history."""
import glob
import re
from pathlib import Path


def configured_nodes(config='/etc/asterisk/rpt.conf'):
    nodes = set()
    visited = set()

    def read(path):
        path = Path(path).resolve()
        if path in visited:
            return
        visited.add(path)
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return
        for line in lines:
            line = line.split(';', 1)[0].strip()
            section = re.fullmatch(r'\[([0-9]+)\](?:\(([^)]*)\))?', line)
            if section and '!' not in [flag.strip() for flag in (section[2] or '').split(',')]:
                nodes.add(section[1])
            include = re.fullmatch(r'#(?:try)?include\s+["<]?([^">]+)[">]?', line)
            if include:
                pattern = Path(include[1].strip())
                if not pattern.is_absolute():
                    pattern = path.parent / pattern
                for child in sorted(glob.glob(str(pattern))):
                    read(child)

    read(config)
    return sorted(nodes, key=lambda node: (int(node), node))
