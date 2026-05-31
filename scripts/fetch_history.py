"""Fetch and cache historical OHLCV data for portfolio symbols.

Reads symbols from data/universe.csv (or data/holdings.csv, or a custom list),
fetches OHLCV history via yfinance, and saves append-only CSV caches under
data/cache/{SYMBOL}_{interval}.csv.

Only missing dates are fetched — already-cached data is never re-downloaded.
The last cached bar is always re-fetched to handle intraday-incomplete closes.

Usage examples:
    # Fetch 1-year daily history for all symbols in data/universe.csv
    python scripts/fetch_history.py --preset 1y

    # Fetch multiple presets at once
    python scripts/fetch_history.py --preset 1y 5y

    # Fetch all standard presets (7d, 1m, 3m, 1y, ytd, 5y, max)
    python scripts/fetch_history.py --all

    # Specific symbols only
    python scripts/fetch_history.py --preset 1y --symbols NVDA ASML 2330.TW

    # Show what's in the cache without fetching
    python scripts/fetch_history.py --status

Granularity used per preset (see INVESTMENT_PLAN.md §3):
    7d, 1m, 3m, 1y, ytd, 5y → daily (1d)
    max (~10 years)          → weekly (1wk)
"""

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src.fetchers.history import HistoryFetcher, PRESETS, _preset_dates

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Symbol loading
# ---------------------------------------------------------------------------

def load_symbols(source: Optional[str] = None) -> List[str]:
    """Load symbols from universe.csv, holdings.csv, or a custom path."""
    candidates = [
        source,
        str(PROJECT_ROOT / 'data' / 'universe.csv'),
        str(PROJECT_ROOT / 'data' / 'holdings.csv'),
        str(PROJECT_ROOT / 'examples' / 'universe.csv'),
        str(PROJECT_ROOT / 'examples' / 'holdings.csv'),
    ]
    for path in candidates:
        if path and Path(path).exists():
            symbols = []
            with open(path, newline='') as f:
                for line in f:
                    if line.startswith('#'):
                        continue
                    row = next(csv.DictReader([line]), None)
                    if row and row.get('Symbol'):
                        symbols.append(row['Symbol'].strip())
            if symbols:
                print(f"Loaded {len(symbols)} symbols from {path}")
                return symbols
    return []


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def show_status(fetcher: HistoryFetcher, symbols: List[str]) -> None:
    print(f"\n{'Symbol':<12} {'Interval':<8} {'Rows':>6}  {'Start':<12} {'End':<12}")
    print("─" * 54)
    for symbol in symbols:
        for interval in ['1d', '1wk']:
            info = fetcher.cache_info(symbol, interval)
            if info:
                print(
                    f"{symbol:<12} {interval:<8} {info['rows']:>6}  "
                    f"{info['start']:<12} {info['end']:<12}"
                )


# ---------------------------------------------------------------------------
# Main fetch loop
# ---------------------------------------------------------------------------

def run_fetch(
    symbols: List[str],
    presets: List[str],
    fetcher: HistoryFetcher,
    delay_secs: float = 0.3,
) -> None:
    total_fetched = 0
    total_cached = 0

    for preset_name in presets:
        preset = PRESETS[preset_name]
        start, end, interval = _preset_dates(preset)

        print(f"\n{'━' * 60}")
        print(f"Preset: {preset_name} ({preset.label}) | interval: {interval} | {start} → {end}")
        print(f"{'━' * 60}")
        print(f"{'Symbol':<12} {'Status':<20} {'Cached':>8} {'New':>8}  {'Range'}")
        print("─" * 70)

        for symbol in symbols:
            print(f"  {symbol:<10}", end=' ', flush=True)
            df, cached_rows, fetched_rows = fetcher.update_cache(symbol, interval, start, end)

            if df is None:
                print("FAILED — could not fetch or read cache")
                continue

            status = "up to date" if fetched_rows == 0 else f"+{fetched_rows} new rows"
            date_range = ""
            if not df.empty:
                date_range = f"{df.index.min().date()} → {df.index.max().date()}"

            print(f"{status:<20} {cached_rows:>8} {fetched_rows:>8}  {date_range}")
            total_fetched += fetched_rows
            total_cached += cached_rows

            if fetched_rows > 0 and delay_secs > 0:
                import time
                time.sleep(delay_secs)  # be a polite yfinance citizen

    print(f"\n{'─' * 60}")
    print(f"Done. Total: {total_fetched} new rows fetched, {total_cached} rows already cached.")
    print(f"Cache location: {fetcher.cache_dir}/")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache historical OHLCV data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "Available presets:",
            *[f"  {k:<6}  {v.label:<20} interval={v.interval}" for k, v in PRESETS.items()],
        ]),
    )
    parser.add_argument(
        '--preset', nargs='+', choices=list(PRESETS), metavar='PRESET',
        help='One or more presets to fetch (e.g. --preset 1y 5y)',
    )
    parser.add_argument(
        '--all', action='store_true',
        help='Fetch all standard presets',
    )
    parser.add_argument(
        '--symbols', nargs='+', metavar='SYMBOL',
        help='Override symbols list (e.g. --symbols NVDA ASML 2330.TW)',
    )
    parser.add_argument(
        '--source', metavar='PATH',
        help='Path to CSV file with a Symbol column (default: data/universe.csv)',
    )
    parser.add_argument(
        '--cache-dir', metavar='DIR',
        help='Override cache directory (default: data/cache/)',
    )
    parser.add_argument(
        '--status', action='store_true',
        help='Show cache status for all symbols and exit (no fetching)',
    )
    parser.add_argument(
        '--delay', type=float, default=0.3, metavar='SECS',
        help='Pause between symbol fetches to avoid rate limits (default: 0.3s)',
    )
    args = parser.parse_args()

    fetcher = HistoryFetcher(cache_dir=args.cache_dir)

    symbols = args.symbols or load_symbols(args.source)
    if not symbols:
        print("No symbols found. Use --symbols or ensure data/universe.csv exists.")
        sys.exit(1)

    if args.status:
        show_status(fetcher, symbols)
        return

    if args.all:
        presets = list(PRESETS.keys())
    elif args.preset:
        presets = args.preset
    else:
        parser.print_help()
        print("\nNo preset specified. Use --preset 1y or --all.")
        sys.exit(1)

    run_fetch(symbols, presets, fetcher, delay_secs=args.delay)


if __name__ == '__main__':
    main()
