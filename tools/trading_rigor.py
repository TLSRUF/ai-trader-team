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

    python tools/trading_rigor.py realized-pnl \\
        --entry 100 --stop 95 --target 115 --exit 110

    python tools/trading_rigor.py correlation \\
        --series-a '[1, 2, 3, 4, 5]' --series-b '[2, 3, 5, 4, 6]'

    python tools/trading_rigor.py portfolio-heat \\
        --risk-pcts '[1, 1.5, 2]' --max-heat-pct 6

    python tools/trading_rigor.py portfolio-heat \\
        --positions-file reports/positions.md --max-heat-pct 6

    python tools/trading_rigor.py kelly \\
        --win-rate 55 --avg-win 200 --avg-loss 100
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, DecimalException, InvalidOperation

from positions_ledger import parse_positions_table


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
    숫자로 변환할 수 없는 값(예: 오타, 빈 문자열)은 처리되지 않은
    decimal.InvalidOperation 트레이스백 대신 명확한 ValueError로 알린다 —
    모든 서브커맨드가 공통으로 이 함수를 거치므로 여기서 한 번에 막는다.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"'{value}'을(를) 숫자로 변환할 수 없습니다.") from exc


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
    if risk_pct_d <= 0:
        raise ValueError("허용 리스크 비율은 0보다 커야 합니다 (음수/0을 넣으면 포지션 크기가 무의미해집니다).")

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


def kelly_criterion(win_rate_pct, avg_win, avg_loss) -> dict:
    """승률과 손익비(평균 승리/평균 손실)로 켈리 기준 최적 베팅 비율을 계산한다.

    f* = p - q/b  (p=승률, q=1-p, b=평균 승리 금액/평균 손실 금액)

    `position_size`가 "계좌의 몇 %를 리스크로 걸 것인가"를 사용자가 직접 정하는
    고정 비율 방식이라면, 이 함수는 과거 성과(예: `/post-mortem`으로 쌓인 승/패
    기록)로부터 통계적으로 최적인 비율을 역산한다. 전액 켈리(full Kelly)는 표본
    오차·연속 손실 시 파산 위험이 커서 실전에서 그대로 쓰지 않는 것이 일반적이므로,
    흔히 쓰이는 half-Kelly(1/2)·quarter-Kelly(1/4)도 함께 반환한다.

    Args:
        win_rate_pct: 승률(%). 0과 100 사이(양 끝값 제외) — 0%/100%는 표본이
            없거나 예외적인 상황이라 사이징 근거로 쓰기엔 부적절하다.
        avg_win: 평균 승리 금액(또는 R-멀티플 등 동일 단위). 0보다 커야 한다.
        avg_loss: 평균 손실 금액. **절댓값**으로 입력한다 (0보다 커야 한다).

    Returns:
        win_rate_pct, payoff_ratio(b), full/half/quarter_kelly_pct, has_edge,
        warnings (켈리 비율이 0 이하면 통계적 우위가 없다는 경고).
    """
    win_rate = exact(win_rate_pct)
    avg_win_d = exact(avg_win)
    avg_loss_d = exact(avg_loss)

    if not (0 < win_rate < 100):
        raise ValueError("승률은 0%보다 크고 100%보다 작아야 합니다 (0%/100%는 표본 부족 또는 예외적 상황).")
    if avg_win_d <= 0 or avg_loss_d <= 0:
        raise ValueError("평균 승리 금액과 평균 손실 금액은 모두 0보다 커야 합니다 (손실은 절댓값으로 입력).")

    p = win_rate / Decimal(100)
    q = 1 - p
    payoff_ratio = avg_win_d / avg_loss_d
    full_kelly = p - (q / payoff_ratio)

    warnings: list[str] = []
    has_edge = full_kelly > 0
    if not has_edge:
        warnings.append(
            f"⚠️ 켈리 비율이 {(full_kelly * 100).quantize(Decimal('0.01'))}%로 0 이하입니다 "
            "— 이 승률/손익비 조합에는 통계적 우위가 없어 베팅하지 않는 것이 최적입니다."
        )

    return {
        "win_rate_pct": str(win_rate),
        "payoff_ratio": str(payoff_ratio.quantize(Decimal("0.01"))),
        "full_kelly_pct": str((full_kelly * 100).quantize(Decimal("0.01"))),
        "half_kelly_pct": str((full_kelly * 100 / 2).quantize(Decimal("0.01"))),
        "quarter_kelly_pct": str((full_kelly * 100 / 4).quantize(Decimal("0.01"))),
        "has_edge": has_edge,
        "warnings": warnings,
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


def realized_pnl(entry, stop, target, exit_price) -> dict:
    """청산된 포지션의 실현 손익을 계획했던 리스크(1R) 대비 R-멀티플로 계산한다.

    `risk_reward`가 진입 전 "계획"만 다룬다면, 이 함수는 실제 청산가로 "실제 결과"를
    계산한다. 방향(long/short)과 1R(진입~손절 거리)은 `risk_reward`와 동일한 방식으로
    정하고, 실제 청산가가 그 1R 대비 몇 배(R-멀티플)의 손익을 냈는지 환산한다.
    가격 등락률이 아니라 "계획한 리스크 대비 성과"로 승패를 일관되게 비교하기 위함이다.

    Args:
        entry: 진입가.
        stop: 손절가 (1R = |entry - stop|).
        target: 목표가 (방향 판정 및 계획 R-멀티플 산정용, `risk_reward`와 동일).
        exit_price: 실제 청산가.

    Returns:
        direction, risk(1R), planned_r_multiple(계획했던 목표 R), realized_return_pct,
        realized_r_multiple, outcome(win/loss/breakeven).
    """
    entry_d = exact(entry)
    stop_d = exact(stop)
    target_d = exact(target)
    exit_d = exact(exit_price)

    if entry_d == 0:
        raise ValueError("진입가가 0이면 실현 수익률(%)을 계산할 수 없습니다.")

    risk = abs(entry_d - stop_d)
    if risk == 0:
        raise ValueError("진입가와 손절가가 같으면 리스크(1R)가 0이 되어 계산할 수 없습니다.")

    direction = "long" if target_d > entry_d else "short"
    planned_r_multiple = abs(target_d - entry_d) / risk

    if direction == "long":
        realized_move = exit_d - entry_d
    else:
        realized_move = entry_d - exit_d

    realized_return_pct = (realized_move / entry_d) * 100
    realized_r_multiple = realized_move / risk

    if realized_r_multiple > 0:
        outcome = "win"
    elif realized_r_multiple < 0:
        outcome = "loss"
    else:
        outcome = "breakeven"

    return {
        "direction": direction,
        "risk": str(risk),
        "planned_r_multiple": str(planned_r_multiple.quantize(Decimal("0.01"))),
        "realized_return_pct": str(realized_return_pct.quantize(Decimal("0.01"))),
        "realized_r_multiple": str(realized_r_multiple.quantize(Decimal("0.01"))),
        "outcome": outcome,
    }


def unrealized_pnl(entry, stop, target, current_price) -> dict:
    """보유 중인(청산 전) 포지션의 현재가 기준 미실현 손익을 계획한 리스크(1R) 대비 R-멀티플로 계산한다.

    계산 로직은 `realized_pnl`과 완전히 동일하다(방향/1R 산정, R-멀티플 환산 공식).
    다만 아직 청산되지 않은 포지션에 그대로 `realized_pnl`을 쓰면 "실현"이라는 이름이
    오해를 부르므로, `/portfolio` 대시보드 등 보유 중 포지션에는 이 함수를 쓴다.
    "승패(win/loss)"도 청산 완료를 암시할 수 있어 status는 profit/loss/breakeven으로 표기한다.

    Args:
        entry: 진입가.
        stop: 손절가 (1R = |entry - stop|).
        target: 목표가 (방향 판정 및 계획 R-멀티플 산정용).
        current_price: 현재가 (실시간 조회값, 예: `tools/market_data.py quote`).

    Returns:
        direction, risk(1R), planned_r_multiple, unrealized_return_pct,
        unrealized_r_multiple, status(profit/loss/breakeven).
    """
    result = realized_pnl(entry, stop, target, current_price)
    status_map = {"win": "profit", "loss": "loss", "breakeven": "breakeven"}
    return {
        "direction": result["direction"],
        "risk": result["risk"],
        "planned_r_multiple": result["planned_r_multiple"],
        "unrealized_return_pct": result["realized_return_pct"],
        "unrealized_r_multiple": result["realized_r_multiple"],
        "status": status_map[result["outcome"]],
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


def portfolio_heat(risk_pcts: list, max_heat_pct=6, allow_empty=False) -> dict:
    """동시 보유 중인 모든 포지션의 계좌 대비 리스크%(손절 시 손실률)를 합산한다.

    개별 트레이드의 리스크·리워드는 괜찮아 보여도, 여러 포지션의 손절이 동시에
    체결되는 최악의 경우 계좌 전체가 얼마나 위험한지는 별도로 확인해야 한다.
    `reports/positions.md`에 기록된 각 포지션의 리스크%를 모아 넘긴다.

    Args:
        risk_pcts: 각 포지션의 계좌 대비 리스크 비율(%) 리스트 (`position-size`의
            결과 중 risk_amount / account_size * 100, 또는 직접 산정한 값).
        max_heat_pct: 허용 한도(%). 기본 6 — 흔히 쓰이는 "전체 포지션 손절 시
            손실 6% 이내" 관행값이며, 근거가 있다면 다른 값으로 조정 가능하다.
        allow_empty: True면 risk_pcts가 비어 있어도 오류 대신 0건/0% 결과를 반환한다.
            원장(`reports/positions.md`)에 "보유중" 행이 하나도 없는(=아직 첫 포지션도
            없는) 정상적인 상태를 표현할 때 쓴다. 기본 False — `--risk-pcts`로 빈 배열을
            직접 넘기는 것은 대개 호출 실수이므로 그 경로는 계속 오류로 취급한다.

    Returns:
        n_positions, total_risk_pct, max_heat_pct, over_limit, warnings.
    """
    if not risk_pcts and not allow_empty:
        raise ValueError("최소 1개 이상의 포지션 리스크%가 필요합니다.")

    values = [exact(v) for v in risk_pcts]
    if any(v < 0 for v in values):
        raise ValueError("리스크%는 음수일 수 없습니다.")

    total = sum(values, Decimal("0"))
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


def load_open_risk_pcts(positions_path) -> list[str]:
    """`reports/positions.md` 형식의 원장에서 "보유중" 상태 행의 계좌리스크%를 모은다.

    수동으로 `--risk-pcts`를 매번 다시 입력하는 대신, 원장(positions.md)을 단일
    소스로 삼아 그 자리에서 파싱한다. "상태" 열이 정확히 "보유중"인 행만 집계하고
    ("청산 (YYYY-MM-DD)" 등은 제외), 값이 비어 있는 행(예시 placeholder 행 포함)은
    건너뛴다.

    Args:
        positions_path: `reports/positions.md` 경로.

    Returns:
        보유중 포지션들의 계좌리스크% 문자열 리스트 (순서는 표 순서 그대로).
    """
    rows = parse_positions_table(positions_path)

    risk_pcts: list[str] = []
    for row in rows:
        if row.get("상태") != "보유중":
            continue
        risk_value = row.get("계좌리스크%", "").rstrip("%").strip()
        if not risk_value:
            continue
        risk_pcts.append(risk_value)

    return risk_pcts


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

    p_kelly = sub.add_parser("kelly", help="승률·손익비로 켈리 기준 최적 베팅 비율을 계산한다")
    p_kelly.add_argument("--win-rate", required=True, type=str, help="승률 (%, 0~100 사이)")
    p_kelly.add_argument("--avg-win", required=True, type=str, help="평균 승리 금액")
    p_kelly.add_argument("--avg-loss", required=True, type=str, help="평균 손실 금액 (절댓값)")

    p_rr = sub.add_parser("risk-reward", help="리스크·리워드 비율을 계산한다")
    p_rr.add_argument("--entry", required=True, type=str, help="진입가")
    p_rr.add_argument("--stop", required=True, type=str, help="손절가")
    p_rr.add_argument("--target", required=True, type=str, help="목표가")

    p_rp = sub.add_parser("realized-pnl", help="청산된 포지션의 실현 손익을 R-멀티플로 계산한다")
    p_rp.add_argument("--entry", required=True, type=str, help="진입가")
    p_rp.add_argument("--stop", required=True, type=str, help="손절가")
    p_rp.add_argument("--target", required=True, type=str, help="목표가 (방향·계획 R 산정용)")
    p_rp.add_argument("--exit", required=True, type=str, dest="exit_price", help="실제 청산가")

    p_up = sub.add_parser("unrealized-pnl", help="보유 중인 포지션의 미실현 손익을 R-멀티플로 계산한다")
    p_up.add_argument("--entry", required=True, type=str, help="진입가")
    p_up.add_argument("--stop", required=True, type=str, help="손절가")
    p_up.add_argument("--target", required=True, type=str, help="목표가 (방향·계획 R 산정용)")
    p_up.add_argument("--current", required=True, type=str, dest="current_price", help="현재가")

    p_corr = sub.add_parser("correlation", help="두 시계열의 피어슨 상관계수를 계산한다")
    p_corr.add_argument("--series-a", required=True, type=str, help='JSON 숫자 배열, 예: \'[1, 2, 3]\'')
    p_corr.add_argument("--series-b", required=True, type=str, help="series-a와 길이가 같은 JSON 숫자 배열")

    p_ph = sub.add_parser("portfolio-heat", help="보유 포지션 전체의 계좌 대비 리스크%를 합산한다")
    p_ph_source = p_ph.add_mutually_exclusive_group(required=True)
    p_ph_source.add_argument("--risk-pcts", type=str, help='JSON 숫자 배열, 예: \'[1, 1.5, 2]\'')
    p_ph_source.add_argument(
        "--positions-file", type=str, help="reports/positions.md 경로 — '보유중' 행의 계좌리스크%를 자동으로 읽는다"
    )
    p_ph.add_argument("--max-heat-pct", type=str, default="6", help="허용 한도 (%), 기본 6")

    args = parser.parse_args(argv)

    try:
        if args.command == "cross-validate":
            values = json.loads(args.values)
            result = cross_validate(args.field, values)
        elif args.command == "position-size":
            result = position_size(args.account, args.risk_pct, args.entry, args.stop)
        elif args.command == "kelly":
            result = kelly_criterion(args.win_rate, args.avg_win, args.avg_loss)
        elif args.command == "risk-reward":
            result = risk_reward(args.entry, args.stop, args.target)
        elif args.command == "realized-pnl":
            result = realized_pnl(args.entry, args.stop, args.target, args.exit_price)
        elif args.command == "unrealized-pnl":
            result = unrealized_pnl(args.entry, args.stop, args.target, args.current_price)
        elif args.command == "correlation":
            series_a = json.loads(args.series_a)
            series_b = json.loads(args.series_b)
            result = correlation(series_a, series_b)
        elif args.command == "portfolio-heat":
            if args.positions_file:
                risk_pcts = load_open_risk_pcts(args.positions_file)
                result = portfolio_heat(risk_pcts, args.max_heat_pct, allow_empty=True)
            else:
                risk_pcts = json.loads(args.risk_pcts)
                result = portfolio_heat(risk_pcts, args.max_heat_pct)
        else:  # pragma: no cover - argparse가 이미 검증함
            parser.error(f"알 수 없는 커맨드: {args.command}")
            return 2
    except (ValueError, json.JSONDecodeError, OSError, DecimalException) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    _print_json(result)

    if isinstance(result.get("warnings"), list) and result["warnings"]:
        return 1  # 편차 경고가 있으면 종료 코드로도 신호를 준다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
