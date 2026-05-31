"""Portfolio risk analysis: HistoryFetcher → FXConverter → PortfolioMetrics.

Pipeline:
  1. Load holdings  → deduplicate to one row per symbol, build market-value weights
  2. HistoryFetcher → historical OHLCV in native listing currency (cached)
  3. FXConverter    → convert all prices to SGD base
  4. PortfolioMetrics → covariance, risk contribution, Sharpe, drawdown, etc.
  5. Save Markdown report  →  output/portfolio-analysis-YYYY-MM-DD.md

Usage:
    python scripts/portfolio_analysis.py                  # default: 1y daily
    python scripts/portfolio_analysis.py --preset 3m
    python scripts/portfolio_analysis.py --preset 5y
    python scripts/portfolio_analysis.py --no-fx          # skip FX (USD analysis)
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src import config
from src.analyzers.portfolio import PortfolioMetrics
from src.fetchers import StooqFetcher, YFinanceFetcher
from src.fetchers.fx import FXConverter
from src.fetchers.history import PRESETS, HistoryFetcher, _preset_dates

# Reuse helpers from daily_report without circular imports
from scripts.daily_report import find_holdings_file, fetch_price, get_fx_rate, load_holdings

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.analysis')

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))

# Minimum fraction of expected trading days a symbol must have to be included
_MIN_COVERAGE = 0.50


# ---------------------------------------------------------------------------
# Step 1 — Build symbol universe from holdings
# ---------------------------------------------------------------------------

def build_universe(holdings: List[Dict]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Aggregate multiple lots per symbol into total quantity and extract currency map.

    Returns:
        qty_map:      {symbol: total_quantity}
        currency_map: {symbol: currency_code}
    """
    qty_map: Dict[str, float] = {}
    currency_map: Dict[str, str] = {}
    for h in holdings:
        sym = h['symbol']
        qty_map[sym] = qty_map.get(sym, 0.0) + h['quantity']
        currency_map[sym] = h['currency']  # same currency across all lots
    return qty_map, currency_map


def compute_market_weights(
    qty_map: Dict[str, float],
    currency_map: Dict[str, str],
) -> pd.Series:
    """
    Fetch current prices, convert to SGD, return market-value weights.
    Symbols that fail to price are excluded (reported as warnings).
    """
    yf = YFinanceFetcher()
    stooq = StooqFetcher()
    fx_cache: Dict[str, float] = {}
    values: Dict[str, float] = {}

    symbols = list(qty_map.keys())
    print(f"\nFetching current prices for {len(symbols)} symbols (for weights)...")

    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(0.25)
        print(f"  {sym}...", end=' ', flush=True)
        result = fetch_price(sym, yf, stooq)
        price = result['price']
        if price is None:
            print("N/A — excluded from analysis")
            continue
        ccy = currency_map[sym]
        if ccy not in fx_cache:
            fx_cache[ccy] = get_fx_rate(ccy)
        fx = fx_cache[ccy]
        is_pence = ccy == 'GBp'
        value = qty_map[sym] * price * fx / (100.0 if is_pence else 1.0)
        values[sym] = value
        sym_in_base = config.BASE_CURRENCY
        _CCY_SYM = {'SGD': 'S$', 'USD': '$'}
        sym_fmt = _CCY_SYM.get(sym_in_base, sym_in_base + ' ')
        print(f"{sym_fmt}{value:,.0f}")

    total = sum(values.values())
    if total == 0:
        raise RuntimeError("No symbols could be priced — cannot compute weights.")

    weights = pd.Series(values, dtype=float) / total
    return weights.sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Step 2 & 3 — Historical prices → SGD returns
# ---------------------------------------------------------------------------

def fetch_sgd_returns(
    symbols: List[str],
    currency_map: Dict[str, str],
    start_date: str,
    end_date: str,
    interval: str,
    use_fx: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    Fetch historical prices, optionally convert to SGD, return returns + prices.

    Returns:
        (returns_sgd, prices_sgd, excluded)
        excluded: symbols dropped due to insufficient history
    """
    print(f"\nFetching {interval} historical prices ({start_date} → {end_date})...")
    fetcher = HistoryFetcher()
    prices = fetcher.fetch(symbols, start_date, end_date, interval=interval)

    if prices.empty:
        raise RuntimeError("HistoryFetcher returned no data.")

    # Report coverage
    expected_days = len(pd.bdate_range(start_date, end_date))
    excluded = []
    keep = []
    for sym in prices.columns:
        coverage = prices[sym].notna().sum() / expected_days
        if coverage < _MIN_COVERAGE:
            print(f"  ⚠  {sym}: only {coverage:.0%} coverage — excluded from analysis")
            excluded.append(sym)
        else:
            keep.append(sym)
            print(f"  ✓  {sym}: {prices[sym].notna().sum()} rows ({coverage:.0%})")

    prices = prices[keep].ffill().bfill()

    if use_fx:
        print(f"\nConverting prices to {config.BASE_CURRENCY} using historical FX rates...")
        fx = FXConverter()
        sub_map = {s: currency_map[s] for s in keep if s in currency_map}
        prices = fx.to_base_currency(prices, sub_map)

    returns = prices.pct_change().dropna()
    return returns, prices, excluded


# ---------------------------------------------------------------------------
# Step 4 — Run PortfolioMetrics
# ---------------------------------------------------------------------------

def run_analysis(
    weights: pd.Series,
    returns: pd.DataFrame,
    prices: pd.DataFrame,
    currency_map: Dict[str, str],
    risk_free_rate: Optional[float] = None,
) -> Dict:
    """Align weights to available returns columns and run PortfolioMetrics.summary()."""
    common = weights.index.intersection(returns.columns)
    if len(common) == 0:
        raise RuntimeError("No overlap between weighted symbols and historical return data.")

    missing = set(weights.index) - set(common)
    if missing:
        print(f"\n  ⚠  Symbols in holdings but no history: {sorted(missing)} — excluded from risk metrics")

    w = weights[common]
    w = w / w.sum()  # renormalise after exclusions

    rfr = risk_free_rate or config.RISK_FREE_RATE
    pm = PortfolioMetrics(risk_free_rate=rfr, trading_days=config.TRADING_DAYS)
    sub_currency_map = {s: currency_map.get(s, 'USD') for s in common}
    result = pm.summary(w, returns[common], prices=prices[common], currency_map=sub_currency_map)
    result['weights'] = w
    result['returns'] = returns[common]
    return result


# ---------------------------------------------------------------------------
# Step 5 — Format report
# ---------------------------------------------------------------------------

def format_analysis_report(
    result: Dict,
    preset: str,
    start_date: str,
    end_date: str,
    excluded: List[str],
    use_fx: bool,
) -> str:
    base = config.BASE_CURRENCY
    weights = result['weights']
    rc_pct = result['risk_contribution_pct']
    returns = result['returns']
    lines = []

    label = f"{PRESETS[preset].label} ({PRESETS[preset].interval})"
    lines += [
        f"# Portfolio Risk Analysis — {date.today().isoformat()}\n",
        f"**Period:** {label} | {start_date} → {end_date}  ",
        f"**Base currency:** {base}{'  ' if use_fx else ' (no FX conversion)'}  ",
        f"**Symbols analysed:** {len(weights)}  ",
    ]
    if excluded:
        lines.append(f"**Excluded (insufficient history):** {', '.join(excluded)}  ")
    lines.append("")

    # ── Risk overview ────────────────────────────────────────────────────────
    sigma = result['portfolio_volatility']
    sharpe = result['portfolio_sharpe']
    sortino = result['portfolio_sortino']
    mdd = result.get('max_drawdown', float('nan'))
    dr = result['diversification_ratio']
    enb = result['effective_number_of_bets']

    lines += [
        "## Risk Overview\n",
        "| Metric | Value |",
        "|---|---|",
        f"| Portfolio Volatility (annualised) | {sigma:.1%} |",
        f"| Sharpe Ratio | {sharpe:.2f} |",
        f"| Sortino Ratio | {sortino:.2f} |",
        f"| Max Drawdown | {mdd:.1%} |",
        f"| Diversification Ratio | {dr:.2f} |",
        f"| Effective Number of Bets | {enb:.1f} |",
        "",
    ]

    # ── Currency exposure ────────────────────────────────────────────────────
    if 'currency_exposure' in result:
        exp = result['currency_exposure']
        lines += ["## Currency Exposure\n", "| Currency | Weight |", "|---|---|"]
        for ccy, wt in exp.items():
            lines.append(f"| {ccy} | {wt:.1%} |")
        lines.append("")

    # ── Holdings by weight and risk ──────────────────────────────────────────
    lines += [
        "## Holdings — Weight vs Risk Contribution\n",
        f"| Symbol | Weight | Risk Contrib | Δ (risk − weight) | Flag |",
        f"|---|---|---|---|---|",
    ]
    table_rows = []
    for sym in weights.index:
        w = weights[sym]
        rc = rc_pct.get(sym, 0.0)
        delta = rc - w * 100
        flag = ""
        if rc > 30:
            flag = "⚠️ dominant"
        elif delta > 10:
            flag = "↑ risk > weight"
        table_rows.append((sym, w, rc, delta, flag))

    for sym, w, rc, delta, flag in sorted(table_rows, key=lambda x: x[2], reverse=True):
        lines.append(f"| {sym} | {w:.1%} | {rc:.1f}% | {delta:+.1f}pp | {flag} |")
    lines.append("")

    # ── Correlation matrix ───────────────────────────────────────────────────
    corr = returns.corr()
    syms = list(corr.columns)
    lines += ["## Correlation Matrix\n"]

    # Flag high pairs
    high_pairs = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            v = corr.iloc[i, j]
            if v > config.MAX_CORRELATION:
                high_pairs.append((syms[i], syms[j], v))

    if high_pairs:
        lines.append("**High correlations (>{:.0%}) — limited diversification benefit:**".format(config.MAX_CORRELATION))
        for a, b, v in sorted(high_pairs, key=lambda x: x[2], reverse=True):
            lines.append(f"- {a} ↔ {b}: {v:.2f}")
        lines.append("")

    # Correlation table (truncate symbol names to 8 chars for readability)
    short = [s[:8] for s in syms]
    header = "| | " + " | ".join(short) + " |"
    sep    = "|---|" + "---|" * len(syms)
    lines += [header, sep]
    for i, sym in enumerate(syms):
        row_vals = " | ".join(
            f"**1.00**" if i == j else f"{corr.iloc[i, j]:+.2f}"
            for j in range(len(syms))
        )
        lines.append(f"| {short[i]} | {row_vals} |")
    lines.append("")

    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                 f"risk-free rate: {config.RISK_FREE_RATE:.1%}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Portfolio risk analysis')
    parser.add_argument('--preset', choices=list(PRESETS), default='1y',
                        help='Historical period (default: 1y)')
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--no-fx', action='store_true',
                        help='Skip FX conversion (analyse in native currencies)')
    args = parser.parse_args()

    holdings_path = args.holdings or find_holdings_file()
    holdings = load_holdings(holdings_path)
    print(f"Loaded {len(holdings)} lots from {holdings_path}")

    qty_map, currency_map = build_universe(holdings)
    print(f"Unique symbols: {len(qty_map)}")

    # Step 1: market-value weights
    weights = compute_market_weights(qty_map, currency_map)
    print(f"\nTop holdings by weight:")
    for sym, w in weights.head(5).items():
        print(f"  {sym}: {w:.1%}")

    # Step 2 & 3: historical prices → SGD returns
    preset = PRESETS[args.preset]
    start_date, end_date, interval = _preset_dates(preset)
    returns, prices, excluded = fetch_sgd_returns(
        list(qty_map.keys()), currency_map,
        start_date, end_date, interval,
        use_fx=not args.no_fx,
    )

    # Step 4: portfolio metrics
    print("\nComputing portfolio metrics...")
    result = run_analysis(weights, returns, prices, currency_map)

    # Step 5: format and save
    sigma = result['portfolio_volatility']
    sharpe = result['portfolio_sharpe']
    mdd = result.get('max_drawdown', float('nan'))
    dr = result['diversification_ratio']
    enb = result['effective_number_of_bets']

    print(f"\n{'='*60}")
    print(f"Portfolio Volatility:      {sigma:.1%}")
    print(f"Sharpe Ratio:              {sharpe:.2f}")
    print(f"Max Drawdown:              {mdd:.1%}")
    print(f"Diversification Ratio:     {dr:.2f}")
    print(f"Effective # of Bets:       {enb:.1f}")
    print(f"\nRisk Contribution (top 5):")
    rc_pct = result['risk_contribution_pct'].sort_values(ascending=False)
    for sym, v in rc_pct.head(5).items():
        w = result['weights'].get(sym, 0)
        print(f"  {sym:<12} rc={v:.1f}%  weight={w:.1%}")
    print(f"{'='*60}")

    report = format_analysis_report(
        result, args.preset, start_date, end_date, excluded, not args.no_fx
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"portfolio-analysis-{date.today().isoformat()}.md"
    out_path.write_text(report)
    print(f"\nFull report saved to: {out_path}")


if __name__ == '__main__':
    main()
