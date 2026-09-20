# 비슷한 프로젝트와 비교

Claude Code용 투자/트레이딩 스킬·프레임워크는 이미 여러 개 있습니다. 이 문서는 그중 대표적인
것들과 이 저장소가 실제로 어떻게 다른지(그리고 어떻게 안 다른지) 정리합니다. 조사는 각
저장소의 공개 README·코드를 직접 읽고 작성했으며, 확인 못한 내부 구현은 "불명확"으로
남겨둡니다 — 확인 안 된 걸 우리가 더 낫다는 근거로 쓰지 않습니다.

## 요약 표

| 프로젝트 | 스타 | 플랫폼 | 핵심 설계 | 백테스트 | 결정론적 계산 계층 | 실적 공개 |
|---|---|---|---|---|---|---|
| **AI Trader Team** (이 저장소) | 2 | Claude Code | 4관점(추세·매크로·리스크·수급) 병렬 논쟁, 절충 없이 Gray Zone 명시 + 수렴했을 때만 집계 역방향 검증 | ✅ walk-forward, 실제 연도별 수치 공개 | ✅ `Decimal` 기반, `tools/trading_rigor.py` | ❌ (실거래 없음, 백테스트만) |
| [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire) | 16,460 | Claude Code / Codex | 가치투자 4대가(버핏·멍거·돤융핑·리루) 관점 대립형 멀티에이전트 | 미구현 — README 자체에 "히스토리컬 백테스트: AI연구 vs 실제 주가"가 체크 안 된 로드맵 항목으로 남아있음 | ✅ `Decimal` 기반, `tools/financial_rigor.py` | ✅ 실계좌 스크린샷 공개 (2024 +69.29%, 2025 +66.38%, 자체 공개 수치) |
| [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) | 2,865 | Claude Code | 워크플로우 매니페스트로 스킬을 조합(시장점검·포트폴리오리뷰·스윙스크리닝·매매일지) | `backtest-expert` 스킬 존재 (세부 방식 불명확) | 불명확, README에 명시 없음 | ❌ (자동매매·시그널 서비스 아님을 명시) |
| [himself65/finance-skills](https://github.com/himself65/finance-skills) | 3,333 | Claude Code/Codex/Cursor 등 범용 | 밸류에이션·소셜리더 등 개별 스킬 라이브러리. 여러 관점이 논쟁하는 구조 아님 | 명시 없음 | 명시 없음 | ❌ |
| [quant-sentiment-ai/claude-equity-research](https://github.com/quant-sentiment-ai/claude-equity-research) | 713 | Claude Code (Plugin) | 단일 에이전트가 골드만삭스 스타일 buy/sell/hold 리포트 하나로 종합 | ❌ | ❌ | ❌ |
| [RKiding/Awesome-finance-skills](https://github.com/RKiding/Awesome-finance-skills) | 3,022 | Claude Code 등 | 뉴스·시그널·리포팅 등 스킬 모음집. 프레임워크보다 라이브러리에 가까움 | 명시 없음 | 명시 없음 | ❌ |

(스타 수는 2026-09-20 기준. 시간이 지나면 바뀝니다.)

## 우리가 실제로 다른 지점

**1. 절충하지 않는 것 자체를 구조화했다.** `/trade-team`은 4개 관점(`agents/*.md`)의 점수·태그가
갈리면 그 즉시 **Gray Zone**으로 확정하고, 잠정 판정이 이미 수렴했을 때만 그 위에 "집계
역방향 검증"(4개 보고서의 반증을 합쳐 새로운 복합 리스크가 있는지 재확인)을 한 번 더
거칩니다. `xbtlin/ai-berkshire`도 "4대가 관점 대립"을 명시적으로 표방하지만, 공개된 README만으로는
최종적으로 하나의 매수/보류/매도 판단에 항상 수렴하는지, 우리처럼 "판정 자체를 갈라놓는" 결과를
허용하는지 확인할 수 없었습니다 — 이 부분은 단정하지 않습니다.

**2. 백테스트는 우리가 유일하게 실제로 구현·공개했습니다.** 위 표의 5개 프로젝트 중
백테스트를 명시한 곳은 `xbtlin/ai-berkshire`(로드맵 미체크 항목)와 `tradermonty/claude-trading-skills`
(`backtest-expert` 스킬 존재, 세부 미공개) 둘뿐이고, 실제 연도별 수치를 공개한 곳은
없습니다. 우리는 `tools/backtest.py`로 workforward 검증을 실행 가능한 코드로 제공하고,
2022–2025년 S&P500 대비 실제 수치를 README에 공개합니다. 다만 이건 **LLM의 정성적 판단을
재현하지 않는**, 규칙화 가능한 부분(이동평균 돌파 + 고정%손절)만 뗀 백테스트라는 한계가
README·`docs/architecture.md`에 명시돼 있습니다 — 4-agent 판단 자체의 과거 성과를 보장하지
않습니다.

**3. 결정론적 계산 계층은 우리와 `ai-berkshire`만 명시적으로 분리합니다.** 둘 다
`Decimal` 기반 계산 스크립트(우리는 `tools/trading_rigor.py`, 그쪽은
`tools/financial_rigor.py`)로 LLM이 암산하지 않게 설계했습니다. 이건 우연이 아니라, 이
저장소의 3계층(Skill/Agent/Tool) 설계 자체가 `ai-berkshire`를 벤치마킹해서 나온 결과입니다
(`docs/architecture.md` 참고). 나머지 프로젝트들은 README에 이런 분리를 명시하지 않았습니다.

## 우리가 밀리는 지점 (숨기지 않습니다)

**`xbtlin/ai-berkshire`는 실계좌 스크린샷을 공개합니다.** 백테스트보다 훨씬 강한 신뢰
신호입니다. 우리는 이 길을 의도적으로 가지 않습니다 — `SECURITY.md`에 명시된 대로 이
프로젝트는 실거래 API 키를 다루지 않고 자금 이동·주문 실행 기능이 없습니다. 이건
트레이드오프이지 우리가 더 우월하다는 뜻이 아닙니다: 실계좌 실적은 (검증 가능하다면) 더
강력한 증거이고, 백테스트는 재현 가능하지만 실제 자금의 심리적·집행 리스크를 반영하지
못합니다.

**규모도 다릅니다.** `xbtlin/ai-berkshire`(16.4천 스타), `tradermonty/claude-trading-skills`
(2.9천), `himself65/finance-skills`(3.3천), `RKiding/Awesome-finance-skills`(3천) 모두 이
저장소(2스타)보다 훨씬 크고 오래 검증된 프로젝트입니다. 이 문서는 "우리가 더 크다"는
주장이 아니라 "설계가 어떻게 다른가"에 대한 것입니다.

## 참고하지 않은 것

[NoFxAiOS/nofx](https://github.com/NoFxAiOS/nofx)(1.3만 스타)는 표에서 뺐습니다 — Claude
Code 스킬이 아니라 실거래소 9곳에 실제 API 키로 자동매매 주문을 내는 독립 트레이딩
터미널이라, 비교 대상이 아니라 범주 자체가 다릅니다. `SECURITY.md`가 명시한 이 프로젝트의
범위(실거래 없음)와 정반대이기 때문에 기능을 참고하지 않았고, README 프레젠테이션(배너·데모
이미지) 스타일만 별도로 참고했습니다.

## 방법론

각 프로젝트의 GitHub API 메타데이터(스타·최신 커밋)와 공개 README를 2026-09-20에 직접
읽고 작성했습니다. 비공개 코드나 실제 사용 경험은 반영하지 못했습니다. 오류나 오래된 정보를
발견하면 [이슈](https://github.com/TLSRUF/ai-trader-team/issues)로 알려주세요.
