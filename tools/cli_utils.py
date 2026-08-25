#!/usr/bin/env python3
"""cli_utils.py — tools/*.py CLI 스크립트들이 공유하는 최소 유틸리티.

각 tools/*.py는 독립적으로 CLI 실행 가능해야 하지만(README 규칙), 이미
market_data.py/trading_rigor.py/positions_ledger.py를 서로 임포트하는 구조라
(예: backtest.py → market_data.py, trading_rigor.py), 여기 유틸을 함께 쓰는 것도
그 독립성을 해치지 않는다. Windows 콘솔 인코딩 처리처럼 스크립트마다 토씨 하나
안 틀리고 반복되던 코드를 한 곳으로 모아, 고칠 때 한 곳만 고치면 되게 한다.
"""

from __future__ import annotations

import contextlib
import sys


def force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글·이모지 출력이 깨지는 것을 방지한다.

    `sys.stdout`/`sys.stderr`가 `reconfigure()`를 지원하지 않거나(구버전 환경 등)
    인코딩 전환이 거부되는 경우는 조용히 무시한다 — 이 실패로 스크립트 본연의
    기능(계산/조회)까지 막을 이유는 없다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")
