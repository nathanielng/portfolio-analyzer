# Investment Decision Plan — Retail AI/Semiconductor Portfolio

> **Disclaimer:** This is an educational decision *framework*, not personalized financial
> advice or a recommendation to buy/sell any security. Markets are largely efficient;
> assume you can be wrong. Size positions so that being wrong is survivable.

---

## 0. Investor Profile & Assumptions

| Parameter | Value |
|---|---|
| Investor type | Retail (limited time, free tools) |
| Tax residence | **Singapore** (no capital-gains tax, no tax on most foreign dividends) |
| Bank accounts | **SGD** (home) + **USD** account → can settle US trades without forced FX |
| Brokers | **Broker-A**, **Broker-B**, **Broker-C**, **Broker-D** (mix of SG-local and US/global) |
| Trading frequency | ~1–3 trades/month (≈12–36/yr) — deliberate, not day-trading |
| Universe | Mix of broad ETFs + AI/semiconductor stocks (NVDA, GOOGL, SK Hynix, ASML, TSMC, etc.) + AI thematic ETFs |
| Selection unit | A **diversified portfolio/basket with explicit weights** — *not* individual stock bets |
| Time horizon | 1–10 years (favor fundamentals over technicals; tolerate volatility) |
| Primary objective | Long-term capital growth with controlled concentration risk |

**Implications of these assumptions:**
- **1–3 trades/month → a monthly review cadence is the natural rhythm.** Enough activity to act on
  conviction and dollar-cost-average; few enough to keep costs and overtrading low.
- **AI/semis universe → concentration is the #1 risk, not stock selection.** These names are highly
  correlated and vertically linked (see §6). The portfolio is essentially one bet on AI capex.
- **1–10yr horizon → valuation + business quality dominate; technicals only help with *timing*, not the decision.**
- **Singapore residence → ETF *domicile* and *withholding tax* can matter more than picking the right stock (see §1.5).**
  No SG capital-gains tax means you don't need to hold ≥12 months for tax reasons — but US estate-tax exposure and
  dividend withholding are real and structural.
- **Buying a *portfolio*, not single names → the unit of analysis is the whole basket.** Portfolio-level metrics
  (correlation/covariance matrix, portfolio volatility, risk contribution, diversification ratio) and an explicit
  **weighting method** become the core of the process (see §6). Per-stock scorecards (§5) now feed *which names make
  the basket*; §6 decides *how much of each*.

---

## 1. Portfolio Architecture (Core / Satellite)

Decide *structure* before picking individual stocks.

```
                 ┌─────────────────────────────────────┐
                 │  CORE  (50–70%)  — broad, low-cost    │
                 │  e.g. VT / VTI / VOO                  │  ← "indexing default"
                 ├─────────────────────────────────────┤
                 │  THEMATIC SATELLITE (15–30%)          │
                 │  AI/semi ETFs: SMH, SOXX, IGV, AIQ    │  ← diversified AI exposure
                 ├─────────────────────────────────────┤
                 │  SINGLE-STOCK SATELLITE (10–25%)      │
                 │  NVDA, GOOGL, ASML, SK Hynix, TSM...  │  ← highest-conviction picks
                 └─────────────────────────────────────┘
```

**Guardrails (set these now, enforce monthly):**
- Single stock ≤ **8%** of total portfolio at cost (let winners run to a hard cap of ~12%, then trim).
- All "pure AI/semi" exposure (single names + thematic ETFs + the AI weight inside broad ETFs) ≤ **40%**.
  *Note: broad ETFs already hold ~10–15% in these same names — count that toward the cap.*
- Keep **3–6 months cash** outside this portfolio so you never have to sell at the bottom.

---

## 1.5 Singapore-Specific Structure: Tax, Domicile & Broker Routing ⚠️

> **Not tax advice — rules change, and your situation is personal. Confirm with a qualified adviser/IRAS.**
> But these are well-known structural facts that materially affect a Singapore-based investor.

### Tax facts that drive structure
- **Singapore: no capital-gains tax, no tax on foreign-sourced dividends** (for most individuals).
  → You don't need to hold ≥12 months for tax reasons. Decisions are driven by the *thesis*, not a tax clock.
- **US dividend withholding = 30% for Singapore residents** (no favourable US–SG tax treaty rate).
  A US-listed dividend payer (or US-domiciled ETF) loses 30% of dividends at source — unrecoverable.
- **US estate tax for non-resident aliens** applies to **US-situs assets above just US$60,000**, at rates up to 40%.
  Directly held US stocks (NVDA, GOOGL) and **US-domiciled ETFs** count. This is the most-overlooked risk for SG investors.

### The big lever: use **Irish-domiciled (UCITS) ETFs** for the index core
For broad/index exposure, prefer **Irish-domiciled UCITS ETFs** over US-domiciled ones:

| | US-domiciled (e.g. VOO/VTI) | **Irish-domiciled UCITS (e.g. CSPX, VUAA)** |
|---|---|---|
| Dividend withholding to fund | — | 15% (US–Ireland treaty) ✓ |
| Withholding to you (SG) on payout | **30%** ✗ | 0% extra ✓ |
| US estate-tax exposure | **Yes (>US$60k)** ✗ | **No** ✓ |
| Accumulating share class? | No | **Yes (VUAA/CSPX acc)** → auto-reinvests, less admin ✓ |
| Listing/currency | US, USD | LSE in USD (CSPX/VUAA) or GBp; also EUR venues |

→ **Recommendation:** build the §1 *core* (and ideally the thematic AI-ETF sleeve) with **Irish-domiciled UCITS ETFs**.
Keep direct US single-stocks (NVDA, GOOGL) modest and be mindful of the aggregate US-situs value vs the estate-tax threshold.
For AI/semi thematic exposure, look for UCITS equivalents (e.g. UCITS semiconductor/robotics-AI ETFs on LSE/Xetra) rather than US-domiciled SMH/SOXX/AIQ where practical.

### Broker routing (match the broker to the market & currency)

| Need | Best fit | Why |
|---|---|---|
| **UCITS ETFs (LSE/Xetra)**, ASML.AS (EUR), SK Hynix (KRW), TSMC TWD, multi-currency | **Broker-D** | Widest global market access, lowest FX spreads, true multi-currency cash |
| **US stocks** (NVDA, GOOGL, TSM ADR) | **Broker-C** or **Broker-D** | Low US commissions; fund the USD leg from your USD account to avoid FX |
| **SGX-listed** ETFs/stocks, SRS investing | **Broker-A** or **Broker-B** | Local SGX access; one integrates with a SG bank, the other has broad global reach |
| Custody comfort / local support | Broker-A, Broker-B | Established SG names |

**Practical routing rules:**
- **Default to Broker-D** for anything non-US-listed (UCITS ETFs, European/Asian listings) and for FX efficiency.
- **Fund USD trades from the USD bank account**; only convert SGD↔USD when rates are reasonable (Broker-D offers near-spot FX).
- Avoid paying FX spread twice — hold the trade currency rather than round-tripping to SGD between trades.
- Mind **custody model** (nominee vs CDP). SGX holdings can sit in CDP (your name); foreign holdings sit under broker nominee — fine, but know the difference.

---

## 2. Step 0 — Write the Thesis Before Looking at Data

For every candidate, write 3 sentences in the journal (§9):
1. **Why might this be mispriced / why will it compound?** (If you can't answer, just buy the ETF.)
2. **Holding period & what success looks like** (e.g., "3–5yr, revenue compounds >20%, margins hold").
3. **Falsification / sell trigger** (e.g., "HBM pricing collapses," "data-center capex guides down 2 quarters," "thesis broke," or a valuation cap).

---

## 3. Step 1 — Data Sources (by purpose)

| Purpose | Free source | Notes |
|---|---|---|
| Prices, basic fundamentals | **yfinance** (in this repo), Polygon free tier | Existing fetchers |
| Official financials & filings | **SEC EDGAR** `data.sec.gov` (company-facts API + full-text search) | 10-K, 10-Q, 8-K. Free, authoritative. *Foreign names (ASML, SK Hynix, TSMC) file **20-F**, not 10-K.* |
| Fundamentals API | **Financial Modeling Prep**, **Alpha Vantage**, **Finnhub**, **Tiingo** | Free tiers; ratios + estimates |
| **FX — current + historical** (USD, EUR, KRW, TWD → **SGD base**) | yfinance (`SGD=X`, `EURSGD=X`, `USDSGD=X`…), **FRED** (`DEXSGUS`), exchangerate-api.com (in this repo, spot only) | Need *historical* series to compute returns in SGD (see §6.5), not just spot |
| **Interest rates** | **FRED** (`DGS10`, `DGS2`, `FEDFUNDS`, `T10Y2Y`), MAS for SGD (`SORA`) | Discount rate for DCF/Sharpe; rate regime drives AI-multiple risk |
| **Commodities / oil** | FRED (`DCOILWTICO`, `DCOILBRENTEU`), yfinance (`CL=F`, `BZ=F`) | Macro/inflation context indicator — *second-order* for this portfolio |
| **Inflation / sentiment** | FRED (`CPIAUCSL`), yfinance (`^VIX`) | Inflation feeds rates; VIX = risk-off gauge |
| News / qualitative | Web search, company IR pages, **earnings-call transcripts** | Primary sources > headlines |
| Analyst estimates | yfinance `.info`, Finnhub | Directional only |

**Listing & currency notes for your specific names:**
- **NVDA, GOOGL** — US-listed, USD, file 10-K.
- **ASML** — US ADR `ASML` (Nasdaq) *and* `ASML.AS` (Amsterdam, EUR). Files **20-F**.
- **SK Hynix** — Korea `000660.KS` (KRW); thin US OTC. Files Korean reports + 20-F-style.
- **TSMC** — ADR `TSM` (USD) *and* `2330.TW` (TWD). **This repo already handles the TWD case.**
- **Decision:** prefer the **USD ADR** where one exists (simpler tax/FX); use local listing only if liquidity/spread is better.

---

## 4. Step 2 — Metrics (every metric benchmarked 3 ways)

> **Rule: a number alone is meaningless.** Always compare to (a) the company's own 5-yr history,
> (b) sector peers, (c) the broad market.

**A. Business quality** — ROIC / ROE (>15% sustained = strong), gross & operating margin *trend*,
revenue & EPS 3–5yr CAGR, free cash flow margin.

**B. Financial health** — Net Debt/EBITDA, interest coverage, current ratio,
**Piotroski F-score (0–9)**, Altman Z-score (<1.8 = danger).

**C. Valuation** — P/E (trailing + forward), **PEG** (key for high-growth AI names),
**EV/EBITDA**, **FCF yield**, P/S. Optional **DCF** for a margin-of-safety estimate
(beware: output is only as good as the growth/discount assumptions).

**D. Per-stock risk** *(inputs to the portfolio in §6)* — annualized volatility, beta, max drawdown,
and the return series needed to build the correlation/covariance matrix. Per-name Sharpe is informative,
but the portfolio-level versions (§6) are what actually matter.

---

## 5. Step 3 — Scoring Frameworks (mechanical first)

Combine loose metrics into tested composites instead of eyeballing:

1. **Piotroski F-score (0–9)** — mechanical fundamental-health screen. Beginner-friendly, easy to code.
2. **Greenblatt Magic Formula** — rank by *earnings yield* (cheap) + *ROIC* (good).
3. **Relative comps table** — the stock's P/E, EV/EBITDA, FCF yield, PEG next to 3–5 peers *and* its own 5-yr average.
4. **DCF (optional)** — intrinsic value vs market cap → margin of safety.

### Weighted scorecard (per candidate)

| Dimension | Weight | Score 1–5 | Weighted |
|---|---|---|---|
| Quality (ROIC, margins) | 30% | | |
| Growth | 20% | | |
| Financial health | 15% | | |
| Valuation / margin of safety | 25% | | |
| Risk & portfolio fit (correlation!) | 10% | | |
| **Total** | 100% | | **/5** |

---

## 6. Step 4 — Portfolio Construction: Correlation, Risk & Allocation ⚠️ (the heart of the process)

Because you're buying a **basket**, the goal is not "is each stock good?" but "do these names, *at these weights*,
give the best return for the risk I take?" That requires portfolio-level math.

### 6.1 First, the reality check — your names are not independent
They're one linked AI-capex supply chain:

```
   ASML ──(litho machines)──▶ TSMC ──(fabs chips for)──▶ NVDA ──(GPUs sold to)──▶ Hyperscalers (GOOGL, MSFT, AMZN)
                                  ▲
   SK Hynix / Micron ──(HBM memory)──┘ ──▶ NVDA
```
- They **rise and fall together** — a data-center capex slowdown hits all at once.
- Owning all five ≈ one ~leveraged bet on AI infrastructure spend, **not** diversification.
- **The math will confirm this:** their pairwise correlations are typically high (~0.5–0.8+). Real diversification
  has to come from **outside** the AI basket (broad core, other sectors/geographies, possibly bonds/gold).

### 6.2 Portfolio-level metrics to compute (the ones that actually matter)

| Metric | What it answers | Note |
|---|---|---|
| **Correlation matrix** | Which holdings move together | Heatmap; the diversification map |
| **Covariance matrix (Σ)** | Inputs for portfolio risk | = correlations scaled by each name's volatility |
| **Portfolio volatility** σₚ = √(wᵀ Σ w) | True portfolio risk | **Less than** the weighted-average of individual vols *only if* correlations <1 — that's the diversification benefit |
| **Diversification ratio** = (Σ wᵢσᵢ) / σₚ | How much diversification you're actually getting | ~1.0 = none (everything correlated); higher = better |
| **Risk contribution (per holding)** | *Who* drives portfolio risk | A 20% NVDA weight can be 40%+ of the risk — concentration hides here |
| **Effective number of bets** (1/Σwᵢ², or via risk) | "How many independent positions do I really have?" | 6 names that all move together ≈ 1–2 real bets |
| **Portfolio Sharpe / Sortino** | Return per unit of risk for the *whole* basket | The number to maximize/compare across candidate weightings |
| **Portfolio max drawdown & VaR/CVaR** | Worst-case pain | Backtest the chosen weights through 2022 (AI/semi drawdown was brutal) |
| **Portfolio beta** | Sensitivity to the broad market | |

### 6.3 How to choose the weights (allocation methods, simplest → most complex)

| Method | Idea | Pros | Cons / caveats |
|---|---|---|---|
| **Equal weight (1/N)** | Same % in each name | Robust, no estimation, hard to get badly wrong | Ignores risk differences |
| **Market-cap weight** | Bigger company = bigger weight | What index ETFs do; cheap | Concentrates into whatever's already big (NVDA) |
| **Inverse-volatility** | Weight ∝ 1/σ | Calmer names get more; simple risk-awareness | Ignores correlations |
| **Risk parity (equal risk contribution)** | Each name contributes equal *risk* | Stops one name dominating risk; great for a concentrated basket | Needs covariance matrix; can over-weight low-vol names |
| **Minimum-variance** | Solve for lowest σₚ | Lowest-risk mix | Often piles into a few low-vol/low-corr names |
| **Max-Sharpe / Mean-Variance (MPT)** | Efficient frontier → tangency portfolio | Theoretically optimal risk-adjusted return | **Fragile:** needs *expected returns*, which are nearly impossible to estimate; tiny input changes → wild weight swings; **will happily over-concentrate** |

**The honest take for your situation:**
- **Mean-variance optimization on a high-correlation AI basket will likely tell you to concentrate even more** —
  garbage-in from noisy expected-return estimates. Don't follow it blindly.
- **Better defaults for a retail investor:** start **equal-weight or risk-parity** *within* the satellite basket,
  then impose hard **constraints** (no single name >8%, total AI/semi <40% per §1). Use the efficient frontier as a
  *diagnostic* ("am I being paid for this risk?"), not an autopilot.
- **Diversification you can actually trust comes from the core**, not from adding a 6th correlated AI chip name.
- **Correlations rise toward 1 in a crash** — so backtest drawdowns and don't assume the matrix holds when it matters most.

### 6.4 Construction workflow
1. Pull aligned daily/weekly return series for all candidates + current holdings (handle FX to a common currency — repo does this).
2. Compute correlation + covariance matrices → heatmap.
3. Filter the basket: drop/shrink names with **>0.7 correlation** to something you already hold (redundant risk).
4. Choose weights via equal-weight or risk-parity, **subject to the §1 caps**.
5. Compute portfolio σ, diversification ratio, risk contributions, Sharpe, and a drawdown/VaR backtest.
6. Inspect **risk contribution** — if one name >~30% of risk, trim it. Iterate.
7. Confirm total AI/semi exposure (incl. the AI weight already inside broad ETFs) stays under the **40% cap**.

---

## 6.5 Currency & Macro-Factor Risk (FX, Rates, Oil) ⚠️

Your base currency is **SGD**, but your assets are in USD / EUR / KRW / TWD. Ignoring this overstates how
diversified and how calm your portfolio really is.

### 6.5.1 FX risk — the key methodological fix
**Your true return = asset return (local ccy) + currency move vs SGD.** Example: NVDA +10% in USD, but USD −5%
vs SGD → your SGD return is only ~+4.5%.

> **Do everything in SGD.** Convert every price series to SGD *before* computing the §6 returns, volatility,
> correlation, and drawdowns. Then **FX risk is automatically inside your portfolio numbers** — no separate FX model.

Nuances worth knowing:
- **Listing currency ≠ economic exposure.** NVDA, ASML, TSMC earn globally, so a USD listing overstates true USD
  exposure. Track an approximate **currency-of-earnings** breakdown, not just listing currency.
- **For long-horizon equities, generally don't hedge FX** — it costs money and currency is a smaller share of equity
  risk. The right move is to **measure and cap** USD exposure, and let the SGD core + non-USD names diversify it.
- Report a **currency exposure breakdown** (% USD / EUR / KRW / TWD / SGD) alongside the §6 weights.

### 6.5.2 Conversion cost — a small but real drag
- Broker-D ≈ near-spot + tiny commission; Broker-B / Broker-A retail FX spreads are wider (~0.2–0.5%).
- **Rules:** hold USD in the USD account and fund USD trades from it; **batch** conversions instead of per-trade;
  prefer rebalancing via new SGD/USD contributions over FX round-trips. Model ~0.1–0.5% per conversion in any
  rebalancing/trade-cost estimate so the math doesn't flatter frequent trading.

### 6.5.3 Interest rates — valuation + FX driver
- **Valuation channel:** rates *are* the discount rate. Long-duration growth/AI names are the most rate-sensitive
  (cf. the 2022 drawdown). Use the 10Y yield (FRED `DGS10`) as the risk-free input to DCF and Sharpe.
- **FX channel:** US–SG rate differentials push USD/SGD. Note MAS runs policy via the **exchange rate (S$NEER)**,
  not a policy rate, so SGD rates (SORA) largely track global/US rates.
- **Use as context, not a trigger:** a rising-rate regime → demand more margin of safety on high-P/E names; it is
  not a day-to-day buy/sell signal.

### 6.5.4 Oil & commodities — second-order context
- Direct impact on AI/semis is low. Oil matters mainly **indirectly**: oil → inflation → rates → tech multiples,
  and as a growth/recession barometer. Track WTI/Brent + CPI + VIX as a **macro regime dashboard**, not as inputs
  to individual position decisions. Don't over-engineer this.

### 6.5.5 Scope discipline
These are **risk-monitoring and valuation inputs**, not a macro-timing model. A 1–3 trades/month retail investor
should *observe* the regime (rates up? USD weak? VIX high?) to size risk and demand margin of safety — not trade on it.

---

## 7. Step 5 — From Target Weights to Trades (Decision, Tilting & Rebalancing)

§6 gives the **baseline target weights** (e.g. risk-parity, capped). The per-stock scorecard×valuation then
**tilts** each name modestly around its baseline — it doesn't pick single bets, it nudges weights:

| | Cheap (margin of safety) | Fair value | Expensive |
|---|---|---|---|
| **High quality (score ≥4)** | **Over-weight** vs baseline | Hold at baseline (DCA) | Under-weight / wait |
| **Medium (3–4)** | At baseline | Hold | Under-weight |
| **Low (<3)** | Keep out of basket | Out | **Exclude / Sell** |

Keep tilts bounded (e.g. ±2–3% around the §6 weight) so a single conviction call can't blow up diversification.

**Execution & rebalancing rules (retail, monthly cadence):**
- **Dollar-cost average in** over 2–4 monthly buys rather than one lump — fits the 1–3 trades/month rhythm and reduces timing risk.
- **Rebalance on a band, not a hunch:** when a holding drifts **>±5 percentage points** (or >25% relative) from its target weight,
  trim/top-up back toward target. This mechanically "sells high, buys low" and keeps risk contributions in check.
- Prefer **rebalancing by directing new contributions** to under-weight names (no selling, no FX churn, low cost) before outright trims.
- Trim any name back to target when it breaches the 8% single-name cap or 40% AI/semi cap.
- **Tax (Singapore resident):** *no* capital-gains tax, so there's no holding-period tax incentive — sell when the thesis says so. Instead, manage **dividend withholding** (favour Irish-domiciled UCITS ETFs for income/index exposure, §1.5) and watch **aggregate US-situs value vs the US$60k estate-tax threshold**. SRS contributions can offer income-tax relief if you invest via an SRS-eligible broker.

**Actions vocabulary:** Buy (new), Accumulate (add to winner/cheap), Hold, Trim (reduce, over cap or rich), Sell (thesis broke / trigger hit), Avoid (no position).

---

## 8. Monthly Workflow (the operating cadence)

Once a month (~1 hour), and only then place 1–3 trades:

1. **Update data** — refresh prices, fundamentals, **FX (→ SGD)**, and the macro dashboard (10Y yield, USD/SGD, CPI, WTI, VIX).
2. **Portfolio health (§6, in SGD)** — recompute actual weights, correlation matrix, portfolio σ, diversification ratio,
   **risk contributions**, **currency-exposure breakdown** (% USD/EUR/KRW/TWD/SGD), AI/semi exposure %, and drawdown.
   Any holding off its target by >±5pp? Any cap breached? Any single name now >~30% of portfolio risk? USD exposure too high?
3. **Re-score** any candidate or held name with new earnings/filings (read the 10-K/20-F/8-K, skim the call).
4. **Check sell triggers** on every holding — did any thesis break?
5. **Decide & rebalance** using §7 — direct new contributions to under-weight names first; trim breaches. Execute 1–3 trades.
6. **Journal** every action (§9).

> Between monthly reviews: do nothing except react to a genuine **8-K / material event** or a pre-set sell trigger. Avoid reacting to headlines.

---

## 9. Decision Journal Template

```
Date:
Ticker:
Action: Buy / Accumulate / Hold / Trim / Sell / Avoid
Thesis (why mispriced / why compounds):
Time horizon:
Scorecard total (/5):  Quality__ Growth__ Health__ Valuation__ Fit__
Valuation snapshot: P/E__ Fwd P/E__ PEG__ EV/EBITDA__ FCF yield__
Correlation w/ existing AI holdings:
Position size (% of portfolio):  Entry price:
SELL TRIGGER (what would prove me wrong):
Notes:
```

Review past entries quarterly — this is how you actually improve.

---

## 10. Behavioral Guardrails

- **Confirmation bias** — actively seek the bear case for each pick.
- **Recency bias** — AI euphoria cuts both ways; the thesis, not the last 3 months of price, drives decisions.
- **Anchoring** — your purchase price is irrelevant to whether to hold today.
- **Overtrading** — the 1–3 trades/month cap is a feature; respect it.
- **FOMO** — a great company at a bad price is a bad investment. The watchlist is allowed to wait.

---

## 11. Tooling Roadmap (build into this repo)

This `portfolio-analyzer` repo already has fetchers + risk-return analysis. Natural additions:

- [ ] **`src/analyzers/portfolio.py`** — correlation + covariance matrices, portfolio σ = √(wᵀΣw), diversification ratio,
      per-holding **risk contribution**, effective number of bets, portfolio Sharpe/Sortino. *(Highest-leverage build.)*
- [ ] **`src/analyzers/allocation.py`** — weighting engines: equal-weight, inverse-vol, **risk parity**, min-variance,
      and a constrained efficient frontier — all honoring the §1 caps. Output target weights.
- [ ] **`src/analyzers/backtest.py`** — apply target weights to history → portfolio drawdown, VaR/CVaR (esp. 2022 AI selloff).
- [ ] **Rebalancing report** — current vs target weights, drift vs ±5pp bands, suggested trades (contributions-first).
- [ ] **`src/fetchers/fx.py`** — historical FX series (yfinance `*=X` / FRED `DEXSGUS`) with caching + backoff.
      Convert all price series to **SGD base** before §6 math, and produce a **currency-exposure report**.
- [ ] **`src/fetchers/macro.py`** — FRED client (rates `DGS10`/`DGS2`/`FEDFUNDS`, CPI, oil `DCOILWTICO`) + VIX;
      outputs a small **macro-regime dashboard** (rates trend, USD/SGD, inflation, oil, risk-off gauge).
- [ ] Model **FX conversion cost** (~0.1–0.5%) inside the rebalancing/trade-cost estimate.
- [ ] `src/analyzers/scorecard.py` — Piotroski F-score, Magic Formula rank, weighted scorecard (feeds §7 tilts).
- [ ] `src/analyzers/valuation.py` — comps table + simple DCF (uses FRED risk-free rate) with margin-of-safety output.
- [ ] SEC EDGAR fetcher (`data.sec.gov`, no key) — 10-K/20-F/8-K pulls, with backoff per CLAUDE.md.
- [ ] Monthly report generator — one CSV/markdown summary to drive the §8 workflow.

> Note: most portfolio math (covariance, risk parity, efficient frontier) is `numpy`/`scipy` — both BSD-licensed,
> matching the CLAUDE.md permissive-license preference. No heavyweight or copyleft dependency needed.

---

### TL;DR
Build a **portfolio, not a pile of single bets**: index the core (Irish-domiciled UCITS for tax, §1.5), then a
**capped, risk-balanced AI/semi satellite**. The scorecard (§5) decides *which* names qualify; the
**correlation/covariance math (§6)** decides *how much of each* — start equal-weight or risk-parity, honor the
8%/40% caps, and rebalance on ±5pp bands. Your AI names are highly correlated, so real diversification comes from
*outside* the basket. Review monthly, write down every thesis and sell trigger, and don't let mean-variance
optimization talk you into more concentration.
