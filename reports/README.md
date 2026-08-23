# reports/

`/screen`, `/trade-team` 등 스킬을 실제로 실행해서 나온 리서치 산출물을 보관하는 폴더입니다.

## 규칙

- 실제 실행 결과만 이 폴더 루트에 저장한다. 파일명에 티커와 기준일을 포함한다 (예: `2026-08-22-AAPL-trade-team.md`).
- **가상/예시 문서는 반드시 `reports/examples/`에만 둔다.** 실제 리포트와 섞이지 않게 분리한다.
- 예시 문서는 실제 시장 데이터를 지어내지 않는다 — 가상 티커와 가상 수치만 사용하고, 문서 상단에 "예시 목적, 실제 데이터 아님"을 명시한다. 실제 종목에 대해 만든 값을 사실처럼 적으면 이 프로젝트의 핵심 원칙(모르는 것을 아는 것처럼 채우지 않는다)에 정면으로 위배된다.
- `positions.md`(보유 포지션 원장)는 실제 데이터만 기록한다. 진입 시 행을 추가하고, 청산 시 행을 삭제하지 않고 상태만 갱신한다 (규칙은 해당 파일 참고).
- `watchlist.md`(관심 종목 워치리스트)도 실제 데이터만 기록한다. `/screen`을 인자 없이 호출하면 이 표의 티커 전체가 대상이 된다 (규칙은 해당 파일 참고).

## 현재 내용

| 폴더/파일 | 설명 |
|---|---|
| [`positions.md`](positions.md) | 보유 포지션 원장 — `/position-review`가 최초 테제를 조회할 때 1순위로 참고 |
| [`watchlist.md`](watchlist.md) | 관심 종목 워치리스트 — `/screen` 인자 생략 시 대상 티커 조회 |
| [`examples/screen-example.md`](examples/screen-example.md) | `/screen` 출력 포맷 예시 (가상 데이터) |
| [`examples/trade-team-example.md`](examples/trade-team-example.md) | `/trade-team` 출력 포맷 예시, Gray Zone 판정 포함 (가상 데이터) |
| [`examples/position-review-example.md`](examples/position-review-example.md) | `/position-review` 출력 포맷 예시, trade-team-example.md의 DEMO-A를 이어받은 드리프트 판정 (가상 데이터) |

실제 리포트는 아직 없습니다 — 스킬을 실제로 실행하면 이 폴더 루트에 쌓입니다.
