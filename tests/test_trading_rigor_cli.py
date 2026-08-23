"""tools/trading_rigor.py의 CLI 진입점(main()) 테스트.

test_trading_rigor.py는 순수 함수(cross_validate, position_size 등)만 직접
호출해서 검증한다. 이 파일은 실제 사용자(에이전트)가 호출하는 진입점인
main() — argparse 서브파서 구성, 디스패치 분기, JSON 파싱 에러 처리,
mutually-exclusive 그룹, 경고 시 종료 코드 — 을 검증한다. 서브커맨드를
추가할 때 파서는 추가했는데 디스패치 분기를 빠뜨리는 실수를 잡아내기 위한
회귀 방지 테스트다.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_trading_rigor_cli.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from trading_rigor import main  # noqa: E402


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    """main(argv)를 호출하고 (종료 코드, stdout, stderr)를 반환한다.

    argparse 자체 에러(필수 인자 누락, mutually-exclusive 위반 등)는
    SystemExit을 던지므로 여기서 잡아 코드로 정규화한다.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


class TestCliSubcommands(unittest.TestCase):
    def test_cross_validate_success(self):
        code, out, _ = run_cli(
            ["cross-validate", "--field", "price", "--values", '{"a": 100, "b": 100.5}']
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["field"], "price")

    def test_position_size_success(self):
        code, out, _ = run_cli(
            ["position-size", "--account", "10000", "--risk-pct", "1", "--entry", "100", "--stop", "95"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["shares"], "20.0000")

    def test_kelly_no_edge_exits_1(self):
        code, out, _ = run_cli(
            ["kelly", "--win-rate", "30", "--avg-win", "100", "--avg-loss", "100"]
        )
        self.assertEqual(code, 1)  # 경고(우위 없음)가 있으면 종료 코드 1
        result = json.loads(out)
        self.assertFalse(result["has_edge"])

    def test_kelly_has_edge_exits_0(self):
        code, out, _ = run_cli(
            ["kelly", "--win-rate", "55", "--avg-win", "200", "--avg-loss", "100"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertTrue(result["has_edge"])

    def test_risk_reward_success(self):
        code, out, _ = run_cli(
            ["risk-reward", "--entry", "100", "--stop", "95", "--target", "115"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["risk_reward_ratio"], "3.00")

    def test_realized_pnl_success(self):
        code, out, _ = run_cli(
            ["realized-pnl", "--entry", "100", "--stop", "95", "--target", "115", "--exit", "110"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["outcome"], "win")

    def test_correlation_success(self):
        code, out, _ = run_cli(
            ["correlation", "--series-a", "[1,2,3]", "--series-b", "[2,4,6]"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["correlation"], "1.0000")

    def test_portfolio_heat_with_risk_pcts(self):
        code, out, _ = run_cli(
            ["portfolio-heat", "--risk-pcts", "[1, 1.5, 2]", "--max-heat-pct", "6"]
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["total_risk_pct"], "4.5")

    def test_portfolio_heat_with_positions_file(self):
        content = (
            "| 티커 | 상태 | 계좌리스크% |\n"
            "|---|---|---|\n"
            "| AAPL | 보유중 | 3 |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "positions.md"
            path.write_text(content, encoding="utf-8")
            code, out, _ = run_cli(["portfolio-heat", "--positions-file", str(path)])
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["total_risk_pct"], "3")


class TestCliErrorHandling(unittest.TestCase):
    def test_invalid_json_returns_1(self):
        code, _, err = run_cli(
            ["cross-validate", "--field", "price", "--values", "{not valid json}"]
        )
        self.assertEqual(code, 1)
        self.assertIn("오류", err)

    def test_value_error_from_function_returns_1(self):
        # entry == stop → risk_reward가 ValueError를 던짐
        code, _, err = run_cli(
            ["risk-reward", "--entry", "100", "--stop", "100", "--target", "115"]
        )
        self.assertEqual(code, 1)
        self.assertIn("오류", err)

    def test_non_numeric_input_returns_1_not_traceback(self):
        # exact()가 decimal.InvalidOperation을 잡아주기 전엔 CLI가 트레이스백을 그대로 뱉었다.
        code, _, err = run_cli(
            ["risk-reward", "--entry", "not-a-number", "--stop", "95", "--target", "115"]
        )
        self.assertEqual(code, 1)
        self.assertIn("오류", err)

    def test_zero_entry_realized_pnl_returns_1_not_traceback(self):
        # entry=0 → decimal.DivisionByZero가 잡히기 전엔 CLI가 트레이스백을 그대로 뱉었다.
        code, _, err = run_cli(
            ["realized-pnl", "--entry", "0", "--stop", "5", "--target", "15", "--exit", "3"]
        )
        self.assertEqual(code, 1)
        self.assertIn("오류", err)

    def test_missing_required_arg_exits_2(self):
        code, _, _ = run_cli(["risk-reward", "--entry", "100", "--stop", "95"])  # --target 누락
        self.assertEqual(code, 2)

    def test_portfolio_heat_requires_one_source(self):
        code, _, _ = run_cli(["portfolio-heat"])  # --risk-pcts도 --positions-file도 없음
        self.assertEqual(code, 2)

    def test_portfolio_heat_rejects_both_sources(self):
        code, _, _ = run_cli(
            ["portfolio-heat", "--risk-pcts", "[1]", "--positions-file", "reports/positions.md"]
        )
        self.assertEqual(code, 2)  # mutually-exclusive 그룹 위반

    def test_missing_command_exits_2(self):
        code, _, _ = run_cli([])  # 서브커맨드 자체를 안 줌
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
