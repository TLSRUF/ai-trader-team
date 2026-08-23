#!/usr/bin/env python3
"""check_skills.py — skills/*.md의 구조(YAML 프론트매터, 필수 헤딩)를 검증한다.

install-claude-commands.sh가 조용히 프론트매터 없는 파일을 복사하거나,
스킬 파일이 규칙(skills/README.md)에서 벗어나는 것을 CI 단계에서 잡아내기
위한 가드레일이다. 외부 의존성 없음 (표준 라이브러리만 사용, 최소 파싱).

검증 항목 (README.md는 제외):
    - 파일 맨 앞에 '---'로 감싼 YAML 프론트매터가 있고 제대로 닫혀 있어야 한다.
    - 프론트매터에 'description', 'argument-hint' 키가 비어 있지 않게 있어야 한다.
    - 본문에 '# /<파일명(확장자 제외)>' 형태의 최상위 헤딩이 있어야 한다
      (파일명 = 커맨드 이름 규칙, skills/README.md 참고).

사용:
    python scripts/check_skills.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
REQUIRED_FRONTMATTER_KEYS = ("description", "argument-hint")


def _force_utf8_stdio() -> None:
    """Windows 콘솔의 기본 코드페이지에서 한글 출력이 깨지는 것을 방지한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """맨 앞 '---' ~ '---' 블록을 최소 파싱한다. 닫는 구분선이 없으면 None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return frontmatter
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()
    return None  # 닫는 '---'를 못 찾음


def check_skill_file(path: Path) -> list[str]:
    """한 스킬 파일의 문제점 목록을 반환한다 (없으면 빈 리스트)."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        errors.append("YAML 프론트매터('---'로 시작/종료)가 없거나 닫히지 않음")
    else:
        for key in REQUIRED_FRONTMATTER_KEYS:
            if not frontmatter.get(key):
                errors.append(f"프론트매터에 '{key}' 키가 없거나 비어 있음")

    expected_heading = f"# /{path.stem}"
    if expected_heading not in text:
        errors.append(f"본문에 최상위 헤딩 '{expected_heading}'이 없음")

    return errors


def main() -> int:
    _force_utf8_stdio()

    if not SKILLS_DIR.is_dir():
        print(f"오류: {SKILLS_DIR} 디렉터리를 찾을 수 없습니다.", file=sys.stderr)
        return 1

    skill_files = sorted(p for p in SKILLS_DIR.glob("*.md") if p.name != "README.md")
    if not skill_files:
        print(f"오류: {SKILLS_DIR}에 검증할 스킬 파일이 없습니다.", file=sys.stderr)
        return 1

    had_error = False
    for path in skill_files:
        errors = check_skill_file(path)
        rel = path.relative_to(REPO_ROOT)
        if errors:
            had_error = True
            print(f"[FAIL] {rel}")
            for err in errors:
                print(f"       - {err}")
        else:
            print(f"[OK]   {rel}")

    if had_error:
        print("\n스킬 구조 검증 실패.", file=sys.stderr)
        return 1

    print(f"\n{len(skill_files)}개 스킬 파일 모두 구조 검증 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
