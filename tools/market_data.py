#!/usr/bin/env python3
"""market_data.py — yfinance 기반 실시간/과거 시세 조회 도구.

trading_rigor.py는 서술과 계산을 분리하기 위해 외부 의존성 없이 순수 계산만
한다. 이 파일은 성격이 다르다 — "시세 조회"는 계산이 아니라 외부 데이터를
가져오는 일이라 표준 라이브러리만으로는 할 수 없다. 그래서 계산 계층
(trading_rigor.py)은 계속 의존성 없이 테스트/실행 가능하게 유지하면서,
조회 계층만 이 파일로 분리하고 최소한의(무료, API 키 불필요) 외부 의존성인
yfinance를 허용한다.

가격은 반환 즉시 Decimal 문자열로 변환해서, 이후 계산은 항상
trading_rigor.py를 거치게 한다 (여기서 직접 손익 계산을 하지 않는다).

CLI 사용 예:
    python tools/market_data.py quote --ticker AAPL

    python tools/market_data.py history --ticker AAPL \\
        --start 2023-01-01 --end 2023-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - 설치 여부에 따라 갈리는 경로
    yf = None


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _require_yfinance() -> None:
    if yf is None:
        raise RuntimeError("yfinance가 설치되어 있지 않습니다. `pip install -r requirements.txt`로 설치하세요.")


def get_quote(ticker: str) -> dict:
    """티커의 현재가(또는 가장 최근 종가)를 조회한다.

    Returns:
        ticker, price(Decimal 문자열), as_of(조회 시각, UTC ISO 8601).
    """
    _require_yfinance()
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("티커를 입력해야 합니다.")

    try:
        fast_info = yf.Ticker(ticker).fast_info
        price = fast_info["lastPrice"]
    except Exception as exc:  # yfinance/네트워크 예외를 한 곳에서 명확한 메시지로 통일
        raise ValueError(f"'{ticker}'의 현재가를 조회하지 못했습니다: {exc}") from exc

    if price is None:
        raise ValueError(f"'{ticker}'의 현재가를 조회할 수 없습니다 (존재하지 않는 티커이거나 데이터 없음).")

    return {
        "ticker": ticker,
        "price": str(Decimal(str(price)).quantize(Decimal("0.01"))),
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_history(ticker: str, start: str, end: str) -> list[dict]:
    """티커의 기간별 일별 종가(Close, 배당·분할 조정됨)를 조회한다. 백테스트용.

    Args:
        ticker: 티커.
        start: 시작일 (YYYY-MM-DD, 포함).
        end: 종료일 (YYYY-MM-DD, 미포함 — yfinance 관례).

    Returns:
        [{"date": "YYYY-MM-DD", "close": Decimal 문자열}, ...] 날짜 오름차순.
    """
    _require_yfinance()
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("티커를 입력해야 합니다.")

    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as exc:
        raise ValueError(f"'{ticker}'의 {start}~{end} 기간 시세 조회 중 오류: {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"'{ticker}'의 {start}~{end} 기간 시세를 찾을 수 없습니다.")

    close = df["Close"].squeeze()  # 단일/복수 티커 컬럼 형태(MultiIndex 등) 모두 Series로 정규화
    rows: list[dict] = []
    for date, value in close.items():
        value = float(value)
        if value != value:  # NaN 체크 (NaN은 자기 자신과도 같지 않다) — math.isnan 없이 표준적으로 판별
            # yfinance가 특정 날짜에 결측치(NaN)를 반환하는 경우가 드물게 있다. 그대로 두면
            # Decimal("NaN").quantize()가 decimal.InvalidOperation을 던져 원인을 알기 어려운
            # 트레이스백으로 죽으므로, 그 날짜는 데이터 없음으로 보고 건너뛴다(백테스트 등
            # 하위 소비자 입장에서는 그 하루가 없는 것과 동일하게 취급된다).
            continue
        rows.append({"date": date.strftime("%Y-%m-%d"), "close": str(Decimal(str(value)).quantize(Decimal("0.01")))})
    return rows


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(prog="market_data.py", description="yfinance 기반 실시간/과거 시세 조회 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    p_quote = sub.add_parser("quote", help="현재가(또는 최근 종가)를 조회한다")
    p_quote.add_argument("--ticker", required=True, help="티커")

    p_hist = sub.add_parser("history", help="기간별 일별 종가를 조회한다")
    p_hist.add_argument("--ticker", required=True, help="티커")
    p_hist.add_argument("--start", required=True, help="시작일 (YYYY-MM-DD)")
    p_hist.add_argument("--end", required=True, help="종료일 (YYYY-MM-DD, 미포함)")

    args = parser.parse_args(argv)

    try:
        if args.command == "quote":
            result = get_quote(args.ticker)
        elif args.command == "history":
            result = get_history(args.ticker, args.start, args.end)
        else:  # pragma: no cover - argparse가 이미 검증함
            parser.error(f"알 수 없는 커맨드: {args.command}")
            return 2
    except (ValueError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
