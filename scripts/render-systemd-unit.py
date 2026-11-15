#!/usr/bin/env python3
"""Render installer units with the same path rules as the upgrader."""
import argparse
from pathlib import Path
import sys

from upgrade import DEFAULT_DB, render_unit, validate_install_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('install', type=Path)
    parser.add_argument('--check-install-path', action='store_true')
    args = parser.parse_args()
    try:
        validate_install_path(args.install)
        if not args.check_install_path:
            sys.stdout.buffer.write(render_unit(sys.stdin.read(), args.install, DEFAULT_DB))
    except ValueError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
