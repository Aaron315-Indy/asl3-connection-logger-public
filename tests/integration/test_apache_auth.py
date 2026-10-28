"""Apache configuration and authorization integration tests."""

import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

APACHE = shutil.which("apache2")
HTPASSWD = shutil.which("htpasswd")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def apache_server():
    if not APACHE:
        pytest.skip("Apache not installed")

    instances = []

    def start(location_rules, full_config=False):
        directory = Path(tempfile.mkdtemp(prefix="asl3-apache-test-"))
        directory.chmod(0o755)
        port = free_port()
        pidfile = directory / "apache.pid"
        logfile = directory / "error.log"
        config = directory / "httpd.conf"

        # Serve a real resource so successful authorization returns 200.
        page = directory / "logger"
        page.mkdir()
        (page / "index.html").write_text("ASL3 test page")

        modules = [
            ("mpm_event", "/usr/lib/apache2/modules/mod_mpm_event.so"),
            ("authz_core", "/usr/lib/apache2/modules/mod_authz_core.so"),
            ("authz_host", "/usr/lib/apache2/modules/mod_authz_host.so"),
            ("authz_user", "/usr/lib/apache2/modules/mod_authz_user.so"),
            ("auth_basic", "/usr/lib/apache2/modules/mod_auth_basic.so"),
            ("authn_core", "/usr/lib/apache2/modules/mod_authn_core.so"),
            ("authn_file", "/usr/lib/apache2/modules/mod_authn_file.so"),
            ("unixd", "/usr/lib/apache2/modules/mod_unixd.so"),
            ("ssl", "/usr/lib/apache2/modules/mod_ssl.so"),
        ]

        load = "\n".join(
            f"LoadModule {name}_module {path}"
            for name, path in modules
            if Path(path).exists()
        )

        if full_config:
            location_block = location_rules
        else:
            location_block = (
                '<Location "/logger/">\n'
                + location_rules
                + '\n</Location>'
            )

        config.write_text(f"""
ServerRoot "{directory}"
ServerName localhost
Listen 127.0.0.1:{port}
PidFile "{pidfile}"
ErrorLog "{logfile}"
LogLevel warn
User www-data
Group www-data
{load}
DocumentRoot "{directory}"
<Directory "{directory}">
    Require all granted
</Directory>
{location_block}
""")

        result = subprocess.run(
            [APACHE, "-f", str(config), "-t"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        process = subprocess.Popen(
            [APACHE, "-f", str(config), "-DFOREGROUND"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        instances.append((process, directory))

        for _ in range(50):
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                with socket.create_connection(("127.0.0.1", port), 0.1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("Apache test instance did not start")

        return f"http://127.0.0.1:{port}/logger/index.html"

    yield start

    for process, directory in instances:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        shutil.rmtree(directory, ignore_errors=True)


def status(url):
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_private_allows_localhost(apache_server):
    url = apache_server("Require ip 127.0.0.1/32")
    assert status(url) == 200


def test_private_rejects_other_network(apache_server):
    url = apache_server("Require ip 192.0.2.0/24")
    assert status(url) == 403


def test_public_requires_authentication(apache_server):
    if not HTPASSWD:
        pytest.skip("htpasswd unavailable")

    with tempfile.TemporaryDirectory() as directory:
        password_file = Path(directory) / "users"
        subprocess.run(
            [HTPASSWD, "-bcB", str(password_file), "testuser", "testpass"],
            check=True,
            capture_output=True,
        )

        url = apache_server(f"""
AuthType Basic
AuthName "ASL3 Test"
AuthUserFile "{password_file}"
Require valid-user
""")
        assert status(url) == 401


def test_public_rejects_plaintext(apache_server):
    # SSLRequireSSL belongs to mod_ssl, which is optional on
    # systems that only deploy the private dashboard.
    ssl_module = Path("/usr/lib/apache2/modules/mod_ssl.so")
    if not ssl_module.exists():
        pytest.skip("mod_ssl is not installed")

    url = apache_server("""
SSLRequireSSL
AuthType Basic
AuthName "ASL3 Test"
Require valid-user
""")
    assert status(url) == 403


def test_rendered_private_configuration(apache_server):
    """Run the real renderer and validate its Apache configuration."""
    renderer = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "render-apache-config.sh"
    )

    result = subprocess.run(
        [
            "bash",
            str(renderer),
            "private",
            "100001",
            "localhost",
            "127.0.0.1/32",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # The renderer's ProxyPass directives require proxy modules.
    # Remove only the proxy directives for this authorization test;
    # retain the actual generated Location authorization block.
    lines = [
        line for line in result.stdout.splitlines()
        if not line.startswith(("ProxyPass ", "ProxyPassReverse "))
    ]

    url = apache_server("\n".join(lines), full_config=True)
    assert status(url) == 200


def test_rendered_private_denies_other_network(apache_server):
    renderer = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "render-apache-config.sh"
    )

    result = subprocess.run(
        [
            "bash",
            str(renderer),
            "private",
            "100001",
            "localhost",
            "192.0.2.0/24",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = [
        line for line in result.stdout.splitlines()
        if not line.startswith(("ProxyPass ", "ProxyPassReverse "))
    ]

    url = apache_server("\n".join(lines), full_config=True)
    assert status(url) == 403


def test_rendered_public_configuration(apache_server):
    """Verify the real public configuration enforces HTTPS and auth."""
    import re

    renderer = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "render-apache-config.sh"
    )

    result = subprocess.run(
        [
            "bash",
            str(renderer),
            "public",
            "100001",
            "localhost",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify required directives exist in generated output.
    assert "SSLRequireSSL" in result.stdout
    assert "AuthType Basic" in result.stdout
    assert "Require valid-user" in result.stdout

    # Use a disposable password file, never the production file.
    with tempfile.TemporaryDirectory() as directory:
        password_file = Path(directory) / "users"

        subprocess.run(
            [
                HTPASSWD,
                "-bcB",
                str(password_file),
                "testuser",
                "testpass",
            ],
            check=True,
            capture_output=True,
        )

        # Remove proxy directives; retain generated security rules.
        config = "\n".join(
            line
            for line in result.stdout.splitlines()
            if not line.startswith(("ProxyPass ", "ProxyPassReverse "))
        )

        config = config.replace(
            "/etc/apache2/asl3-connection-logger.htpasswd",
            str(password_file),
        )

        url = apache_server(config, full_config=True)

        # Plain HTTP must be forbidden regardless of credentials.
        assert status(url) == 403


def test_rendered_public_https_authentication():
    """Test actual rendered public rules over isolated HTTPS."""
    import base64
    import ssl
    import urllib.error
    import urllib.request

    if not shutil.which("openssl") or not HTPASSWD:
        pytest.skip("OpenSSL or htpasswd unavailable")

    module_dir = Path("/usr/lib/apache2/modules")
    required = [
        "mod_ssl.so",
        "mod_socache_shmcb.so",
        "mod_authz_user.so",
    ]
    if any(not (module_dir / name).is_file() for name in required):
        pytest.skip("Required Apache TLS/auth module unavailable")

    renderer = Path(__file__).resolve().parents[2] / "scripts/render-apache-config.sh"

    with tempfile.TemporaryDirectory(prefix="asl3-https-test-") as temp:
        root = Path(temp)
        root.chmod(0o755)
        (root / "logger").mkdir()
        (root / "logger" / "index.html").write_text("AUTHORIZED")

        cert = root / "cert.pem"
        key = root / "key.pem"
        users = root / "users"
        config = root / "httpd.conf"
        port = free_port()

        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-nodes", "-days", "1",
            "-keyout", str(key), "-out", str(cert),
            "-subj", "/CN=localhost",
        ], check=True, capture_output=True)

        subprocess.run([
            HTPASSWD, "-bcB", str(users), "testuser", "testpass"
        ], check=True, capture_output=True)

        rendered = subprocess.run([
            "bash", str(renderer), "public", "100001", "localhost"
        ], check=True, capture_output=True, text=True).stdout

        # Test the generated authorization rules while serving a local
        # fixture instead of proxying to the production dashboard.
        rendered = "\n".join(
            line for line in rendered.splitlines()
            if not line.startswith(("ProxyPass ", "ProxyPassReverse "))
        ).replace(
            "/etc/apache2/asl3-connection-logger.htpasswd",
            str(users),
        )

        modules = [
            "mpm_event", "authz_core", "authz_host", "authz_user",
            "auth_basic", "authn_core", "authn_file", "socache_shmcb", "ssl",
        ]
        loads = "\n".join(
            f"LoadModule {name}_module {module_dir / ('mod_' + name + '.so')}"
            for name in modules
        )

        config.write_text(f"""
ServerRoot "{root}"
ServerName localhost
Listen 127.0.0.1:{port}
PidFile "{root / 'apache.pid'}"
ErrorLog "{root / 'error.log'}"
User www-data
Group www-data
{loads}
SSLSessionCache "shmcb:{root / 'sslcache'}(512000)"
<VirtualHost 127.0.0.1:{port}>
    ServerName localhost
    SSLEngine on
    SSLCertificateFile "{cert}"
    SSLCertificateKeyFile "{key}"
    DocumentRoot "{root}"
    <Directory "{root}">
        Require all granted
    </Directory>
    {rendered}
</VirtualHost>
""")

        syntax = subprocess.run(
            [APACHE, "-f", str(config), "-t"],
            capture_output=True, text=True,
        )
        assert syntax.returncode == 0, syntax.stderr

        process = subprocess.Popen(
            [APACHE, "-f", str(config), "-DFOREGROUND"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise AssertionError(
                        process.stderr.read().decode()
                    )
                try:
                    with socket.create_connection(("127.0.0.1", port), 0.1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("HTTPS test Apache did not start")

            url = f"https://127.0.0.1:{port}/logger/index.html"
            context = ssl._create_unverified_context()

            def request(credentials=None):
                headers = {}
                if credentials is not None:
                    token = base64.b64encode(
                        credentials.encode()
                    ).decode()
                    headers["Authorization"] = f"Basic {token}"

                req = urllib.request.Request(url, headers=headers)
                try:
                    with urllib.request.urlopen(
                        req, context=context, timeout=5
                    ) as response:
                        return response.status
                except urllib.error.HTTPError as error:
                    return error.code

            assert request() == 401
            assert request("testuser:wrong") == 401
            assert request("testuser:testpass") == 200

        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
