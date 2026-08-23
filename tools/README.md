# tools/

이 폴더는 LLM 서술과 분리된 **결정론적 계산/검증 스크립트**를 담습니다. 금액·비율·밸류에이션처럼 정확도가 중요한 계산은 여기 스크립트로 수행하고, 에이전트는 결과를 인용만 합니다.

## 규칙

- 외부 의존성 최소화 (가능하면 표준 라이브러리만 사용)
- 부동소수점 오차가 문제되는 계산은 `Decimal` 등 정확한 타입 사용
- CLI로 직접 실행 가능해야 함 (에이전트가 Bash로 호출)
- 각 스크립트는 입력/출력 형식을 문서 상단 docstring에 명시

## 현재 구현된 도구

| 파일 | 설명 |
|---|---|
| [`trading_rigor.py`](trading_rigor.py) | 시세/지표 교차검증, 리스크 기반 포지션 사이징, 리스크·리워드 비율, 두 시계열 간 상관계수, 포트폴리오 전체 리스크(히트) 계산. `Decimal` 기반, 외부 의존성 없음, CLI(`argparse`)로 직접 실행 가능 |

```bash
python tools/trading_rigor.py cross-validate --field price --values '{"소스A": 101.2, "소스B": 101.5}'
python tools/trading_rigor.py position-size --account 10000 --risk-pct 1 --entry 100 --stop 95
python tools/trading_rigor.py risk-reward --entry 100 --stop 95 --target 115
python tools/trading_rigor.py correlation --series-a '[1, 2, 3, 4, 5]' --series-b '[2, 3, 5, 4, 6]'
python tools/trading_rigor.py portfolio-heat --risk-pcts '[1, 1.5, 2]' --max-heat-pct 6
python tools/trading_rigor.py portfolio-heat --positions-file reports/positions.md --max-heat-pct 6
```

`correlation`은 피어슨 상관계수(-1~1)와 함께 낮음(<0.3)/중간(0.3~0.7)/높음(≥0.7) 등급을 절대값 기준으로 반환합니다. 리스크 관리자가 "기존 보유 포지션과의 분산 효과"를 감이 아니라 수치로 판정할 때 사용합니다.

`portfolio-heat`는 보유 포지션 각각의 계좌 대비 리스크%를 합산해, 모든 포지션이 동시에 손절될 경우 계좌가 잃는 비율(포트폴리오 히트)을 계산합니다. `--risk-pcts`로 직접 JSON 배열을 넘기거나(둘 중 하나 필수), `--positions-file reports/positions.md`로 원장을 넘기면 "상태"가 "보유중"인 행의 계좌리스크%를 자동으로 읽어들입니다 — 후자를 쓰면 값을 매번 손으로 다시 입력할 필요가 없습니다. 한도(기본 6%)를 초과하면 경고와 함께 종료 코드 1을 반환합니다.

교차검증에서 편차 경고가 하나라도 있으면 종료 코드 1을 반환합니다 (스크립트에서 감지하기 쉽도록).
