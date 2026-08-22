# tests/

`tools/`, `scripts/`의 계산/검증 스크립트에 대한 테스트를 담습니다.

## 현재 테스트

| 파일 | 대상 |
|---|---|
| [`test_trading_rigor.py`](test_trading_rigor.py) | `tools/trading_rigor.py` — 교차검증, 포지션 사이징, 리스크·리워드, 상관관계, 포트폴리오 히트 계산 |
| [`test_check_skills.py`](test_check_skills.py) | `scripts/check_skills.py` — 프론트매터 파싱, 스킬 파일 구조 검증 |

개별 실행:

```bash
python -m unittest tests/test_trading_rigor.py -v
python -m unittest tests/test_check_skills.py -v
```

전체 실행 (CI와 동일):

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
