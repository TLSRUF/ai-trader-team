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

CLI 사용 예:
    python tools/backtest.py run --ticker AAPL --start 2024-01-01 --end 2025-01-01

    python tools/backtest.py run --tickers '["AAPL", "MSFT", "NVDA"]' \\
        --start 2024-01-01 --end 2025-01-01 --sma-window 20 --stop-pct 5 \\
        --target-r 2 --risk-pct 1
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
) -> list[dict]:
    """SMA 상향 돌파 진입 + 고정% 손절 + 고정 R:R 목표가 전략을 단일 티커에 시뮬레이션한다.

    Args:
        closes: `market_data.get_history()` 반환 형태
            [{"date": "YYYY-MM-DD", "close": "123.45"}, ...] (날짜 오름차순).
        sma_window: 이동평균 기간(거래일).
        stop_pct: 손절 폭(%, 진입가 대비). 예: "5" → 진입가의 5% 아래가 손절가.
        target_r_multiple: 목표 R-멀티플. 예: "2" → 손절폭의 2배를 목표 수익폭으로.
        max_hold_days: 최대 보유일. 이 기간 내 손절/목표 미도달이면 그날 종가로 청산(timeout).

    Returns:
        거래 리스트. 각 항목: entry_date, exit_date, entry, exit, r_multiple, reason
        (reason은 "stop"/"target"/"timeout"/"end_of_data" 중 하나).
    """
    sma_window = int(sma_window)
    stop_pct_d = exact(stop_pct)
    target_r_d = exact(target_r_multiple)
    max_hold_days = int(max_hold_days)

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


def aggregate_results(trades_by_ticker: dict[str, list[dict]], risk_pct_per_trade="1") -> dict:
    """여러 티커의 거래를 하나의 계좌 단위로 합쳐 복리 수익률을 계산한다.

    거래를 청산일(exit_date) 순서로 정렬한 뒤, 매 거래마다 계좌의
    `risk_pct_per_trade`%를 그 거래의 R-멀티플만큼 얻거나 잃는다고 가정하고
    복리로 누적한다. 동시에 여러 포지션을 보유할 때의 상호작용(포트폴리오 히트
    한도 등)은 반영하지 않는 단순화된 근사치다.

    Args:
        trades_by_ticker: {티커: `simulate_trend_strategy`의 거래 리스트}.
        risk_pct_per_trade: 거래당 계좌 리스크 비율(%).

    Returns:
        n_trades, wins, win_rate_pct, total_return_pct(계좌 기준 복리 총수익률),
        trades(청산일 순 정렬, 티커 포함).
    """
    risk_pct_d = exact(risk_pct_per_trade)
    if risk_pct_d <= 0:
        raise ValueError("risk_pct_per_trade는 0보다 커야 합니다.")

    all_trades: list[dict] = []
    for ticker, trades in trades_by_ticker.items():
        for t in trades:
            all_trades.append({**t, "ticker": ticker})
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
        "trades": all_trades,
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
    p_run.add_argument("--sma-window", type=str, default="20", help="이동평균 기간(거래일), 기본 20")
    p_run.add_argument("--stop-pct", type=str, default="5", help="손절 폭(%, 진입가 대비), 기본 5")
    p_run.add_argument("--target-r", type=str, default="2", help="목표 R-멀티플, 기본 2")
    p_run.add_argument("--max-hold-days", type=str, default="60", help="최대 보유일, 기본 60")
    p_run.add_argument("--risk-pct", type=str, default="1", help="거래당 계좌 리스크 비율(%), 기본 1")

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
                )
            result = aggregate_results(trades_by_ticker, args.risk_pct)
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
