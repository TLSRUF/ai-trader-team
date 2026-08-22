# tests/

`tools/`의 계산/검증 스크립트에 대한 테스트를 담습니다.

## 현재 테스트

| 파일 | 대상 |
|---|---|
| [`test_trading_rigor.py`](test_trading_rigor.py) | `tools/trading_rigor.py` — 교차검증, 포지션 사이징, 리스크·리워드 계산 |

실행:

```bash
python -m unittest tests/test_trading_rigor.py -v
```
