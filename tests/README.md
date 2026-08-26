# tests/

`tools/`, `scripts/`의 계산/검증 스크립트에 대한 테스트를 담습니다.

## 현재 테스트

| 파일 | 대상 |
|---|---|
| [`test_trading_rigor.py`](test_trading_rigor.py) | `tools/trading_rigor.py`의 순수 함수 — 교차검증, 포지션 사이징(고정 비율/켈리 기준), 리스크·리워드, 실현/미실현 손익(R-멀티플), 상관관계, 포트폴리오 히트 계산 |
| [`test_trading_rigor_cli.py`](test_trading_rigor_cli.py) | `tools/trading_rigor.py`의 `main()`(CLI 진입점) — 서브커맨드 디스패치, JSON 파싱 에러, mutually-exclusive 그룹, 경고 시 종료 코드 |
| [`test_check_skills.py`](test_check_skills.py) | `scripts/check_skills.py` — 프론트매터 파싱, 스킬 파일 구조 검증, `.claude/commands/*.md` 동기화 검증 |
| [`test_check_agents.py`](test_check_agents.py) | `scripts/check_agents.py` — 에이전트 파일 필수 헤딩 검증 |
| [`test_market_data.py`](test_market_data.py) | `tools/market_data.py` — 시세 파싱·에러 처리 (`unittest.mock`으로 yfinance를 모킹, 실제 네트워크 호출 없음) |
| [`test_positions_ledger.py`](test_positions_ledger.py) | `tools/positions_ledger.py` — 원장 표 파싱 |
| [`test_portfolio_dashboard.py`](test_portfolio_dashboard.py) | `tools/portfolio_dashboard.py` — 집계 로직, 부분 실패 처리 (`market_data.get_quote`를 모킹, 실제 네트워크 호출 없음) |
| [`test_backtest.py`](test_backtest.py) | `tools/backtest.py` — 진입/청산(손절·목표·타임아웃·데이터 종료)·다중 티커 집계 로직 (손으로 만든 고정 가격 시계열, 실제 네트워크 호출 없음) |

개별 실행:

```bash
python -m unittest tests/test_trading_rigor.py -v
python -m unittest tests/test_trading_rigor_cli.py -v
python -m unittest tests/test_check_skills.py -v
python -m unittest tests/test_check_agents.py -v
python -m unittest tests/test_market_data.py -v
python -m unittest tests/test_positions_ledger.py -v
python -m unittest tests/test_portfolio_dashboard.py -v
python -m unittest tests/test_backtest.py -v
```

전체 실행:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

CI와 동일하게(커버리지 90% 하한선 포함) 실행:

```bash
pip install -r requirements-dev.txt
coverage run --source=tools,scripts -m unittest discover -s tests -p "test_*.py" -v
coverage report -m --fail-under=90
```
