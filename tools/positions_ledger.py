#!/usr/bin/env python3
"""positions_ledger.py — reports/positions.md 형식의 마크다운 표를 파싱하는 공용 유틸.

`trading_rigor.py`의 `load_open_risk_pcts`(계좌리스크% 열만 추출)와
`portfolio_dashboard.py`(모든 열이 필요)가 같은 표 형식을 서로 다른 방식으로
다시 파싱하지 않도록, 표 → 행 딕셔너리 리스트 변환을 이 모듈 하나로 모았다.
표준 라이브러리만 사용한다 — 외부 의존성 없음.
"""

from __future__ import annotations

from pathlib import Path


def parse_positions_table(positions_path) -> list[dict[str, str]]:
    """`reports/positions.md`의 "현재 포지션" 표를 파싱해 행 딕셔너리 리스트로 반환한다.

    헤더 행("| 티커 | 상태 | ... |")을 자동으로 찾고, 그 아래 구분선(`---`) 다음부터
    표가 끝날 때까지의 각 행을 `{헤더: 값}` 딕셔너리로 만든다. "티커" 칸이 비어 있거나
    `_(...)_ ` 형태(예: `_(아직 기록된 포지션 없음)_`)인 placeholder 행은 제외한다.

    Args:
        positions_path: `reports/positions.md` 경로.

    Returns:
        표 순서 그대로의 행 딕셔너리 리스트 (실제 데이터 행만, placeholder 제외).
    """
    path = Path(positions_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "티커" in line and "상태" in line:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"{path}에서 원장 표 헤더('| 티커 | 상태 | ... |')를 찾을 수 없습니다.")

    headers = [h.strip() for h in lines[header_idx].strip().strip("|").split("|")]

    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 2 :]:  # +2: 헤더 다음의 '---' 구분선 건너뛰기
        stripped = line.strip()
        if not stripped.startswith("|"):
            break  # 표가 끝남
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        # strict=False: 사람이 직접 편집하는 markdown 표라 셀 수가 헤더 수보다
        # 많아지는 경우(오탈자로 인한 '|' 추가 등)가 있을 수 있다 — 그런 초과분은
        # 무시하고 관대하게 파싱하는 게 의도된 동작이다(엄격 검증은 이미 위에서
        # 부족한 셀을 채우는 패딩으로 처리했다).
        row = dict(zip(headers, cells, strict=False))

        ticker = row.get("티커", "")
        if not ticker or ticker.startswith("_("):
            continue  # placeholder 행

        rows.append(row)

    return rows
