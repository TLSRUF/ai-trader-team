#!/usr/bin/env python3
"""check_agents.py — agents/*.md가 필수 구조(헤딩)를 갖추고 있는지 검증한다.

agents/README.md는 "각 에이전트 정의는 다음을 포함해야 함"이라고 구조를
명시하지만(담당 관점/핵심 질문, 우선순위로 보는 데이터, 평가 기준, 출력 포맷),
이를 강제하는 장치가 없었다. check_skills.py가 skills/*.md에 대해 하는 역할을
agents/*.md에 대해 동일하게 수행하는 가드레일이다. 외부 의존성 없음
(표준 라이브러리만 사용, 최소 파싱).

검증 항목 (README.md는 제외):
    - 본문에 다음 헤딩이 모두 있어야 한다 (접두 매칭 — 괄호 등 접미사는 허용):
      '## 담당 관점', '## 핵심 질문', '## 우선순위로 보는 데이터',
      '## 평가 기준', '## 출력 포맷'

사용:
    python scripts/check_agents.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
REQUIRED_HEADINGS = (
    "## 담당 관점",
    "## 핵심 질문",
    "## 우선순위로 보는 데이터",
    "## 평가 기준",
    "## 출력 포맷",
)


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def check_agent_file(path: Path) -> list[str]:
    """한 에이전트 파일의 문제점 목록을 반환한다 (없으면 빈 리스트)."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]

    for heading in REQUIRED_HEADINGS:
        if not any(line.startswith(heading) for line in lines):
            errors.append(f"필수 헤딩 '{heading}...'이 없음 (agents/README.md 규칙)")

    return errors


def main() -> int:
    _force_utf8_stdio()

    if not AGENTS_DIR.is_dir():
        print(f"오류: {AGENTS_DIR} 디렉터리를 찾을 수 없습니다.", file=sys.stderr)
        return 1

    agent_files = sorted(p for p in AGENTS_DIR.glob("*.md") if p.name != "README.md")
    if not agent_files:
        print(f"오류: {AGENTS_DIR}에 검증할 에이전트 파일이 없습니다.", file=sys.stderr)
        return 1

    had_error = False
    for path in agent_files:
        errors = check_agent_file(path)
        rel = path.relative_to(REPO_ROOT)
        if errors:
            had_error = True
            print(f"[FAIL] {rel}")
            for err in errors:
                print(f"       - {err}")
        else:
            print(f"[OK]   {rel}")

    if had_error:
        print("\n에이전트 구조 검증 실패.", file=sys.stderr)
        return 1

    print(f"\n{len(agent_files)}개 에이전트 파일 모두 구조 검증 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
