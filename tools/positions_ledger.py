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
            # 닫는 '|' 누락처럼 뒤쪽 칸이 비는 경우는 흔하고 안전하다 — 빈 문자열로
            # 채워도 앞쪽 칸들의 정렬은 그대로이고, 이후 실제로 그 칸의 값을 쓰는
            # 코드(예: Decimal 파싱)가 있다면 거기서 명확하게 실패한다.
            cells += [""] * (len(headers) - len(cells))
        elif len(cells) > len(headers):
            # 셀이 헤더보다 많아지는 건 보통 어느 칸 값 안에 이스케이프 안 된 '|'가
            # 섞여 있다는 뜻이다 — 그 지점부터 모든 뒤쪽 칸이 한 칸씩 밀린다. 예전엔
            # zip(strict=False)로 넘치는 칸을 조용히 버렸는데, 그러면 예컨대 "계좌리스크%"
            # 칸에 다른 칸의 값이 밀려 들어가도 아무 에러 없이 조용히 틀린 숫자로 계산에
            # 쓰일 수 있었다. 포지션 사이징에 쓰이는 파일이라 침묵하는 오류보다
            # 명확한 에러가 낫다.
            raise ValueError(
                f"{path}의 행이 헤더보다 셀이 많습니다 (헤더 {len(headers)}개, "
                f"이 행 {len(cells)}개). 어떤 칸 값 안에 '|' 문자가 섞여 있을 수 "
                f"있습니다 — 해당 칸에서 '|'를 빼거나 다른 문자로 바꿔주세요: {stripped!r}"
            )
        row = dict(zip(headers, cells, strict=True))

        ticker = row.get("티커", "")
        if not ticker or ticker.startswith("_("):
            continue  # placeholder 행

        rows.append(row)

    return rows
