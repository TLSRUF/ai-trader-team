> ⚠️ **예시 목적 문서입니다. 실제 데이터가 아닙니다.** 아래 티커(`DEMO-A`~`DEMO-D`)와 모든 수치는 `skills/screen.md`의 출력 포맷을 보여주기 위해 만든 가상 값입니다. 실제 투자 판단에 사용하지 마세요.

# /screen 결과 (2026-08-22, 예시)

입력: `/screen DEMO-A DEMO-B DEMO-C DEMO-D`

| 티커 | 판정 | 탈락/주의 사유 |
|---|---|---|
| DEMO-A | Pass | 7개 메트릭 모두 통과. 손절가능여부: 진입 50 / 손절 45 / 목표 65 → risk-reward 3.00 (기준 1:2 이상 충족) |
| DEMO-B | Fail | 유동성 부족 — 최근 20일 평균 거래대금이 목표 포지션 대비 기준 미달 |
| DEMO-C | Watch | 다른 6개 메트릭 통과, 단 3일 내 실적발표 임박 — 발표 후 재평가 권장 |
| DEMO-D | Fail | 변동성 과도 — ATR%가 리스크 관리 가능 범위를 초과해 손절선 설정 불가 |

## 계산 근거 (DEMO-A, 손절가능여부 항목)

```
$ python tools/trading_rigor.py risk-reward --entry 50 --stop 45 --target 65
{
  "direction": "long",
  "risk": "5",
  "reward": "15",
  "risk_reward_ratio": "3.00"
}
```

## 다음 단계

Pass 판정 종목만 `/trade-team <티커>`로 이어서 심층 분석하세요.

(예시이므로 실제로는 `DEMO-A`에 대해 `/trade-team DEMO-A`를 실행하는 흐름 — 그 결과 예시는 [`trade-team-example.md`](trade-team-example.md) 참고)
