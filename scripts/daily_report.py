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

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.daily_report')

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = PROJECT_ROOT / 'data' / 'portfolio_snapshot.json'
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))

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
# Price fetching + FX → BASE_CURRENCY
# ---------------------------------------------------------------------------

def fetch_price(symbol: str, yf_fetcher: YFinanceFetcher, stooq_fetcher: StooqFetcher) -> Dict:
    result = yf_fetcher.fetch_price(symbol)
    if result['price'] is not None:
        return result
    logger.info(f"yfinance returned None for {symbol}, trying Stooq")
    return stooq_fetcher.fetch_price(symbol)


def get_fx_rate(from_currency: str, to_currency: Optional[str] = None) -> float:
    """Spot FX rate from_currency → BASE_CURRENCY (or specified to_currency)."""
    to = to_currency or config.BASE_CURRENCY
    if from_currency == to:
        return 1.0
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
    if snap.get('ytd_year') != year:
        snap['ytd_baseline'] = total_value
        snap['ytd_year'] = year
    if total_value > snap.get('peak', 0):
        snap['peak'] = total_value
        snap['peak_date'] = today
    snap['last_value'] = total_value
    snap['last_date'] = today
    snap['base_currency'] = config.BASE_CURRENCY
    return snap


# ---------------------------------------------------------------------------
# Report formatting (full Markdown)
# ---------------------------------------------------------------------------

def format_report(
    holdings_data: List[Dict],
    total_value: float,
    total_cost: float,
    snap: Dict,
    macro: Optional[Dict],
    news: Optional[Dict[str, List[str]]],
    report_date: str,
) -> str:
    base = config.BASE_CURRENCY
    gain_loss = total_value - total_cost
    gain_pct = (gain_loss / total_cost * 100) if total_cost else 0
    peak = snap.get('peak', total_value)
    drawdown_pct = ((total_value - peak) / peak * 100) if peak else 0
    ytd_base = snap.get('ytd_baseline', total_value)
    ytd_pct = ((total_value - ytd_base) / ytd_base * 100) if ytd_base else 0

    lines = [f"# Portfolio Daily Report — {report_date}\n"]
    lines += [
        "## Portfolio Summary\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Value ({base}) | {ccy(total_value)} |",
        f"| Total Cost Basis | {ccy(total_cost)} |",
        f"| Unrealized P&L | {ccy(gain_loss)} ({gain_pct:+.2f}%) |",
        f"| YTD Return | {ytd_pct:+.2f}% |",
        f"| Max Drawdown from Peak | {drawdown_pct:.2f}% (peak {ccy(peak)}) |",
        "",
    ]

    lines += [
        "## Holdings\n",
        f"| Symbol | Qty | Avg Cost | Current ({base}) | Value ({base}) | P&L % | Account |",
        f"|--------|-----|----------|-----------------|---------------|-------|---------|",
    ]
    movers = []
    for h in sorted(holdings_data, key=lambda x: x['value_base'], reverse=True):
        pl_pct = h.get('pl_pct', 0)
        current_str = ccy(h['current_base']) if h.get('current_base') is not None else "N/A"
        lines.append(
            f"| {h['symbol']} | {h['quantity']:.0f} | {ccy(h['avg_cost_base'])} | "
            f"{current_str} | {ccy(h['value_base'])} | {pl_pct:+.2f}% | {h['account']} |"
        )
        movers.append((h['symbol'], pl_pct))
    lines.append("")

    if len(movers) > 1:
        gainers = sorted([m for m in movers if m[1] > 0], key=lambda x: x[1], reverse=True)[:3]
        losers = sorted([m for m in movers if m[1] < 0], key=lambda x: x[1])[:3]
        lines.append("## Movers\n")
        if gainers:
            lines.append("**Top gainers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in gainers))
        if losers:
            lines.append("**Top losers:** " + ", ".join(f"{s} {p:+.2f}%" for s, p in losers))
        lines.append("")

    if news and any(v for v in news.values()):
        lines.append("## News\n")
        for symbol, headlines in news.items():
            if headlines:
                lines.append(f"**{symbol}**")
                for headline in headlines:
                    lines.append(f"- {headline}")
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
    news: Optional[Dict[str, List[str]]],
    report_date: str,
    report_filename: str,
) -> str:
    gain_loss = total_value - total_cost
    gain_pct = (gain_loss / total_cost * 100) if total_cost else 0
    peak = snap.get('peak', total_value)
    drawdown_pct = ((total_value - peak) / peak * 100) if peak else 0
    ytd_base = snap.get('ytd_baseline', total_value)
    ytd_pct = ((total_value - ytd_base) / ytd_base * 100) if ytd_base else 0

    lines = [
        f"📊 *Portfolio — {report_date}*",
        "─" * 28,
        f"{ccy(total_value)}  |  P&L {gain_pct:+.1f}%",
        f"YTD {ytd_pct:+.2f}%  |  Drawdown {drawdown_pct:.2f}%",
        "",
    ]

    movers = [(h['symbol'], h.get('pl_pct', 0)) for h in holdings_data]
    gainers = sorted([m for m in movers if m[1] > 0], key=lambda x: x[1], reverse=True)[:3]
    losers = sorted([m for m in movers if m[1] < 0], key=lambda x: x[1])[:3]
    if gainers:
        lines.append("▲ " + "  ".join(f"{s} {p:+.2f}%" for s, p in gainers))
    if losers:
        lines.append("▼ " + "  ".join(f"{s} {p:+.2f}%" for s, p in losers))
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
        for symbol, headlines in list(news.items())[:5]:
            for h in headlines[:2]:
                news_lines.append(f"• *{symbol}*: {h}")
        if news_lines:
            lines.append("📰 *News*")
            lines.extend(news_lines)
            lines.append("")

    lines.append(f"_{report_filename}_")
    return "\n".join(lines)


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

        avg_cost_base = h['avg_cost'] * fx
        current_base = current_price * fx if current_price is not None else None
        value_base = (current_base if current_base is not None else avg_cost_base) * h['quantity']
        cost_base = avg_cost_base * h['quantity']
        pl_pct = ((current_base - avg_cost_base) / avg_cost_base * 100) if current_base else 0.0

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

    report_date = date.today().isoformat()
    report = format_report(
        holdings_data, total_value, total_cost, snap, macro, news, report_date
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
                report_date, out_path.name,
            )
            tg.send(msg)
        else:
            print("Telegram not configured — skipping (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Generate daily portfolio report")
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--no-macro',    action='store_true', help='Skip FRED macro fetch')
    parser.add_argument('--no-news',     action='store_true', help='Skip news headlines')
    parser.add_argument('--no-telegram', action='store_true', help='Skip Telegram delivery')
    args = parser.parse_args()

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
