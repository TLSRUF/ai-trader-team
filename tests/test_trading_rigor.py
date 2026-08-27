"""tools/trading_rigor.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_trading_rigor.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from trading_rigor import (  # noqa: E402
    correlation,
    cross_validate,
    exact,
    kelly_criterion,
    load_open_risk_pcts,
    portfolio_heat,
    position_size,
    realized_pnl,
    risk_reward,
    unrealized_pnl,
)


class TestExact(unittest.TestCase):
    def test_float_avoids_binary_rounding_error(self):
        # 0.1 + 0.2 는 float으로 계산하면 0.30000000000000004 가 된다.
        self.assertEqual(exact(0.1) + exact(0.2), Decimal("0.3"))

    def test_accepts_decimal_passthrough(self):
        d = Decimal("1.5")
        self.assertIs(exact(d), d)

    def test_non_numeric_string_raises_value_error(self):
        # 이전엔 decimal.InvalidOperation이 그대로 새어나갔다.
        with self.assertRaises(ValueError):
            exact("not-a-number")


class TestCrossValidate(unittest.TestCase):
    def test_requires_at_least_two_sources(self):
        with self.assertRaises(ValueError):
            cross_validate("price", {"소스A": 100})

    def test_no_warning_when_within_one_percent(self):
        result = cross_validate("price", {"소스A": 100.0, "소스B": 100.5})
        self.assertEqual(result["warnings"], [])

    def test_warns_when_deviation_exceeds_one_percent(self):
        result = cross_validate("price", {"소스A": 100.0, "소스B": 110.0})
        self.assertEqual(len(result["warnings"]), 2)

    def test_median_of_three_sources(self):
        result = cross_validate("price", {"a": 100, "b": 101, "c": 102})
        self.assertEqual(result["median"], "101")


class TestPositionSize(unittest.TestCase):
    def test_basic_calculation(self):
        # 계좌 10000, 리스크 1% = 100, 손절폭 5 → 수량 20
        result = position_size(account_size=10000, risk_pct=1, entry=100, stop=95)
        self.assertEqual(result["risk_amount"], "100.00")
        self.assertEqual(result["stop_distance"], "5")
        self.assertEqual(result["shares"], "20.0000")

    def test_entry_equals_stop_raises(self):
        with self.assertRaises(ValueError):
            position_size(account_size=10000, risk_pct=1, entry=100, stop=100)

    def test_non_positive_account_raises(self):
        with self.assertRaises(ValueError):
            position_size(account_size=0, risk_pct=1, entry=100, stop=95)

    def test_negative_risk_pct_raises(self):
        # 이전엔 음수 risk-pct가 조용히 음수 수량/포지션 가치를 반환했다.
        with self.assertRaises(ValueError):
            position_size(account_size=10000, risk_pct=-1, entry=100, stop=95)

    def test_zero_risk_pct_raises(self):
        with self.assertRaises(ValueError):
            position_size(account_size=10000, risk_pct=0, entry=100, stop=95)


class TestKellyCriterion(unittest.TestCase):
    def test_has_edge_no_warning(self):
        # p=0.55, b=2 → f* = 0.55 - 0.45/2 = 0.325
        result = kelly_criterion(win_rate_pct=55, avg_win=200, avg_loss=100)
        self.assertEqual(result["payoff_ratio"], "2.00")
        self.assertEqual(result["full_kelly_pct"], "32.50")
        self.assertEqual(result["half_kelly_pct"], "16.25")
        self.assertEqual(result["quarter_kelly_pct"], "8.12")
        self.assertTrue(result["has_edge"])
        self.assertEqual(result["warnings"], [])

    def test_no_edge_warns(self):
        # p=0.3, b=1 → f* = 0.3 - 0.7/1 = -0.4
        result = kelly_criterion(win_rate_pct=30, avg_win=100, avg_loss=100)
        self.assertEqual(result["full_kelly_pct"], "-40.00")
        self.assertFalse(result["has_edge"])
        self.assertEqual(len(result["warnings"]), 1)

    def test_win_rate_must_be_below_100(self):
        with self.assertRaises(ValueError):
            kelly_criterion(win_rate_pct=100, avg_win=100, avg_loss=100)

    def test_win_rate_must_be_above_0(self):
        with self.assertRaises(ValueError):
            kelly_criterion(win_rate_pct=0, avg_win=100, avg_loss=100)

    def test_zero_avg_loss_raises(self):
        with self.assertRaises(ValueError):
            kelly_criterion(win_rate_pct=55, avg_win=200, avg_loss=0)

    def test_negative_avg_win_raises(self):
        with self.assertRaises(ValueError):
            kelly_criterion(win_rate_pct=55, avg_win=-200, avg_loss=100)


class TestRiskReward(unittest.TestCase):
    def test_long_ratio(self):
        result = risk_reward(entry=100, stop=95, target=115)
        self.assertEqual(result["direction"], "long")
        self.assertEqual(result["risk_reward_ratio"], "3.00")

    def test_short_ratio(self):
        result = risk_reward(entry=100, stop=105, target=85)
        self.assertEqual(result["direction"], "short")
        self.assertEqual(result["risk_reward_ratio"], "3.00")

    def test_zero_risk_raises(self):
        with self.assertRaises(ValueError):
            risk_reward(entry=100, stop=100, target=110)


class TestRealizedPnl(unittest.TestCase):
    def test_long_win(self):
        result = realized_pnl(entry=100, stop=95, target=115, exit_price=110)
        self.assertEqual(result["direction"], "long")
        self.assertEqual(result["risk"], "5")
        self.assertEqual(result["planned_r_multiple"], "3.00")
        self.assertEqual(result["realized_return_pct"], "10.00")
        self.assertEqual(result["realized_r_multiple"], "2.00")
        self.assertEqual(result["outcome"], "win")

    def test_long_loss(self):
        result = realized_pnl(entry=100, stop=95, target=115, exit_price=90)
        self.assertEqual(result["realized_r_multiple"], "-2.00")
        self.assertEqual(result["outcome"], "loss")

    def test_long_breakeven(self):
        result = realized_pnl(entry=100, stop=95, target=115, exit_price=100)
        self.assertEqual(result["realized_r_multiple"], "0.00")
        self.assertEqual(result["outcome"], "breakeven")

    def test_short_win(self):
        result = realized_pnl(entry=100, stop=105, target=85, exit_price=95)
        self.assertEqual(result["direction"], "short")
        self.assertEqual(result["realized_r_multiple"], "1.00")
        self.assertEqual(result["outcome"], "win")

    def test_short_loss(self):
        result = realized_pnl(entry=100, stop=105, target=85, exit_price=108)
        self.assertEqual(result["direction"], "short")
        self.assertEqual(result["realized_r_multiple"], "-1.60")
        self.assertEqual(result["outcome"], "loss")

    def test_zero_risk_raises(self):
        with self.assertRaises(ValueError):
            realized_pnl(entry=100, stop=100, target=115, exit_price=110)

    def test_zero_entry_raises(self):
        # 이전엔 entry=0일 때 decimal.DivisionByZero가 그대로 새어나갔다.
        with self.assertRaises(ValueError):
            realized_pnl(entry=0, stop=5, target=15, exit_price=3)


class TestUnrealizedPnl(unittest.TestCase):
    def test_same_math_as_realized_pnl_with_renamed_keys(self):
        realized = realized_pnl(entry=100, stop=95, target=115, exit_price=110)
        unrealized = unrealized_pnl(entry=100, stop=95, target=115, current_price=110)
        self.assertEqual(unrealized["direction"], realized["direction"])
        self.assertEqual(unrealized["risk"], realized["risk"])
        self.assertEqual(unrealized["planned_r_multiple"], realized["planned_r_multiple"])
        self.assertEqual(unrealized["unrealized_return_pct"], realized["realized_return_pct"])
        self.assertEqual(unrealized["unrealized_r_multiple"], realized["realized_r_multiple"])

    def test_status_uses_profit_not_win(self):
        # "win/loss"는 청산 완료를 암시할 수 있어 status는 profit/loss/breakeven을 쓴다.
        result = unrealized_pnl(entry=100, stop=95, target=115, current_price=110)
        self.assertEqual(result["status"], "profit")
        self.assertNotIn("outcome", result)

    def test_loss_status(self):
        result = unrealized_pnl(entry=100, stop=95, target=115, current_price=90)
        self.assertEqual(result["status"], "loss")

    def test_breakeven_status(self):
        result = unrealized_pnl(entry=100, stop=95, target=115, current_price=100)
        self.assertEqual(result["status"], "breakeven")

    def test_zero_risk_raises(self):
        with self.assertRaises(ValueError):
            unrealized_pnl(entry=100, stop=100, target=115, current_price=110)


class TestCorrelation(unittest.TestCase):
    def test_requires_equal_length(self):
        with self.assertRaises(ValueError):
            correlation([1, 2, 3], [1, 2])

    def test_requires_at_least_three_points(self):
        with self.assertRaises(ValueError):
            correlation([1, 2], [1, 2])

    def test_perfect_positive_correlation(self):
        result = correlation([1, 2, 3, 4], [2, 4, 6, 8])
        self.assertEqual(result["correlation"], "1.0000")
        self.assertEqual(result["level"], "높음")

    def test_perfect_negative_correlation(self):
        result = correlation([1, 2, 3, 4], [8, 6, 4, 2])
        self.assertEqual(result["correlation"], "-1.0000")
        self.assertEqual(result["level"], "높음")

    def test_zero_variance_raises(self):
        with self.assertRaises(ValueError):
            correlation([1, 1, 1], [1, 2, 3])

    def test_low_correlation_level(self):
        result = correlation([1, 2, 3, 4, 5, 6, 7], [4, 1, 5, 9, 2, 6, 3])
        self.assertEqual(result["level"], "낮음")

    def test_middle_correlation_level(self):
        result = correlation([8, 19, 18, 5, 12], [20, 16, 19, 3, 20])
        self.assertEqual(result["correlation"], "0.5309")
        self.assertEqual(result["level"], "중간")


class TestPortfolioHeat(unittest.TestCase):
    def test_requires_at_least_one_position(self):
        with self.assertRaises(ValueError):
            portfolio_heat([])

    def test_rejects_negative_risk(self):
        with self.assertRaises(ValueError):
            portfolio_heat([1, -0.5])

    def test_under_limit_no_warning(self):
        result = portfolio_heat([1, 1.5, 2], max_heat_pct=6)
        self.assertEqual(result["total_risk_pct"], "4.5")
        self.assertFalse(result["over_limit"])
        self.assertEqual(result["warnings"], [])

    def test_over_limit_warns(self):
        result = portfolio_heat([3, 2, 2.5], max_heat_pct=6)
        self.assertEqual(result["total_risk_pct"], "7.5")
        self.assertTrue(result["over_limit"])
        self.assertEqual(len(result["warnings"]), 1)

    def test_default_max_heat_pct_is_six(self):
        result = portfolio_heat([2, 2])
        self.assertEqual(result["max_heat_pct"], "6")

    def test_allow_empty_returns_zero_heat_instead_of_raising(self):
        result = portfolio_heat([], allow_empty=True)
        self.assertEqual(result["n_positions"], 0)
        self.assertEqual(result["total_risk_pct"], "0")
        self.assertFalse(result["over_limit"])
        self.assertEqual(result["warnings"], [])


class TestLoadOpenRiskPcts(unittest.TestCase):
    def _write(self, tmp_dir: str, content: str) -> Path:
        path = Path(tmp_dir) / "positions.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_collects_only_open_positions(self):
        content = (
            "# 보유 포지션 원장\n\n"
            "## 현재 포지션\n\n"
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| AAPL | 보유중 | 2026-08-01 | 200 | 190 | 230 | 1.5 | t1 | |\n"
            "| TSLA | 청산 (2026-08-10) | 2026-07-01 | 250 | 240 | 300 | 2 | t2 | |\n"
            "| NVDA | 보유중 | 2026-08-15 | 120 | 110 | 150 | 2.5% | t3 | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            result = load_open_risk_pcts(path)
            self.assertEqual(result, ["1.5", "2.5"])

    def test_skips_placeholder_row(self):
        content = (
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| _(아직 기록된 포지션 없음)_ | | | | | | | | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            self.assertEqual(load_open_risk_pcts(path), [])

    def test_missing_header_raises(self):
        content = "이 파일에는 원장 표가 없다.\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            with self.assertRaises(ValueError):
                load_open_risk_pcts(path)

    def test_skips_open_position_with_blank_risk_pct(self):
        # "보유중"이라도 계좌리스크% 칸이 비어 있으면(원장 기록 누락) 값을 지어내지
        # 않고 건너뛴다 — 나머지 보유중 행은 그대로 집계에 포함된다.
        content = (
            "# 보유 포지션 원장\n\n"
            "## 현재 포지션\n\n"
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| AAPL | 보유중 | 2026-08-01 | 200 | 190 | 230 | | t1 | |\n"
            "| NVDA | 보유중 | 2026-08-15 | 120 | 110 | 150 | 2.5 | t3 | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            self.assertEqual(load_open_risk_pcts(path), ["2.5"])

    def test_feeds_directly_into_portfolio_heat(self):
        content = (
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| AAPL | 보유중 | 2026-08-01 | 200 | 190 | 230 | 3 | t1 | |\n"
            "| NVDA | 보유중 | 2026-08-15 | 120 | 110 | 150 | 4 | t3 | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            risk_pcts = load_open_risk_pcts(path)
            result = portfolio_heat(risk_pcts)
            self.assertEqual(result["total_risk_pct"], "7")
            self.assertTrue(result["over_limit"])

    def test_empty_ledger_feeds_into_portfolio_heat_without_raising(self):
        # reports/positions.md의 실제 초기 상태(placeholder 행만 있는 빈 원장)를
        # 그대로 portfolio-heat --positions-file로 넘겨도(allow_empty=True) 첫
        # 포지션을 추가하기 전 정상적으로 0% 히트를 돌려줘야 한다.
        content = (
            "| 티커 | 상태 | 진입일 | 진입가 | 손절가 | 목표가 | 계좌리스크% | 최초 테제 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| _(아직 기록된 포지션 없음)_ | | | | | | | | |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, content)
            risk_pcts = load_open_risk_pcts(path)
            result = portfolio_heat(risk_pcts, allow_empty=True)
            self.assertEqual(result["n_positions"], 0)
            self.assertEqual(result["total_risk_pct"], "0")
            self.assertFalse(result["over_limit"])


if __name__ == "__main__":
    unittest.main()
