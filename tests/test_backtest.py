"""tools/backtest.py 단위 테스트.

손으로 만든 고정 가격 시계열만 사용한다 — 실제 네트워크 호출(market_data)은
하지 않는다.

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_backtest.py
"""

from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from backtest import aggregate_results, simulate_trend_strategy  # noqa: E402


def _closes(prices: list, start_date: str = "2024-01-01") -> list[dict]:
    """가격 리스트를 market_data.get_history() 형태로 변환한다 (날짜는 순번으로 부여)."""
    from datetime import date, timedelta

    d = date.fromisoformat(start_date)
    return [{"date": (d + timedelta(days=i)).isoformat(), "close": str(p)} for i, p in enumerate(prices)]


class TestSimulateTrendStrategy(unittest.TestCase):
    def test_no_trades_when_not_enough_data(self):
        closes = _closes([100] * 10)  # sma_window(20)보다 짧음
        trades = simulate_trend_strategy(closes, sma_window=20)
        self.assertEqual(trades, [])

    def test_target_hit_produces_win_trade(self):
        # 21일 횡보(100) 후 급등 돌파(entry=110) → stop_pct=5 → risk=5.5, target_r=2 → target=121
        # (크로스오버 판정에 어제/오늘 두 SMA가 모두 필요해 횡보가 sma_window+1일 필요하다)
        flat = [100] * 21
        breakout = [110]  # 상향 돌파 진입 신호
        rally = [115, 121, 121]  # 목표가(121) 도달
        closes = _closes(flat + breakout + rally)
        trades = simulate_trend_strategy(closes, sma_window=20, stop_pct="5", target_r_multiple="2")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "target")
        self.assertEqual(trades[0]["r_multiple"], "2.00")

    def test_stop_hit_produces_loss_trade(self):
        flat = [100] * 21
        breakout = [110]  # entry=110, stop = 110*0.95 = 104.5
        drop = [104]  # 손절가 하회
        closes = _closes(flat + breakout + drop)
        trades = simulate_trend_strategy(closes, sma_window=20, stop_pct="5", target_r_multiple="2")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "stop")
        self.assertEqual(trades[0]["r_multiple"], "-1.00")

    def test_timeout_closes_position(self):
        flat = [100] * 21
        breakout = [110]
        sideways = [111] * 5  # 손절도 목표도 도달 안 함
        closes = _closes(flat + breakout + sideways)
        trades = simulate_trend_strategy(
            closes, sma_window=20, stop_pct="5", target_r_multiple="2", max_hold_days=3
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "timeout")

    def test_open_position_force_closed_at_end_of_data(self):
        flat = [100] * 21
        breakout = [110]
        sideways = [111, 112]  # 데이터가 여기서 끝남 (max_hold_days 미도달)
        closes = _closes(flat + breakout + sideways)
        trades = simulate_trend_strategy(
            closes, sma_window=20, stop_pct="5", target_r_multiple="2", max_hold_days=60
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "end_of_data")

    def test_invalid_sma_window_raises(self):
        with self.assertRaises(ValueError):
            simulate_trend_strategy(_closes([100] * 30), sma_window=0)

    def test_friction_pct_reduces_r_multiple(self):
        flat = [100] * 21
        breakout = [110]
        rally = [115, 121, 121]
        closes = _closes(flat + breakout + rally)
        no_friction = simulate_trend_strategy(closes, sma_window=20, stop_pct="5", target_r_multiple="2")
        with_friction = simulate_trend_strategy(
            closes, sma_window=20, stop_pct="5", target_r_multiple="2", friction_pct="1"
        )
        self.assertEqual(no_friction[0]["r_multiple"], "2.00")
        # friction_pct=1% of 진입가(110)=1.10, risk=5.5 → 1.10/5.5=0.20R 차감
        self.assertEqual(with_friction[0]["r_multiple"], "1.80")

    def test_negative_friction_pct_raises(self):
        with self.assertRaises(ValueError):
            simulate_trend_strategy(_closes([100] * 30), sma_window=20, friction_pct="-1")


class TestAggregateResults(unittest.TestCase):
    def test_compounds_across_tickers_by_exit_date(self):
        trades_by_ticker = {
            "AAA": [{"entry_date": "2024-01-01", "exit_date": "2024-02-01", "entry": "100", "exit": "110", "r_multiple": "2.00", "reason": "target"}],
            "BBB": [{"entry_date": "2024-01-05", "exit_date": "2024-01-20", "entry": "50", "exit": "45", "r_multiple": "-1.00", "reason": "stop"}],
        }
        result = aggregate_results(trades_by_ticker, risk_pct_per_trade="1")
        self.assertEqual(result["n_trades"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["win_rate_pct"], "50.00")
        # BBB(1/20)가 AAA(2/1)보다 먼저 청산 → 순서: -1R(1%) 먼저, +2R(1%) 나중
        # equity = (1 - 0.01) * (1 + 0.02) = 0.99 * 1.02 = 1.0098 → +0.98%
        self.assertEqual(result["total_return_pct"], "0.98")
        self.assertEqual(result["trades"][0]["ticker"], "BBB")  # 청산일 순 정렬 확인

    def test_no_trades_returns_zero(self):
        result = aggregate_results({"AAA": []})
        self.assertEqual(result["n_trades"], 0)
        self.assertEqual(result["total_return_pct"], "0.00")
        self.assertEqual(result["win_rate_pct"], "0.00")

    def test_non_positive_risk_pct_raises(self):
        with self.assertRaises(ValueError):
            aggregate_results({"AAA": []}, risk_pct_per_trade="0")


if __name__ == "__main__":
    unittest.main()
