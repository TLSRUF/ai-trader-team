"""tools/backtest.py 단위 테스트.

손으로 만든 고정 가격 시계열만 사용한다 — 실제 네트워크 호출(market_data)은
하지 않는다.

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_backtest.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from decimal import DecimalException
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import backtest  # noqa: E402
from backtest import (  # noqa: E402
    DEFAULT_WALK_FORWARD_PARAM_GRID,
    _add_months,
    _slice_history,
    _validate_param_grid,
    aggregate_results,
    simulate_trend_strategy,
    walk_forward,
)


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

    def test_zero_stop_pct_raises_instead_of_dividing_by_zero(self):
        # stop_pct<=0이면 stop_price==entry_price가 되어 risk가 0이 되고, 실제로 손절이
        # 트리거되면 r_multiple 계산이 decimal.InvalidOperation(0으로 나누기)으로 죽는다.
        # 그 전에 명확한 ValueError로 막아야 한다.
        closes = _closes([100] * 30)
        with self.assertRaises(ValueError):
            simulate_trend_strategy(closes, stop_pct="0")

    def test_negative_stop_pct_raises(self):
        closes = _closes([100] * 30)
        with self.assertRaises(ValueError):
            simulate_trend_strategy(closes, stop_pct="-3")

    def test_zero_target_r_multiple_raises(self):
        closes = _closes([100] * 30)
        with self.assertRaises(ValueError):
            simulate_trend_strategy(closes, target_r_multiple="0")

    def test_negative_target_r_multiple_raises(self):
        closes = _closes([100] * 30)
        with self.assertRaises(ValueError):
            simulate_trend_strategy(closes, target_r_multiple="-2")

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

    def test_max_heat_pct_skips_overlapping_trade_over_limit(self):
        # 두 거래가 겹치는 기간(01-10~01-20) 보유 — risk 5%씩, 한도 5%라 동시에 둘 다는 못 연다.
        trades_by_ticker = {
            "AAA": [{"entry_date": "2024-01-01", "exit_date": "2024-01-20", "entry": "100", "exit": "110", "r_multiple": "2.00", "reason": "target"}],
            "BBB": [{"entry_date": "2024-01-10", "exit_date": "2024-01-25", "entry": "50", "exit": "45", "r_multiple": "-1.00", "reason": "stop"}],
        }
        result = aggregate_results(trades_by_ticker, risk_pct_per_trade="5", max_heat_pct="5")
        self.assertEqual(result["n_trades"], 1)
        self.assertEqual(result["skipped_for_heat_limit"], 1)
        # 진입일이 빠른 AAA가 먼저 채택되고, 겹치는 BBB는 스킵된다.
        self.assertEqual(result["trades"][0]["ticker"], "AAA")

    def test_max_heat_pct_allows_non_overlapping_trades(self):
        # AAA가 청산(01-10)된 뒤에 BBB가 진입(01-11)하므로 겹치지 않아 둘 다 채택된다.
        trades_by_ticker = {
            "AAA": [{"entry_date": "2024-01-01", "exit_date": "2024-01-10", "entry": "100", "exit": "110", "r_multiple": "2.00", "reason": "target"}],
            "BBB": [{"entry_date": "2024-01-11", "exit_date": "2024-01-25", "entry": "50", "exit": "45", "r_multiple": "-1.00", "reason": "stop"}],
        }
        result = aggregate_results(trades_by_ticker, risk_pct_per_trade="5", max_heat_pct="5")
        self.assertEqual(result["n_trades"], 2)
        self.assertEqual(result["skipped_for_heat_limit"], 0)

    def test_risk_pct_greater_than_max_heat_pct_raises(self):
        with self.assertRaises(ValueError):
            aggregate_results({"AAA": []}, risk_pct_per_trade="10", max_heat_pct="5")

    def test_max_heat_pct_none_keeps_default_unlimited_behavior(self):
        trades_by_ticker = {
            "AAA": [{"entry_date": "2024-01-01", "exit_date": "2024-01-20", "entry": "100", "exit": "110", "r_multiple": "2.00", "reason": "target"}],
            "BBB": [{"entry_date": "2024-01-10", "exit_date": "2024-01-25", "entry": "50", "exit": "45", "r_multiple": "-1.00", "reason": "stop"}],
        }
        result = aggregate_results(trades_by_ticker, risk_pct_per_trade="5")
        self.assertEqual(result["n_trades"], 2)
        self.assertEqual(result["skipped_for_heat_limit"], 0)


class TestAddMonthsAndSliceHistory(unittest.TestCase):
    def test_add_months_clamps_to_shorter_month(self):
        from datetime import date

        self.assertEqual(_add_months(date(2024, 1, 31), 1), date(2024, 2, 29))  # 2024는 윤년
        self.assertEqual(_add_months(date(2023, 1, 31), 1), date(2023, 2, 28))
        self.assertEqual(_add_months(date(2024, 1, 15), 12), date(2025, 1, 15))
        self.assertEqual(_add_months(date(2024, 10, 1), 6), date(2025, 4, 1))

    def test_slice_history_is_half_open_interval(self):
        closes = _closes([100, 101, 102, 103], start_date="2024-01-01")
        sliced = _slice_history(closes, "2024-01-02", "2024-01-04")
        self.assertEqual([row["date"] for row in sliced], ["2024-01-02", "2024-01-03"])


class TestValidateParamGrid(unittest.TestCase):
    def test_accepts_well_formed_grid(self):
        grid = [{"sma_window": "10", "stop_pct": "3", "target_r_multiple": "2", "max_hold_days": "60"}]
        self.assertEqual(_validate_param_grid(grid), grid)

    def test_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            _validate_param_grid([])

    def test_rejects_non_list(self):
        with self.assertRaises(ValueError):
            _validate_param_grid({"sma_window": "10"})

    def test_rejects_missing_key(self):
        with self.assertRaises(ValueError):
            _validate_param_grid([{"sma_window": "10", "stop_pct": "3", "target_r_multiple": "2"}])

    def test_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            _validate_param_grid(
                [{"sma_window": "10", "stop_pct": "3", "target_r_multiple": "2", "max_hold_days": "60", "extra": "1"}]
            )


class TestWalkForward(unittest.TestCase):
    def test_raises_when_period_shorter_than_one_window(self):
        closes = _closes([100] * 400, start_date="2024-01-01")
        with self.assertRaises(ValueError):
            walk_forward({"AAA": closes}, "2024-01-01", "2024-06-01", window_months=12, step_months=6)

    def test_zero_step_months_raises_instead_of_hanging(self):
        # step_months<=0이면 롤링 커서가 전혀 전진하지 않아 while 루프가 끝나지 않는다
        # (과거의 무한 루프 버그) — 조용히 멈추는 대신 명확한 ValueError로 막는다.
        closes = _closes([100] * 731, start_date="2024-01-01")
        with self.assertRaises(ValueError):
            walk_forward({"AAA": closes}, "2024-01-01", "2026-01-01", window_months=12, step_months=0)

    def test_negative_step_months_raises(self):
        closes = _closes([100] * 731, start_date="2024-01-01")
        with self.assertRaises(ValueError):
            walk_forward({"AAA": closes}, "2024-01-01", "2026-01-01", window_months=12, step_months=-1)

    def test_zero_window_months_raises(self):
        closes = _closes([100] * 731, start_date="2024-01-01")
        with self.assertRaises(ValueError):
            walk_forward({"AAA": closes}, "2024-01-01", "2026-01-01", window_months=0, step_months=6)

    def test_windows_are_sequential_and_non_overlapping_with_flat_prices(self):
        # 2024-01-01 ~ 2026-01-01(24개월), 가격이 평평해 돌파 신호가 전혀 없다 →
        # 모든 파라미터 조합의 in-sample 성과가 0이므로 그리드의 첫 조합이 선택되고,
        # out-of-sample 거래도 항상 0건이어야 한다. 윈도우 개수/기간 계산만 검증한다.
        closes = _closes([100] * 731, start_date="2024-01-01")
        result = walk_forward(
            {"AAA": closes}, "2024-01-01", "2026-01-01", window_months=12, step_months=6
        )
        windows = result["windows"]
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["in_sample_period"], ["2024-01-01", "2025-01-01"])
        self.assertEqual(windows[0]["out_of_sample_period"], ["2025-01-01", "2025-07-01"])
        self.assertEqual(windows[1]["in_sample_period"], ["2024-07-01", "2025-07-01"])
        self.assertEqual(windows[1]["out_of_sample_period"], ["2025-07-01", "2026-01-01"])
        for w in windows:
            self.assertEqual(w["out_of_sample_n_trades"], 0)
            self.assertEqual(w["selected_params"], DEFAULT_WALK_FORWARD_PARAM_GRID[0])
        self.assertEqual(result["overall_out_of_sample"]["n_trades"], 0)
        self.assertEqual(result["overall_out_of_sample"]["total_return_pct"], "0.00")

    def test_custom_param_grid_is_the_only_candidate_selected(self):
        # 커스텀 그리드가 원소 하나뿐이면, 그 파라미터가 (승패와 무관하게) 항상 선택돼야 한다.
        closes = _closes([100] * 731, start_date="2024-01-01")
        custom = [{"sma_window": "5", "stop_pct": "8", "target_r_multiple": "2", "max_hold_days": "30"}]
        result = walk_forward(
            {"AAA": closes}, "2024-01-01", "2026-01-01", window_months=12, step_months=6, param_grid=custom
        )
        for w in result["windows"]:
            self.assertEqual(w["selected_params"], custom[0])


class TestMainDecimalExceptionHandling(unittest.TestCase):
    def test_stray_decimal_exception_is_reported_cleanly_not_raised(self):
        # 근본 원인(stop_pct<=0 검증 누락)은 이미 수정했지만, 앞으로 나올 수 있는
        # 예상 못한 Decimal 예외에 대비해 CLI가 DecimalException을 잡아 명확한
        # "오류: ..." 메시지 + 종료코드 1로 처리하는지(트레이스백으로 죽지 않는지) 확인한다.
        with patch("backtest.market_data.get_history", side_effect=DecimalException("boom")):
            code = backtest.main(["run", "--ticker", "AAPL", "--start", "2024-01-01", "--end", "2024-02-01"])
        self.assertEqual(code, 1)


class TestMainRunAndWalkForwardHappyPath(unittest.TestCase):
    """main()의 `run`/`walk-forward` 성공 경로(CLI 인자 → 함수 호출 조립 → JSON 출력)를 검증한다.

    기존 테스트는 `simulate_trend_strategy`/`aggregate_results`/`walk_forward`를 직접
    호출해 로직 자체는 검증했지만, main()이 `args.sma_window`/`args.stop_pct` 등을
    각 함수 키워드 인자로 올바르게 연결하는지, 최종적으로 stdout에 결과를 JSON으로
    출력하고 0을 반환하는지는(오류 경로만 있고 정상 경로가 없어) 검증되지 않았다.
    """

    def test_run_command_prints_result_json_and_returns_0(self):
        prices = [100 + i * 0.1 for i in range(60)]
        with patch("backtest.market_data.get_history", return_value=_closes(prices)):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = backtest.main(
                    ["run", "--tickers", '["AAPL","MSFT"]', "--start", "2024-01-01", "--end", "2024-06-01"]
                )
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertIn("total_return_pct", result)
        self.assertIn("n_trades", result)

    def test_run_command_empty_tickers_list_returns_1(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = backtest.main(["run", "--tickers", "[]", "--start", "2024-01-01", "--end", "2024-06-01"])
        self.assertEqual(code, 1)
        self.assertIn("최소 1개 이상의 티커가 필요합니다", stderr.getvalue())

    def test_walk_forward_command_prints_result_json_and_returns_0(self):
        prices = [100 + i * 0.1 for i in range(560)]
        with patch("backtest.market_data.get_history", return_value=_closes(prices, start_date="2022-01-01")):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = backtest.main(
                    [
                        "walk-forward",
                        "--tickers",
                        '["AAPL"]',
                        "--start",
                        "2022-01-01",
                        "--end",
                        "2023-07-01",
                        "--window-months",
                        "12",
                        "--step-months",
                        "6",
                    ]
                )
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertIn("windows", result)
        self.assertIn("overall_out_of_sample", result)

    def test_walk_forward_command_empty_tickers_list_returns_1(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = backtest.main(
                ["walk-forward", "--tickers", "[]", "--start", "2022-01-01", "--end", "2023-07-01"]
            )
        self.assertEqual(code, 1)
        self.assertIn("최소 1개 이상의 티커가 필요합니다", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
