#!/usr/bin/env python3
"""trading_rigor.py — 결정론적 시세 교차검증 / 포지션 사이징 도구.

LLM 서술과 계산을 분리해서 부동소수점 오차, 단위 혼동 같은 실수를 원천 차단한다.
표준 라이브러리만 사용한다 (decimal, json, argparse) — 외부 의존성 없음.

CLI 사용 예:
    python tools/trading_rigor.py cross-validate --field price \\
        --values '{"소스A": 101.2, "소스B": 101.5}'

    python tools/trading_rigor.py position-size \\
        --account 10000 --risk-pct 1 --entry 100 --stop 95

    python tools/trading_rigor.py risk-reward \\
        --entry 100 --stop 95 --target 115
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 이모지(⚠️) 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def exact(value) -> Decimal:
    """숫자를 정확한 Decimal로 변환한다.

    float은 문자열을 경유해서 변환해 부동소수점 오차(예: 0.1 + 0.2 != 0.3)를 피한다.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def cross_validate(field: str, values: dict) -> dict:
    """여러 출처의 값을 비교해 중위수를 기준으로 편차가 큰 출처를 경고한다.

    Args:
        field: 비교 대상 항목 이름 (예: "price", "revenue").
        values: {"출처명": 값, ...} 형태의 딕셔너리. 최소 2개 이상이어야 한다.

    Returns:
        field, median, 출처별 값/편차율, 1% 초과 편차에 대한 경고 목록.
    """
    if len(values) < 2:
        raise ValueError("교차검증에는 최소 2개 이상의 독립 출처가 필요합니다.")

    decimals = {src: exact(v) for src, v in values.items()}
    sorted_vals = sorted(decimals.values())
    n = len(sorted_vals)
    mid = n // 2
    median = sorted_vals[mid] if n % 2 == 1 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2

    sources: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    for src, val in decimals.items():
        if median == 0:
            deviation_pct = Decimal("0") if val == 0 else Decimal("999.99")
        else:
            deviation_pct = abs((val - median) / median) * 100
        sources[src] = {
            "value": str(val),
            "deviation_pct": str(deviation_pct.quantize(Decimal("0.01"))),
        }
        if deviation_pct > 1:
            warnings.append(
                f"⚠️ {src}: {field} 값이 중위수 대비 {deviation_pct:.2f}% 벗어남 (값={val})"
            )

    return {"field": field, "median": str(median), "sources": sources, "warnings": warnings}


def position_size(account_size, risk_pct, entry, stop) -> dict:
    """계좌 규모, 허용 리스크 비율(%), 진입가, 손절가로 포지션 크기를 계산한다.

    리스크 금액 = account_size * (risk_pct / 100)
    손절 폭     = |entry - stop|
    수량        = 리스크 금액 / 손절 폭
    """
    account_size_d = exact(account_size)
    risk_pct_d = exact(risk_pct)
    entry_d = exact(entry)
    stop_d = exact(stop)

    if entry_d == stop_d:
        raise ValueError("진입가와 손절가가 같으면 손절 폭이 0이 되어 계산할 수 없습니다.")
    if account_size_d <= 0:
        raise ValueError("계좌 규모는 0보다 커야 합니다.")

    risk_amount = account_size_d * (risk_pct_d / Decimal(100))
    stop_distance = abs(entry_d - stop_d)
    shares = risk_amount / stop_distance
    position_value = shares * entry_d

    return {
        "risk_amount": str(risk_amount.quantize(Decimal("0.01"))),
        "stop_distance": str(stop_distance),
        "shares": str(shares.quantize(Decimal("0.0001"))),
        "position_value": str(position_value.quantize(Decimal("0.01"))),
        "position_pct_of_account": str(
            (position_value / account_size_d * 100).quantize(Decimal("0.01"))
        ),
    }


def risk_reward(entry, stop, target) -> dict:
    """진입가/손절가/목표가로 리스크·리워드 비율을 계산한다."""
    entry_d = exact(entry)
    stop_d = exact(stop)
    target_d = exact(target)

    risk = abs(entry_d - stop_d)
    reward = abs(target_d - entry_d)

    if risk == 0:
        raise ValueError("진입가와 손절가가 같으면 리스크가 0이 되어 비율을 계산할 수 없습니다.")

    ratio = reward / risk
    direction = "long" if target_d > entry_d else "short"

    return {
        "direction": direction,
        "risk": str(risk),
        "reward": str(reward),
        "risk_reward_ratio": str(ratio.quantize(Decimal("0.01"))),
    }


def _print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="trading_rigor.py", description="결정론적 시세 교차검증 / 포지션 사이징 도구"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_cv = sub.add_parser("cross-validate", help="여러 출처의 값을 교차검증한다")
    p_cv.add_argument("--field", required=True, help="비교 대상 항목 이름")
    p_cv.add_argument("--values", required=True, help='JSON 딕셔너리, 예: \'{"소스A": 101.2, "소스B": 101.5}\'')

    p_ps = sub.add_parser("position-size", help="리스크 기반 포지션 크기를 계산한다")
    p_ps.add_argument("--account", required=True, type=str, help="계좌 규모")
    p_ps.add_argument("--risk-pct", required=True, type=str, help="허용 리스크 비율 (%)")
    p_ps.add_argument("--entry", required=True, type=str, help="진입가")
    p_ps.add_argument("--stop", required=True, type=str, help="손절가")

    p_rr = sub.add_parser("risk-reward", help="리스크·리워드 비율을 계산한다")
    p_rr.add_argument("--entry", required=True, type=str, help="진입가")
    p_rr.add_argument("--stop", required=True, type=str, help="손절가")
    p_rr.add_argument("--target", required=True, type=str, help="목표가")

    args = parser.parse_args(argv)

    try:
        if args.command == "cross-validate":
            values = json.loads(args.values)
            result = cross_validate(args.field, values)
        elif args.command == "position-size":
            result = position_size(args.account, args.risk_pct, args.entry, args.stop)
        elif args.command == "risk-reward":
            result = risk_reward(args.entry, args.stop, args.target)
        else:  # pragma: no cover - argparse가 이미 검증함
            parser.error(f"알 수 없는 커맨드: {args.command}")
            return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    _print_json(result)

    if isinstance(result.get("warnings"), list) and result["warnings"]:
        return 1  # 편차 경고가 있으면 종료 코드로도 신호를 준다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
