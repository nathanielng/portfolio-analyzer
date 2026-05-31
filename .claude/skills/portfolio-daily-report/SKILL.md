# portfolio-daily-report

Generate a daily portfolio report for the portfolio-analyzer project: current valuations, unrealized P&L, YTD return, drawdown from peak, and the FRED macro dashboard (rates, VIX, yield curve).

## Project

`~/code/portfolio-analyzer`

## When to use

Invoke `/portfolio-daily-report` when the user wants:
- A snapshot of their current portfolio value and P&L
- The macro regime dashboard (rates, VIX, yield curve)
- To update the peak/YTD snapshot in `data/portfolio_snapshot.json`

## How to run

```bash
cd ~/code/portfolio-analyzer
source ~/.venv/bin/activate
python scripts/daily_report.py
```

With options:
```bash
# Use a specific holdings file
python scripts/daily_report.py --holdings data/holdings.csv

# Skip the FRED/VIX macro fetch (faster, offline)
python scripts/daily_report.py --no-macro
```

## Inputs

| File | Purpose |
|------|---------|
| `data/holdings.csv` | Positions (Symbol, Quantity, AvgCost, Currency, Account, Broker). Falls back to `examples/holdings.csv`. |
| `data/portfolio_snapshot.json` | Persisted peak value and YTD baseline. Auto-created on first run. |
| `FRED_API_KEY` env var | Optional. Unlocks FRED JSON API (higher rate limits). Falls back to keyless CSV endpoint. |

## Outputs

| File | Contents |
|------|----------|
| `output/daily-report-YYYY-MM-DD.md` | Full markdown report |
| `data/portfolio_snapshot.json` | Updated peak and YTD baseline |

Report is also printed to stdout.

## What the report covers

1. **Portfolio Summary** — total value, cost basis, unrealized P&L %, YTD return, max drawdown from peak
2. **Holdings table** — per-position current price, USD value, P&L %
3. **Movers** — top 3 gainers and losers
4. **Macro Dashboard** — 10Y/2Y Treasury yields, 10Y-2Y spread (flags inversion), Fed Funds, WTI crude, VIX

## Data sources (all free)

- **YFinance** — primary price fetcher (handles non-US listings like 2330.TW)
- **Stooq** — US equity fallback if yfinance returns None
- **FRED** — rates, spread, crude, CPI (keyless CSV or JSON API with key)
- **exchangerate-api.com** — spot FX conversion (TWD→USD, SGD→USD, etc.)

## After running

If the user wants to save key insights to Obsidian, suggest `/save-learnings`.
If they want to rebalance based on the new values, suggest `/portfolio-rebalance`.
