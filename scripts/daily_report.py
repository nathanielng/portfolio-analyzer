"""Daily portfolio report: current values, P&L, macro dashboard.

Reads holdings from data/holdings.csv (falls back to examples/holdings.csv),
fetches current prices via YFinance (Stooq for US-only fallback), converts
non-USD positions, and overlays the FRED macro dashboard.

Saves:
  output/daily-report-YYYY-MM-DD.md   — human-readable report
  data/portfolio_snapshot.json        — running peak / YTD baseline

Usage:
    python scripts/daily_report.py
    python scripts/daily_report.py --holdings path/to/holdings.csv
    python scripts/daily_report.py --no-macro
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src.fetchers import MacroFetcher, StooqFetcher, YFinanceFetcher

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.daily_report')

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = PROJECT_ROOT / 'data' / 'portfolio_snapshot.json'
OUTPUT_DIR = PROJECT_ROOT / 'output'


# ---------------------------------------------------------------------------
# Holdings loading
# ---------------------------------------------------------------------------

def load_holdings(path: str) -> List[Dict]:
    """Load holdings CSV, skipping comment lines."""
    rows = []
    with open(path, newline='') as f:
        reader = csv.DictReader(filter(lambda line: not line.startswith('#'), f))
        for row in reader:
            rows.append({
                'symbol':   row['Symbol'].strip(),
                'quantity': float(row['Quantity']),
                'avg_cost': float(row['AvgCost']),
                'currency': row['Currency'].strip().upper(),
                'account':  row.get('Account', '').strip(),
                'broker':   row.get('Broker', '').strip(),
            })
    return rows


def find_holdings_file() -> str:
    for candidate in [
        PROJECT_ROOT / 'data' / 'holdings.csv',
        PROJECT_ROOT / 'examples' / 'holdings.csv',
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "No holdings.csv found in data/ or examples/. "
        "Copy examples/holdings.csv to data/holdings.csv and fill in your positions."
    )


# ---------------------------------------------------------------------------
# Price fetching with Stooq fallback
# ---------------------------------------------------------------------------

def fetch_price(symbol: str, yf_fetcher: YFinanceFetcher, stooq_fetcher: StooqFetcher) -> Dict:
    result = yf_fetcher.fetch_price(symbol)
    if result['price'] is not None:
        return result
    logger.info(f"yfinance returned None for {symbol}, trying Stooq")
    return stooq_fetcher.fetch_price(symbol)


def get_fx_rate(from_currency: str, to_currency: str = 'USD') -> float:
    """Fetch spot FX rate via exchangerate-api.com (free, no key)."""
    if from_currency == to_currency:
        return 1.0
    try:
        import requests
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rate = resp.json()['rates'].get(to_currency)
        return float(rate) if rate else 1.0
    except Exception as e:
        logger.warning(f"FX fetch failed ({from_currency}->{to_currency}): {e}")
        return 1.0


# ---------------------------------------------------------------------------
# Snapshot: peak & YTD tracking
# ---------------------------------------------------------------------------

def load_snapshot() -> Dict:
    if SNAPSHOT_PATH.exists():
        return json.loads(SNAPSHOT_PATH.read_text())
    return {}


def save_snapshot(snap: Dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2))


def update_snapshot(snap: Dict, total_value: float) -> Dict:
    today = date.today().isoformat()
    year = str(date.today().year)

    # YTD baseline: reset each new year
    if snap.get('ytd_year') != year:
        snap['ytd_baseline'] = total_value
        snap['ytd_year'] = year

    # Peak tracking
    if total_value > snap.get('peak', 0):
        snap['peak'] = total_value
        snap['peak_date'] = today

    snap['last_value'] = total_value
    snap['last_date'] = today
    return snap


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    holdings_data: List[Dict],
    total_value: float,
    total_cost: float,
    snap: Dict,
    macro: Optional[Dict],
    report_date: str,
) -> str:
    lines = []
    lines.append(f"# Portfolio Daily Report — {report_date}\n")

    # --- Portfolio summary ---
    gain_loss = total_value - total_cost
    gain_pct = (gain_loss / total_cost * 100) if total_cost else 0

    peak = snap.get('peak', total_value)
    drawdown_pct = ((total_value - peak) / peak * 100) if peak else 0

    ytd_base = snap.get('ytd_baseline', total_value)
    ytd_pct = ((total_value - ytd_base) / ytd_base * 100) if ytd_base else 0

    lines.append("## Portfolio Summary\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Value | ${total_value:,.2f} |")
    lines.append(f"| Total Cost Basis | ${total_cost:,.2f} |")
    lines.append(f"| Unrealized P&L | ${gain_loss:+,.2f} ({gain_pct:+.2f}%) |")
    lines.append(f"| YTD Return | {ytd_pct:+.2f}% |")
    lines.append(f"| Max Drawdown from Peak | {drawdown_pct:.2f}% (peak ${peak:,.2f}) |")
    lines.append("")

    # --- Holdings table ---
    lines.append("## Holdings\n")
    lines.append("| Symbol | Qty | Avg Cost | Current | Value (USD) | P&L % | Account |")
    lines.append("|--------|-----|----------|---------|-------------|-------|---------|")

    movers = []
    for h in sorted(holdings_data, key=lambda x: x['value_usd'], reverse=True):
        pl_pct = h.get('pl_pct', 0)
        current = h.get('current_usd')
        current_str = f"${current:.2f}" if current else "N/A"
        lines.append(
            f"| {h['symbol']} | {h['quantity']:.0f} | "
            f"${h['avg_cost_usd']:.2f} | {current_str} | "
            f"${h['value_usd']:,.2f} | {pl_pct:+.2f}% | {h['account']} |"
        )
        movers.append((h['symbol'], pl_pct))

    lines.append("")

    # --- Top movers ---
    movers_sorted = sorted(movers, key=lambda x: x[1])
    if len(movers_sorted) > 1:
        lines.append("## Movers\n")
        gainers = [m for m in movers_sorted if m[1] > 0][-3:][::-1]
        losers = [m for m in movers_sorted if m[1] < 0][:3]
        if gainers:
            lines.append("**Top gainers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in gainers))
        if losers:
            lines.append("**Top losers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in losers))
        lines.append("")

    # --- Macro dashboard ---
    if macro:
        lines.append("## Macro Dashboard\n")
        lines.append("| Indicator | Value |")
        lines.append("|-----------|-------|")

        def _fmt(val, suffix=''):
            return f"{val:.2f}{suffix}" if val is not None else "N/A"

        inverted_flag = " ⚠️ INVERTED" if macro.get('inverted') else ""
        lines.append(f"| 10Y Treasury | {_fmt(macro.get('dgs10'), '%')} |")
        lines.append(f"| 2Y Treasury | {_fmt(macro.get('dgs2'), '%')} |")
        lines.append(f"| 10Y-2Y Spread | {_fmt(macro.get('spread_10y2y'), 'bp')}{inverted_flag} |")
        lines.append(f"| Fed Funds Rate | {_fmt(macro.get('fedfunds'), '%')} |")
        lines.append(f"| WTI Crude | ${_fmt(macro.get('wti'))} |")
        lines.append(f"| VIX | {_fmt(macro.get('vix'))} |")
        lines.append("")

    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate daily portfolio report")
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--no-macro', action='store_true', help='Skip macro data fetch')
    args = parser.parse_args()

    holdings_path = args.holdings or find_holdings_file()
    print(f"Loading holdings from: {holdings_path}")
    holdings = load_holdings(holdings_path)
    print(f"Found {len(holdings)} positions\n")

    yf = YFinanceFetcher()
    stooq = StooqFetcher()

    # Fetch FX rates we'll need (cache per currency)
    fx_cache: Dict[str, float] = {}

    holdings_data = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        symbol = h['symbol']
        currency = h['currency']
        print(f"  Fetching {symbol}...", end=' ', flush=True)

        result = fetch_price(symbol, yf, stooq)
        current_price = result['price']

        # FX to USD
        if currency not in fx_cache:
            fx_cache[currency] = get_fx_rate(currency, 'USD')
        fx = fx_cache[currency]

        avg_cost_usd = h['avg_cost'] * fx
        current_usd = current_price * fx if current_price else None
        value_usd = (current_usd or avg_cost_usd) * h['quantity']
        cost_usd = avg_cost_usd * h['quantity']
        pl_pct = ((current_usd - avg_cost_usd) / avg_cost_usd * 100) if current_usd else 0

        holdings_data.append({
            **h,
            'avg_cost_usd': avg_cost_usd,
            'current_usd': current_usd,
            'value_usd': value_usd,
            'pl_pct': pl_pct,
        })
        total_value += value_usd
        total_cost += cost_usd

        status = f"${current_usd:.2f}" if current_usd else "price unavailable"
        print(status)

    print(f"\nTotal portfolio value: ${total_value:,.2f}")

    # Snapshot
    snap = load_snapshot()
    snap = update_snapshot(snap, total_value)
    save_snapshot(snap)

    # Macro
    macro = None
    if not args.no_macro:
        print("\nFetching macro data...")
        fred_key = os.getenv('FRED_API_KEY')
        macro = MacroFetcher(fred_api_key=fred_key).regime_dashboard()

    # Format and save report
    report_date = date.today().isoformat()
    report = format_report(holdings_data, total_value, total_cost, snap, macro, report_date)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"daily-report-{report_date}.md"
    out_path.write_text(report)

    print(f"\n{'='*60}")
    print(report)
    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
