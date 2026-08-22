#!/usr/bin/env bash
# install-claude-commands.sh
#
# skills/*.md (canonical source) 를 이 프로젝트의 .claude/commands/ 로 복사해서
# Claude Code 슬래시 커맨드(/screen, /trade-team 등)로 등록되게 한다.
#
# .claude/commands/*.md 는 생성물이다 — 직접 수정하지 말고 skills/*.md 를 고친 뒤
# 이 스크립트를 다시 실행할 것.
#
# 사용법:
#   ./scripts/install-claude-commands.sh

set -euo pipefail

# 이 스크립트의 위치를 기준으로 저장소 루트를 찾는다 (어디서 실행해도 동작하도록).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC_DIR="$REPO_ROOT/skills"
DEST_DIR="$REPO_ROOT/.claude/commands"

if [ ! -d "$SRC_DIR" ]; then
  echo "오류: $SRC_DIR 를 찾을 수 없습니다." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

count=0
for src_file in "$SRC_DIR"/*.md; do
  [ -e "$src_file" ] || continue

  base="$(basename "$src_file")"

  # skills/README.md 같은 안내 문서는 커맨드가 아니므로 건너뛴다.
  if [ "$base" = "README.md" ]; then
    continue
  fi

  dest_file="$DEST_DIR/$base"
  cp "$src_file" "$dest_file"
  echo "설치됨: /${base%.md}  ←  skills/$base"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "설치할 스킬이 없습니다 (skills/*.md 확인 필요)."
  exit 1
fi

echo ""
echo "총 ${count}개 커맨드를 .claude/commands/ 에 설치했습니다."
echo "Claude Code에서 이 저장소를 열면 /screen, /trade-team 등이 바로 사용 가능합니다."
