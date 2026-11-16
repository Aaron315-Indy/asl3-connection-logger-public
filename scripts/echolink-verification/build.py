"""Build one self-contained verification artifact, without installation."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipapp

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path('/var/tmp/asl3-v025-echolink-verify.pyz')
BOOTSTRAP = '''import runpy
import signal
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile
if sys.version_info < (3, 11):
    sys.exit("FAIL: Python >=3.11 with sqlite3 is required")
def terminate(signum, frame):
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, terminate)
try:
    with tempfile.TemporaryDirectory(prefix="asl3-v025-code-", dir="/var/tmp") as temporary:
        root = Path(temporary)
        with ZipFile(sys.argv[0]) as archive:
            archive.extractall(root)
        sys.path.insert(0, str(root / "src"))
        runpy.run_path(str(root / "verify.py"), run_name="__main__")
except (Exception, KeyboardInterrupt) as exc:
    sys.exit(f"FAIL verification bootstrap: {type(exc).__name__}: {exc}")
'''

with tempfile.TemporaryDirectory(prefix='asl3-v025-build-', dir='/var/tmp') as temporary:
    stage = Path(temporary)
    # Include all package dependencies, without build artifacts or bytecode.
    shutil.copytree(ROOT / 'src/asl3_connection_logger', stage / 'src/asl3_connection_logger',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'build-info.json'))
    for name in ('verify.py', 'README.md'):
        shutil.copy2(Path(__file__).parent / name, stage / name)
    shutil.copy2(ROOT / 'LICENSE', stage / 'LICENSE')
    (stage / '__main__.py').write_text(BOOTSTRAP)
    hashes = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(stage.rglob('*')) if p.is_file()}
    (stage / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2, sort_keys=True) + '\n')
    zipapp.create_archive(stage, OUTPUT, compressed=True)
OUTPUT.chmod(0o644)
print(OUTPUT)
print('SHA256 ' + hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
