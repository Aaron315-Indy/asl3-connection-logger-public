#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a local source archive from committed HEAD, with frozen provenance."""
import argparse
import io
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
archive = subprocess.check_output(["git", "-C", str(root), "archive", "--format=tar", commit])
# HEAD only: uncommitted files are intentionally excluded.
with tarfile.open(fileobj=io.BytesIO(archive)) as source, tarfile.open(args.output, "w:gz") as target:
    for member in source:
        if member.name != "src/asl3_connection_logger/build-info.json":
            target.addfile(member, source.extractfile(member) if member.isfile() else None)
    data = json.dumps({"commit": commit, "dirty": False,
                       "built_at": datetime.now(timezone.utc).isoformat()}).encode()
    member = tarfile.TarInfo("src/asl3_connection_logger/build-info.json")
    member.size = len(data)
    member.mode = 0o644
    target.addfile(member, io.BytesIO(data))
print(f"Created {args.output.name} from {commit}")
