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
| [`trading_rigor.py`](trading_rigor.py) | 시세/지표 교차검증, 리스크 기반 포지션 사이징, 리스크·리워드 비율 계산. `Decimal` 기반, 외부 의존성 없음, CLI(`argparse`)로 직접 실행 가능 |

```bash
python tools/trading_rigor.py cross-validate --field price --values '{"소스A": 101.2, "소스B": 101.5}'
python tools/trading_rigor.py position-size --account 10000 --risk-pct 1 --entry 100 --stop 95
python tools/trading_rigor.py risk-reward --entry 100 --stop 95 --target 115
```

교차검증에서 편차 경고가 하나라도 있으면 종료 코드 1을 반환합니다 (스크립트에서 감지하기 쉽도록).
