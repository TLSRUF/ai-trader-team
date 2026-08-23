#!/usr/bin/env python3
"""portfolio_dashboard.py — 보유 포지션 실시간 대시보드.

reports/positions.md의 "보유중" 행 전체를 읽어 각 티커의 실시간 시세를
조회하고(market_data.py), 미실현 손익(R-멀티플)과 포트폴리오 전체 리스크(히트)를
계산(trading_rigor.py)해 하나의 요약으로 만든다.

이 작업은 순수 집계·계산이라 주관적 판단이 필요 없다 — 그래서 /portfolio 같은
스킬(에이전트)이 티커마다 여러 번 Bash를 호출하게 하는 대신, 이 스크립트 하나로
전체 계산을 끝낸다. 계산 로직 자체는 여기서 새로 만들지 않고 market_data.py /
trading_rigor.py를 그대로 조합한다.

한 티커의 시세 조회가 실패해도(네트워크 문제, 상장폐지 등) 전체가 멈추지 않고
그 티커만 errors에 기록한 뒤 나머지를 계속 처리한다.

CLI 사용 예:
    python tools/portfolio_dashboard.py
    python tools/portfolio_dashboard.py --positions-file reports/positions.md
"""

from __future__ import annotations

import argparse
import json
import sys

import market_data
import trading_rigor
from positions_ledger import parse_positions_table


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def build_dashboard(positions_path) -> dict:
    """`positions_path`의 "보유중" 포지션 전체에 대해 실시간 대시보드 데이터를 만든다.

    Returns:
        n_positions(보유중 행 수), n_quoted(시세 조회 성공 수), positions(포지션별
        상세), portfolio_heat(계좌 전체 리스크 합산, 보유중 행이 하나도 없으면
        None), errors(시세 조회 실패 등 개별 오류 메시지 목록).
    """
    rows = parse_positions_table(positions_path)
    open_rows = [r for r in rows if r.get("상태") == "보유중"]

    positions: list[dict] = []
    errors: list[str] = []
    risk_pcts: list[str] = []

    for row in open_rows:
        ticker = row.get("티커", "").strip()
        entry = row.get("진입가", "").strip()
        stop = row.get("손절가", "").strip()
        target = row.get("목표가", "").strip()
        risk_pct = row.get("계좌리스크%", "").rstrip("%").strip()

        if risk_pct:
            risk_pcts.append(risk_pct)  # 포트폴리오 히트는 현재가와 무관하게 계산 가능하므로 먼저 모은다

        if not (ticker and entry and stop and target):
            errors.append(f"{ticker or '(티커 없음)'}: 진입가/손절가/목표가 중 값이 비어 있어 건너뜀")
            continue

        try:
            quote = market_data.get_quote(ticker)
            pnl = trading_rigor.unrealized_pnl(entry, stop, target, quote["price"])
        except (ValueError, RuntimeError) as exc:
            errors.append(f"{ticker}: {exc}")
            continue

        positions.append(
            {
                "ticker": ticker,
                "entry": entry,
                "stop": stop,
                "target": target,
                "current_price": quote["price"],
                "as_of": quote["as_of"],
                **pnl,
            }
        )

    heat = trading_rigor.portfolio_heat(risk_pcts) if risk_pcts else None

    return {
        "n_positions": len(open_rows),
        "n_quoted": len(positions),
        "positions": positions,
        "portfolio_heat": heat,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(prog="portfolio_dashboard.py", description="보유 포지션 실시간 대시보드")
    parser.add_argument(
        "--positions-file", default="reports/positions.md", help="원장 경로 (기본: reports/positions.md)"
    )
    args = parser.parse_args(argv)

    try:
        result = build_dashboard(args.positions_file)
    except (ValueError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["errors"]:
        return 1  # 일부라도 조회 실패가 있었으면 종료 코드로도 신호를 준다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
