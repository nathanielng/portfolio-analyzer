# portfolio-rebalance

Generate rebalancing recommendations for the portfolio-analyzer project: compares current holdings weights against targets, flags drift beyond the ±5pp band, and proposes contributions-first trades.

## Project

`~/code/portfolio-analyzer`

## When to use

Invoke `/portfolio-rebalance` when the user wants:
- To see which positions have drifted outside the rebalance band
- Proposed buy/sell trades to restore target weights
- To plan deployment of new cash (contributions-first to avoid FX churn)

## How to run

```bash
cd ~/code/portfolio-analyzer
source ~/.venv/bin/activate
python scripts/rebalance.py
```

With options:
```bash
# Deploy $5,000 of new cash alongside rebalancing
python scripts/rebalance.py --contribution 5000

# Use a tighter ±3pp band
python scripts/rebalance.py --band 0.03

# Explicit file paths
python scripts/rebalance.py --holdings data/holdings.csv --targets data/targets.csv
```

## Inputs

| File | Purpose |
|------|---------|
| `data/holdings.csv` | Current positions (Symbol, Quantity, AvgCost, Currency). Falls back to `examples/holdings.csv`. |
| `data/targets.csv` | Target weights (Symbol, TargetWeight as fraction, Tier). Falls back to `examples/targets.csv`. |

## Outputs

Printed to stdout:
1. **Weight comparison table** — current %, target %, drift %, ⚠ flag for out-of-band positions
2. **Proposed trades** — BUY/SELL, drift %, trade value in USD, note (contribution / sell proceeds / est. FX cost)

## Rebalancing logic

- Band: ±5pp by default (configurable with `--band`)
- **Contributions-first**: new cash is allocated to the most underweight positions before any sells are triggered — minimises FX conversion costs
- Non-US listings (2330.TW, CSPX.L) are converted to USD via exchangerate-api.com for weight calculation
- Price unavailable → falls back to cost basis for weight calculation (noted in output)

## Tips for the user

- If `--contribution` covers all the underweight gap, no sells are needed at all
- The `Tier` column in `targets.csv` (core / thematic / single) is for reference — the rebalancer doesn't enforce tier caps yet (planned in INVESTMENT_PLAN.md §7)
- Run `/portfolio-daily-report` first to get fresh prices; rebalance uses the same fetchers

## After running

If the user wants to record the rebalance decision, suggest `/save-learnings`.
