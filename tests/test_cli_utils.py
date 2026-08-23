"""tools/cli_utils.py 단위 테스트.

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_cli_utils.py
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from cli_utils import force_utf8_stdio  # noqa: E402


class _FakeStream:
    """`reconfigure()`를 지원/미지원/실패하는 스트림을 흉내내는 스텁."""

    def __init__(self, supports_reconfigure=True, raises=None):
        self._supports = supports_reconfigure
        self._raises = raises
        self.reconfigured_with = None
        if supports_reconfigure:
            self.reconfigure = self._reconfigure
        # supports_reconfigure=False면 아예 속성을 만들지 않는다 (getattr(..., None)로 감지되게).

    def _reconfigure(self, encoding=None):
        if self._raises is not None:
            raise self._raises
        self.reconfigured_with = encoding


class TestForceUtf8Stdio(unittest.TestCase):
    def test_reconfigures_stdout_and_stderr_to_utf8(self):
        fake_out, fake_err = _FakeStream(), _FakeStream()
        with patch("cli_utils.sys.stdout", fake_out), patch("cli_utils.sys.stderr", fake_err):
            force_utf8_stdio()
        self.assertEqual(fake_out.reconfigured_with, "utf-8")
        self.assertEqual(fake_err.reconfigured_with, "utf-8")

    def test_stream_without_reconfigure_is_silently_skipped(self):
        fake_out = _FakeStream(supports_reconfigure=False)
        with patch("cli_utils.sys.stdout", fake_out), patch("cli_utils.sys.stderr", _FakeStream()):
            force_utf8_stdio()  # 예외 없이 조용히 넘어가야 한다

    def test_reconfigure_failure_is_silently_swallowed(self):
        fake_out = _FakeStream(raises=ValueError("already reading input"))
        with patch("cli_utils.sys.stdout", fake_out), patch("cli_utils.sys.stderr", _FakeStream()):
            force_utf8_stdio()  # ValueError/OSError는 삼켜지고 스크립트 실행을 막지 않는다


if __name__ == "__main__":
    unittest.main()
