import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from asl3_connection_logger._version import VERSION
from asl3_connection_logger.version import version_info, version_label
from asl3_connection_logger.web import DashboardHandler

ROOT = Path(__file__).resolve().parents[1]


def test_semver_and_authoritative_packaging():
    assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", VERSION)
    config = (ROOT / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in config
    assert 'asl3_connection_logger._version.VERSION' in config


def test_cli():
    result = subprocess.run([sys.executable, "-m", "asl3_connection_logger", "--version"],
                            capture_output=True, text=True, check=True,
                            env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert "ASL3 Connection Logger " + VERSION in result.stdout
    assert not result.stderr
    result = subprocess.run([sys.executable, "-m", "asl3_connection_logger.web", "--version"],
                            capture_output=True, text=True, check=True,
                            env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert VERSION in result.stdout


def test_identity_http_without_database(tmp_path):
    handler = type("TestHandler", (DashboardHandler,), {"database": str(tmp_path / "absent.db")})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/version") as response:
            info = json.load(response)
            assert response.headers["Cache-Control"] == "no-store"
        assert set(info) == {"version", "commit", "build"}
        assert set(info["build"]) == {"type", "built_at", "dirty"}
        assert info["version"] == VERSION
        assert info["build"]["type"] == ("development" if "-" in VERSION else "release")
        for page in ("/", "/?node=100001", "/?status=completed"):
            with urlopen(base + page) as response:
                html = response.read().decode()
            assert f"<footer>ASL3 Connection Logger · {version_label(info)} · GPLv3</footer>" in html
            assert "{{APPLICATION_VERSION}}" not in html
        assert not (tmp_path / "absent.db").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_without_git_and_frozen_stamp(tmp_path, monkeypatch):
    import asl3_connection_logger.version as module
    package = tmp_path / "src/asl3_connection_logger"
    package.mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(package / "version.py"))
    assert module.version_info()["commit"] is None
    commit = "a" * 40
    (package / "build-info.json").write_text(json.dumps({
        "commit": commit, "built_at": "2026-11-11T00:00:00+00:00", "dirty": False,
        "hostname": "must-not-be-exposed"}))
    info = module.version_info()
    assert info["commit"] == commit
    assert "hostname" not in json.dumps(info)
    assert info["build"]["built_at"] == "2026-11-11T00:00:00+00:00"


def test_missing_git_executable(monkeypatch):
    import asl3_connection_logger.version as module
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(module.subprocess, "check_output", missing)
    assert module.version_info()["commit"] is None
    assert module.version_info()["version"] == VERSION


def test_preflight_before_pip_and_mutations():
    setup = (ROOT / "scripts/setup.sh").read_text()
    assert setup.index("/scripts/show-versions.sh") < setup.index("Proceed?") < setup.index("-m pip install")
    for name, mutation in [("install.sh", "cp -a"), ("install-dashboard.sh", "useradd")]:
        text = (ROOT / "scripts" / name).read_text()
        assert text.index("/scripts/show-versions.sh") < text.index(mutation)


def test_preflight_staged_source(tmp_path):
    env = dict(os.environ)
    result = subprocess.run(["bash", str(ROOT / "scripts/show-versions.sh"), str(ROOT), str(tmp_path)],
                            env=env, text=True, capture_output=True, check=True)
    assert "Installed version: not installed" in result.stdout
    assert "Incoming version: " + VERSION in result.stdout


def test_wheel_sdist_and_release_archive(tmp_path):
    import shutil
    import tarfile
    import zipfile
    source = tmp_path / "source"
    source.mkdir()
    for name in ("pyproject.toml", "setup.py", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(ROOT / "src/asl3_connection_logger", source / "src/asl3_connection_logger",
                    ignore=shutil.ignore_patterns("__pycache__", "build-info.json"))
    (source / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/build-release.py", source / "scripts/build-release.py")

    def run(*command):
        return subprocess.check_output(command, cwd=source, stderr=subprocess.STDOUT, text=True)
    run("git", "init", "-q")
    run("git", "add", ".")
    run("git", "-c", "user.name=Version Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "fixture")
    commit = run("git", "rev-parse", "HEAD").strip()
    archive = tmp_path / "release.tar.gz"
    run(sys.executable, "scripts/build-release.py", str(archive))
    extracted = tmp_path / "archive"
    with tarfile.open(archive) as tar:
        tar.extractall(extracted, filter="data")
    assert not (extracted / ".git").exists()
    env = {**os.environ, "PYTHONPATH": str(extracted / "src"), "PATH": "/nonexistent"}
    info = json.loads(subprocess.check_output(
        [sys.executable, "-m", "asl3_connection_logger", "--json"], cwd=tmp_path, env=env))
    assert info["commit"] == commit
    assert info["version"] == VERSION
    assert info["build"]["built_at"]
    assert info["build"]["dirty"] is False
    # Build from the Git-free release source to verify stamp propagation.
    subprocess.check_output([sys.executable, "setup.py", "sdist", "bdist_wheel"],
                            cwd=extracted, stderr=subprocess.STDOUT)
    wheel = next((extracted / "dist").glob("*.whl"))
    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as z:
        z.extractall(installed)
    env["PYTHONPATH"] = str(installed)
    installed_info = json.loads(subprocess.check_output(
        [sys.executable, "-m", "asl3_connection_logger", "--json"], cwd=tmp_path, env=env))
    assert installed_info == info
    with tarfile.open(next((extracted / "dist").glob("*.tar.gz"))) as tar:
        stamp = next(member for member in tar if member.name.endswith("/build-info.json"))
        assert json.load(tar.extractfile(stamp))["commit"] == commit
