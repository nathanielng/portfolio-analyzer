"""
Portfolio snapshot: fetch current prices, compute per-lot metrics, generate dashboard.

Outputs:
  data/portfolio_data.json   — structured data (for programmatic use)
  output/dashboard.html      — self-contained interactive dashboard (Chart.js)

View dashboard:
  open output/dashboard.html          # direct browser open (requires internet for CDN)
  cd output && python -m http.server 8080  # then http://localhost:8080/dashboard.html

Usage:
    python scripts/portfolio_snapshot.py
    python scripts/portfolio_snapshot.py --holdings data/holdings.csv
"""

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

import csv as _csv

from src import config
from src.fetchers import StooqFetcher, YFinanceFetcher
from src.fetchers.history import HistoryFetcher, PRESETS, _preset_dates
from src.fetchers.fx import FXConverter
from src.analyzers.risk_metrics import RiskMetrics
from scripts.daily_report import fetch_price, find_holdings_file, get_fx_rate, load_holdings

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('portfolio_analyzer.snapshot')

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'output')))
DATA_DIR = PROJECT_ROOT / 'data'

_PENCE = {'GBp', 'GBX'}


# ---------------------------------------------------------------------------
# Per-lot metric calculation
# ---------------------------------------------------------------------------

def compute_lot(h: Dict, current_price: Optional[float], fx: float) -> Dict:
    """Compute all metrics for one holdings lot."""
    qty = h['quantity']
    avg_cost = h['avg_cost']          # None if unknown
    ccy = h['currency']
    is_pence = ccy in _PENCE
    fx_adj = fx / 100.0 if is_pence else fx

    current_price_sgd = current_price * fx_adj if current_price is not None else None
    avg_cost_sgd = avg_cost * fx_adj if avg_cost is not None else None

    value_sgd = qty * current_price_sgd if current_price_sgd is not None else 0.0
    cost_sgd = qty * avg_cost_sgd if avg_cost_sgd is not None else 0.0

    gain_sgd = (value_sgd - cost_sgd) if (avg_cost_sgd is not None and current_price_sgd is not None) else None
    gain_pct = ((current_price - avg_cost) / avg_cost * 100
                if (avg_cost and current_price is not None) else None)

    # Annualized return (CAGR) from contract date
    contract_date = h.get('contract_date') or 'NA'
    years_held = None
    ann_return_pct = None

    if contract_date and contract_date.upper() != 'NA' and avg_cost and current_price is not None:
        try:
            buy_date = datetime.strptime(contract_date, '%Y-%m-%d').date()
            years_held = (date.today() - buy_date).days / 365.25
            if years_held > 0:
                ann_return_pct = ((current_price / avg_cost) ** (1 / years_held) - 1) * 100
        except ValueError:
            pass

    return {
        'symbol':           h['symbol'],
        'qty':              round(qty, 6),
        'avg_cost':         round(avg_cost, 4) if avg_cost is not None else None,
        'avg_cost_sgd':     round(avg_cost_sgd, 4) if avg_cost_sgd is not None else None,
        'currency':         ccy,
        'current_price':    round(current_price, 4) if current_price is not None else None,
        'current_price_sgd': round(current_price_sgd, 4) if current_price_sgd is not None else None,
        'value_sgd':        round(value_sgd, 2),
        'cost_sgd':         round(cost_sgd, 2),
        'gain_sgd':         round(gain_sgd, 2) if gain_sgd is not None else None,
        'gain_pct':         round(gain_pct, 2) if gain_pct is not None else None,
        'years_held':       round(years_held, 2) if years_held is not None else None,
        'ann_return_pct':   round(ann_return_pct, 2) if ann_return_pct is not None else None,
        'account':          h['account'],
        'broker':           h['broker'],
        'contract_date':    contract_date if contract_date.upper() != 'NA' else None,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _agg_by_key(lots: List[Dict], key: str) -> List[Dict]:
    """Aggregate lots by a string key (account, currency) into value + pct."""
    buckets: Dict[str, float] = {}
    for lot in lots:
        k = lot[key]
        buckets[k] = buckets.get(k, 0.0) + lot['value_sgd']
    total = sum(buckets.values()) or 1
    return sorted(
        [{'name': k, 'value_sgd': round(v, 2), 'pct': round(v / total * 100, 2)}
         for k, v in buckets.items()],
        key=lambda x: x['value_sgd'], reverse=True,
    )


def aggregate_by_symbol(lots: List[Dict]) -> List[Dict]:
    symbols: Dict[str, Dict] = {}
    for lot in lots:
        sym = lot['symbol']
        if sym not in symbols:
            symbols[sym] = dict(currency=lot['currency'], total_qty=0.0,
                                total_cost_sgd=0.0, total_value_sgd=0.0,
                                has_cost=False, accounts=set(), lots=[])
        e = symbols[sym]
        e['total_qty'] += lot['qty']
        e['total_value_sgd'] += lot['value_sgd']
        e['total_cost_sgd'] += lot['cost_sgd']
        if lot['gain_sgd'] is not None:
            e['has_cost'] = True
        e['accounts'].add(lot['account'])
        e['lots'].append(lot)

    total_portfolio = sum(e['total_value_sgd'] for e in symbols.values()) or 1
    result = []
    for sym, e in sorted(symbols.items(), key=lambda x: x[1]['total_value_sgd'], reverse=True):
        tv = e['total_value_sgd']
        tc = e['total_cost_sgd']
        gain = round(tv - tc, 2) if e['has_cost'] else None
        gain_pct = round((tv - tc) / tc * 100, 2) if (e['has_cost'] and tc > 0) else None

        # Cost-weighted average annualised return across lots that have CAGR + known cost
        ann_lots = [(l['ann_return_pct'], l['cost_sgd'])
                    for l in e['lots']
                    if l.get('ann_return_pct') is not None
                    and l.get('years_held', 0) >= 1   # < 1yr CAGRs are too extreme to be meaningful
                    and l['cost_sgd'] > 0]
        ann_weight = sum(c for _, c in ann_lots)
        ann_return = (round(sum(r * c for r, c in ann_lots) / ann_weight, 2)
                      if ann_weight > 0 else None)

        result.append({
            'symbol':          sym,
            'currency':        e['currency'],
            'total_qty':       round(e['total_qty'], 4),
            'total_cost_sgd':  round(tc, 2),
            'total_value_sgd': round(tv, 2),
            'total_gain_sgd':  gain,
            'gain_pct':        gain_pct,
            'ann_return_pct':  ann_return,
            'weight_pct':      round(tv / total_portfolio * 100, 2),
            'accounts':        sorted(e['accounts']),
            'lots':            e['lots'],
        })
    return result


# ---------------------------------------------------------------------------
# Main data builder
# ---------------------------------------------------------------------------

def build_data(holdings: List[Dict]) -> Dict:
    yf = YFinanceFetcher()
    stooq = StooqFetcher()

    # Fetch price once per unique symbol
    unique_symbols = list(dict.fromkeys(h['symbol'] for h in holdings))
    print(f"\nFetching prices for {len(unique_symbols)} symbols...")
    price_cache: Dict[str, Optional[float]] = {}
    for i, sym in enumerate(unique_symbols):
        if i > 0:
            time.sleep(0.25)
        print(f"  {sym}...", end=' ', flush=True)
        r = fetch_price(sym, yf, stooq)
        price_cache[sym] = r['price']
        print(r['price'] or 'N/A')

    # Fetch FX rates
    currencies = list(dict.fromkeys(h['currency'] for h in holdings))
    fx_cache: Dict[str, float] = {}
    for ccy in currencies:
        fx_cache[ccy] = get_fx_rate(ccy)

    # Compute lot metrics
    lots = [compute_lot(h, price_cache.get(h['symbol']), fx_cache[h['currency']])
            for h in holdings]

    by_symbol = aggregate_by_symbol(lots)
    by_account = _agg_by_key(lots, 'account')
    by_currency = _agg_by_key(lots, 'currency')

    total_value = sum(l['value_sgd'] for l in lots)
    total_cost = sum(l['cost_sgd'] for l in lots)
    total_gain = total_value - total_cost

    # Portfolio-level cost-weighted annualised return (lots with ≥1yr history only)
    ann_lots_p = [(l['ann_return_pct'], l['cost_sgd'])
                  for l in lots
                  if l.get('ann_return_pct') is not None
                  and l.get('years_held', 0) >= 1
                  and l['cost_sgd'] > 0]
    ann_w = sum(c for _, c in ann_lots_p)
    portfolio_ann_return = (round(sum(r * c for r, c in ann_lots_p) / ann_w, 2)
                            if ann_w > 0 else None)

    # Capture USDSGD rate for the dashboard toggles
    usdsgd = fx_cache.get('USD') or get_fx_rate('USD')

    return {
        'meta': {
            'generated':          datetime.now().strftime('%Y-%m-%d %H:%M'),
            'base_currency':      config.BASE_CURRENCY,
            'n_lots':             len(lots),
            'n_symbols':          len(by_symbol),
            'fx_rates':           {'USDSGD': round(usdsgd, 4)},
            'fx_cost_pct':        round(config.FX_CONVERSION_COST * 100, 2),
        },
        'summary': {
            'total_value':       round(total_value, 2),
            'total_cost':        round(total_cost, 2),
            'total_gain':        round(total_gain, 2),
            'total_gain_pct':    round(total_gain / total_cost * 100, 2) if total_cost > 0 else None,
            'portfolio_ann_pct': portfolio_ann_return,  # cost-weighted CAGR, ≥1yr lots only
        },
        'lots':        lots,
        'by_symbol':   by_symbol,
        'by_account':  by_account,
        'by_currency':  by_currency,
        'correlation':  None,  # filled in by main() after build_data()
    }


# ---------------------------------------------------------------------------
# Watchlist loading
# ---------------------------------------------------------------------------

def load_watchlist(path: Optional[str] = None) -> List[Dict]:
    """Load watchlist CSV (Symbol, Currency columns required). Returns [] if absent."""
    candidates = [
        path,
        str(PROJECT_ROOT / 'data' / 'watchlist.csv'),
        str(PROJECT_ROOT / 'examples' / 'watchlist.csv'),
    ]
    for p in candidates:
        if not p or not Path(p).exists():
            continue
        rows = []
        with open(p, newline='') as f:
            reader = _csv.DictReader(
                filter(lambda line: not line.startswith('#'), f)
            )
            for row in reader:
                sym = row.get('Symbol', '').strip()
                ccy = row.get('Currency', 'USD').strip().upper()
                if sym:
                    rows.append({'symbol': sym, 'currency': ccy})
        if rows:
            print(f"Loaded {len(rows)} watchlist symbols from {p}")
            return rows
    return []


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------

def compute_correlations(
    symbols: List[str],
    currency_map: Dict[str, str],
    preset: str = '1y',
    watchlist: Optional[List[Dict]] = None,
) -> Optional[Dict]:
    """
    Fetch historical prices, convert to SGD, return a correlation matrix dict.

    Uses HistoryFetcher's cache so repeated runs are fast.
    Returns None on failure (dashboard gracefully hides the section).
    """
    try:
        # Merge holdings symbols with watchlist-only symbols
        watch_syms: List[str] = []
        all_symbols = list(symbols)
        all_currency_map = dict(currency_map)
        for w in (watchlist or []):
            if w['symbol'] not in all_symbols:
                all_symbols.append(w['symbol'])
                all_currency_map[w['symbol']] = w['currency']
                watch_syms.append(w['symbol'])

        start, end, interval = _preset_dates(PRESETS[preset])
        print(f"\nFetching {preset} price history for correlation ({start} → {end})...")
        prices = HistoryFetcher().fetch(all_symbols, start, end, interval=interval)
        if prices.empty:
            logger.warning("HistoryFetcher returned no data for correlation")
            return None

        # Convert all prices to SGD base so correlations capture FX risk
        sub_map = {s: all_currency_map.get(s, 'USD') for s in prices.columns}
        prices_sgd = FXConverter().to_base_currency(prices, sub_map)

        rm = RiskMetrics()
        returns = rm.calculate_returns(prices_sgd)
        corr = rm.calculate_correlation_matrix(returns)

        syms = list(corr.columns)
        # only include watchlist symbols that actually made it into the matrix
        watch_in_matrix = [s for s in watch_syms if s in syms]
        print(f"  Correlation matrix: {len(syms)}×{len(syms)} from {len(returns)} observations"
              + (f"  (watchlist: {watch_in_matrix})" if watch_in_matrix else ""))
        return {
            'period':        preset,
            'base_currency': config.BASE_CURRENCY,
            'symbols':       syms,
            'matrix':        [[round(v, 4) for v in row] for row in corr.values.tolist()],
            'n_obs':         len(returns),
            'watchlist':     watch_in_matrix,
        }
    except Exception as e:
        logger.warning(f"Correlation computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# HTML dashboard template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#2d3436}
.hdr{background:linear-gradient(135deg,#2c3e50,#3498db);color:#fff;padding:24px 32px}
.hdr-top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.hdr h1{font-size:1.6rem;font-weight:700;letter-spacing:-.5px}
.hdr .sub{font-size:.8rem;opacity:.7;margin-top:2px}
.kpis{display:flex;flex-wrap:wrap;gap:14px;margin-top:18px}
/* Anonymise button */
.anon-btn{background:rgba(255,255,255,.15);border:1.5px solid rgba(255,255,255,.35);color:#fff;
          padding:8px 18px;border-radius:8px;cursor:pointer;font-size:.82rem;font-weight:700;
          transition:all .2s;white-space:nowrap;margin-top:4px}
.anon-btn:hover{background:rgba(255,255,255,.28)}
body.anon .anon-btn{background:rgba(255,255,255,.95);color:#2c3e50;border-color:transparent}
/* Anonymised state — hide absolute-value elements */
body.anon .abs-col{display:none}
body.anon .kpi-abs{opacity:0;pointer-events:none}
.kpi{background:rgba(255,255,255,.12);border-radius:10px;padding:12px 20px;min-width:140px}
.kpi .lbl{font-size:.7rem;text-transform:uppercase;letter-spacing:.5px;opacity:.8}
.kpi .val{font-size:1.4rem;font-weight:700;margin-top:3px}
.kpi .val.pos{color:#2ecc71}.kpi .val.neg{color:#ff7675}
.wrap{max-width:1400px;margin:0 auto;padding:24px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:20px}
.span2{grid-column:1/-1}
.card{background:#fff;border-radius:14px;padding:20px 24px;box-shadow:0 2px 12px rgba(0,0,0,.06)}

/* Chart card header with toggles */
.chdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:12px;flex-wrap:wrap}
.chdr h3{font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#636e72;padding-top:4px}
.ctrls{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tgl-grp{display:flex;background:#f0f2f5;border-radius:7px;padding:2px}
.tgl{padding:4px 13px;border:none;background:transparent;border-radius:5px;font-size:.75rem;
     font-weight:600;color:#636e72;cursor:pointer;transition:all .15s}
.tgl.on{background:#fff;color:#2d3436;box-shadow:0 1px 4px rgba(0,0,0,.12)}
.tgl-grp.dim{opacity:.35;pointer-events:none}

/* FX note */
.fx-note{font-size:.7rem;color:#b2bec3;margin-bottom:12px;min-height:1rem}

/* Donut charts */
.card h3.alone{font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:#636e72;margin-bottom:16px}

/* Table */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.82rem}
thead th{background:#f8f9fa;padding:10px 12px;text-align:left;font-size:.72rem;font-weight:700;
         text-transform:uppercase;letter-spacing:.4px;color:#636e72;cursor:pointer;user-select:none;
         white-space:nowrap;border-bottom:2px solid #e9ecef}
thead th:hover{background:#eef0f2}
thead th.sort-asc::after{content:' ↑'}thead th.sort-desc::after{content:' ↓'}
tbody td{padding:9px 12px;border-bottom:1px solid #f1f2f6;white-space:nowrap}
tbody tr:hover td{background:#fafbfc}
.pos{color:#27ae60;font-weight:500}.neg{color:#e74c3c;font-weight:500}.na{color:#b2bec3}
.tag{display:inline-block;font-size:.68rem;padding:2px 7px;border-radius:4px;font-weight:600}
.tag-cash{background:#dfe6e9;color:#2d3436}.tag-cpf{background:#dfe6fd;color:#2d3436}
.tag-srs{background:#ffeaa7;color:#6c5ce7}.tag-taxable{background:#d5f5e3;color:#1a7c4d}
@media(max-width:900px){.g2,.g3{grid-template-columns:1fr}.span2{grid-column:auto}}
/* Correlation heatmap */
.corr-scroll{overflow-x:auto;overflow-y:auto;max-height:520px}
.corr-tbl{border-collapse:collapse;font-size:.76rem;white-space:nowrap}
.corr-tbl thead th{position:sticky;top:0;z-index:2;background:#f8f9fa;padding:6px 8px;
  text-align:center;font-size:.7rem;font-weight:700;color:#636e72;min-width:58px}
.corr-tbl thead th:first-child{position:sticky;left:0;z-index:3;text-align:left}
.corr-tbl tbody th{position:sticky;left:0;z-index:1;background:#f8f9fa;padding:6px 10px;
  text-align:right;font-size:.7rem;font-weight:700;color:#636e72;white-space:nowrap}
.corr-tbl td{width:58px;height:40px;text-align:center;font-size:.74rem;font-weight:500;
  cursor:default;transition:filter .1s}
.corr-tbl td:hover{filter:brightness(.88)}
.corr-meta{font-size:.72rem;color:#b2bec3;margin-bottom:10px}
.corr-flags{margin-top:14px;font-size:.78rem;color:#636e72;line-height:1.7}
.corr-flags strong{color:#e17055}
.corr-watch{background:#ffeaa7 !important;font-style:italic;color:#6c5ce7 !important}
.corr-legend{font-size:.72rem;color:#636e72;margin-top:10px}
.corr-legend span{display:inline-block;margin-right:16px}
.leg-hold{background:#f8f9fa;padding:2px 7px;border-radius:4px;font-weight:600}
.leg-watch{background:#ffeaa7;padding:2px 7px;border-radius:4px;font-style:italic;color:#6c5ce7;font-weight:600}
</style>
</head>
<body>
<div class="hdr">
  <div class="hdr-top">
    <div>
      <h1>Portfolio Dashboard</h1>
      <div class="sub">Generated __GENERATED__ &nbsp;·&nbsp; Base currency: __BASE_CCY__</div>
    </div>
    <button class="anon-btn" id="anon-btn">🔒 Anonymise</button>
  </div>
  <div class="kpis" id="kpis"></div>
</div>
<div class="wrap">

  <!-- Row 1: Value + Gain (with toggles) -->
  <div class="g2">
    <div class="card">
      <div class="chdr">
        <h3>Portfolio Value by Symbol</h3>
        <div class="ctrls">
          <div class="tgl-grp" id="val-ccy">
            <button class="tgl on" data-v="SGD">SGD</button>
            <button class="tgl"    data-v="USD">USD</button>
          </div>
        </div>
      </div>
      <div class="fx-note" id="val-note"></div>
      <div style="position:relative;height:420px"><canvas id="c-value"></canvas></div>
    </div>
    <div class="card">
      <div class="chdr">
        <h3>Unrealised Gain / Loss</h3>
        <div class="ctrls">
          <div class="tgl-grp" id="gain-ccy">
            <button class="tgl on" data-v="SGD">SGD</button>
            <button class="tgl"    data-v="USD">USD</button>
          </div>
          <div class="tgl-grp" id="gain-mode">
            <button class="tgl on" data-v="abs">S$</button>
            <button class="tgl"    data-v="pct">%</button>
            <button class="tgl"    data-v="ann">Ann%</button>
          </div>
        </div>
      </div>
      <div class="fx-note" id="gain-note"></div>
      <div style="position:relative;height:420px"><canvas id="c-gain"></canvas></div>
    </div>
  </div>

  <!-- Row 2: Three donuts -->
  <div class="g3">
    <div class="card">
      <h3 class="alone">Allocation by Value</h3>
      <div style="max-width:280px;margin:0 auto"><canvas id="c-alloc"></canvas></div>
    </div>
    <div class="card">
      <h3 class="alone">By Account Type</h3>
      <div style="max-width:280px;margin:0 auto"><canvas id="c-acct"></canvas></div>
    </div>
    <div class="card">
      <h3 class="alone">By Currency</h3>
      <div style="max-width:280px;margin:0 auto"><canvas id="c-ccy"></canvas></div>
    </div>
  </div>

  <!-- Correlation heatmap -->
  <div class="g2" id="corr-section">
    <div class="card span2">
      <div class="chdr">
        <h3 class="alone" style="margin-bottom:0">Correlation Matrix</h3>
        <div id="corr-preset-label" style="font-size:.72rem;color:#b2bec3;padding-top:4px"></div>
      </div>
      <div id="corr-inner"><span class="na">Computing…</span></div>
    </div>
  </div>

  <!-- Row 3: CAGR -->
  <div class="g2">
    <div class="card span2">
      <h3 class="alone">Annualised Return by Lot (CAGR — contract dates known &amp; ≥ 1 yr held)</h3>
      <div style="position:relative;height:560px"><canvas id="c-cagr"></canvas></div>
    </div>
  </div>

  <!-- Row 4: Table -->
  <div class="card">
    <h3 class="alone">All Positions — click any column header to sort</h3>
    <div class="tbl-wrap">
      <table id="tbl">
        <thead><tr>
          <th data-col="symbol">Symbol</th>
          <th data-col="currency">Ccy</th>
          <th data-col="qty" class="abs-col">Qty</th>
          <th data-col="avg_cost">Avg Cost</th>
          <th data-col="current_price">Current</th>
          <th data-col="value_sgd" class="abs-col">Value (SGD)</th>
          <th data-col="gain_sgd" class="abs-col">Gain (SGD)</th>
          <th data-col="gain_pct">Gain %</th>
          <th data-col="ann_return_pct">Ann. Return</th>
          <th data-col="years_held">Yrs Held</th>
          <th data-col="account">Account</th>
          <th data-col="contract_date">Contract Date</th>
        </tr></thead>
        <tbody id="tbl-body"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const D = __DATA_JSON__;
const RATE   = D.meta.fx_rates.USDSGD;   // SGD per 1 USD
const FCOST  = D.meta.fx_cost_pct;        // e.g. 0.2

const PALETTE = ['#3498db','#e74c3c','#2ecc71','#f39c12','#9b59b6',
                 '#1abc9c','#e67e22','#fd79a8','#00cec9','#55efc4',
                 '#fdcb6e','#6c5ce7','#a29bfe','#fab1a0','#74b9ff'];
const CCY_SYM = {SGD:'S$',USD:'$',TWD:'NT$',GBP:'£',GBp:'p',EUR:'€',KRW:'₩'};

function csym(c){ return CCY_SYM[c]||(c+' '); }

// Total monetary amounts (portfolio value, gain): always whole numbers
function fmtV(v,ccy){
  return v==null?'—':csym(ccy||D.meta.base_currency)+Math.abs(v).toLocaleString('en-SG',{maximumFractionDigits:0});
}

// Per-share prices: magnitude-aware decimals
// ≥1000 → 0dp, ≥10 → 2dp, ≥1 → 3dp, ≥0.1 → 3dp, <0.1 → 4dp
function fmtPrice(v,ccy){
  if(v==null) return '—';
  const a=Math.abs(v);
  const dp = a>=1000?0 : a>=10?2 : a>=1?3 : a>=0.1?3 : 4;
  return csym(ccy||D.meta.base_currency)+v.toLocaleString('en-SG',{minimumFractionDigits:dp,maximumFractionDigits:dp});
}

// Quantities: whole numbers get no decimals; fractional shares get up to 4dp (trailing zeros trimmed)
function fmtQty(v){
  if(v==null) return '—';
  if(Math.abs(v-Math.round(v))<0.00005) return Math.round(v).toLocaleString('en-SG');
  // Fractional: trim trailing zeros, cap at 4dp
  const trimmed=v.toFixed(4).replace(/\.?0+$/,'');
  const dp=Math.min((trimmed.split('.')[1]||'').length, 4);
  return v.toLocaleString('en-SG',{minimumFractionDigits:dp,maximumFractionDigits:dp});
}

function fmtP(v){ return v==null?'—':(v>0?'+':'')+v.toFixed(2)+'%'; }
function fmtN(v,dp=2){ return v==null?'—':v.toLocaleString('en-SG',{minimumFractionDigits:dp,maximumFractionDigits:dp}); }

// ── Anonymise state ───────────────────────────────────────────────────────
let anon = false;

function toggleAnon(){
  anon = !anon;
  document.body.classList.toggle('anon', anon);
  document.getElementById('anon-btn').textContent = anon ? '🔓 Show Values' : '🔒 Anonymise';
  // In anon mode absolute gain is meaningless — switch to % if currently abs
  if(anon && gainMode==='abs'){
    gainMode='pct';
    document.querySelectorAll('#gain-mode .tgl').forEach(b=>b.classList.remove('on'));
    document.querySelector('#gain-mode [data-v="pct"]').classList.add('on');
  }
  // Dim the [S$] gain-mode button so user knows it's unavailable
  document.querySelector('#gain-mode [data-v="abs"]').classList.toggle('dim', anon);
  updKPIs(); updVal(); updGain(); renderTable(currentLots);
}
document.getElementById('anon-btn').addEventListener('click', toggleAnon);

// ── KPI header ────────────────────────────────────────────────────────────
const s=D.summary;
function updKPIs(){
  const annStr = s.portfolio_ann_pct!=null ? ` · ${fmtP(s.portfolio_ann_pct)}/yr` : '';
  const gainVal = anon
    ? fmtP(s.total_gain_pct)+annStr
    : (s.total_gain>=0?'+':'')+fmtV(s.total_gain)+' ('+fmtP(s.total_gain_pct)+annStr+')';
  document.getElementById('kpis').innerHTML=[
    {lbl:'Total Value', val:anon?'—':fmtV(s.total_value), cls:'', extra:'kpi-abs'},
    {lbl:'Total Gain',  val:gainVal, cls:s.total_gain>=0?'pos':'neg', extra:''},
    {lbl:'Positions',   val:D.meta.n_lots+' lots / '+D.meta.n_symbols+' symbols', cls:'', extra:''},
    {lbl:'1 USD',       val:'S$'+RATE.toFixed(4)+' spot', cls:'', extra:''},
  ].map(k=>`<div class="kpi ${k.extra}"><div class="lbl">${k.lbl}</div><div class="val ${k.cls}">${k.val}</div></div>`).join('');
}
updKPIs();

Chart.defaults.font.family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif';
Chart.defaults.font.size=12;

// ── FX note helper ────────────────────────────────────────────────────────
function fxNote(ccy, mode){
  if(mode==='pct') return 'Total gain % is currency-independent.';
  if(mode==='ann') return 'Annualised return (CAGR) is currency-independent. Symbols with no contract dates are omitted.';
  const base = `Spot rate: 1 USD = S$${RATE.toFixed(4)} · Conv. cost: ~${FCOST}%`;
  return ccy==='USD' ? base+' (display only — no actual conversion)' : base;
}

// ── State ─────────────────────────────────────────────────────────────────
let valCcy='SGD', gainCcy='SGD', gainMode='abs';

// Pre-sorted data
const bySymVal  = [...D.by_symbol].sort((a,b)=>b.total_value_sgd-a.total_value_sgd);
const bySymGain = D.by_symbol.filter(s=>s.total_gain_sgd!=null).sort((a,b)=>b.total_gain_sgd-a.total_gain_sgd);

// ── Chart instances ───────────────────────────────────────────────────────
let valueChart, gainChart;

function makeHBar(id, height){
  return new Chart(document.getElementById(id),{
    type:'bar',
    data:{labels:[],datasets:[{data:[],borderRadius:4,borderSkipped:false}]},
    options:{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{}}},
      scales:{x:{grid:{color:'#f1f2f6'},ticks:{callback:v=>v}},
              y:{grid:{display:false}}}
    }
  });
}

valueChart = makeHBar('c-value');
gainChart  = makeHBar('c-gain');

// ── Update: value chart ───────────────────────────────────────────────────
function updVal(){
  // In anon mode always show weight %; CCY toggle is dimmed
  document.getElementById('val-ccy').classList.toggle('dim', anon);
  if(anon){
    valueChart.data.labels = bySymVal.map(s=>s.symbol);
    valueChart.data.datasets[0].data = bySymVal.map(s=>s.weight_pct);
    valueChart.data.datasets[0].backgroundColor = PALETTE.slice(0,bySymVal.length);
    valueChart.options.scales.x.ticks.callback = v=>v.toFixed(1)+'%';
    valueChart.options.plugins.tooltip.callbacks = {
      label: ctx=>[bySymVal[ctx.dataIndex].weight_pct.toFixed(2)+'% of portfolio']
    };
    document.getElementById('val-note').textContent = 'Showing allocation % only (anonymised).';
  } else {
    const div = valCcy==='USD' ? RATE : 1;
    valueChart.data.labels = bySymVal.map(s=>s.symbol);
    valueChart.data.datasets[0].data = bySymVal.map(s=>+(s.total_value_sgd/div).toFixed(0));
    valueChart.data.datasets[0].backgroundColor = PALETTE.slice(0,bySymVal.length);
    valueChart.options.scales.x.ticks.callback = v=>fmtV(v,valCcy);
    valueChart.options.plugins.tooltip.callbacks = {
      label: ctx=>{
        const sym=bySymVal[ctx.dataIndex];
        return [fmtV(ctx.raw,valCcy), sym.weight_pct.toFixed(1)+'% of portfolio'];
      }
    };
    document.getElementById('val-note').textContent = fxNote(valCcy,'val');
  }
  valueChart.update();
}

// ── Update: gain chart ────────────────────────────────────────────────────
function updGain(){
  const isCcyIndep = gainMode==='pct' || gainMode==='ann';
  const div = (!isCcyIndep && gainCcy==='USD') ? RATE : 1;

  // dim CCY toggle when mode is currency-independent
  document.getElementById('gain-ccy').classList.toggle('dim', isCcyIndep);

  let labels, values, colors;

  if(gainMode==='ann'){
    const sorted = [...D.by_symbol]
      .filter(s=>s.ann_return_pct!=null)
      .sort((a,b)=>b.ann_return_pct-a.ann_return_pct);
    labels = sorted.map(s=>s.symbol+' ('+fmtP(s.gain_pct)+' total)');
    values = sorted.map(s=>s.ann_return_pct);
    colors = sorted.map(s=>s.ann_return_pct>=0?'rgba(39,174,96,.75)':'rgba(231,76,60,.75)');
    gainChart.options.scales.x.ticks.callback = v=>fmtP(v);
    gainChart.options.plugins.tooltip.callbacks = {
      label: ctx=>{
        const sym=sorted[ctx.dataIndex];
        return [`Ann. return: ${fmtP(ctx.raw)}`,`Total gain: ${fmtP(sym.gain_pct)}`,`Value: ${fmtV(sym.total_value_sgd)}`];
      }
    };
  } else if(gainMode==='pct'){
    const sorted = [...bySymGain].sort((a,b)=>b.gain_pct-a.gain_pct);
    labels = sorted.map(s=>s.symbol);
    values = sorted.map(s=>s.gain_pct);
    colors = sorted.map(s=>s.gain_pct>=0?'rgba(39,174,96,.75)':'rgba(231,76,60,.75)');
    gainChart.options.scales.x.ticks.callback = v=>fmtP(v);
    gainChart.options.plugins.tooltip.callbacks = {
      label: ctx=>{ const sym=sorted[ctx.dataIndex]; return [fmtP(ctx.raw), fmtV(sym.total_gain_sgd)+' total gain']; }
    };
  } else {
    labels = bySymGain.map(s=>s.symbol+' ('+fmtP(s.gain_pct)+')');
    values = bySymGain.map(s=>+(s.total_gain_sgd/div).toFixed(0));
    colors = bySymGain.map(s=>s.total_gain_sgd>=0?'rgba(39,174,96,.75)':'rgba(231,76,60,.75)');
    gainChart.options.scales.x.ticks.callback = v=>fmtV(v,gainCcy);
    gainChart.options.plugins.tooltip.callbacks = {
      label: ctx=>{ const sym=bySymGain[ctx.dataIndex]; return [fmtV(ctx.raw,gainCcy), fmtP(sym.gain_pct)]; }
    };
  }

  gainChart.data.labels = labels;
  gainChart.data.datasets[0].data = values;
  gainChart.data.datasets[0].backgroundColor = colors;
  gainChart.update();
  document.getElementById('gain-note').textContent = fxNote(gainCcy, gainMode);
}

// Initial render
updVal(); updGain();

// ── Toggle wiring ─────────────────────────────────────────────────────────
function bindTgl(groupId, onChange){
  document.getElementById(groupId).querySelectorAll('.tgl').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.getElementById(groupId).querySelectorAll('.tgl').forEach(b=>b.classList.remove('on'));
      btn.classList.add('on');
      onChange(btn.dataset.v);
    });
  });
}
bindTgl('val-ccy',   v=>{ valCcy=v;   updVal(); });
bindTgl('gain-ccy',  v=>{ gainCcy=v;  updGain(); });
bindTgl('gain-mode', v=>{ gainMode=v; updGain(); });

// ── Donut helper ──────────────────────────────────────────────────────────
function donut(id,labels,values,colors){
  new Chart(document.getElementById(id),{
    type:'doughnut',
    data:{labels,datasets:[{data:values,backgroundColor:colors,borderWidth:2,borderColor:'#fff'}]},
    options:{responsive:true,plugins:{
      legend:{position:'bottom',labels:{boxWidth:12,padding:10}},
      tooltip:{callbacks:{label:ctx=>{
        const tot=ctx.dataset.data.reduce((a,b)=>a+b,0);
        return ctx.label+': '+fmtV(ctx.raw)+' ('+(ctx.raw/tot*100).toFixed(1)+'%)';
      }}}
    }}
  });
}

donut('c-alloc', D.by_symbol.map(s=>s.symbol), D.by_symbol.map(s=>s.total_value_sgd), PALETTE.slice(0,D.by_symbol.length));
const ACOL={cash:'#74b9ff',CPF:'#a29bfe',SRS:'#fdcb6e',taxable:'#55efc4'};
donut('c-acct', D.by_account.map(a=>a.name), D.by_account.map(a=>a.value_sgd), D.by_account.map(a=>ACOL[a.name]||'#dfe6e9'));
const CCOL={SGD:'#00b894',USD:'#0984e3',TWD:'#e17055',GBp:'#6c5ce7',EUR:'#fdcb6e'};
donut('c-ccy', D.by_currency.map(c=>c.name), D.by_currency.map(c=>c.value_sgd), D.by_currency.map(c=>CCOL[c.name]||'#b2bec3'));

// ── CAGR chart ────────────────────────────────────────────────────────────
const cagrLots=D.lots.filter(l=>l.ann_return_pct!=null&&l.years_held>=1).sort((a,b)=>b.ann_return_pct-a.ann_return_pct);
if(cagrLots.length){
  new Chart(document.getElementById('c-cagr'),{
    type:'bar',
    data:{
      labels:cagrLots.map(l=>l.symbol+(l.contract_date?' ('+l.contract_date+')':'')),
      datasets:[{data:cagrLots.map(l=>l.ann_return_pct),
                 backgroundColor:cagrLots.map(l=>l.ann_return_pct>=0?'rgba(39,174,96,.75)':'rgba(231,76,60,.75)'),
                 borderRadius:4,borderSkipped:false}]
    },
    options:{
      indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>{
        const l=cagrLots[ctx.dataIndex];
        return [`CAGR: ${fmtP(ctx.raw)}`,`Held: ${fmtN(l.years_held,1)} yrs`,`Total gain: ${fmtP(l.gain_pct)}`];
      }}}},
      scales:{x:{grid:{color:'#f1f2f6'},ticks:{callback:v=>fmtP(v)}},y:{grid:{display:false}}}
    }
  });
} else {
  document.getElementById('c-cagr').closest('.card').style.display='none';
}

// ── Table ─────────────────────────────────────────────────────────────────
const TAG={cash:'tag-cash',CPF:'tag-cpf',SRS:'tag-srs',taxable:'tag-taxable'};
let currentLots = D.lots;
function renderTable(lots){
  currentLots = lots;
  document.getElementById('tbl-body').innerHTML=lots.map(l=>`
    <tr>
      <td><strong>${l.symbol}</strong></td>
      <td>${l.currency}</td>
      <td class="abs-col">${fmtQty(l.qty)}</td>
      <td>${l.avg_cost!=null?fmtPrice(l.avg_cost,l.currency):'<span class="na">—</span>'}</td>
      <td>${l.current_price!=null?fmtPrice(l.current_price,l.currency):'<span class="na">N/A</span>'}</td>
      <td class="abs-col">${fmtV(l.value_sgd)}</td>
      <td class="abs-col ${l.gain_sgd==null?'na':l.gain_sgd>=0?'pos':'neg'}">${l.gain_sgd==null?'—':(l.gain_sgd>=0?'+':'')+fmtV(l.gain_sgd)}</td>
      <td class="${l.gain_pct==null?'na':l.gain_pct>=0?'pos':'neg'}">${fmtP(l.gain_pct)}</td>
      <td class="${l.ann_return_pct==null?'na':l.ann_return_pct>=0?'pos':'neg'}">${fmtP(l.ann_return_pct)}</td>
      <td>${l.years_held!=null?fmtN(l.years_held,1)+'y':'<span class="na">—</span>'}</td>
      <td><span class="tag ${TAG[l.account]||'tag-cash'}">${l.account}</span></td>
      <td>${l.contract_date||'<span class="na">—</span>'}</td>
    </tr>`).join('');
}
renderTable(D.lots);
// ── Correlation heatmap ───────────────────────────────────────────────────
function corrColor(v){
  // +1 → blue (#2980b9), 0 → white, -1 → red (#e74c3c)
  if(isNaN(v)) return '#f0f2f5';
  const t = Math.abs(v);
  if(v > 0){
    return `rgb(${Math.round(255-t*203)},${Math.round(255-t*103)},${Math.round(255-t*36)})`;
  } else {
    return `rgb(${Math.round(255-t*24)},${Math.round(255-t*179)},${Math.round(255-t*195)})`;
  }
}
function corrText(v){ return Math.abs(v)>0.55 ? '#fff' : '#2d3436'; }

function renderCorr(){
  const C = D.correlation;
  if(!C || !C.symbols || !C.symbols.length){
    document.getElementById('corr-section').style.display='none';
    return;
  }
  const syms=C.symbols, mat=C.matrix;
  const watchSet = new Set(C.watchlist||[]);
  const wCls = s => watchSet.has(s) ? 'corr-watch' : '';

  document.getElementById('corr-preset-label').textContent =
    `${C.period} daily returns · ${C.n_obs} observations · base: ${C.base_currency}`;

  // Build table
  let html='<div class="corr-scroll"><table class="corr-tbl"><thead><tr><th></th>';
  html += syms.map(s=>`<th class="${wCls(s)}" title="${s}${watchSet.has(s)?' (watchlist)':''}">${s}</th>`).join('');
  html += '</tr></thead><tbody>';
  for(let i=0;i<syms.length;i++){
    html += `<tr><th class="${wCls(syms[i])}">${syms[i]}</th>`;
    for(let j=0;j<syms.length;j++){
      const v=mat[i][j];
      const bg=corrColor(v), fg=corrText(v);
      const bld=(i!==j&&Math.abs(v)>0.7)?'font-weight:700;':'';
      const tip=`${syms[i]} ↔ ${syms[j]}: ${v>=0?'+':''}${v.toFixed(2)}`;
      html+=`<td style="background:${bg};color:${fg};${bld}" title="${tip}">${v.toFixed(2)}</td>`;
    }
    html+='</tr>';
  }
  html+='</tbody></table></div>';

  // Legend (only if there are watchlist symbols)
  if(watchSet.size>0){
    html+=`<div class="corr-legend"><span class="leg-hold">Normal header</span> = holdings &nbsp;
           <span class="leg-watch">Italic / yellow</span> = watchlist (no position)</div>`;
  }

  // Flag high pairs
  const high=[];
  for(let i=0;i<syms.length;i++)
    for(let j=i+1;j<syms.length;j++)
      if(Math.abs(mat[i][j])>0.7) high.push([syms[i],syms[j],mat[i][j]]);
  high.sort((a,b)=>Math.abs(b[2])-Math.abs(a[2]));

  if(high.length){
    html+=`<div class="corr-flags"><strong>⚠ High correlations (|r| &gt; 0.70):</strong><br>`;
    html+=high.map(([a,b,v])=>`${a} ↔ ${b}: ${v>=0?'+':''}${v.toFixed(2)}`).join(' &nbsp;·&nbsp; ');
    html+='</div>';
  } else {
    html+='<div class="corr-flags" style="color:#27ae60">✓ No pairs exceed |r| = 0.70</div>';
  }

  document.getElementById('corr-inner').innerHTML=html;
}
renderCorr();

// ── Sortable table ─────────────────────────────────────────────────────────
let sortCol=null,sortAsc=true;
document.querySelectorAll('#tbl thead th').forEach(th=>{
  th.addEventListener('click',()=>{
    const col=th.dataset.col;
    if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=true;}
    document.querySelectorAll('#tbl thead th').forEach(t=>t.classList.remove('sort-asc','sort-desc'));
    th.classList.add(sortAsc?'sort-asc':'sort-desc');
    renderTable([...D.lots].sort((a,b)=>{
      const av=a[col]??-Infinity,bv=b[col]??-Infinity;
      return sortAsc?(av>bv?1:av<bv?-1:0):(av<bv?1:av>bv?-1:0);
    }));
  });
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_outputs(data: Dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = DATA_DIR / 'portfolio_data.json'
    json_path.write_text(json.dumps(data, indent=2))
    print(f"\nData saved:      {json_path}")

    # HTML — embed data and replace template placeholders
    html = (HTML_TEMPLATE
            .replace('__DATA_JSON__', json.dumps(data))
            .replace('__GENERATED__', data['meta']['generated'])
            .replace('__BASE_CCY__', data['meta']['base_currency']))
    html_path = OUTPUT_DIR / 'dashboard.html'
    html_path.write_text(html)
    print(f"Dashboard saved: {html_path}")
    print(f"\nView it:")
    print(f"  open {html_path}")
    print(f"  # or serve: cd output && python -m http.server 8080")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description='Portfolio snapshot + dashboard')
    parser.add_argument('--holdings', help='Path to holdings CSV')
    parser.add_argument('--no-corr', action='store_true',
                        help='Skip correlation matrix (faster, no historical fetch)')
    parser.add_argument('--corr-preset', choices=list(PRESETS), default='1y',
                        help='History period for correlation (default: 1y)')
    args = parser.parse_args()

    holdings_path = args.holdings or find_holdings_file()
    holdings = load_holdings(holdings_path)
    print(f"Loaded {len(holdings)} lots from {holdings_path}")

    data = build_data(holdings)
    s = data['summary']
    print(f"\nTotal value: S${s['total_value']:,.2f}")
    print(f"Total gain:  S${s['total_gain']:+,.2f} ({s['total_gain_pct']:+.2f}%)")

    if not args.no_corr:
        symbols = list(dict.fromkeys(h['symbol'] for h in holdings))
        currency_map = {h['symbol']: h['currency'] for h in holdings}
        watchlist = load_watchlist()
        data['correlation'] = compute_correlations(
            symbols, currency_map, preset=args.corr_preset, watchlist=watchlist
        )

    save_outputs(data)


if __name__ == '__main__':
    main()
