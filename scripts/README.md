# scripts/

설치·동기화용 스크립트를 담습니다 (예: `skills/*.md`를 다른 AI 클라이언트 포맷으로 동기화, 커맨드 설치 스크립트 등).

## 현재 스크립트

| 파일 | 설명 |
|---|---|
| [`install-claude-commands.sh`](install-claude-commands.sh) | `skills/*.md`(canonical source)를 `.claude/commands/`로 복사해 Claude Code 슬래시 커맨드로 등록 |

```bash
./scripts/install-claude-commands.sh
```

`.claude/commands/*.md`는 생성물이다. 직접 수정하지 말고 `skills/*.md`를 고친 뒤 스크립트를 다시 실행할 것.
