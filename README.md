# AI Trader Team

개인이 AI 에이전트를 통해 전문 수준의 투자 리서치 팀을 갖추기 위한 프레임워크입니다. 슬래시 커맨드(스킬) → 병렬 서브에이전트(관점별 페르소나) → 결정론적 검증 도구, 3계층으로 구성됩니다.

> ⚠️ 교육 및 연구 목적입니다. 투자자문이 아니며, 최종 판단과 책임은 사용자 본인에게 있습니다.

## 아키텍처

```
Skill Layer   (skills/)   ← 시나리오별 진입점
     ↓
Agent Layer   (agents/)   ← 관점별 병렬 서브에이전트
     ↓
Tool Layer    (tools/)    ← 정밀 계산 · 데이터 검증
```

자세한 설명은 [docs/architecture.md](docs/architecture.md)를 참고하세요.

## 폴더 구조

| 폴더 | 역할 |
|---|---|
| `skills/` | 슬래시 커맨드 정의 (canonical source) |
| `agents/` | 관점별 에이전트 페르소나 정의 |
| `tools/` | 결정론적 계산/검증 스크립트 |
| `scripts/` | 설치 · 동기화 스크립트 |
| `docs/` | 설계 문서 |
| `tests/` | `tools/` 스크립트 테스트 |

## 기여

작업은 항상 **이슈 → 토픽 브랜치 → PR** 순서를 따릅니다. 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)

## 참고

3계층 아키텍처는 [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire)를 벤치마킹했습니다.
