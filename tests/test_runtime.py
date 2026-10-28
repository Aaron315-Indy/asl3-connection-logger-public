# SPDX-License-Identifier: GPL-3.0-or-later
"""Asterisk runtime identifier tests."""

from unittest.mock import patch, MagicMock

from asl3_connection_logger.runtime import get_runtime_id


def test_runtime_identifier():
    def fake_read_text(path):
        path = str(path)

        if path.endswith("boot_id"):
            return "test-boot-id\n"

        if path.endswith("/stat"):
            return (
                "992 (asterisk) S "
                + " ".join(["0"] * 19)
                + " 123456 0 0"
            )

        raise AssertionError(path)

    result = MagicMock()
    result.stdout = "992\n"

    with patch("pathlib.Path.read_text", autospec=True) as read:
        read.side_effect = fake_read_text

        with patch("subprocess.run", return_value=result):
            runtime = get_runtime_id()

    assert runtime.startswith("test-boot-id:")
