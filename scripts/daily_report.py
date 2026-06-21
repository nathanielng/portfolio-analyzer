"""Daily portfolio report: current values, P&L, macro dashboard, news headlines.

Reads holdings from data/holdings.csv (falls back to examples/holdings.csv),
fetches current prices via YFinance (Stooq for US-only fallback), converts all
positions to BASE_CURRENCY (default SGD — see src/config.py and INVESTMENT_PLAN.md
§6.5), overlays the FRED macro dashboard and per-ticker news, then:

  1. Saves full Markdown report  →  output/daily-report-YYYY-MM-DD.md
  2. Persists running peak/YTD   →  data/portfolio_snapshot.json
  3. Sends condensed summary     →  Telegram (if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set)

If the script errors, a Telegram error alert is sent (if configured).

Usage:
    python scripts/daily_report.py
    python scripts/daily_report.py --holdings path/to/holdings.csv
    python scripts/daily_report.py --no-macro --no-news --no-telegram
"""

import argparse
import csv
import json
import logging
import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src import config
from src.fetchers import MacroFetcher, StooqFetcher, YFinanceFetcher
from src.fetchers.news import NewsFetcher
from src.utils.telegram import from_env as telegram_from_env
from src.utils.freshness import mark_refreshed
from src.utils import quote_cache

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.daily_report')

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = PROJECT_ROOT / 'data' / 'portfolio_snapshot.json'
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))

# Stocks to exclude from daily report (held for eventual sale)
EXCLUDED_SYMBOLS = {'F83.SI', 'B58.SI'}

# Benchmark for comparison
BENCHMARK_SYMBOL = 'SPY'

_CCY_SYMBOL: Dict[str, str] = {
    'USD': '$', 'SGD': 'S$', 'EUR': '€', 'GBP': '£',
    'TWD': 'NT$', 'KRW': '₩', 'HKD': 'HK$',
}


def ccy(amount: float, currency: Optional[str] = None) -> str:
    code = currency or config.BASE_CURRENCY
    sym = _CCY_SYMBOL.get(code, code + ' ')
    return f"{sym}{amount:,.2f}"


# ---------------------------------------------------------------------------
# Holdings loading
# ---------------------------------------------------------------------------

_UNKNOWN_COST = {'na', 'n/a', 'unknown', ''}


def _parse_avg_cost(raw: str) -> Optional[float]:
    """Return None if cost is unknown (NA / 0), otherwise the float value."""
    s = raw.strip().lower()
    if s in _UNKNOWN_COST:
        return None
    v = float(s)
    return None if v == 0 else v


def load_holdings(path: str) -> List[Dict]:
    rows = []
    with open(path, newline='') as f:
        reader = csv.DictReader(filter(lambda line: not line.startswith('#'), f))
        for row in reader:
            cd = row.get('ContractDate', '').strip()
            rows.append({
                'symbol':        row['Symbol'].strip(),
                'quantity':      float(row['Quantity']),
                'avg_cost':      _parse_avg_cost(row['AvgCost']),  # None = cost unknown
                'currency':      row['Currency'].strip().upper(),
                'account':       row.get('Account', '').strip(),
                'broker':        row.get('Broker', '').strip(),
                'contract_date': cd if cd.upper() not in ('NA', '') else None,
                'sector':        row.get('Sector', '').strip() or 'Other',
                'asset_class':   row.get('AssetClass', '').strip() or 'Stock',
                'geography':     row.get('Geography', '').strip() or 'Other',
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
# Price fetching + FX → BASE_CURRENCY
# ---------------------------------------------------------------------------

def fetch_price(symbol: str, yf_fetcher: YFinanceFetcher, stooq_fetcher: StooqFetcher) -> Dict:
    """Fetch a current quote (yfinance → Stooq fallback), via the shared quote cache.

    Cached per symbol so a second script run in the same TTL window (e.g. the
    08:00 / 08:10 cron pair) reuses the result instead of re-fetching.
    """
    def _produce() -> Dict:
        result = yf_fetcher.fetch_price(symbol)
        if result['price'] is not None:
            return result
        logger.info(f"yfinance returned None for {symbol}, trying Stooq")
        return stooq_fetcher.fetch_price(symbol)

    return quote_cache.cached(
        f'quote:{symbol}', _produce,
        cache_if=lambda r: r.get('price') is not None,  # never cache a failed fetch
    )


def get_fx_rate(from_currency: str, to_currency: Optional[str] = None) -> float:
    """Spot FX rate from_currency → BASE_CURRENCY (or specified to_currency), cached."""
    to = to_currency or config.BASE_CURRENCY
    if from_currency == to:
        return 1.0

    def _produce() -> Optional[float]:
        try:
            import requests
            resp = requests.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_currency}", timeout=10
            )
            resp.raise_for_status()
            rate = resp.json()['rates'].get(to)
            if rate:
                logger.info(f"FX {from_currency}→{to}: {rate}")
                return float(rate)
            logger.warning(f"FX: no rate found for {from_currency}→{to}")
        except Exception as e:
            logger.warning(f"FX fetch failed ({from_currency}→{to}): {e}")
        return None

    rate = quote_cache.cached(
        f'fx:{from_currency}>{to}', _produce,
        cache_if=lambda r: r is not None,  # don't cache the failure fallback
    )
    return rate if rate is not None else 1.0


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
    from datetime import timedelta
    today = date.today()
    today_str = today.isoformat()
    year = str(today.year)

    if snap.get('ytd_year') != year:
        snap['ytd_baseline'] = total_value
        snap['ytd_year'] = year
    if total_value > snap.get('peak', 0):
        snap['peak'] = total_value
        snap['peak_date'] = today_str

    snap['last_value'] = total_value
    snap['last_date'] = today_str
    snap['base_currency'] = config.BASE_CURRENCY

    # Track historical values for return calculations
    if 'value_history' not in snap:
        snap['value_history'] = {}
    snap['value_history'][today_str] = total_value

    # Prune old entries (keep last 400 days for 1Y calculation)
    cutoff = (today - timedelta(days=400)).isoformat()
    snap['value_history'] = {k: v for k, v in snap['value_history'].items() if k >= cutoff}

    return snap


def calculate_returns(snap: Dict) -> Dict:
    """Calculate 1Y, 3M, YTD returns from snapshot history."""
    from datetime import timedelta

    today = date.today()
    current_value = snap.get('last_value', 0)
    if current_value == 0:
        return {'return_1y': None, 'return_3m': None, 'return_ytd': None}

    returns = {}

    # YTD return
    ytd_baseline = snap.get('ytd_baseline')
    if ytd_baseline:
        returns['return_ytd'] = ((current_value - ytd_baseline) / ytd_baseline * 100) if ytd_baseline else None
    else:
        returns['return_ytd'] = None

    # 1Y and 3M returns from history
    history = snap.get('value_history', {})

    # 1Y return (365 days ago)
    date_1y_ago = (today - timedelta(days=365)).isoformat()
    if date_1y_ago in history:
        value_1y_ago = history[date_1y_ago]
        returns['return_1y'] = ((current_value - value_1y_ago) / value_1y_ago * 100)
    else:
        # Find closest date before 1Y ago
        closest_date = None
        for hist_date in sorted(history.keys()):
            if hist_date <= date_1y_ago:
                closest_date = hist_date
        if closest_date:
            value_1y_ago = history[closest_date]
            returns['return_1y'] = ((current_value - value_1y_ago) / value_1y_ago * 100)
        else:
            returns['return_1y'] = None

    # 3M return (90 days ago)
    date_3m_ago = (today - timedelta(days=90)).isoformat()
    if date_3m_ago in history:
        value_3m_ago = history[date_3m_ago]
        returns['return_3m'] = ((current_value - value_3m_ago) / value_3m_ago * 100)
    else:
        # Find closest date before 3M ago
        closest_date = None
        for hist_date in sorted(history.keys()):
            if hist_date <= date_3m_ago:
                closest_date = hist_date
        if closest_date:
            value_3m_ago = history[closest_date]
            returns['return_3m'] = ((current_value - value_3m_ago) / value_3m_ago * 100)
        else:
            returns['return_3m'] = None

    return returns


def calculate_price_return_1y(price_history: Dict[str, float]) -> Optional[float]:
    """Calculate 1Y return from a price history dict {date: price, ...}. Returns None if no data."""
    from datetime import timedelta
    today = date.today()
    today_str = today.isoformat()
    current_price = price_history.get(today_str)
    if current_price is None:
        # Use most recent price
        if not price_history:
            return None
        current_price = price_history[max(price_history.keys())]

    # Find price from 1Y ago
    date_1y_ago = (today - timedelta(days=365)).isoformat()
    price_1y_ago = price_history.get(date_1y_ago)
    if price_1y_ago is None:
        # Find closest date
        closest_date = None
        for hist_date in sorted(price_history.keys()):
            if hist_date <= date_1y_ago:
                closest_date = hist_date
        if closest_date:
            price_1y_ago = price_history[closest_date]
        else:
            return None

    if price_1y_ago == 0:
        return None
    return ((current_price - price_1y_ago) / price_1y_ago * 100)


def calculate_position_return_1y(holdings_data: List[Dict], snapshot: Dict) -> Dict[str, Optional[float]]:
    """Calculate 1Y return for each position. Returns {symbol: return_pct or None}."""
    from datetime import timedelta
    today = date.today()
    today_str = today.isoformat()
    history = snapshot.get('value_history', {})

    returns_by_symbol = {}
    for holding in holdings_data:
        symbol = holding['symbol']
        contract_date = holding.get('contract_date')

        # Check if position existed 1Y ago
        date_1y_ago = (today - timedelta(days=365)).isoformat()
        position_exists_1y_ago = False

        if contract_date and contract_date > date_1y_ago:
            # Position didn't exist 1Y ago; skip 1Y calculation
            returns_by_symbol[symbol] = None
            continue

        # Use the average cost as baseline (conservative approach)
        avg_cost = holding.get('avg_cost')
        current_price = holding.get('current_base')
        if avg_cost and current_price:
            # Approximate: use current price vs avg cost (not a true 1Y return, but reasonable proxy)
            # A proper 1Y would need historical prices
            returns_by_symbol[symbol] = ((current_price - avg_cost) / avg_cost * 100)
        else:
            returns_by_symbol[symbol] = None

    return returns_by_symbol


# ---------------------------------------------------------------------------
# Portfolio allocation & benchmark
# ---------------------------------------------------------------------------

def calculate_allocation(holdings_data: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Calculate portfolio allocation by sector and geography (excluding held-for-sale positions)."""
    # Exclude held-for-sale symbols
    active_holdings = [h for h in holdings_data if h['symbol'] not in EXCLUDED_SYMBOLS]
    total_value = sum(h['value_base'] for h in active_holdings)
    if total_value == 0:
        return {'sector': {}, 'geography': {}, 'asset_class': {}}

    sectors = {}
    geographies = {}
    asset_classes = {}

    for h in active_holdings:
        weight = h['value_base'] / total_value

        sector = h.get('sector', 'Other')
        sectors[sector] = sectors.get(sector, 0) + weight

        geo = h.get('geography', 'Other')
        geographies[geo] = geographies.get(geo, 0) + weight

        ac = h.get('asset_class', 'Stock')
        asset_classes[ac] = asset_classes.get(ac, 0) + weight

    return {
        'sector': dict(sorted(sectors.items(), key=lambda x: x[1], reverse=True)),
        'geography': dict(sorted(geographies.items(), key=lambda x: x[1], reverse=True)),
        'asset_class': dict(sorted(asset_classes.items(), key=lambda x: x[1], reverse=True)),
    }


def calculate_rebalancing_guidance(holdings_data: List[Dict], targets_path: Optional[str] = None) -> List[str]:
    """Generate rebalancing guidance comparing current to target allocation."""
    if not targets_path or not Path(targets_path).exists():
        return []

    try:
        target_weights = {}
        with open(targets_path, newline='') as f:
            reader = csv.DictReader(filter(lambda line: not line.startswith('#'), f))
            for row in reader:
                target_weights[row['Symbol']] = float(row['TargetWeight'])
    except Exception as e:
        logger.warning(f"Could not load targets: {e}")
        return []

    total_value = sum(h['value_base'] for h in holdings_data)
    if total_value == 0:
        return []

    guidance = []
    for h in holdings_data:
        symbol = h['symbol']
        if symbol not in target_weights:
            continue

        current_weight = h['value_base'] / total_value
        target_weight = target_weights[symbol]
        delta = current_weight - target_weight

        if abs(delta) > 0.01:  # Only flag if > 1% difference
            direction = "BUY" if delta < 0 else "SELL"
            guidance.append(f"  {direction} {symbol}: {current_weight*100:.1f}% → {target_weight*100:.1f}%")

    return guidance


# ---------------------------------------------------------------------------
# Report formatting (full Markdown)
# ---------------------------------------------------------------------------

def format_report(
    holdings_data: List[Dict],
    total_value: float,
    total_cost: float,
    snap: Dict,
    macro: Optional[Dict],
    news: Optional[Dict[str, List[Dict[str, str]]]],
    report_date: str,
    benchmark_data: Optional[Dict] = None,
    targets_path: Optional[str] = None,
) -> str:
    base = config.BASE_CURRENCY
    gain_loss = total_value - total_cost
    gain_pct = (gain_loss / total_cost * 100) if total_cost else 0
    peak = snap.get('peak', total_value)
    drawdown_pct = ((total_value - peak) / peak * 100) if peak else 0
    ytd_base = snap.get('ytd_baseline', total_value)
    ytd_pct = ((total_value - ytd_base) / ytd_base * 100) if ytd_base else 0

    lines = [f"# Portfolio Daily Report — {report_date}\n"]

    # Calculate period returns
    returns = calculate_returns(snap)
    return_1y = returns.get('return_1y')
    return_3m = returns.get('return_3m')

    lines += [
        "## Portfolio Summary\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Value ({base}) | {ccy(total_value)} |",
        f"| Total Cost Basis | {ccy(total_cost)} |",
        f"| All-Time P&L | {ccy(gain_loss)} ({gain_pct:+.2f}%) |",
    ]

    # Add return metrics
    if return_1y is not None:
        lines.append(f"| 1-Year Return | {return_1y:+.2f}% |")
    if return_3m is not None:
        lines.append(f"| 3-Month Return | {return_3m:+.2f}% |")
    lines.append(f"| YTD Return | {ytd_pct:+.2f}% |")
    lines.append(f"| Max Drawdown from Peak | {drawdown_pct:.2f}% (peak {ccy(peak)}) |")
    lines += [""]

    lines += [
        "## Holdings\n",
        f"| Symbol | Qty | Avg Cost | Current ({base}) | Value ({base}) | P&L % | Account |",
        f"|--------|-----|----------|-----------------|---------------|-------|---------|",
    ]
    movers = []
    for h in sorted(holdings_data, key=lambda x: x['value_base'], reverse=True):
        # Skip excluded symbols from main report
        if h['symbol'] in EXCLUDED_SYMBOLS:
            continue
        pl_pct = h.get('pl_pct')
        cost_str = ccy(h['avg_cost_base']) if h.get('avg_cost_base') is not None else "—"
        current_str = ccy(h['current_base']) if h.get('current_base') is not None else "N/A"
        pl_str = f"{pl_pct:+.2f}%" if pl_pct is not None else "—"
        lines.append(
            f"| {h['symbol']} | {h['quantity']:.4g} | {cost_str} | "
            f"{current_str} | {ccy(h['value_base'])} | {pl_str} | {h['account']} |"
        )
        if pl_pct is not None:
            movers.append((h['symbol'], pl_pct))
    lines.append("")

    # Filter out excluded symbols from movers
    movers_filtered = [m for m in movers if m[0] not in EXCLUDED_SYMBOLS]
    if len(movers_filtered) > 1:
        gainers = sorted([m for m in movers_filtered if m[1] > 0], key=lambda x: x[1], reverse=True)[:3]
        losers = sorted([m for m in movers_filtered if m[1] < 0], key=lambda x: x[1])[:3]
        lines.append("## Movers\n")
        if gainers:
            lines.append("**Top gainers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in gainers))
        if losers:
            lines.append("**Top losers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in losers))
        lines.append("")

    # Portfolio allocation breakdown
    allocation = calculate_allocation(holdings_data)
    if allocation['sector']:
        lines.append("## Portfolio Allocation\n")
        lines.append("### By Sector")
        for sector, weight in allocation['sector'].items():
            lines.append(f"- {sector}: {weight*100:.1f}%")
        lines.append("")
        lines.append("### By Geography")
        for geo, weight in allocation['geography'].items():
            lines.append(f"- {geo}: {weight*100:.1f}%")
        lines.append("")
        lines.append("### By Asset Class")
        for ac, weight in allocation['asset_class'].items():
            lines.append(f"- {ac}: {weight*100:.1f}%")
        lines.append("")

    # Rebalancing guidance
    guidance = calculate_rebalancing_guidance(holdings_data, targets_path)
    if guidance:
        lines.append("## Rebalancing Guidance\n")
        for item in guidance:
            lines.append(item)
        lines.append("")

    # Benchmark comparison
    if benchmark_data:
        lines.append("## Benchmark Comparison\n")
        lines.append(f"| Metric | Portfolio | {BENCHMARK_SYMBOL} |")
        lines.append("|--------|-----------|-----------|")
        if benchmark_data.get('portfolio_ytd') is not None and benchmark_data.get('benchmark_ytd') is not None:
            lines.append(f"| YTD Return | {benchmark_data['portfolio_ytd']:+.2f}% | {benchmark_data['benchmark_ytd']:+.2f}% |")
        lines.append("")

    if news and any(v for v in news.values()):
        lines.append("## News\n")
        for symbol, articles in sorted(news.items()):
            # Skip excluded symbols
            if symbol in EXCLUDED_SYMBOLS:
                continue
            if articles:
                lines.append(f"**{symbol}**")
                for article in articles:
                    title = article.get('title', '')
                    link = article.get('link', '')
                    if link:
                        lines.append(f"- [{title}]({link})")
                    else:
                        lines.append(f"- {title}")
        lines.append("")

    if macro:
        def _fmt(val, suffix=''):
            return f"{val:.2f}{suffix}" if val is not None else "N/A"
        inverted_flag = " ⚠️ INVERTED" if macro.get('inverted') else ""
        lines += [
            "## Macro Dashboard\n",
            "| Indicator | Value |",
            "|-----------|-------|",
            f"| 10Y Treasury | {_fmt(macro.get('dgs10'), '%')} |",
            f"| 2Y Treasury | {_fmt(macro.get('dgs2'), '%')} |",
            f"| 10Y-2Y Spread | {_fmt(macro.get('spread_10y2y'), 'bp')}{inverted_flag} |",
            f"| Fed Funds Rate | {_fmt(macro.get('fedfunds'), '%')} |",
            f"| WTI Crude | ${_fmt(macro.get('wti'))} |",
            f"| VIX | {_fmt(macro.get('vix'))} |",
            "",
        ]

    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Base currency: {base}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram summary (condensed)
# ---------------------------------------------------------------------------

def format_telegram(
    holdings_data: List[Dict],
    total_value: float,
    total_cost: float,
    snap: Dict,
    macro: Optional[Dict],
    news: Optional[Dict[str, List[Dict[str, str]]]],
    report_date: str,
    benchmark_data: Optional[Dict] = None,
) -> str:
    gain_loss = total_value - total_cost
    gain_pct = (gain_loss / total_cost * 100) if total_cost else 0
    peak = snap.get('peak', total_value)
    drawdown_pct = ((total_value - peak) / peak * 100) if peak else 0
    ytd_base = snap.get('ytd_baseline', total_value)
    ytd_pct = ((total_value - ytd_base) / ytd_base * 100) if ytd_base else 0

    returns = calculate_returns(snap)
    return_1y = returns.get('return_1y')
    return_3m = returns.get('return_3m')

    lines = [
        f"📊 *Portfolio — {report_date}*",
        "─" * 28,
        f"{ccy(total_value)}  |  All-time P&L {gain_pct:+.1f}%",
    ]

    # Add returns line on single line: 1Y | 3M | YTD | Drawdown
    returns_parts = []
    if return_1y is not None:
        returns_parts.append(f"1Y {return_1y:+.1f}%")
    if return_3m is not None:
        returns_parts.append(f"3M {return_3m:+.1f}%")
    returns_parts.append(f"YTD {ytd_pct:+.1f}%")
    returns_parts.append(f"DD {drawdown_pct:.1f}%")

    lines.append(" | ".join(returns_parts))
    lines.append("")

    # Deduplicate movers by symbol: 1Y return for positions >= 1Y, YTD for newer
    from datetime import timedelta
    symbol_returns = {}
    symbol_timeframe = {}  # Track which timeframe for each symbol
    today = date.today()
    date_1y_ago = (today - timedelta(days=365)).isoformat()
    year_start = f"{today.year}-01-01"

    for h in holdings_data:
        if h['symbol'] in EXCLUDED_SYMBOLS:
            continue

        contract_date = h.get('contract_date')
        pl_pct = h.get('pl_pct')
        if pl_pct is None:
            continue

        # Determine timeframe: 1Y if held >= 1Y, otherwise YTD
        if contract_date and contract_date > date_1y_ago:
            timeframe = 'YTD'  # Position < 1Y old
        else:
            timeframe = '1Y'   # Position >= 1Y old

        # Aggregate by symbol (keep best return if multiple lots)
        if h['symbol'] not in symbol_returns:
            symbol_returns[h['symbol']] = pl_pct
            symbol_timeframe[h['symbol']] = timeframe
        else:
            if pl_pct > symbol_returns[h['symbol']]:
                symbol_returns[h['symbol']] = pl_pct
                symbol_timeframe[h['symbol']] = timeframe

    movers = list(symbol_returns.items())
    gainers = sorted([m for m in movers if m[1] > 0], key=lambda x: x[1], reverse=True)[:3]
    losers = sorted([m for m in movers if m[1] < 0], key=lambda x: x[1])[:3]
    if gainers:
        labels = [f"{s} {p:+.1f}%" for s, p in gainers]
        lines.append("▲ " + "  ".join(labels) + " (1Y)")

    # Add benchmark comparison between gainers and losers
    if benchmark_data:
        benchmark_parts = []
        for symbol in ['SPY', 'QQQ']:
            if symbol in benchmark_data:
                return_1y = benchmark_data[symbol].get('return_1y')
                ret_str = f"{return_1y:+.1f}%" if return_1y is not None else "—"
                benchmark_parts.append(f"{symbol} {ret_str} (1Y)")
        if benchmark_parts:
            lines.append("📊 " + " | ".join(benchmark_parts))

    if losers:
        labels = [f"{s} {p:+.1f}%" for s, p in losers]
        loser_timeframe = "YTD" if all(symbol_timeframe.get(s) == 'YTD' for s, _ in losers) else "1Y"
        lines.append("▼ " + "  ".join(labels) + f" ({loser_timeframe})")
    if gainers or losers:
        lines.append("")

    if macro:
        def _m(val, suffix=''):
            return f"{val:.1f}{suffix}" if val is not None else "—"
        inv = " ⚠️" if macro.get('inverted') else ""
        lines.append(
            f"📈 10Y {_m(macro.get('dgs10'), '%')} | "
            f"Spread {_m(macro.get('spread_10y2y'), 'bp')}{inv} | "
            f"VIX {_m(macro.get('vix'))}"
        )
        lines.append("")

    if news:
        news_lines = []
        # Top US/tech symbols always included, Singapore news condensed
        priority_symbols = {'AMZN', 'AAPL', 'GOOG', 'D05.SI', 'BN4.SI', 'ES3.SI'}
        included_symbols = set()

        for symbol in sorted(priority_symbols):
            if symbol in news and news[symbol] and symbol not in EXCLUDED_SYMBOLS:
                article = news[symbol][0]
                title = article.get('title', '')[:70]  # Truncate long titles
                link = article.get('link', '')
                if link:
                    news_lines.append(f"• [{symbol}]({link}) {title}")
                else:
                    news_lines.append(f"• *{symbol}*: {title}")
                included_symbols.add(symbol)

        # Add other symbols if space allows (but NOT excluded symbols)
        for symbol, articles in sorted(news.items()):
            if symbol not in included_symbols and symbol not in EXCLUDED_SYMBOLS and articles:
                article = articles[0]
                title = article.get('title', '')[:70]
                link = article.get('link', '')
                if link:
                    news_lines.append(f"• [{symbol}]({link}) {title}")
                else:
                    news_lines.append(f"• *{symbol}*: {title}")

        if news_lines:
            lines.append("📰 *News*")
            lines.extend(news_lines[:6])  # Max 6 news items for Telegram char limit
            lines.append("")

    msg = "\n".join(lines)

    # Split into multiple messages if over 4000 chars (Telegram limit)
    if len(msg) > 4000:
        # Return as-is; caller can handle splitting if needed
        logger.warning(f"Telegram message exceeds 4000 chars ({len(msg)})")

    return msg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _run(args) -> str:
    holdings_path = args.holdings or find_holdings_file()
    print(f"Loading holdings from: {holdings_path}")
    holdings = load_holdings(holdings_path)
    print(f"Found {len(holdings)} positions\n")

    yf = YFinanceFetcher()
    stooq = StooqFetcher()
    fx_cache: Dict[str, float] = {}
    holdings_data: List[Dict] = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        symbol = h['symbol']
        listing_ccy = h['currency']
        print(f"  Fetching {symbol}...", end=' ', flush=True)

        result = fetch_price(symbol, yf, stooq)
        current_price = result['price']

        if listing_ccy not in fx_cache:
            fx_cache[listing_ccy] = get_fx_rate(listing_ccy)
        fx = fx_cache[listing_ccy]

        avg_cost_base = h['avg_cost'] * fx if h['avg_cost'] is not None else None
        current_base = current_price * fx if current_price is not None else None

        # Value: use current price if available, fall back to cost (or 0 if both unknown)
        if current_base is not None:
            value_base = current_base * h['quantity']
        elif avg_cost_base is not None:
            value_base = avg_cost_base * h['quantity']
        else:
            value_base = 0.0

        cost_base = avg_cost_base * h['quantity'] if avg_cost_base is not None else 0.0
        pl_pct = (
            (current_base - avg_cost_base) / avg_cost_base * 100
            if (current_base is not None and avg_cost_base)
            else None  # None = unknown, distinct from 0%
        )

        holdings_data.append({**h, 'avg_cost_base': avg_cost_base,
                               'current_base': current_base,
                               'value_base': value_base, 'pl_pct': pl_pct})
        total_value += value_base
        total_cost += cost_base
        print(ccy(current_base) if current_base is not None else "price unavailable")

    print(f"\nTotal portfolio value: {ccy(total_value)} ({config.BASE_CURRENCY})")

    snap = update_snapshot(load_snapshot(), total_value)
    save_snapshot(snap)

    macro = None
    if not args.no_macro:
        print("Fetching macro data...")
        macro = MacroFetcher(fred_api_key=os.getenv('FRED_API_KEY')).regime_dashboard()

    news = None
    if not args.no_news:
        print("Fetching news headlines...")
        news = NewsFetcher(max_per_ticker=3).fetch_many([h['symbol'] for h in holdings])

    # Fetch benchmark data (SPY and QQQ for comparison)
    benchmark_data = {}
    benchmark_history_path = PROJECT_ROOT / 'data' / 'benchmark_history.json'

    # Load existing benchmark history
    benchmark_history = {}
    if benchmark_history_path.exists():
        try:
            benchmark_history = json.loads(benchmark_history_path.read_text())
        except Exception as e:
            logger.warning(f"Could not load benchmark history: {e}")
            benchmark_history = {'meta': {}, 'SPY': {}, 'QQQ': {}}

    # Fetch current prices and store in history
    today_str = date.today().isoformat()
    for benchmark_symbol in ['SPY', 'QQQ']:
        try:
            print(f"Fetching {benchmark_symbol} benchmark data...")
            result = fetch_price(benchmark_symbol, yf, stooq)
            if result.get('price'):
                current_price = result['price']

                # Update history
                if benchmark_symbol not in benchmark_history:
                    benchmark_history[benchmark_symbol] = {}
                benchmark_history[benchmark_symbol][today_str] = current_price

                # Calculate 1Y return from history
                return_1y = calculate_price_return_1y(benchmark_history[benchmark_symbol])
                benchmark_data[benchmark_symbol] = {'price': current_price, 'return_1y': return_1y}
        except Exception as e:
            logger.warning(f"Could not fetch {benchmark_symbol}: {e}")

    # Save benchmark history
    benchmark_history['meta'] = {
        'updated': today_str,
        'benchmarks': ['SPY', 'QQQ']
    }
    try:
        benchmark_history_path.write_text(json.dumps(benchmark_history, indent=2))
    except Exception as e:
        logger.warning(f"Could not save benchmark history: {e}")

    # Load target allocation
    targets_path = PROJECT_ROOT / 'data' / 'targets.csv'

    report_date = date.today().isoformat()
    report = format_report(
        holdings_data, total_value, total_cost, snap, macro, news, report_date,
        benchmark_data=benchmark_data if benchmark_data else None, targets_path=str(targets_path) if targets_path.exists() else None
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"daily-report-{report_date}.md"
    out_path.write_text(report)

    print(f"\n{'='*60}")
    print(report)
    print(f"\nSaved to: {out_path}")

    if not args.no_telegram:
        tg = telegram_from_env()
        if tg:
            print("Sending Telegram summary...")
            msg = format_telegram(
                holdings_data, total_value, total_cost, snap, macro, news,
                report_date, benchmark_data
            )
            tg.send(msg)
        else:
            print("Telegram not configured — skipping (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")

    mark_refreshed('daily_report')
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Generate daily portfolio report")
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--no-macro',    action='store_true', help='Skip FRED macro fetch')
    parser.add_argument('--no-news',     action='store_true', help='Skip news headlines')
    parser.add_argument('--no-telegram', action='store_true', help='Skip Telegram delivery')
    parser.add_argument('--no-cache', action='store_true',
                        help='Bypass the shared quote cache — force fresh price/FX fetches')
    args = parser.parse_args()

    if args.no_cache:
        quote_cache.ENABLED = False

    tg = None if args.no_telegram else telegram_from_env()

    try:
        _run(args)
    except Exception:
        err = traceback.format_exc()
        logger.error(f"daily_report failed:\n{err}")
        print(f"\nERROR:\n{err}", file=sys.stderr)
        if tg:
            tg.send_error("daily_report.py", err)
        sys.exit(1)


if __name__ == '__main__':
    main()
