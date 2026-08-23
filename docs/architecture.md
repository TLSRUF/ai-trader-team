# 아키텍처

AI Trader Team은 세 계층(Skill/Agent/Tool) 설계로 시작했지만, 실제로 쓰이면서 상태를
이어주는 4번째 계층(`reports/`)이 자연스럽게 자리잡았습니다.

```
Skill Layer   (skills/)   ← 시나리오별 진입점, 슬래시 커맨드
     ↓                         ↑
Agent Layer   (agents/)   ← 관점별 페르소나, 병렬 실행되는 서브에이전트
     ↓                         ↑
Tool Layer    (tools/)    ← 정밀 계산, 데이터 검증 (결정론적 스크립트)
     ↓                         ↑
Report Layer  (reports/)  ← 원장·산출물 — 스킬 실행 간 상태를 이어주는 단일 소스
```

위쪽 화살표(`↑`)가 나타내듯, `reports/`는 결과물을 쌓아두기만 하는 곳이 아니라 다음 스킬
호출이 다시 읽어들이는 입력이기도 합니다 (아래 Report Layer 참고).

## Skill Layer

- `skills/*.md` 하나당 하나의 슬래시 커맨드
- "무엇을, 어떤 순서로, 어떤 에이전트를 몇 개나 병렬로 불러서" 할지 정의
- 비용이 큰 스킬(다중 에이전트 풀 리서치)과 비용이 작은 스킬(단일 스크리닝)을 구분해서, 저비용 스킬로 먼저 후보를 거른 뒤에만 고비용 스킬을 쓰도록 유도

## Agent Layer

- `agents/*.md` 하나당 하나의 관점(페르소나)
- 서로 다른 판단 기준을 갖도록 설계 — 의견이 갈리는 것 자체가 유의미한 신호가 되게 함
- 스킬이 실행될 때 서브에이전트(예: Task 도구, `run_in_background: true`)로 동시에 여러 개 띄우고, 각 에이전트는 완료 후 결과를 조율자(team-lead 역할을 하는 메인 에이전트)에게 보고
- 데이터는 최소 2개 이상 독립 출처로 교차검증, 출처별 신뢰도를 🟢/🟡/🔴로 태깅
- 웹 검색 등 외부 접근이 막히면 학습 지식으로 대체 답변하지 않고 명시적으로 "미확인" 표시

## Tool Layer

- `tools/*.py`(또는 다른 언어) — 서술(LLM)과 계산을 분리
- 부동소수점 오차, 단위 혼동(예: 통화 단위) 같은 실수를 원천 차단
- CLI로 호출 가능해야 하며, 에이전트는 결과를 그대로 인용

## Report Layer

- `reports/*.md` — 스킬 실행 결과와 원장(ledger)을 보관. Skill/Agent/Tool 세 계층이
  "그때그때 계산"에 집중한다면, 이 계층은 "그 결과를 다음 실행이 다시 참고할 수 있게"
  이어주는 역할을 한다.
- **원장 2종**: `positions.md`(보유 포지션), `watchlist.md`(관심 종목) — 실제 데이터만
  기록하며, `/position-review`·`/screen`이 인자 없이 호출되면 이 표를 조회 대상으로 삼는다.
  `/post-mortem`은 같은 원장의 "청산가" 칸을 조회해 실현 손익을 계산한다.
- **실행 산출물**: `/trade-team`·`/position-review`·`/post-mortem` 실행 결과는 각각
  `reports/<날짜>-<티커>-<스킬명>.md`로 저장된다. `/position-review`가 최초 테제를 조회할 때
  (원장에 링크가 없으면) `trade-team` 리포트를 이 파일명 규칙으로 찾고, `/post-mortem`도
  귀인 분석을 위해 같은 방식으로 최초 `trade-team` 리포트를 찾는다.
- **예시 문서**: `reports/examples/`에만 가상 데이터를 두어, 실제 원장/리포트와 절대 섞이지
  않게 분리한다.
- 이 계층 덕분에 스킬들이 서로 독립적으로 실행돼도(`/screen` → `/trade-team` →
  `/position-review` → `/post-mortem`) 매번 사용자에게 같은 정보를 다시 물어보지 않는다.

## 부가 계층 — 구조 검증 (`scripts/`)

- `scripts/check_skills.py`가 `skills/*.md`의 프론트매터·헤딩 규칙을 검증하고 CI(`.github/workflows/test.yml`)에 연결되어 있다.
- Skill/Agent/Tool/Report 네 계층이 스스로를 실행하는 쪽이라면, 이 스크립트는 그 계층들의
  구조가 문서화된 규칙(`skills/README.md`)에서 벗어나지 않았는지 자동으로 지키는 가드레일이다.

## 종합 원칙

1. 명확한 판정 — 애매한 절충 답변 대신 구조화된 결론(예: Pass/Fail/Gray Zone) 출력
2. 다중 관점 충돌 — 여러 에이전트의 의견 불일치를 감추지 않고 그대로 노출
3. 재현 가능성 — 같은 입력에는 구조적으로 일관된 프로세스로 답을 냄
4. 비용 계층화 — 깊은 리서치는 필요할 때만, 그 전에 저비용 스킬로 필터링
5. 상태 연속성 — 스킬 실행 결과는 `reports/`에 남아 다음 실행이 다시 참고할 수 있어야 함

## 참고

이 구조는 [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire)의 3계층 설계(Skill/Agent/Tool)를 벤치마킹했습니다.
