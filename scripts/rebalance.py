"""Rebalancing recommendation: current vs target weights → proposed trades.

Reads holdings (data/holdings.csv) and targets (data/targets.csv),
fetches current prices, computes weight drift, and proposes trades
for positions outside the rebalance band (default ±5pp).

Usage:
    python scripts/rebalance.py
    python scripts/rebalance.py --contribution 5000
    python scripts/rebalance.py --band 0.03
    python scripts/rebalance.py --holdings path/to/holdings.csv --targets path/to/targets.csv
"""

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src.fetchers import StooqFetcher, YFinanceFetcher
from src.rebalancers import Rebalancer

load_dotenv()
logging.basicConfig(level=logging.WARNING)

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def load_holdings(path: str) -> List[Dict]:
    rows = []
    with open(path, newline='') as f:
        reader = csv.DictReader(filter(lambda line: not line.startswith('#'), f))
        for row in reader:
            rows.append({
                'symbol':   row['Symbol'].strip(),
                'quantity': float(row['Quantity']),
                'avg_cost': float(row['AvgCost']),
                'currency': row['Currency'].strip().upper(),
            })
    return rows


def load_targets(path: str) -> Dict[str, float]:
    targets = {}
    with open(path, newline='') as f:
        reader = csv.DictReader(filter(lambda line: not line.startswith('#'), f))
        for row in reader:
            targets[row['Symbol'].strip()] = float(row['TargetWeight'])
    return targets


def find_file(name: str) -> str:
    for candidate in [
        PROJECT_ROOT / 'data' / name,
        PROJECT_ROOT / 'examples' / name,
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"{name} not found in data/ or examples/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_fx_rate(from_currency: str, to_currency: str = 'USD') -> float:
    if from_currency == to_currency:
        return 1.0
    try:
        import requests
        resp = requests.get(
            f"https://api.exchangerate-api.com/v4/latest/{from_currency}", timeout=10
        )
        resp.raise_for_status()
        rate = resp.json()['rates'].get(to_currency)
        return float(rate) if rate else 1.0
    except Exception as e:
        print(f"  Warning: FX fetch failed ({from_currency}->{to_currency}): {e}")
        return 1.0


def fetch_price(symbol: str, yf: YFinanceFetcher, stooq: StooqFetcher) -> float | None:
    result = yf.fetch_price(symbol)
    if result['price'] is not None:
        return result['price'], result.get('currency', 'USD')
    result = stooq.fetch_price(symbol)
    return result['price'], 'USD'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Portfolio rebalancing recommendations")
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--targets', help='Path to targets CSV')
    parser.add_argument('--contribution', type=float, default=0.0,
                        help='New cash to deploy (USD)')
    parser.add_argument('--band', type=float, default=0.05,
                        help='Rebalance band (default 0.05 = ±5pp)')
    args = parser.parse_args()

    holdings_path = args.holdings or find_file('holdings.csv')
    targets_path = args.targets or find_file('targets.csv')

    print(f"Holdings : {holdings_path}")
    print(f"Targets  : {targets_path}")
    print(f"Band     : ±{args.band*100:.0f}pp")
    if args.contribution:
        print(f"New cash : ${args.contribution:,.2f}")
    print()

    holdings = load_holdings(holdings_path)
    targets = load_targets(targets_path)

    yf = YFinanceFetcher()
    stooq = StooqFetcher()
    fx_cache: Dict[str, float] = {}

    # Compute current values in USD
    symbol_values: Dict[str, float] = {}
    for h in holdings:
        symbol = h['symbol']
        currency = h['currency']
        print(f"  Fetching {symbol}...", end=' ', flush=True)

        price, price_currency = fetch_price(symbol, yf, stooq)

        if currency not in fx_cache:
            fx_cache[currency] = get_fx_rate(currency, 'USD')
        fx = fx_cache[currency]

        if price:
            value_usd = price * fx * h['quantity']
            print(f"${price:.2f} → ${value_usd:,.2f} USD")
        else:
            # Fall back to cost basis if price unavailable
            value_usd = h['avg_cost'] * fx * h['quantity']
            print(f"price unavailable — using cost basis ${value_usd:,.2f} USD")

        symbol_values[symbol] = symbol_values.get(symbol, 0) + value_usd

    total_value = sum(symbol_values.values())
    print(f"\nTotal portfolio value: ${total_value:,.2f}\n")

    # Current weights
    current_weights = pd.Series(symbol_values) / total_value
    target_weights = pd.Series(targets)

    # Normalize target weights in case they don't sum to 1
    target_sum = target_weights.sum()
    if abs(target_sum - 1.0) > 0.01:
        print(f"Warning: target weights sum to {target_sum:.3f}, normalizing to 1.0")
        target_weights = target_weights / target_sum

    # Run rebalancer
    rebalancer = Rebalancer(band=args.band)
    result = rebalancer.summary(
        current_weights, target_weights, total_value, new_contribution=args.contribution
    )

    # --- Weight comparison table ---
    print("=" * 65)
    print("WEIGHT COMPARISON")
    print("=" * 65)
    drift_df = result['drift'].copy()
    drift_df.index.name = 'Symbol'
    drift_df['flag'] = drift_df['outside_band'].map({True: '⚠', False: ''})
    drift_df = drift_df.drop(columns='outside_band')
    print(drift_df.to_string())
    print()

    # --- Proposed trades ---
    print("=" * 65)
    print("PROPOSED TRADES")
    print("=" * 65)

    if result['in_balance']:
        print(f"✓ All positions within ±{result['band_pct']:.0f}pp band. No trades needed.")
    else:
        trades = result['trades']
        print(trades.to_string(index=False))
        total_buys = trades.loc[trades['action'] == 'BUY', 'trade_value'].sum()
        total_sells = trades.loc[trades['action'] == 'SELL', 'trade_value'].sum()
        print(f"\n  Total buys : ${total_buys:,.2f}")
        print(f"  Total sells: ${total_sells:,.2f}")
        net = total_buys - total_sells - args.contribution
        if abs(net) > 1:
            print(f"  Net cash needed (beyond contribution): ${net:,.2f}")


if __name__ == '__main__':
    main()
