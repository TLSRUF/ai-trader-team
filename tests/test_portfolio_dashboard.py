"""tools/portfolio_dashboard.py 단위 테스트.

실제 네트워크 호출을 하지 않는다 — market_data.get_quote를 unittest.mock으로
모킹해서 집계 로직만 검증한다.

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_portfolio_dashboard.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import portfolio_dashboard  # noqa: E402

POSITIONS_CONTENT = (
    "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 청산가 | 계좌리스크% | 최초 테제 | 비고 |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
    "| AAPL | 보유중 | 2026-08-01 | 200 | 190 | 260 | | 1.5 | t1 | |\n"
    "| BADCO | 보유중 | 2026-08-01 | 100 | 90 | 130 | | 2 | t2 | |\n"
    "| MSFT | 청산 (2026-08-10) | 2026-07-01 | 300 | 290 | 350 | 320 | 2 | t3 | |\n"
)


def _fake_get_quote(ticker: str) -> dict:
    if ticker == "AAPL":
        return {"ticker": "AAPL", "price": "220.00", "as_of": "2026-08-23T00:00:00+00:00"}
    raise ValueError(f"'{ticker}'의 현재가를 조회하지 못했습니다: not found")


class TestBuildDashboard(unittest.TestCase):
    def _write(self, tmp_dir: str, content: str) -> Path:
        path = Path(tmp_dir) / "positions.md"
        path.write_text(content, encoding="utf-8")
        return path

    @patch("portfolio_dashboard.market_data.get_quote", side_effect=_fake_get_quote)
    def test_excludes_closed_positions(self, _mock_quote):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, POSITIONS_CONTENT)
            result = portfolio_dashboard.build_dashboard(path)
        self.assertEqual(result["n_positions"], 2)  # MSFT(청산)는 제외

    @patch("portfolio_dashboard.market_data.get_quote", side_effect=_fake_get_quote)
    def test_partial_failure_does_not_block_others(self, _mock_quote):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, POSITIONS_CONTENT)
            result = portfolio_dashboard.build_dashboard(path)
        self.assertEqual(result["n_quoted"], 1)
        self.assertEqual(result["positions"][0]["ticker"], "AAPL")
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("BADCO", result["errors"][0])

    @patch("portfolio_dashboard.market_data.get_quote", side_effect=_fake_get_quote)
    def test_unrealized_pnl_computed(self, _mock_quote):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, POSITIONS_CONTENT)
            result = portfolio_dashboard.build_dashboard(path)
        aapl = result["positions"][0]
        self.assertEqual(aapl["current_price"], "220.00")
        self.assertEqual(aapl["status"], "profit")

    @patch("portfolio_dashboard.market_data.get_quote", side_effect=_fake_get_quote)
    def test_portfolio_heat_includes_all_open_positions_regardless_of_quote_success(self, _mock_quote):
        # 포트폴리오 히트는 손절 시 손실(계좌리스크%) 계산이라 현재가 조회 성공 여부와 무관하다.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, POSITIONS_CONTENT)
            result = portfolio_dashboard.build_dashboard(path)
        self.assertIsNotNone(result["portfolio_heat"])
        self.assertEqual(result["portfolio_heat"]["total_risk_pct"], "3.5")  # 1.5 + 2

    def test_no_open_positions_returns_none_heat(self):
        content = "| 티커 | 상태 | 계좌리스크% |\n|---|---|---|\n| _(아직 기록된 포지션 없음)_ | | |\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            result = portfolio_dashboard.build_dashboard(path)
        self.assertEqual(result["n_positions"], 0)
        self.assertIsNone(result["portfolio_heat"])
        self.assertEqual(result["errors"], [])

    def test_missing_price_fields_recorded_as_error_not_crash(self):
        content = (
            "| 티커 | 상태 | 진입가 | 손절가 | 목표가 | 계좌리스크% |\n"
            "|---|---|---|---|---|---|\n"
            "| AAPL | 보유중 | | 190 | 260 | 1.5 |\n"  # 진입가 누락
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            result = portfolio_dashboard.build_dashboard(path)
        self.assertEqual(result["n_quoted"], 0)
        self.assertEqual(len(result["errors"]), 1)
        # 계좌리스크%는 진입가와 무관하게 여전히 집계된다.
        self.assertIsNotNone(result["portfolio_heat"])


if __name__ == "__main__":
    unittest.main()
