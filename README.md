# AI Trader Team

[![Test](https://github.com/TLSRUF/ai-trader-team/actions/workflows/test.yml/badge.svg?branch=dev)](https://github.com/TLSRUF/ai-trader-team/actions/workflows/test.yml)

개인이 AI 에이전트를 통해 전문 수준의 투자 리서치 팀을 갖추기 위한 프레임워크입니다. 슬래시 커맨드(스킬) → 병렬 서브에이전트(관점별 페르소나) → 결정론적 검증 도구, 3계층으로 구성됩니다.

> ⚠️ 교육 및 연구 목적입니다. 투자자문이 아니며, 최종 판단과 책임은 사용자 본인에게 있습니다.

## 아키텍처

```
Skill Layer   (skills/)   ← 시나리오별 진입점
     ↓                        ↑
Agent Layer   (agents/)   ← 관점별 병렬 서브에이전트
     ↓                        ↑
Tool Layer    (tools/)    ← 정밀 계산 · 데이터 검증
     ↓                        ↑
Report Layer  (reports/)  ← 원장·산출물, 다음 실행이 다시 읽어들이는 상태
```

계층별 자세한 설명은 [docs/architecture.md](docs/architecture.md)를 참고하세요.

## 설치

```bash
git clone https://github.com/TLSRUF/ai-trader-team.git
cd ai-trader-team
./scripts/install-claude-commands.sh
```

Claude Code에서 이 저장소를 열면 `/screen`, `/trade-team`, `/position-review` 슬래시 커맨드를 바로 사용할 수 있습니다.

```
/screen AAA BBB CCC     # 저비용 스크리닝으로 후보를 먼저 거르고
/screen                 # 인자 생략 시 reports/watchlist.md 전체를 스크리닝
/trade-team AAA         # Pass한 종목만 4-agent 심층 분석
/position-review AAA    # 진입 후 주기적으로 최초 테제가 아직 유효한지 재점검
```

**권장 흐름**: `/screen`으로 후보를 거르고 → Pass한 종목만 `/trade-team`으로 심층 분석해서 진입 판단하고 → 진입 후에는 `/position-review`로 테제 드리프트를 주기적으로 점검합니다. 보유 포지션과 관심 종목은 각각 `reports/positions.md`, `reports/watchlist.md`에 원장으로 남아 다음 실행 때 자동으로 조회됩니다.

## 폴더 구조

| 폴더 | 역할 |
|---|---|
| `skills/` | 슬래시 커맨드 정의 (canonical source) |
| `agents/` | 관점별 에이전트 페르소나 정의 |
| `tools/` | 결정론적 계산/검증 스크립트 |
| `reports/` | 실행 결과 리포트, 보유 포지션/워치리스트 원장 |
| `scripts/` | 설치 · 동기화 스크립트 |
| `docs/` | 설계 문서 |
| `tests/` | `tools/`, `scripts/` 스크립트 테스트 |

## 기여

작업은 항상 **이슈 → 토픽 브랜치 → PR** 순서를 따릅니다. 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)

## 참고

3계층 아키텍처는 [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire)를 벤치마킹했습니다.
