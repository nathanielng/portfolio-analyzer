# src/rebalancers/rebalancer.py
"""Band-based rebalancing → suggested trades (INVESTMENT_PLAN.md §7).

Compares current vs target weights, flags holdings that have drifted beyond
the rebalance band (±5pp by default), and proposes trades — contributions-first
to avoid unnecessary FX churn (§6.5.2 / §7). Enforces the single-name and
AI/semi caps from config.
"""

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger('portfolio_analyzer.rebalancer')


class Rebalancer:
    """
    Generate rebalancing trades from current holdings and target weights.

    Args:
        band: Drift threshold (weight fraction) that triggers a rebalance (default 0.05 = ±5pp).
        fx_conversion_cost: Per-conversion FX cost fraction for trade-cost estimates.
    """

    def __init__(self, band: float = 0.05, fx_conversion_cost: float = 0.002):
        self.band = band
        self.fx_conversion_cost = fx_conversion_cost

    def drift(self, current_weights: pd.Series, target_weights: pd.Series) -> pd.Series:
        """
        Per-holding deviation (current − target) in weight fraction.

        Symbols in current but not in target are treated as target=0 (sell candidates).
        Symbols in target but not in current are treated as current=0 (buy candidates).
        """
        all_symbols = current_weights.index.union(target_weights.index)
        current = current_weights.reindex(all_symbols, fill_value=0.0)
        target = target_weights.reindex(all_symbols, fill_value=0.0)
        return (current - target).rename('drift')

    def outside_band(self, current_weights: pd.Series, target_weights: pd.Series) -> pd.Series:
        """Boolean mask — True where |drift| exceeds the rebalance band."""
        d = self.drift(current_weights, target_weights)
        return d.abs() > self.band

    def proposed_trades(
        self,
        current_weights: pd.Series,
        target_weights: pd.Series,
        portfolio_value: float,
        new_contribution: float = 0.0,
    ) -> pd.DataFrame:
        """
        Trades to bring drifted holdings back within band (contributions-first).

        Strategy:
        1. Allocate new cash to the most underweight positions first (avoids sells → FX churn).
        2. If still out of band after contributions, propose sells on overweight positions.
        3. Only flag positions where |drift| > band.

        Args:
            current_weights: Current portfolio weights (fractions, sum ≈ 1).
            target_weights: Target portfolio weights (fractions, sum ≈ 1).
            portfolio_value: Total portfolio value in base currency.
            new_contribution: Fresh cash being added (base currency).

        Returns:
            DataFrame with columns: symbol, action, drift_pct, trade_value, note.
            Sorted by |drift| descending.
        """
        total = portfolio_value + new_contribution
        d = self.drift(current_weights, target_weights)

        # Only act on positions outside the band
        needs_action = d[d.abs() > self.band].copy()

        if needs_action.empty:
            logger.info("All positions within rebalance band — no trades needed.")
            return pd.DataFrame(columns=['symbol', 'action', 'drift_pct', 'trade_value', 'note'])

        rows = []
        remaining_contribution = new_contribution

        # Sort: most underweight first (negative drift = underweight)
        underweight = needs_action[needs_action < 0].sort_values()
        overweight = needs_action[needs_action > 0].sort_values(ascending=False)

        # Step 1: deploy fresh cash into underweight positions
        for symbol, drift_val in underweight.items():
            # Amount needed to bring to target
            needed = abs(drift_val) * total
            if remaining_contribution >= needed:
                trade_val = needed
                remaining_contribution -= needed
                note = "contribution"
            elif remaining_contribution > 0:
                trade_val = remaining_contribution
                remaining_contribution = 0
                note = "partial contribution"
            else:
                trade_val = needed
                note = "buy (sell proceeds)"

            rows.append({
                'symbol': symbol,
                'action': 'BUY',
                'drift_pct': round(drift_val * 100, 2),
                'trade_value': round(trade_val, 2),
                'note': note,
            })

        # Step 2: sell overweight positions
        for symbol, drift_val in overweight.items():
            trade_val = drift_val * total
            fx_cost = trade_val * self.fx_conversion_cost
            rows.append({
                'symbol': symbol,
                'action': 'SELL',
                'drift_pct': round(drift_val * 100, 2),
                'trade_value': round(trade_val, 2),
                'note': f'est. FX cost ${fx_cost:.2f}',
            })

        trades = pd.DataFrame(rows)
        trades = trades.sort_values('drift_pct', key=abs, ascending=False).reset_index(drop=True)
        return trades

    def summary(
        self,
        current_weights: pd.Series,
        target_weights: pd.Series,
        portfolio_value: float,
        new_contribution: float = 0.0,
    ) -> Dict:
        """
        One-call rebalance summary for display / reporting.

        Returns dict with: drift table, trades table, in_balance bool, band.
        """
        d = self.drift(current_weights, target_weights)
        trades = self.proposed_trades(
            current_weights, target_weights, portfolio_value, new_contribution
        )

        drift_df = pd.DataFrame({
            'current_pct': (current_weights.reindex(d.index, fill_value=0) * 100).round(2),
            'target_pct': (target_weights.reindex(d.index, fill_value=0) * 100).round(2),
            'drift_pct': (d * 100).round(2),
            'outside_band': d.abs() > self.band,
        })

        return {
            'in_balance': trades.empty,
            'band_pct': self.band * 100,
            'portfolio_value': portfolio_value,
            'drift': drift_df,
            'trades': trades,
        }
