# tools/

이 폴더는 LLM 서술과 분리된 **결정론적 계산/검증 스크립트**를 담습니다. 금액·비율·밸류에이션처럼 정확도가 중요한 계산은 여기 스크립트로 수행하고, 에이전트는 결과를 인용만 합니다.

## 규칙

- 외부 의존성 최소화 (가능하면 표준 라이브러리만 사용)
  - **예외**: 실시간/과거 "시세 조회"는 표준 라이브러리로 할 수 없는 일이라, `market_data.py` 한 파일에만 `yfinance`(무료, API 키 불필요)를 허용한다. 계산 계층(`trading_rigor.py`)은 계속 의존성 없이 유지한다 — `requirements.txt` 참고.
- 부동소수점 오차가 문제되는 계산은 `Decimal` 등 정확한 타입 사용
- CLI로 직접 실행 가능해야 함 (에이전트가 Bash로 호출)
- 각 스크립트는 입력/출력 형식을 문서 상단 docstring에 명시

## 현재 구현된 도구

| 파일 | 설명 |
|---|---|
| [`trading_rigor.py`](trading_rigor.py) | 시세/지표 교차검증, 리스크 기반 포지션 사이징(고정 비율/켈리 기준), 리스크·리워드 비율, 실현 손익(R-멀티플), 두 시계열 간 상관계수, 포트폴리오 전체 리스크(히트) 계산. `Decimal` 기반, 외부 의존성 없음, CLI(`argparse`)로 직접 실행 가능 |
| [`market_data.py`](market_data.py) | `yfinance`로 실시간 현재가·과거 일별 종가를 조회. 계산은 하지 않고 조회한 값을 Decimal 문자열로 반환만 함 — 이후 계산은 `trading_rigor.py`를 거친다 |
| [`positions_ledger.py`](positions_ledger.py) | `reports/positions.md` 표를 파싱해 행 딕셔너리 리스트로 반환하는 공용 유틸 (`trading_rigor.py`·`portfolio_dashboard.py`가 공유) |
| [`portfolio_dashboard.py`](portfolio_dashboard.py) | 보유 포지션 전체의 실시간 시세·미실현 손익·포트폴리오 히트를 한 번에 계산 (`market_data.py` + `trading_rigor.py` 조합, 순수 집계라 LLM 판단 없음) |
| [`backtest.py`](backtest.py) | 기계적 추세추종 전략(SMA 상향 돌파 진입 + 고정% 손절 + 고정 R:R 목표가)을 과거 데이터로 시뮬레이션. **주의**: AI Trader Team의 4-agent 정성적 판단을 재현하지 않는다 — 아래 설명 참고 |

```bash
python tools/market_data.py quote --ticker AAPL
python tools/market_data.py history --ticker AAPL --start 2023-01-01 --end 2023-12-31
```

`quote`는 현재가(또는 가장 최근 종가)를, `history`는 기간별 일별 종가(배당·분할 조정됨)를 조회합니다. `pip install -r requirements.txt`로 `yfinance`를 먼저 설치해야 합니다. 존재하지 않는 티커·네트워크 실패 시 트레이스백 대신 `오류: ...` 메시지와 종료 코드 1을 반환합니다.

```bash
python tools/portfolio_dashboard.py
python tools/portfolio_dashboard.py --positions-file reports/positions.md
```

`portfolio_dashboard.py`는 `reports/positions.md`의 "보유중" 행 전체에 대해 실시간 시세를 조회하고 미실현 손익(R-멀티플)·포트폴리오 히트를 계산해 JSON으로 반환합니다. 한 티커의 시세 조회가 실패해도(네트워크 문제, 상장폐지 등) 전체가 멈추지 않고 그 티커만 `errors`에 기록한 뒤 나머지를 계속 처리합니다. `/portfolio` 스킬이 이 스크립트 하나만 호출해서 결과를 표로 옮깁니다.

```bash
python tools/trading_rigor.py cross-validate --field price --values '{"소스A": 101.2, "소스B": 101.5}'
python tools/trading_rigor.py position-size --account 10000 --risk-pct 1 --entry 100 --stop 95
python tools/trading_rigor.py kelly --win-rate 55 --avg-win 200 --avg-loss 100
python tools/trading_rigor.py risk-reward --entry 100 --stop 95 --target 115
python tools/trading_rigor.py realized-pnl --entry 100 --stop 95 --target 115 --exit 110
python tools/trading_rigor.py unrealized-pnl --entry 100 --stop 95 --target 115 --current 108
python tools/trading_rigor.py correlation --series-a '[1, 2, 3, 4, 5]' --series-b '[2, 3, 5, 4, 6]'
python tools/trading_rigor.py portfolio-heat --risk-pcts '[1, 1.5, 2]' --max-heat-pct 6
python tools/trading_rigor.py portfolio-heat --positions-file reports/positions.md --max-heat-pct 6
```

`kelly`는 승률(%)과 손익비(평균 승리/평균 손실)로 켈리 기준 최적 베팅 비율을 계산합니다. 전액 켈리(`full_kelly_pct`)는 파산 위험이 커서 실전에서 그대로 쓰지 않는 것이 일반적이므로, 흔히 쓰이는 half-Kelly·quarter-Kelly도 함께 반환합니다. 비율이 0 이하면(통계적 우위 없음) 경고와 함께 종료 코드 1을 반환합니다. `position-size`가 사용자가 정한 고정 리스크 비율로 사이징한다면, `kelly`는 과거 성과(예: `/post-mortem`으로 쌓인 승/패 기록)로부터 비율을 역산합니다.

`realized-pnl`은 청산된 포지션의 실제 청산가를 계획했던 리스크(1R = |진입가-손절가|) 대비 R-멀티플로 환산합니다. 가격 등락률이 아니라 "계획한 리스크 대비 실제 성과"로 승패(win/loss/breakeven)를 일관되게 비교할 때 사용하며, 청산 후 회고를 위한 기반 계산입니다. `unrealized-pnl`은 계산 로직이 완전히 동일하되 **아직 청산되지 않은** 포지션에 쓰는 버전입니다(현재가를 넘김) — `/portfolio` 대시보드가 사용합니다. 청산을 암시하는 "win/loss" 대신 `status`가 profit/loss/breakeven으로 나옵니다.

`correlation`은 피어슨 상관계수(-1~1)와 함께 낮음(<0.3)/중간(0.3~0.7)/높음(≥0.7) 등급을 절대값 기준으로 반환합니다. 리스크 관리자가 "기존 보유 포지션과의 분산 효과"를 감이 아니라 수치로 판정할 때 사용합니다.

`portfolio-heat`는 보유 포지션 각각의 계좌 대비 리스크%를 합산해, 모든 포지션이 동시에 손절될 경우 계좌가 잃는 비율(포트폴리오 히트)을 계산합니다. `--risk-pcts`로 직접 JSON 배열을 넘기거나(둘 중 하나 필수), `--positions-file reports/positions.md`로 원장을 넘기면 "상태"가 "보유중"인 행의 계좌리스크%를 자동으로 읽어들입니다 — 후자를 쓰면 값을 매번 손으로 다시 입력할 필요가 없습니다. 한도(기본 6%)를 초과하면 경고와 함께 종료 코드 1을 반환합니다.

교차검증에서 편차 경고가 하나라도 있으면 종료 코드 1을 반환합니다 (스크립트에서 감지하기 쉽도록).

```bash
python tools/backtest.py run --ticker AAPL --start 2024-01-01 --end 2025-01-01
python tools/backtest.py run --tickers '["AAPL", "MSFT", "NVDA"]' \
    --start 2024-01-01 --end 2025-01-01 --sma-window 20 --stop-pct 5 --target-r 2 --risk-pct 1
```

`backtest.py`는 이동평균(기본 20일) 상향 돌파를 진입 신호로, 고정 손절%(기본 5%)와 고정 목표 R-멀티플(기본 2R)을 청산 규칙으로 쓰는 기계적 전략을 시뮬레이션합니다. 여러 티커를 바스켓으로 넘기면 모든 거래를 청산일 순으로 합쳐 거래당 계좌 리스크%(기본 1%)만큼 복리로 누적한 총수익률을 계산합니다.

> ⚠️ **`backtest.py`는 AI Trader Team의 4-agent 정성적 판단(`agents/*.md`)을 재현하지 않습니다.** 그 판단은 매번 LLM이 웹검색으로 그 시점의 최신 데이터를 확인하는 구조라, 과거 특정 시점의 시장/뉴스 상황을 재현해서 "그때 이 AI가 어떻게 판단했을지"를 기계적으로 재실행하는 건 불가능합니다(과거 데이터 재현 불가, 매 시점 LLM 재실행 비용도 비현실적). 대신 이 프로젝트가 갖춘 결정론적 규칙(`position-size`/`risk-reward`가 표현하는 방식)만 떼어낸 근사 전략입니다 — 결과를 해석할 때 이 한계를 항상 함께 고려하세요.
