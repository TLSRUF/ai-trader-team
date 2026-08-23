#!/usr/bin/env python3
"""backtest.py — 기계적 추세추종 전략 백테스트 엔진.

⚠️ 중요한 한계: 이 백테스트는 AI Trader Team의 4-agent 정성적 판단(추세·매크로·
리스크·수급 분석, agents/*.md)을 재현하지 않는다. 그 판단은 매번 LLM이 웹검색으로
해당 시점의 최신 데이터를 확인하는 구조라, 과거 특정 날짜의 시장/뉴스 상황을 그대로
재현해서 "그때 이 AI가 어떻게 판단했을지"를 기계적으로 재실행하는 건 사실상
불가능하다(과거 시점 데이터 재현 불가, 매 시점 LLM 재실행 비용도 비현실적).

대신 이 프로젝트가 이미 갖춘 결정론적 규칙 — 추세 추종 진입(이동평균 상향 돌파),
고정 손절%, 고정 R:R 목표가(risk-reward가 표현하는 방식), 고정 리스크%
사이징(position-size가 표현하는 방식) — 만 떼어내 기계적으로 근사한 전략을
시뮬레이션한다. 결과를 해석할 때 이 한계를 항상 함께 언급할 것.

기본 파라미터(sma=10 / stop=3% / target-r=3 / max-hold=120)는 2023~2025년,
10종목/20종목 두 유니버스에서 교차 검증된 튜닝값이다 (reports/2026-08-23-backtest-
comparison.md 참고). `--friction-pct`로 수수료·슬리피지 근사치를 반영하면 더 보수적인
(현실적인) 결과를 얻을 수 있다 — 기본값은 무마찰(0)이라 실제보다 낙관적일 수 있다.

CLI 사용 예:
    python tools/backtest.py run --ticker AAPL --start 2024-01-01 --end 2025-01-01

    python tools/backtest.py run --tickers '["AAPL", "MSFT", "NVDA"]' \\
        --start 2024-01-01 --end 2025-01-01 --sma-window 10 --stop-pct 3 \\
        --target-r 3 --max-hold-days 120 --risk-pct 1 --friction-pct 0.1
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal

import market_data
from trading_rigor import exact


def simulate_trend_strategy(
    closes: list[dict],
    sma_window=20,
    stop_pct="5",
    target_r_multiple="2",
    max_hold_days=60,
    friction_pct="0",
) -> list[dict]:
    """SMA 상향 돌파 진입 + 고정% 손절 + 고정 R:R 목표가 전략을 단일 티커에 시뮬레이션한다.

    Args:
        closes: `market_data.get_history()` 반환 형태
            [{"date": "YYYY-MM-DD", "close": "123.45"}, ...] (날짜 오름차순).
        sma_window: 이동평균 기간(거래일).
        stop_pct: 손절 폭(%, 진입가 대비). 예: "5" → 진입가의 5% 아래가 손절가.
        target_r_multiple: 목표 R-멀티플. 예: "2" → 손절폭의 2배를 목표 수익폭으로.
        max_hold_days: 최대 보유일. 이 기간 내 손절/목표 미도달이면 그날 종가로 청산(timeout).
        friction_pct: 거래 왕복 비용(수수료+슬리피지 근사, % of 진입가). 기본 0(무마찰,
            하위 호환). 실제 체결에서는 특히 손절가가 갭으로 뚫리는 경우 등 이론값보다
            불리하게 체결되므로, 현실적인 수치(예: 0.1)를 넣으면 모든 거래의 R-멀티플에서
            이 비용만큼 차감해 더 보수적인(현실적인) 결과를 얻을 수 있다.

    Returns:
        거래 리스트. 각 항목: entry_date, exit_date, entry, exit, r_multiple, reason
        (reason은 "stop"/"target"/"timeout"/"end_of_data" 중 하나).
    """
    sma_window = int(sma_window)
    stop_pct_d = exact(stop_pct)
    target_r_d = exact(target_r_multiple)
    max_hold_days = int(max_hold_days)
    friction_pct_d = exact(friction_pct)
    if friction_pct_d < 0:
        raise ValueError("friction_pct는 음수일 수 없습니다.")

    if sma_window < 1:
        raise ValueError("sma_window는 1 이상이어야 합니다.")
    if len(closes) < sma_window + 2:
        return []  # 이동평균을 계산할 데이터가 부족하면 거래 없음

    prices = [Decimal(row["close"]) for row in closes]
    dates = [row["date"] for row in closes]

    def sma_at(i: int) -> Decimal:
        window = prices[i - sma_window : i]
        return sum(window) / sma_window

    trades: list[dict] = []
    in_position = False
    entry_price = entry_date = stop_price = target_price = None
    days_held = 0

    for i in range(sma_window + 1, len(prices)):
        # sma_at(i)는 prices[i-sma_window:i]가 필요하므로 i >= sma_window에서 유효하다.
        # 크로스오버 판정에는 sma_at(i-1)도 필요해 i-1 >= sma_window, 즉 i >= sma_window+1부터
        # 시작해야 한다 (i == sma_window에서 시작하면 sma_at(i-1)이 데이터 부족으로 깨진다).
        if not in_position:
            sma_today = sma_at(i)
            sma_yesterday = sma_at(i - 1)
            if prices[i - 1] <= sma_yesterday and prices[i] > sma_today:
                in_position = True
                entry_price = prices[i]
                entry_date = dates[i]
                days_held = 0
                risk = entry_price * (stop_pct_d / 100)
                stop_price = entry_price - risk
                target_price = entry_price + risk * target_r_d
            continue

        days_held += 1
        price = prices[i]
        exit_price, reason = None, None
        if price <= stop_price:
            exit_price, reason = stop_price, "stop"
        elif price >= target_price:
            exit_price, reason = target_price, "target"
        elif days_held >= max_hold_days:
            exit_price, reason = price, "timeout"

        if reason:
            risk = entry_price - stop_price
            r_multiple = (exit_price - entry_price) / risk
            r_multiple -= (entry_price * friction_pct_d / 100) / risk  # 왕복 마찰비용 차감
            trades.append(
                {
                    "entry_date": entry_date,
                    "exit_date": dates[i],
                    "entry": str(entry_price.quantize(Decimal("0.01"))),
                    "exit": str(exit_price.quantize(Decimal("0.01"))),
                    "r_multiple": str(r_multiple.quantize(Decimal("0.01"))),
                    "reason": reason,
                }
            )
            in_position = False

    if in_position:
        # 백테스트 기간이 끝날 때까지 청산되지 않은 포지션 — 마지막 종가로 강제 청산해서
        # 조용히 누락시키지 않는다 (미실현 손익도 결과에 포함).
        risk = entry_price - stop_price
        r_multiple = (prices[-1] - entry_price) / risk
        r_multiple -= (entry_price * friction_pct_d / 100) / risk
        trades.append(
            {
                "entry_date": entry_date,
                "exit_date": dates[-1],
                "entry": str(entry_price.quantize(Decimal("0.01"))),
                "exit": str(prices[-1].quantize(Decimal("0.01"))),
                "r_multiple": str(r_multiple.quantize(Decimal("0.01"))),
                "reason": "end_of_data",
            }
        )

    return trades


def aggregate_results(
    trades_by_ticker: dict[str, list[dict]], risk_pct_per_trade="1", max_heat_pct=None
) -> dict:
    """여러 티커의 거래를 하나의 계좌 단위로 합쳐 복리 수익률을 계산한다.

    거래를 청산일(exit_date) 순서로 정렬한 뒤, 매 거래마다 계좌의
    `risk_pct_per_trade`%를 그 거래의 R-멀티플만큼 얻거나 잃는다고 가정하고
    복리로 누적한다.

    `max_heat_pct`를 지정하면 `tools/trading_rigor.py portfolio-heat`가 표현하는
    것과 같은 동시 포지션 리스크 한도를 반영한다: 어떤 신규 진입 시점에 이미
    보유 중인(청산되지 않은) 포지션들의 리스크% 합이 `risk_pct_per_trade`를 더했을 때
    한도를 넘으면, 그 신호는 자본 부족으로 스킵한다(실제 계좌라면 그 시점엔 이미
    다른 포지션에 자본이 묶여 있어 새 진입을 못 하는 상황을 근사). 진입일(entry_date)
    순서로 그리디하게 채택/스킵을 결정하고, 채택된 거래만 청산일 순으로 복리 누적한다.
    `max_heat_pct=None`(기본값)이면 기존과 동일하게 무제한 동시 보유를 가정한다.

    Args:
        trades_by_ticker: {티커: `simulate_trend_strategy`의 거래 리스트}.
        risk_pct_per_trade: 거래당 계좌 리스크 비율(%).
        max_heat_pct: 동시 보유 포지션 총 리스크% 한도. None이면 한도 없음(기존 동작).

    Returns:
        n_trades, wins, win_rate_pct, total_return_pct(계좌 기준 복리 총수익률),
        skipped_for_heat_limit(한도 초과로 스킵된 거래 수), trades(청산일 순 정렬, 티커 포함).
    """
    risk_pct_d = exact(risk_pct_per_trade)
    if risk_pct_d <= 0:
        raise ValueError("risk_pct_per_trade는 0보다 커야 합니다.")

    all_trades: list[dict] = []
    for ticker, trades in trades_by_ticker.items():
        for t in trades:
            all_trades.append({**t, "ticker": ticker})

    skipped = 0
    if max_heat_pct is not None:
        max_heat_d = exact(max_heat_pct)
        if max_heat_d <= 0:
            raise ValueError("max_heat_pct는 0보다 커야 합니다.")
        if risk_pct_d > max_heat_d:
            raise ValueError("risk_pct_per_trade가 max_heat_pct보다 커서 단 하나의 포지션도 열 수 없습니다.")
        candidates = sorted(all_trades, key=lambda t: (t["entry_date"], t["ticker"]))
        open_positions: list[str] = []  # 채택된 미청산 포지션들의 exit_date
        accepted: list[dict] = []
        for t in candidates:
            open_positions = [exit_date for exit_date in open_positions if exit_date > t["entry_date"]]
            current_heat = risk_pct_d * len(open_positions)
            if current_heat + risk_pct_d <= max_heat_d:
                open_positions.append(t["exit_date"])
                accepted.append(t)
            else:
                skipped += 1
        all_trades = accepted

    all_trades.sort(key=lambda t: t["exit_date"])

    equity = Decimal("1")
    wins = 0
    for t in all_trades:
        r = Decimal(t["r_multiple"])
        equity *= 1 + (r * risk_pct_d / 100)
        if r > 0:
            wins += 1

    n = len(all_trades)
    total_return_pct = (equity - 1) * 100
    win_rate_pct = (Decimal(wins) / n * 100) if n else Decimal("0")

    return {
        "n_trades": n,
        "wins": wins,
        "win_rate_pct": str(win_rate_pct.quantize(Decimal("0.01"))),
        "total_return_pct": str(total_return_pct.quantize(Decimal("0.01"))),
        "skipped_for_heat_limit": skipped,
        "trades": all_trades,
    }


DEFAULT_WALK_FORWARD_PARAM_GRID: list[dict[str, str]] = [
    {
        "sma_window": sw,
        "stop_pct": sp,
        "target_r_multiple": tr,
        "max_hold_days": mh,
    }
    for sw in ("10", "20")
    for sp in ("3", "5")
    for tr in ("2", "3")
    for mh in ("60", "120")
]


def _add_months(d, months: int):
    """`datetime.date`에 개월수를 더한다(월말 일수 초과 시 그 달 마지막 날로 clamp)."""
    import calendar

    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _slice_history(closes: list[dict], start: str, end: str) -> list[dict]:
    return [row for row in closes if start <= row["date"] < end]


_PARAM_GRID_KEYS = ("sma_window", "stop_pct", "target_r_multiple", "max_hold_days")


def _validate_param_grid(param_grid) -> list[dict[str, str]]:
    """CLI `--param-grid`로 들어온 JSON을 검증한다.

    `simulate_trend_strategy(**params)`에 그대로 펼쳐 넣기 때문에, 키가 하나라도
    빠지거나 오타가 있으면 그리드서치 도중 알아보기 힘든 TypeError로 죽는다 —
    그 전에 명확한 ValueError로 미리 걸러낸다.
    """
    if not isinstance(param_grid, list) or not param_grid:
        raise ValueError("--param-grid는 비어 있지 않은 JSON 배열이어야 합니다.")
    for i, params in enumerate(param_grid):
        if not isinstance(params, dict) or set(params) != set(_PARAM_GRID_KEYS):
            raise ValueError(
                f"--param-grid[{i}]는 {sorted(_PARAM_GRID_KEYS)} 키를 정확히 가진 객체여야 합니다: {params!r}"
            )
    return param_grid


def walk_forward(
    histories: dict[str, list[dict]],
    start: str,
    end: str,
    window_months=12,
    step_months=6,
    risk_pct_per_trade="1",
    friction_pct="0",
    max_heat_pct=None,
    param_grid=None,
) -> dict:
    """롤링 윈도우 워크포워드 검증: in-sample 구간에서만 파라미터를 고르고, 그 결과를
    한 번도 보지 않은 다음 out-of-sample 구간에 그대로 적용한다. 이후 구간을 한 스텝씩
    밀어가며 반복한다.

    각 in-sample 윈도우 안에서는 `param_grid`의 모든 조합을 백테스트해 `total_return_pct`가
    가장 높은 조합을 선택한다(하이퍼파라미터를 그 구간에만 과적합시키는 흔한 방식이지만,
    선택에 out-of-sample 데이터가 전혀 쓰이지 않는다는 점이 일반적인 "전체 기간에 맞춘
    파라미터 튜닝"과의 핵심 차이다). 선택된 파라미터로 곧바로 다음 구간을 시뮬레이션해
    미래 데이터를 들여다보지 않은 채로 성과를 측정한다.

    Args:
        histories: {티커: `market_data.get_history()` 반환값}. 전체 [start, end] 구간을
            미리 한 번만 조회해 넘기면, 윈도우별로 API를 다시 호출하지 않고 메모리에서
            날짜로 슬라이스한다.
        start, end: 전체 검증 기간 (YYYY-MM-DD).
        window_months: in-sample(파라미터 선택용) 구간 길이(개월).
        step_months: out-of-sample(검증용) 구간 길이이자 롤링 스텝(개월).
        risk_pct_per_trade, friction_pct, max_heat_pct: `aggregate_results`/
            `simulate_trend_strategy`에 그대로 전달.
        param_grid: 탐색할 파라미터 조합 리스트. 기본값은 `DEFAULT_WALK_FORWARD_PARAM_GRID`.

    Returns:
        windows(윈도우별 선택 파라미터·in/out-of-sample 성과), overall_out_of_sample
        (모든 윈도우의 out-of-sample 거래만 이어붙인 전체 성과).
    """
    from datetime import date as _date

    window_months = int(window_months)
    step_months = int(step_months)
    if window_months < 1:
        raise ValueError("window_months는 1 이상이어야 합니다.")
    if step_months < 1:
        # step_months가 0 이하면 cursor가 매 반복에서 전혀 전진하지 않아(또는 뒤로 가서)
        # 아래 while 루프가 끝나지 않는다 — 조용히 멈춰버리는 대신 여기서 명확히 막는다.
        raise ValueError("step_months는 1 이상이어야 합니다 (0 이하면 윈도우가 전진하지 않아 무한 루프가 됩니다).")

    param_grid = param_grid or DEFAULT_WALK_FORWARD_PARAM_GRID
    start_d = _date.fromisoformat(start)
    end_d = _date.fromisoformat(end)

    windows: list[tuple[str, str, str, str]] = []
    cursor = start_d
    while True:
        in_start, in_end = cursor, _add_months(cursor, window_months)
        oos_start, oos_end = in_end, _add_months(in_end, step_months)
        if oos_end > end_d:
            break
        windows.append((in_start.isoformat(), in_end.isoformat(), oos_start.isoformat(), oos_end.isoformat()))
        cursor = _add_months(cursor, step_months)

    if not windows:
        raise ValueError(
            "지정된 기간이 window_months+step_months보다 짧아 walk-forward 윈도우를 만들 수 없습니다."
        )

    per_window: list[dict] = []
    oos_trades_all: dict[str, list[dict]] = {t: [] for t in histories}

    for in_start, in_end, oos_start, oos_end in windows:
        best_params, best_score, best_in_sample = None, None, None
        for params in param_grid:
            trades_by_ticker = {
                ticker: simulate_trend_strategy(
                    _slice_history(closes, in_start, in_end), friction_pct=friction_pct, **params
                )
                for ticker, closes in histories.items()
            }
            in_sample = aggregate_results(trades_by_ticker, risk_pct_per_trade, max_heat_pct)
            score = Decimal(in_sample["total_return_pct"])
            if best_score is None or score > best_score:
                best_score, best_params, best_in_sample = score, params, in_sample

        oos_trades_by_ticker = {
            ticker: simulate_trend_strategy(
                _slice_history(closes, oos_start, oos_end), friction_pct=friction_pct, **best_params
            )
            for ticker, closes in histories.items()
        }
        oos_result = aggregate_results(oos_trades_by_ticker, risk_pct_per_trade, max_heat_pct)
        for ticker, trades in oos_trades_by_ticker.items():
            oos_trades_all[ticker].extend(trades)

        per_window.append(
            {
                "in_sample_period": [in_start, in_end],
                "out_of_sample_period": [oos_start, oos_end],
                "selected_params": best_params,
                "in_sample_return_pct": best_in_sample["total_return_pct"],
                "out_of_sample_return_pct": oos_result["total_return_pct"],
                "out_of_sample_n_trades": oos_result["n_trades"],
                "out_of_sample_win_rate_pct": oos_result["win_rate_pct"],
            }
        )

    overall = aggregate_results(oos_trades_all, risk_pct_per_trade, max_heat_pct)

    return {
        "windows": per_window,
        "overall_out_of_sample": {
            "n_trades": overall["n_trades"],
            "win_rate_pct": overall["win_rate_pct"],
            "total_return_pct": overall["total_return_pct"],
            "skipped_for_heat_limit": overall["skipped_for_heat_limit"],
        },
    }


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(prog="backtest.py", description="기계적 추세추종 전략 백테스트 엔진")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="추세추종 백테스트를 실행한다")
    src = p_run.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker", type=str, help="단일 티커")
    src.add_argument("--tickers", type=str, help='JSON 문자열 배열, 예: \'["AAPL", "MSFT"]\'')
    p_run.add_argument("--start", required=True, help="시작일 (YYYY-MM-DD)")
    p_run.add_argument("--end", required=True, help="종료일 (YYYY-MM-DD)")
    # 기본값은 2023~2025년, 10종목/20종목 두 유니버스에서 교차 검증된 튜닝값이다
    # (reports/2026-08-23-backtest-comparison.md 참고). 최초 기본값(20/5/2/60)보다
    # 세 연도 모두 일관되게 우수했다 — 특정 연도에만 맞춘 과적합이 아님을 확인했다.
    p_run.add_argument("--sma-window", type=str, default="10", help="이동평균 기간(거래일), 기본 10")
    p_run.add_argument("--stop-pct", type=str, default="3", help="손절 폭(%, 진입가 대비), 기본 3")
    p_run.add_argument("--target-r", type=str, default="3", help="목표 R-멀티플, 기본 3")
    p_run.add_argument("--max-hold-days", type=str, default="120", help="최대 보유일, 기본 120")
    p_run.add_argument("--risk-pct", type=str, default="1", help="거래당 계좌 리스크 비율(%), 기본 1")
    p_run.add_argument(
        "--friction-pct", type=str, default="0", help="거래 왕복 비용(수수료+슬리피지 근사, %), 기본 0(무마찰)"
    )
    p_run.add_argument(
        "--max-heat-pct",
        type=str,
        default=None,
        help="동시 보유 포지션 총 리스크%% 한도 (예: 6). 지정 시 tools/trading_rigor.py "
        "portfolio-heat와 같은 방식으로 한도 초과 신규 진입을 스킵한다. 기본 None(한도 없음)",
    )

    p_wf = sub.add_parser(
        "walk-forward", help="롤링 윈도우로 in-sample에서 파라미터를 고르고 out-of-sample에 적용해 검증한다"
    )
    src_wf = p_wf.add_mutually_exclusive_group(required=True)
    src_wf.add_argument("--ticker", type=str, help="단일 티커")
    src_wf.add_argument("--tickers", type=str, help='JSON 문자열 배열, 예: \'["AAPL", "MSFT"]\'')
    p_wf.add_argument("--start", required=True, help="시작일 (YYYY-MM-DD)")
    p_wf.add_argument("--end", required=True, help="종료일 (YYYY-MM-DD)")
    p_wf.add_argument("--window-months", type=int, default=12, help="in-sample(파라미터 선택) 구간 길이(개월), 기본 12")
    p_wf.add_argument("--step-months", type=int, default=6, help="out-of-sample 구간 길이·롤링 스텝(개월), 기본 6")
    p_wf.add_argument("--risk-pct", type=str, default="1", help="거래당 계좌 리스크 비율(%), 기본 1")
    p_wf.add_argument("--friction-pct", type=str, default="0", help="거래 왕복 비용(%), 기본 0")
    p_wf.add_argument("--max-heat-pct", type=str, default=None, help="동시 보유 포지션 총 리스크%% 한도")
    p_wf.add_argument(
        "--param-grid",
        type=str,
        default=None,
        help="탐색할 파라미터 조합의 JSON 배열, 각 원소는 sma_window/stop_pct/target_r_multiple/"
        "max_hold_days 키를 모두 가진 객체. 생략 시 DEFAULT_WALK_FORWARD_PARAM_GRID(16개 조합) 사용. "
        '예: \'[{"sma_window": "10", "stop_pct": "8", "target_r_multiple": "2", "max_hold_days": "60"}]\'',
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            tickers = json.loads(args.tickers) if args.tickers else [args.ticker]
            if not tickers:
                raise ValueError("최소 1개 이상의 티커가 필요합니다.")
            trades_by_ticker = {}
            for ticker in tickers:
                closes = market_data.get_history(ticker, args.start, args.end)
                trades_by_ticker[ticker] = simulate_trend_strategy(
                    closes,
                    sma_window=args.sma_window,
                    stop_pct=args.stop_pct,
                    target_r_multiple=args.target_r,
                    max_hold_days=args.max_hold_days,
                    friction_pct=args.friction_pct,
                )
            result = aggregate_results(trades_by_ticker, args.risk_pct, args.max_heat_pct)
        elif args.command == "walk-forward":
            tickers = json.loads(args.tickers) if args.tickers else [args.ticker]
            if not tickers:
                raise ValueError("최소 1개 이상의 티커가 필요합니다.")
            histories = {ticker: market_data.get_history(ticker, args.start, args.end) for ticker in tickers}
            param_grid = _validate_param_grid(json.loads(args.param_grid)) if args.param_grid else None
            result = walk_forward(
                histories,
                args.start,
                args.end,
                window_months=args.window_months,
                step_months=args.step_months,
                risk_pct_per_trade=args.risk_pct,
                friction_pct=args.friction_pct,
                max_heat_pct=args.max_heat_pct,
                param_grid=param_grid,
            )
        else:  # pragma: no cover - argparse가 이미 검증함
            parser.error(f"알 수 없는 커맨드: {args.command}")
            return 2
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
