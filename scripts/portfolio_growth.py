"""
Portfolio growth over time, decomposed into:
  1. Invested capital  — cumulative fund injections (cost basis of each lot, by purchase date)
  2. Capital gains      — market value above invested capital (stock appreciation + FX)

Method
------
- Each lot injects (quantity × avg_cost × FX-at-purchase) of capital on its ContractDate.
- Invested capital at time t = sum of injections on/before t (a rising step function).
- Market value at time t = sum over lots-held-by-t of (quantity × historical price, FX→SGD).
- Capital gain at time t = market value − invested capital.

Everything is in SGD (config.BASE_CURRENCY). Weekly resolution.

Outputs:
  data/portfolio_growth.json   — the time series (gitignored)
  output/portfolio-growth.html — interactive Chart.js area chart (gitignored)

View:
  open output/portfolio-growth.html
  # or: cd output && python -m http.server 8080  → http://localhost:8080/portfolio-growth.html

Usage:
  python scripts/portfolio_growth.py
  python scripts/portfolio_growth.py --holdings data/holdings.csv
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

import pandas as pd
from dotenv import load_dotenv

from src import config
from src.fetchers import StooqFetcher, YFinanceFetcher
from src.fetchers.history import HistoryFetcher
from src.fetchers.fx import FXConverter
from scripts.daily_report import find_holdings_file, load_holdings, get_fx_rate, fetch_price

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.growth')

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))
DATA_DIR = PROJECT_ROOT / 'data'
_PENCE = {'GBp', 'GBX'}


# ---------------------------------------------------------------------------
# Time-series construction
# ---------------------------------------------------------------------------

def build_growth(holdings: List[Dict]) -> Dict:
    # Partition lots ---------------------------------------------------------
    #  - dated   : cost + contract date  → drive the timeline (accurate)
    #  - undated : cost but no date       → excluded from the timeline (we can't
    #              place the injection in time without faking a loss); reported
    #              separately at current value
    #  - no_cost : no cost basis          → excluded entirely (can't decompose)
    dated   = [h for h in holdings if h['avg_cost'] is not None and h.get('contract_date')]
    undated = [h for h in holdings if h['avg_cost'] is not None and not h.get('contract_date')]
    no_cost = [h for h in holdings if h['avg_cost'] is None]

    if not dated:
        raise RuntimeError("No lots with both a cost and a contract date — cannot build a timeline.")

    for h in dated:
        h['_inj'] = datetime.strptime(h['contract_date'], '%Y-%m-%d').date()
    earliest = min(h['_inj'] for h in dated)

    # Price all costed symbols (so undated lots can be valued for the note too)
    symbols = sorted({h['symbol'] for h in dated + undated})
    start = earliest.isoformat()
    end = date.today().isoformat()

    # Historical prices (weekly), native currency --------------------------
    print(f"Fetching weekly history for {len(symbols)} symbols since {start}...")
    prices_native = HistoryFetcher().fetch(symbols, start, end, interval='1wk')
    if prices_native.empty:
        raise RuntimeError("No price history returned.")

    # Convert to SGD ---------------------------------------------------------
    ccy_map = {h['symbol']: h['currency'] for h in dated + undated}
    print(f"Converting to {config.BASE_CURRENCY}...")
    prices_sgd = FXConverter().to_base_currency(prices_native, ccy_map)

    # Use the natural (union) weekly index and fill each column's gaps.
    # NB: do NOT reindex to a strict W-MON grid — symbols whose weekly bars
    # land on a different weekday would become all-NaN.
    prices_sgd = prices_sgd.sort_index().ffill().bfill()
    idx = prices_sgd.index

    # FX series per currency for cost-basis-at-purchase ---------------------
    fx_series: Dict[str, pd.Series] = {}
    for ccy in set(ccy_map.values()):
        if ccy in _PENCE:
            s = FXConverter().fetch_fx_series('GBP', start, end)
        elif ccy == config.BASE_CURRENCY:
            continue
        else:
            s = FXConverter().fetch_fx_series(ccy, start, end)
        if s is not None and not s.empty:
            fx_series[ccy] = s.reindex(idx).ffill().bfill()

    def fx_at(ccy: str, d: date) -> float:
        if ccy == config.BASE_CURRENCY:
            return 1.0
        key = 'GBP' if ccy in _PENCE else ccy
        s = fx_series.get(key)
        if s is None:
            s = fx_series.get(ccy)
        if s is None or s.empty:
            return get_fx_rate(ccy)  # spot fallback
        try:
            val = float(s.asof(pd.Timestamp(d)))
            return val if val == val else get_fx_rate(ccy)  # NaN guard
        except Exception:
            return get_fx_rate(ccy)

    # Per-lot SGD cost basis (FX at purchase) -------------------------------
    for h in dated:
        ccy = h['currency']
        rate = fx_at(ccy, h['_inj'])
        pence_adj = 0.01 if ccy in _PENCE else 1.0
        h['_sgd_cost'] = h['quantity'] * h['avg_cost'] * rate * pence_adj

    # Build invested-capital and market-value series (DATED lots only) ------
    invested = pd.Series(0.0, index=idx)
    market = pd.Series(0.0, index=idx)
    idx_dates = idx.date

    for h in dated:
        held_mask = pd.Series(idx_dates >= h['_inj'], index=idx)
        invested = invested + held_mask.map(lambda held: h['_sgd_cost'] if held else 0.0)
        if h['symbol'] not in prices_sgd.columns:
            continue
        contrib = (prices_sgd[h['symbol']] * h['quantity']).where(held_mask, 0.0)
        market = market + contrib

    # Current value of undated lots (excluded from timeline, shown in note) --
    undated_value = 0.0
    for h in undated:
        if h['symbol'] in prices_sgd.columns:
            undated_value += float(prices_sgd[h['symbol']].iloc[-1]) * h['quantity']

    # Assemble series --------------------------------------------------------
    series = []
    for ts in idx:
        inv = float(invested.loc[ts])
        mkt = float(market.loc[ts])
        if inv <= 0 and mkt <= 0:
            continue  # before any holdings existed
        series.append({
            'date':     ts.date().isoformat(),
            'invested': round(inv, 2),
            'value':    round(mkt, 2),
            'gain':     round(mkt - inv, 2),
            'gain_pct': round((mkt - inv) / inv * 100, 2) if inv > 0 else None,
        })

    # --- Endpoint reconciliation with the dashboard -------------------------
    # Prefer the dashboard's own stored values (data/portfolio_data.json) so the
    # two views agree EXACTLY — same prices, FX, instant. A fresh fetch would
    # price at a different moment and re-introduce a gap. Fall back to live spot.
    dated_spot, undated_spot, nocost_spot, full_value, source = _reconcile_endpoint(
        dated, undated, no_cost
    )

    # Pin the chart's last point to the dated-lots value at the dashboard's pricing
    if series:
        inv_last = series[-1]['invested']
        series[-1]['value'] = round(dated_spot, 2)
        series[-1]['gain'] = round(dated_spot - inv_last, 2)
        series[-1]['gain_pct'] = round((dated_spot - inv_last) / inv_last * 100, 2) if inv_last else None

    latest = series[-1] if series else {}
    return {
        'meta': {
            'generated':     datetime.now().strftime('%Y-%m-%d %H:%M'),
            'base_currency': config.BASE_CURRENCY,
            'start':         series[0]['date'] if series else None,
            'end':           series[-1]['date'] if series else None,
            'n_points':      len(series),
            'full_value':    round(full_value, 2),       # all lots (= dashboard total)
            'shown_value':   round(dated_spot, 2),       # dated lots only (what the chart plots)
            'undated_lots':  sorted({h['symbol'] for h in undated}),
            'undated_value': round(undated_spot, 2),
            'excluded_no_cost': sorted({h['symbol'] for h in no_cost}),
            'nocost_value':  round(nocost_spot, 2),
            'endpoint_source': source,                    # 'dashboard' or 'live spot'
        },
        'latest': latest,
        'series': series,
    }


def _reconcile_endpoint(dated, undated, no_cost):
    """Return (dated_value, undated_value, nocost_value, full_value, source).

    Prefer data/portfolio_data.json (the dashboard's stored, same-instant values)
    so the growth chart and dashboard agree exactly. Fall back to a live spot
    fetch if that file is absent.
    """
    pdata = DATA_DIR / 'portfolio_data.json'
    if pdata.exists():
        try:
            d = json.loads(pdata.read_text())
            lots = d['lots']
            hcost = lambda l: l.get('avg_cost') is not None
            hdate = lambda l: bool(l.get('contract_date'))
            dated_v   = sum(l['value_sgd'] for l in lots if hcost(l) and hdate(l))
            undated_v = sum(l['value_sgd'] for l in lots if hcost(l) and not hdate(l))
            nocost_v  = sum(l['value_sgd'] for l in lots if not hcost(l))
            full_v    = d['summary']['total_value']
            print(f"Endpoint reconciled to dashboard (data/portfolio_data.json, {d['meta']['generated']})")
            return dated_v, undated_v, nocost_v, full_v, 'dashboard'
        except Exception as e:
            logger.warning(f"Could not read portfolio_data.json ({e}); falling back to live spot")

    # Fallback: live spot fetch (different instant than the dashboard)
    print("portfolio_data.json not found — fetching live spot prices...")
    yf, stooq = YFinanceFetcher(), StooqFetcher()
    px: Dict[str, Optional[float]] = {}
    fxr: Dict[str, float] = {}

    def val(h) -> float:
        sym, ccy = h['symbol'], h['currency']
        if sym not in px:
            px[sym] = fetch_price(sym, yf, stooq)['price']
        if px[sym] is None:
            return 0.0
        if ccy not in fxr:
            fxr[ccy] = get_fx_rate(ccy)
        pence = 0.01 if ccy in _PENCE else 1.0
        return h['quantity'] * px[sym] * fxr[ccy] * pence

    dated_v   = sum(val(h) for h in dated)
    undated_v = sum(val(h) for h in undated)
    nocost_v  = sum(val(h) for h in no_cost)
    return dated_v, undated_v, nocost_v, dated_v + undated_v + nocost_v, 'live spot'


# ---------------------------------------------------------------------------
# HTML (Chart.js)
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Growth</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#2d3436}
.hdr{background:linear-gradient(135deg,#2c3e50,#27ae60);color:#fff;padding:24px 32px}
.hdr h1{font-size:1.5rem;font-weight:700}
.hdr .sub{font-size:.8rem;opacity:.75;margin-top:3px}
.kpis{display:flex;flex-wrap:wrap;gap:14px;margin-top:16px}
.kpi{background:rgba(255,255,255,.12);border-radius:10px;padding:10px 18px;min-width:150px}
.kpi .lbl{font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;opacity:.8}
.kpi .val{font-size:1.3rem;font-weight:700;margin-top:2px}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
.card{background:#fff;border-radius:14px;padding:22px 26px;box-shadow:0 2px 12px rgba(0,0,0,.06)}
.note{font-size:.72rem;color:#b2bec3;margin-top:14px;line-height:1.6}
</style>
</head>
<body>
<div class="hdr">
  <h1>Portfolio Growth — Capital vs Gains</h1>
  <div class="sub">Generated __GENERATED__ · Base currency: __BASE__ · __START__ → __END__</div>
  <div class="kpis" id="kpis"></div>
</div>
<div class="wrap">
  <div class="card">
    <div style="position:relative;height:480px"><canvas id="chart"></canvas></div>
    <div class="note" id="note"></div>
  </div>
</div>
<script>
const D = __DATA__;
const CCY = {SGD:'S$',USD:'$'}[D.meta.base_currency] || (D.meta.base_currency+' ');
const fmt = v => v==null ? '—' : CCY + Math.round(v).toLocaleString('en-SG');
const fmtP = v => v==null ? '—' : (v>0?'+':'')+v.toFixed(1)+'%';

const L = D.latest;
document.getElementById('kpis').innerHTML = [
  {l:'Full Portfolio (all lots)', v: fmt(D.meta.full_value)},
  {l:'Shown Here (dated lots)', v: fmt(D.meta.shown_value)},
  {l:'Invested Capital', v: fmt(L.invested)},
  {l:'Capital Gains', v: fmt(L.gain)+' ('+fmtP(L.gain_pct)+')'},
].map(k=>`<div class="kpi"><div class="lbl">${k.l}</div><div class="val">${k.v}</div></div>`).join('');

const labels = D.series.map(p=>p.date);
const invested = D.series.map(p=>p.invested);
const value = D.series.map(p=>p.value);

new Chart(document.getElementById('chart'), {
  type:'line',
  data:{ labels, datasets:[
    { label:'Invested Capital (fund injections)', data:invested,
      borderColor:'#2980b9', backgroundColor:'rgba(41,128,185,.35)',
      fill:'origin', borderWidth:2, pointRadius:0, tension:.1, stepped:false },
    { label:'Portfolio Value (market)', data:value,
      borderColor:'#27ae60', backgroundColor:'rgba(39,174,96,.30)',
      fill:'-1', borderWidth:2, pointRadius:0, tension:.1 },
  ]},
  options:{
    responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
    plugins:{
      legend:{position:'top'},
      tooltip:{callbacks:{label:ctx=>{
        const p=D.series[ctx.dataIndex];
        if(ctx.datasetIndex===0) return 'Invested: '+fmt(p.invested);
        return ['Value: '+fmt(p.value), 'Gain: '+fmt(p.gain)+' ('+fmtP(p.gain_pct)+')'];
      }}}
    },
    scales:{
      x:{ticks:{maxTicksLimit:14,autoSkip:true},grid:{display:false}},
      y:{ticks:{callback:v=>fmt(v)},grid:{color:'#f1f2f6'}}
    }
  }
});

// Caveats
let notes = ['This timeline plots only lots with both a cost and a purchase date ('+fmt(D.meta.shown_value)+'). Your full portfolio is '+fmt(D.meta.full_value)+' — the difference is excluded lots (below). The final point uses today’s spot price; earlier points are weekly closes.'];
notes.push('Green band above the blue line = unrealised capital gains; below = underwater. The early underwater stretch is real — Banyan Tree and COSCO fell sharply after 2008 and never recovered.');
if(D.meta.undated_lots.length) notes.push('Excluded — no purchase date (~'+fmt(D.meta.undated_value)+'): '+D.meta.undated_lots.join(', ')+'. Add ContractDate in holdings.csv to include them.');
if(D.meta.excluded_no_cost.length) notes.push('Excluded — no cost basis (~'+fmt(D.meta.nocost_value)+'): '+D.meta.excluded_no_cost.join(', ')+'.');
document.getElementById('note').innerHTML = notes.map(n=>'• '+n).join('<br>');
</script>
</body>
</html>
"""


def save_outputs(data: Dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    (DATA_DIR / 'portfolio_growth.json').write_text(json.dumps(data, indent=2))
    print(f"Data saved:  {DATA_DIR / 'portfolio_growth.json'}")

    html = (HTML
            .replace('__DATA__', json.dumps(data))
            .replace('__GENERATED__', data['meta']['generated'])
            .replace('__BASE__', data['meta']['base_currency'])
            .replace('__START__', str(data['meta']['start']))
            .replace('__END__', str(data['meta']['end'])))
    out = OUTPUT_DIR / 'portfolio-growth.html'
    out.write_text(html)
    print(f"Chart saved: {out}")
    print(f"\nView:  open {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Portfolio growth: capital vs gains over time')
    parser.add_argument('--holdings', help='Path to holdings CSV')
    args = parser.parse_args()

    holdings = load_holdings(args.holdings or find_holdings_file())
    print(f"Loaded {len(holdings)} lots")

    data = build_growth(holdings)
    L, m = data['latest'], data['meta']
    bc = m['base_currency']
    print(f"\n{'='*56}")
    print(f"Full portfolio (all lots, daily spot): {bc} {m['full_value']:,.0f}")
    print(f"Shown on chart (dated lots only):      {bc} {m['shown_value']:,.0f}")
    print(f"  Invested capital: {bc} {L['invested']:,.0f}")
    print(f"  Capital gains:    {bc} {L['gain']:,.0f} ({L['gain_pct']:+.1f}%)")
    if m['undated_lots']:
        print(f"Excluded — no purchase date (~{bc} {m['undated_value']:,.0f}): "
              f"{', '.join(m['undated_lots'])}")
    if m['excluded_no_cost']:
        print(f"Excluded — no cost basis (~{bc} {m['nocost_value']:,.0f}): "
              f"{', '.join(m['excluded_no_cost'])}")
    print('='*56)

    save_outputs(data)


if __name__ == '__main__':
    main()
