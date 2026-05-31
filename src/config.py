# src/config.py
"""Central configuration — implements the guardrails in INVESTMENT_PLAN.md.

All values are overridable via environment variables (loaded with python-dotenv
in the scripts), so credentials/tuning stay out of code. See .env.example.
"""

import os

# --- Base currency (INVESTMENT_PLAN.md §6.5) -------------------------------
# All returns / risk / correlation math is computed in this currency so that
# FX risk is automatically captured.
BASE_CURRENCY = os.getenv('BASE_CURRENCY', 'SGD')

# --- Exposure caps (§1) ----------------------------------------------------
SINGLE_NAME_CAP = float(os.getenv('SINGLE_NAME_CAP', '0.08'))        # soft cap per single stock
SINGLE_NAME_HARD_CAP = float(os.getenv('SINGLE_NAME_HARD_CAP', '0.12'))  # hard cap before forced trim
AI_SEMI_CAP = float(os.getenv('AI_SEMI_CAP', '0.40'))               # max aggregate AI/semi exposure

# --- Portfolio construction (§6) -------------------------------------------
MAX_CORRELATION = float(os.getenv('MAX_CORRELATION', '0.70'))       # redundancy threshold (§6.4)
MAX_RISK_CONTRIBUTION = float(os.getenv('MAX_RISK_CONTRIBUTION', '0.30'))  # trim if one name > this share of risk

# --- Rebalancing & tilts (§7) ----------------------------------------------
REBALANCE_BAND = float(os.getenv('REBALANCE_BAND', '0.05'))         # ±5 percentage points
TILT_BAND = float(os.getenv('TILT_BAND', '0.03'))                   # ±3pp scorecard tilt around baseline

# --- Risk / valuation inputs -----------------------------------------------
RISK_FREE_RATE = float(os.getenv('RISK_FREE_RATE', '0.04'))         # fallback if FRED unavailable
TRADING_DAYS = int(os.getenv('TRADING_DAYS', '252'))

# --- FX conversion cost (§6.5.2), as a fraction ----------------------------
FX_CONVERSION_COST = float(os.getenv('FX_CONVERSION_COST', '0.002'))  # ~0.2%

# --- Data paths ------------------------------------------------------------
DATA_DIR = os.getenv('DATA_DIR', 'data')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
UNIVERSE_CSV = os.getenv('UNIVERSE_CSV', os.path.join(DATA_DIR, 'universe.csv'))
HOLDINGS_CSV = os.getenv('HOLDINGS_CSV', os.path.join(DATA_DIR, 'holdings.csv'))
TARGETS_CSV = os.getenv('TARGETS_CSV', os.path.join(DATA_DIR, 'targets.csv'))
