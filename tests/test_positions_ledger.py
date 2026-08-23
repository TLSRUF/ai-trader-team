"""tools/positions_ledger.py 단위 테스트.

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_positions_ledger.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from positions_ledger import parse_positions_table  # noqa: E402


class TestParsePositionsTable(unittest.TestCase):
    def _write(self, tmp_dir: str, content: str) -> Path:
        path = Path(tmp_dir) / "positions.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_all_columns(self):
        content = (
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 청산가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
            "| AAPL | 보유중 | 2026-08-01 | 200 | 190 | 230 | | 1.5 | t1 | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            rows = parse_positions_table(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["티커"], "AAPL")
        self.assertEqual(rows[0]["진입가"], "200")
        self.assertEqual(rows[0]["청산가"], "")

    def test_skips_placeholder_row(self):
        content = (
            "| 티커 | 상태 | 계좌리스크% |\n"
            "|---|---|---|\n"
            "| _(아직 기록된 포지션 없음)_ | | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            self.assertEqual(parse_positions_table(path), [])

    def test_includes_closed_positions(self):
        # load_open_risk_pcts는 "보유중"만 쓰지만, 이 파서 자체는 모든 상태를 반환한다
        # (post-mortem/dashboard처럼 청산 행이 필요한 경우도 있으므로).
        content = (
            "| 티커 | 상태 | 청산가 |\n"
            "|---|---|---|\n"
            "| AAPL | 청산 (2026-08-10) | 44 |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            rows = parse_positions_table(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["상태"], "청산 (2026-08-10)")
        self.assertEqual(rows[0]["청산가"], "44")

    def test_missing_header_raises(self):
        content = "이 파일에는 원장 표가 없다.\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            with self.assertRaises(ValueError):
                parse_positions_table(path)

    def test_short_row_padded_with_empty_strings(self):
        # 셀 개수가 헤더보다 적어도(예: 표 뒤쪽 열 생략) 에러 없이 빈 문자열로 채운다.
        content = "| 티커 | 상태 | 비고 |\n|---|---|---|\n| AAPL | 보유중 |\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            rows = parse_positions_table(path)
        self.assertEqual(rows[0]["비고"], "")


if __name__ == "__main__":
    unittest.main()
