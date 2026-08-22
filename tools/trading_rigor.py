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

    python tools/trading_rigor.py correlation \\
        --series-a '[1, 2, 3, 4, 5]' --series-b '[2, 3, 5, 4, 6]'

    python tools/trading_rigor.py portfolio-heat \\
        --risk-pcts '[1, 1.5, 2]' --max-heat-pct 6
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


def correlation(series_a: list, series_b: list) -> dict:
    """두 시계열(예: 신규 포지션 후보 vs 기존 보유 포지션의 수익률)의 피어슨 상관계수를 계산한다.

    리스크 관리자가 "분산 효과가 진짜 있는가"를 감으로 판단하지 않도록 하기 위한 함수다.

    Args:
        series_a: 숫자 리스트 (예: 일별 수익률).
        series_b: series_a와 길이가 같은 숫자 리스트.

    Returns:
        n(데이터 포인트 수), correlation(피어슨 r, -1~1), level(낮음/중간/높음 — 절대값 기준).
    """
    a = [exact(v) for v in series_a]
    b = [exact(v) for v in series_b]

    if len(a) != len(b):
        raise ValueError("두 시계열의 길이가 같아야 합니다.")
    n = len(a)
    if n < 3:
        raise ValueError("상관관계 계산에는 최소 3개 이상의 데이터 포인트가 필요합니다.")

    mean_a = sum(a) / n
    mean_b = sum(b) / n
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    variance_a = sum((x - mean_a) ** 2 for x in a)
    variance_b = sum((y - mean_b) ** 2 for y in b)

    if variance_a == 0 or variance_b == 0:
        raise ValueError("한쪽 시계열의 분산이 0이라 상관계수를 계산할 수 없습니다 (값이 모두 동일함).")

    r = covariance / (variance_a * variance_b).sqrt()
    r = max(Decimal("-1"), min(Decimal("1"), r))  # 반올림 오차로 -1/1을 살짝 벗어나는 것 방지
    abs_r = abs(r)

    if abs_r >= Decimal("0.7"):
        level = "높음"
    elif abs_r >= Decimal("0.3"):
        level = "중간"
    else:
        level = "낮음"

    return {"n": n, "correlation": str(r.quantize(Decimal("0.0001"))), "level": level}


def portfolio_heat(risk_pcts: list, max_heat_pct=6) -> dict:
    """동시 보유 중인 모든 포지션의 계좌 대비 리스크%(손절 시 손실률)를 합산한다.

    개별 트레이드의 리스크·리워드는 괜찮아 보여도, 여러 포지션의 손절이 동시에
    체결되는 최악의 경우 계좌 전체가 얼마나 위험한지는 별도로 확인해야 한다.
    `reports/positions.md`에 기록된 각 포지션의 리스크%를 모아 넘긴다.

    Args:
        risk_pcts: 각 포지션의 계좌 대비 리스크 비율(%) 리스트 (`position-size`의
            결과 중 risk_amount / account_size * 100, 또는 직접 산정한 값).
        max_heat_pct: 허용 한도(%). 기본 6 — 흔히 쓰이는 "전체 포지션 손절 시
            손실 6% 이내" 관행값이며, 근거가 있다면 다른 값으로 조정 가능하다.

    Returns:
        n_positions, total_risk_pct, max_heat_pct, over_limit, warnings.
    """
    if not risk_pcts:
        raise ValueError("최소 1개 이상의 포지션 리스크%가 필요합니다.")

    values = [exact(v) for v in risk_pcts]
    if any(v < 0 for v in values):
        raise ValueError("리스크%는 음수일 수 없습니다.")

    total = sum(values)
    max_heat = exact(max_heat_pct)
    over_limit = total > max_heat

    warnings: list[str] = []
    if over_limit:
        warnings.append(
            f"⚠️ 포트폴리오 히트 {total}%가 한도 {max_heat}%를 초과했습니다 "
            f"— 모든 포지션이 동시에 손절되면 계좌의 {total}%를 잃습니다."
        )

    return {
        "n_positions": len(values),
        "total_risk_pct": str(total),
        "max_heat_pct": str(max_heat),
        "over_limit": over_limit,
        "warnings": warnings,
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

    p_corr = sub.add_parser("correlation", help="두 시계열의 피어슨 상관계수를 계산한다")
    p_corr.add_argument("--series-a", required=True, type=str, help='JSON 숫자 배열, 예: \'[1, 2, 3]\'')
    p_corr.add_argument("--series-b", required=True, type=str, help="series-a와 길이가 같은 JSON 숫자 배열")

    p_ph = sub.add_parser("portfolio-heat", help="보유 포지션 전체의 계좌 대비 리스크%를 합산한다")
    p_ph.add_argument("--risk-pcts", required=True, type=str, help='JSON 숫자 배열, 예: \'[1, 1.5, 2]\'')
    p_ph.add_argument("--max-heat-pct", type=str, default="6", help="허용 한도 (%), 기본 6")

    args = parser.parse_args(argv)

    try:
        if args.command == "cross-validate":
            values = json.loads(args.values)
            result = cross_validate(args.field, values)
        elif args.command == "position-size":
            result = position_size(args.account, args.risk_pct, args.entry, args.stop)
        elif args.command == "risk-reward":
            result = risk_reward(args.entry, args.stop, args.target)
        elif args.command == "correlation":
            series_a = json.loads(args.series_a)
            series_b = json.loads(args.series_b)
            result = correlation(series_a, series_b)
        elif args.command == "portfolio-heat":
            risk_pcts = json.loads(args.risk_pcts)
            result = portfolio_heat(risk_pcts, args.max_heat_pct)
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
