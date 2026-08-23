# skills/

이 폴더는 슬래시 커맨드(스킬)의 **canonical source**입니다. 하나의 스킬 = 하나의 `.md` 파일이며, 실행 순서·프롬프트 지침·출력 포맷을 정의합니다.

## 규칙

- 파일명 = 커맨드 이름 (예: `investment-team.md` → `/investment-team`)
- 각 스킬 파일은 다음을 명시해야 함:
  - 목적과 사용 시점
  - 실행 순서 (단계별)
  - 어떤 `agents/`를 몇 개, 어떤 방식(병렬/순차)으로 호출하는지
  - 계산이 필요하면 어떤 `tools/` 스크립트를 사용하는지
  - 출력 포맷 (표, 등급, 결론 형식 등)
- 다른 AI 클라이언트용 포맷(예: Codex)은 이 폴더에서 자동 생성하며, 생성된 파일은 직접 수정하지 않는다.

## 현재 정의된 스킬

| 파일 | 커맨드 | 비용 | 설명 |
|---|---|---|---|
| [`screen.md`](screen.md) | `/screen` | 낮음 (단일 에이전트) | 7개 하드 메트릭으로 후보를 빠르게 Pass/Fail/Watch 판정 |
| [`trade-team.md`](trade-team.md) | `/trade-team` | 높음 (4-agent 병렬) | `agents/`의 4개 관점(추세·매크로·리스크·수급)을 병렬 실행해 하나의 리포트로 종합 |
| [`position-review.md`](position-review.md) | `/position-review` | 낮음 (단일 에이전트) | 보유 포지션의 최초 진입 근거가 여전히 유효한지 재점검, 드리프트 판정 |

**권장 흐름**: 후보가 여러 개면 `/screen`으로 먼저 거른 뒤, Pass한 종목만 `/trade-team`으로 심층 분석한다. 진입 후에는 주기적으로 `/position-review`로 테제 드리프트를 점검한다.
