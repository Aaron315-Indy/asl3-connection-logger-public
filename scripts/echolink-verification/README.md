ASL3 Connection Logger v0.2.5 — isolated live EchoLink verification

Run on PROD node651861:
  sudo -u asterisk /usr/bin/python3 -I -B /var/tmp/asl3-v025-echolink-verify.pyz

Requirements: existing Python >=3.11 with its standard library (including
sqlite3), existing asterisk CLI accessible via PATH and its control socket,
and outbound HTTPS/trusted CA certificates for the existing AllStarLink
metadata lookup. All logger source dependencies are bundled. There are no
pip dependencies, installations, upgrades, external downloads of code, or
changes to Asterisk configuration/services. Do not run via the installed
logger venv. The system Python runs the bundled code in isolation.

The package checks the hostname (default node651861), executes the read-only
`asterisk -rx "echolink dbdump"`, and requires at least three valid actual
entries. It prefers IDs 100016 and 930729 if present, plus another actual
entry. No fixture directory or fallback is included. It independently checks
ID + 3000000 against the parser mapping and exact raw callsigns. It runs the
new sync service code against a new database, checks cache and resolver,
and serves the unchanged logger DashboardHandler on an ephemeral loopback
port. It requests /api/dashboard and checks both sessions and top_nodes.
The installed dashboard process and installed database are never used.

The live AllStarLink lookup defaults to node 651861. It must return a callsign.
The test also inserts manual overrides ONLY into the disposable database,
repeats live synchronization, verifies EchoLink callsign override precedence
and AllStarLink location override precedence, and checks that seeded session
and event history remain identical. No actual radio connection is made.

Success prints PASS rows with actual IDs, mapped logger nodes and callsigns,
then PASS overall live verification; exit status 0. A missing module, CLI
failure/timeout, malformed/empty dump, fewer than three entries, directory
changes affecting chosen records, HTTPS failure, or assertion failure prints
FAIL and exits nonzero. A partial PASS is not overall success.

All extraction and database files live in private TemporaryDirectory locations
under /var/tmp, never /opt or /var/lib. They are removed on success, failure,
Ctrl-C, and handled SIGTERM. SIGKILL/power loss cannot run cleanup; if needed,
remove only the specific orphaned asl3-v025-code-* / asl3-v025-live-* directory
owned by this run. The .pyz itself remains available for reuse/removal.

Options: --expected-host HOST --allstar-node NODE --timeout SECONDS.
--expected-host does not enable any module or bypass the live-directory check.
No option accepts a production database path or a saved directory dump.

Local simulated tests exercise success, real loopback HTTP, failure and cleanup.
Those are development validation only, not evidence of a PROD live PASS.
The packaged DEV run must fail because chan_echolink is disabled there.

Bundled SHA256SUMS.json identifies every source member; LICENSE is included.
To inspect: python3 -m zipfile -l /var/tmp/asl3-v025-echolink-verify.pyz
