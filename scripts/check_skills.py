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
    - `.claude/commands/<파일명>`이 존재하고 `skills/<파일명>`과 내용이 완전히 같아야
      한다 (`install-claude-commands.sh`로 만드는 생성물 — skills/*.md를 고친 뒤
      스크립트를 재실행하지 않으면 실제 Claude Code가 로드하는 커맨드가 구버전으로
      남는 드리프트를 CI 단계에서 잡아낸다).
    - `.claude/commands/`에 대응하는 `skills/*.md`가 더 이상 없는 파일(고아 커맨드)이
      없어야 한다 (스킬을 이름 변경/삭제한 뒤 재설치 스크립트를 돌리지 않으면, 이미
      없어진 스킬의 구버전 슬래시 커맨드가 Claude Code에 계속 남아있게 되는 드리프트를
      잡아낸다 — `install-claude-commands.sh`가 복사만 하고 정리는 하지 않기 때문).

사용:
    python scripts/check_skills.py

드리프트가 감지되면:
    ./scripts/install-claude-commands.sh
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
REQUIRED_FRONTMATTER_KEYS = ("description", "argument-hint")

sys.path.insert(0, str(REPO_ROOT / "tools"))
from cli_utils import force_utf8_stdio  # noqa: E402


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


def check_skill_file(path: Path, commands_dir: Path | None = None) -> list[str]:
    """한 스킬 파일의 문제점 목록을 반환한다 (없으면 빈 리스트).

    Args:
        path: 검증할 skills/*.md 경로.
        commands_dir: `.claude/commands/` 대응 디렉터리. 테스트에서 임시
            디렉터리로 교체할 수 있도록 인자로 뺐다 (기본값: 실제 저장소 경로).
    """
    if commands_dir is None:
        commands_dir = COMMANDS_DIR

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

    command_path = commands_dir / path.name
    if not command_path.is_file():
        errors.append(
            f".claude/commands/{path.name}이 없음 — ./scripts/install-claude-commands.sh 실행 필요"
        )
    elif command_path.read_text(encoding="utf-8") != text:
        errors.append(
            f".claude/commands/{path.name}이 skills/{path.name}과 다름 (드리프트) "
            "— ./scripts/install-claude-commands.sh 재실행 필요"
        )

    return errors


def find_orphaned_commands(skill_files: list[Path], commands_dir: Path | None = None) -> list[str]:
    """`.claude/commands/`에는 있지만 대응하는 `skills/*.md`가 없는 파일명 목록을 반환한다.

    `install-claude-commands.sh`는 복사만 할 뿐 정리는 하지 않으므로, 스킬을 이름
    변경/삭제해도 옛 커맨드 파일이 `.claude/commands/`에 그대로 남아 Claude Code에
    구버전 슬래시 커맨드로 계속 노출될 수 있다. README.md는 커맨드가 아니므로 제외한다.

    Args:
        skill_files: 현재 유효한 `skills/*.md` 경로 목록 (README.md 제외, 검증 대상).
        commands_dir: `.claude/commands/` 경로. 디렉터리가 없으면 빈 목록을 반환한다
            (아직 한 번도 설치하지 않은 상태 — 다른 검증에서 이미 에러로 잡힌다).

    Returns:
        고아 커맨드 파일명 목록 (정렬됨).
    """
    if commands_dir is None:
        commands_dir = COMMANDS_DIR
    if not commands_dir.is_dir():
        return []

    valid_names = {p.name for p in skill_files}
    command_names = {p.name for p in commands_dir.glob("*.md") if p.name != "README.md"}
    return sorted(command_names - valid_names)


def main() -> int:
    force_utf8_stdio()

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

    orphans = find_orphaned_commands(skill_files)
    if orphans:
        had_error = True
        print("[FAIL] .claude/commands/ 고아 파일 (대응하는 skills/*.md 없음)")
        for name in orphans:
            print(f"       - .claude/commands/{name} — 이름 변경/삭제된 스킬의 잔재로 보임. 직접 삭제할 것")

    if had_error:
        print("\n스킬 구조 검증 실패.", file=sys.stderr)
        return 1

    print(f"\n{len(skill_files)}개 스킬 파일 모두 구조 검증 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
