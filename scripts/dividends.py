"""
Dividend report: per-holding income, yield, lifetime received, withholding.

For each holding it computes (in SGD base):
  - Trailing-12m dividend per share and income (shares × DPS × FX)
  - Yield on current value and yield on cost
  - Lifetime dividends received since purchase (dated lots only)
  - Withholding adjustment: US-listed dividends are taxed 30% for a Singapore
    resident (no SG–US treaty rate); SGX dividends are tax-free.

Outputs:
  data/dividends.json              — structured data
  output/dividends-YYYY-MM-DD.md   — readable report (also printed)

Usage:
  python scripts/dividends.py
  python scripts/dividends.py --holdings data/holdings.csv

Caveats:
  - Income/lifetime figures convert at *current* FX (a snapshot approximation;
    historical payouts were at the FX of their pay date).
  - Withholding rule is by listing currency (USD → 30%). ADRs like ASML (NL 15%)
    or TSM (TW 21%) would need per-symbol rates if added to holdings.
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from src import config
from src.fetchers import StooqFetcher, YFinanceFetcher
from src.fetchers.dividends import DividendFetcher, trailing_12m, received_since
from scripts.daily_report import find_holdings_file, load_holdings, get_fx_rate, fetch_price

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.dividends')

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))
DATA_DIR = PROJECT_ROOT / 'data'
_PENCE = {'GBp', 'GBX'}

# Dividend withholding tax for a Singapore-resident investor, by listing currency.
# US-domiciled payers: 30% (no favourable SG–US treaty rate). SGX: tax-free.
WITHHOLDING = {'USD': 0.30, 'SGD': 0.0}


def _sym(ccy: str) -> str:
    return {'SGD': 'S$', 'USD': '$', 'TWD': 'NT$'}.get(ccy, ccy + ' ')


def build(holdings: List[Dict]) -> Dict:
    symbols = sorted({h['symbol'] for h in holdings})
    print(f"Fetching dividend history for {len(symbols)} symbols...")
    divs = DividendFetcher().fetch_many(symbols)

    yf, stooq = YFinanceFetcher(), StooqFetcher()
    px: Dict[str, Optional[float]] = {}
    fxr: Dict[str, float] = {}

    def price(sym):
        if sym not in px:
            px[sym] = fetch_price(sym, yf, stooq)['price']
        return px[sym]

    def fx(ccy):
        if ccy not in fxr:
            fxr[ccy] = get_fx_rate(ccy)
        return fxr[ccy]

    # Aggregate by symbol -----------------------------------------------------
    rows = []
    for sym in symbols:
        lots = [h for h in holdings if h['symbol'] == sym]
        ccy = lots[0]['currency']
        pence = 0.01 if ccy in _PENCE else 1.0
        rate = fx(ccy) * pence
        qty = sum(h['quantity'] for h in lots)

        ttm_dps = trailing_12m(divs.get(sym))          # per share, native ccy
        ttm_income = ttm_dps * qty * rate              # SGD

        p = price(sym)
        cur_value = (p * qty * rate) if p is not None else 0.0

        # cost basis (SGD) for yield-on-cost — only lots with a known cost
        cost = sum(h['quantity'] * h['avg_cost'] * rate
                   for h in lots if h['avg_cost'] is not None)

        # lifetime received since purchase (dated lots only)
        lifetime = 0.0
        lifetime_known = True
        for h in lots:
            if h.get('contract_date'):
                since = datetime.strptime(h['contract_date'], '%Y-%m-%d')
                lifetime += received_since(divs.get(sym), since) * h['quantity'] * rate
            elif h['avg_cost'] is not None:
                lifetime_known = False   # has cost but no date → can't time dividends

        wht = WITHHOLDING.get(ccy, 0.0)
        rows.append({
            'symbol':        sym,
            'currency':      ccy,
            'shares':        round(qty, 4),
            'ttm_dps':       round(ttm_dps, 4),
            'ttm_income':    round(ttm_income, 2),
            'ttm_income_net': round(ttm_income * (1 - wht), 2),
            'withholding_pct': round(wht * 100, 0),
            'cur_value':     round(cur_value, 2),
            'yield_on_value': round(ttm_income / cur_value * 100, 2) if cur_value > 0 else None,
            'yield_on_cost':  round(ttm_income / cost * 100, 2) if cost > 0 else None,
            'lifetime_received': round(lifetime, 2) if lifetime > 0 else 0.0,
            'lifetime_complete': lifetime_known,
            'pays_dividend': ttm_dps > 0 or (divs.get(sym) is not None and len(divs.get(sym)) > 0),
        })

    payers = [r for r in rows if r['pays_dividend']]
    payers.sort(key=lambda r: r['ttm_income'], reverse=True)

    total_income = sum(r['ttm_income'] for r in rows)
    total_net = sum(r['ttm_income_net'] for r in rows)
    total_value = sum(r['cur_value'] for r in rows)
    total_lifetime = sum(r['lifetime_received'] for r in rows)

    return {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'base_currency': config.BASE_CURRENCY,
            'n_payers': len(payers),
            'n_symbols': len(rows),
        },
        'summary': {
            'ttm_income_gross': round(total_income, 2),
            'ttm_income_net':   round(total_net, 2),
            'withholding_drag': round(total_income - total_net, 2),
            'portfolio_yield_gross': round(total_income / total_value * 100, 2) if total_value else None,
            'portfolio_yield_net':   round(total_net / total_value * 100, 2) if total_value else None,
            'lifetime_received': round(total_lifetime, 2),
        },
        'holdings': payers,
        'non_payers': sorted(r['symbol'] for r in rows if not r['pays_dividend']),
    }


def format_report(d: Dict) -> str:
    base = d['meta']['base_currency']
    s = d['summary']
    L = [f"# Dividend Report — {date.today().isoformat()}\n",
         f"**Base currency:** {base} · {d['meta']['n_payers']} dividend-payers "
         f"of {d['meta']['n_symbols']} holdings\n",
         "## Summary\n",
         "| Metric | Value |", "|---|---|",
         f"| TTM dividend income (gross) | {_sym(base)}{s['ttm_income_gross']:,.0f} |",
         f"| TTM income (net of withholding) | {_sym(base)}{s['ttm_income_net']:,.0f} |",
         f"| Withholding drag (US 30%) | −{_sym(base)}{s['withholding_drag']:,.0f} |",
         f"| Portfolio yield (gross / net) | {s['portfolio_yield_gross']}% / {s['portfolio_yield_net']}% |",
         f"| Lifetime dividends received (dated lots) | {_sym(base)}{s['lifetime_received']:,.0f} |",
         ""]

    L += ["## Dividend Payers\n",
          "| Symbol | Shares | TTM DPS | TTM Income | Net | Yield (val) | Yield (cost) | Lifetime | WHT |",
          "|--------|-------:|--------:|-----------:|----:|------------:|-------------:|---------:|----:|"]
    for r in d['holdings']:
        life = f"{_sym(base)}{r['lifetime_received']:,.0f}" + ("" if r['lifetime_complete'] else "*")
        yoc = f"{r['yield_on_cost']}%" if r['yield_on_cost'] is not None else "—"
        L.append(
            f"| {r['symbol']} | {r['shares']:.4g} | {_sym(r['currency'])}{r['ttm_dps']:.4g} | "
            f"{_sym(base)}{r['ttm_income']:,.0f} | {_sym(base)}{r['ttm_income_net']:,.0f} | "
            f"{r['yield_on_value']}% | {yoc} | {life} | {r['withholding_pct']:.0f}% |"
        )
    L.append("")
    if d['non_payers']:
        L.append(f"**Non-payers:** {', '.join(d['non_payers'])}\n")
    L += ["\n*\\* lifetime incomplete — symbol has undated lots, so dividends before "
          "the (unknown) purchase date may be over/under-counted.*",
          "*Income converted at current FX; US dividends withheld 30% (SG resident). "
          "SGX dividends are tax-free.*",
          f"\n*Generated {d['meta']['generated']}*"]
    return "\n".join(L)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dividend income & yield report")
    parser.add_argument('--holdings', help='Path to holdings CSV')
    args = parser.parse_args()

    holdings = load_holdings(args.holdings or find_holdings_file())
    print(f"Loaded {len(holdings)} lots")

    data = build(holdings)
    report = format_report(data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'dividends.json').write_text(json.dumps(data, indent=2))
    out = OUTPUT_DIR / f"dividends-{date.today().isoformat()}.md"
    out.write_text(report)

    print(f"\n{'='*60}\n{report}\n{'='*60}")
    print(f"\nSaved: {out}  and  data/dividends.json")


if __name__ == '__main__':
    main()
