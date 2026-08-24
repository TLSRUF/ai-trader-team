# AI Trader Team

[![Test](https://github.com/TLSRUF/ai-trader-team/actions/workflows/test.yml/badge.svg?branch=dev)](https://github.com/TLSRUF/ai-trader-team/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](requirements.txt)
[![Skills](https://img.shields.io/badge/skills-5-informational.svg)](skills/)
[![Agents](https://img.shields.io/badge/agents-4-informational.svg)](agents/)

English | [한국어](README.md)

A framework for giving one person a professional-grade investment research team, built on AI agents. It's organized into three layers: slash commands (skills) → parallel sub-agents (perspective-based personas) → deterministic verification tools.

> ⚠️ For educational and research purposes only. This is not investment advice — the final judgment and responsibility are always the user's own.

## Who this is for

- **Swing traders** — quickly filter candidates with `/screen`, then get a 4-perspective (trend / macro / risk / flow) cross-check with `/trade-team` before entry.
- **Long-term holders** — periodically re-verify whether the original thesis behind an open position still holds with `/position-review`.
- **Strategy validators** — instead of relying on qualitative judgment, confirm whether a rule-based strategy is overfit using `tools/backtest.py`'s walk-forward validation.
- **Claude Code users** — already comfortable with Claude Code workflows and looking for a reference design that combines skills, sub-agents, and deterministic tools.

## Architecture

```
Skill Layer   (skills/)   ← per-scenario entry points
     ↓                        ↑
Agent Layer   (agents/)   ← parallel perspective sub-agents
     ↓                        ↑
Tool Layer    (tools/)    ← precise calculation · data verification
     ↓                        ↑
Report Layer  (reports/)  ← ledgers/artifacts, state re-read by the next run
```

See [docs/architecture.md](docs/architecture.md) for a detailed breakdown of each layer.

## Installation

```bash
git clone https://github.com/TLSRUF/ai-trader-team.git
cd ai-trader-team
pip install -r requirements.txt   # required for live/historical quotes (market_data.py)
./scripts/install-claude-commands.sh
```

Opening this repository in Claude Code makes the `/screen`, `/trade-team`, `/position-review`, `/portfolio`, and `/post-mortem` slash commands available immediately.

```
/screen AAA BBB CCC     # cheap first-pass screening to narrow down candidates
/screen                 # with no arguments, screens the entire reports/watchlist.md
/trade-team AAA         # deep 4-agent analysis, only for tickers that passed screening
/position-review AAA    # periodically re-check whether the original thesis still holds after entry
/portfolio               # real-time dashboard of quotes and unrealized P&L across all open positions
/post-mortem AAA         # review realized P&L (R-multiple) and judgment attribution after exit
```

**Recommended flow**: filter candidates with `/screen` → deep-dive the ones that passed with `/trade-team` to decide on entry → after entry, periodically check for thesis drift with `/position-review` and track real-time P&L with `/portfolio` → after exit, review with `/post-mortem`. Open positions and watchlist tickers are kept as ledgers in `reports/positions.md` and `reports/watchlist.md` respectively, and are automatically read back in on the next run.

## Backtesting (`tools/backtest.py`)

Separate from the 4-agent qualitative judgment (the skills above), this tool validates a mechanical trend-following strategy — built purely from the deterministic rules this project already has — against historical data. **It does not reproduce an LLM's qualitative judgment** — the news and context available at each point in time can't be replayed. Instead, it's used to check how robust an approximate strategy ("SMA breakout + fixed % stop + fixed R:R target") is across asset classes and time periods.

```bash
# Simple run — with friction cost (commission + slippage approximation) applied
python tools/backtest.py run --tickers '["AAPL","MSFT","NVDA"]' \
    --start 2023-01-01 --end 2026-08-01 --friction-pct 0.1

# With a concurrent-position capital constraint (portfolio heat limit)
python tools/backtest.py run --tickers '["AAPL","MSFT","NVDA"]' \
    --start 2023-01-01 --end 2026-08-01 --max-heat-pct 6

# Walk-forward validation — select parameters only on the in-sample window,
# then apply them blind to the next, never-seen window to check for overfitting
python tools/backtest.py walk-forward --tickers '["AAPL","MSFT","NVDA"]' \
    --start 2022-01-01 --end 2026-08-01 --window-months 12 --step-months 6
```

For actual validation results, see `reports/2026-08-23-backtest-comparison.md` (parameter tuning on large-cap US equities) and `reports/2026-08-23-backtest-crypto-extension.md` (crypto extension — concluding that the same strategy does not generalize across asset classes).

## Sample output

`/trade-team` runs four perspective sub-agents in parallel and synthesizes them into a single report, like this (excerpted from [reports/examples/trade-team-example.md](reports/examples/trade-team-example.md) — this is example data, not real; do not use it for actual investment decisions):

| Perspective | Tag | Score | Key rationale |
|---|---|---|---|
| Trend | Bull | 4/5 | Bullish alignment across multiple timeframes, breakout confirmed with volume |
| Macro | Neutral | 3/5 | Liquidity environment is favorable, but sector rotation direction conflicts |
| Risk | Bear | 2/5 | Large historical drawdowns in similar past regimes; already holding a highly correlated position |
| Flow | Bull | 4/5 | Confirmed net buying flow and unusual volume; options positioning is neutral |

> **One-line conclusion**: 3 of 4 perspectives (trend, macro, flow) are positive, but the risk manager objects on the basis of a loss scenario — a genuine **Gray Zone** requiring a judgment call on whether to size down or wait for the risk signal to clear.

This kind of disagreement (Gray Zone) is by design, not a bug — the four agents are answering different questions ("will the price go up?" vs. "can this account's context absorb a loss?"), so a natural split in conclusions is expected. The final call always stays with the user. Real output examples for the other skills are all available in [reports/examples/](reports/examples/).

## Folder structure

| Folder | Role |
|---|---|
| `skills/` | Slash command definitions (canonical source) |
| `agents/` | Perspective-based agent persona definitions |
| `tools/` | Deterministic calculation/verification scripts |
| `reports/` | Run output reports, open-position/watchlist ledgers |
| `scripts/` | Install · sync scripts |
| `docs/` | Design documents |
| `tests/` | Tests for `tools/` and `scripts/` scripts |

## Contributing

All work follows **issue → topic branch → PR**. See [CONTRIBUTING.md](CONTRIBUTING.md) (Korean) for the full ruleset.

## License

[MIT](LICENSE)

## Credits

The three-layer architecture was benchmarked against [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire).
