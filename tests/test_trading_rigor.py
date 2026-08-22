"""tools/trading_rigor.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_trading_rigor.py
"""

from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from trading_rigor import cross_validate, exact, position_size, risk_reward  # noqa: E402


class TestExact(unittest.TestCase):
    def test_float_avoids_binary_rounding_error(self):
        # 0.1 + 0.2 는 float으로 계산하면 0.30000000000000004 가 된다.
        self.assertEqual(exact(0.1) + exact(0.2), Decimal("0.3"))

    def test_accepts_decimal_passthrough(self):
        d = Decimal("1.5")
        self.assertIs(exact(d), d)


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


if __name__ == "__main__":
    unittest.main()
