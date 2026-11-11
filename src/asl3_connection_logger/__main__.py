# SPDX-License-Identifier: GPL-3.0-or-later
"""Application identity CLI; works without a database or Git installation."""
import argparse
import json
from .version import version_info, version_label


def main():
    parser = argparse.ArgumentParser(description="ASL3 Connection Logger")
    parser.add_argument("--version", action="version",
                        version="ASL3 Connection Logger " + version_label())
    parser.add_argument("--json", action="store_true", help="Print public build identity as JSON")
    args = parser.parse_args()
    if args.json:
        print(json.dumps(version_info()))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
