#!/usr/bin/env python3
"""
Generate portfolio recommendations based on watchlist performance and correlations.

Implements multiple portfolio optimization strategies:
1. Minimum Variance - lowest risk portfolio
2. Maximum Sharpe Ratio - best risk-adjusted returns
3. Risk Parity - equal risk contribution
4. Sector Balanced - balanced across business groups
5. Equal Weight - baseline for comparison
"""

import json
import numpy as np
from pathlib import Path
from scipy.optimize import minimize
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / 'output' / 'watchlist-data.json'
OUTPUT_PATH = PROJECT_ROOT / 'output' / 'portfolio_recommendation.html'

# Risk-free rate for Sharpe ratio calculation
RISK_FREE_RATE = 0.04

# Stock groups for sector-balanced portfolio
STOCK_GROUPS = {
    'Chip Design': ['NVDA', 'AMD', 'INTC', 'ARM', 'SNPS'],
    'Manufacturing & Memory': ['TSM', 'MU', '000660.KS', 'ASML'],
    'Cloud & Enterprise': ['MSFT', 'AMZN', 'GOOGL', 'META', 'ORCL', 'AVGO'],
    'Consumer Hardware': ['AAPL'],
}


def load_data() -> Dict:
    """Load watchlist data from JSON."""
    with open(DATA_PATH, 'r') as f:
        return json.load(f)


def extract_metrics(data: Dict) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract symbols, returns, volatility, and correlation matrix.

    Returns:
        - symbols: list of stock symbols (excluding benchmarks)
        - returns: array of 1Y returns (%)
        - volatility: array of annualized volatility (%)
        - correlation: correlation matrix
    """
    # Filter out benchmarks
    watchlist = [s for s in data['watchlist'] if s['symbol'] not in ['SMH', 'QQQM']]
    symbols = [s['symbol'] for s in watchlist]

    # Extract 1Y metrics
    returns = np.array([s['metrics']['1y'].get('return', 0) for s in watchlist])
    volatility = np.array([s['metrics']['1y'].get('volatility', 0) for s in watchlist])

    # Extract correlation matrix (ordered by symbols)
    corr_matrix = data.get('correlation_matrix', {})
    n = len(symbols)
    correlation = np.eye(n)
    for i, sym1 in enumerate(symbols):
        for j, sym2 in enumerate(symbols):
            if sym1 in corr_matrix and sym2 in corr_matrix[sym1]:
                correlation[i, j] = corr_matrix[sym1][sym2] or 1.0 if i == j else 0.0

    return symbols, returns, volatility, correlation


def calculate_portfolio_return(weights: np.ndarray, returns: np.ndarray) -> float:
    """Calculate portfolio return."""
    return np.sum(weights * returns)


def calculate_portfolio_volatility(weights: np.ndarray, correlation: np.ndarray, volatility: np.ndarray) -> float:
    """Calculate portfolio volatility."""
    # Build covariance matrix from correlation and volatility
    cov_matrix = np.outer(volatility, volatility) * correlation
    return np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))


def calculate_sharpe_ratio(weights: np.ndarray, returns: np.ndarray, correlation: np.ndarray, volatility: np.ndarray) -> float:
    """Calculate Sharpe ratio (return per unit of risk)."""
    port_return = calculate_portfolio_return(weights, returns)
    port_vol = calculate_portfolio_volatility(weights, correlation, volatility)
    if port_vol == 0:
        return 0
    return (port_return - RISK_FREE_RATE) / port_vol


def optimize_min_variance(returns: np.ndarray, correlation: np.ndarray, volatility: np.ndarray) -> np.ndarray:
    """
    Minimize portfolio variance.

    Formula: minimize w^T * Σ * w
    where w = weights, Σ = covariance matrix
    """
    n = len(returns)

    def objective(w):
        return calculate_portfolio_volatility(w, correlation, volatility)

    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
    bounds = tuple((0, 1) for _ in range(n))
    initial_guess = np.array([1/n] * n)

    result = minimize(objective, initial_guess, method='SLSQP', bounds=bounds, constraints=constraints)
    return result.x


def optimize_max_sharpe(returns: np.ndarray, correlation: np.ndarray, volatility: np.ndarray) -> np.ndarray:
    """
    Maximize Sharpe ratio (risk-adjusted returns).

    Formula: maximize (w^T * μ - rf) / sqrt(w^T * Σ * w)
    where w = weights, μ = returns, rf = risk-free rate, Σ = covariance matrix
    """
    n = len(returns)

    def objective(w):
        return -calculate_sharpe_ratio(w, returns, correlation, volatility)

    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
    bounds = tuple((0, 1) for _ in range(n))
    initial_guess = np.array([1/n] * n)

    result = minimize(objective, initial_guess, method='SLSQP', bounds=bounds, constraints=constraints)
    return result.x


def optimize_risk_parity(correlation: np.ndarray, volatility: np.ndarray) -> np.ndarray:
    """
    Risk Parity: each asset contributes equally to portfolio risk.

    Formula: w_i = (1/σ_i) / Σ(1/σ_j)
    where σ_i = volatility of asset i
    """
    inverse_vol = 1.0 / volatility
    weights = inverse_vol / np.sum(inverse_vol)
    return weights


def optimize_sector_balanced(symbols: List[str], returns: np.ndarray, correlation: np.ndarray, volatility: np.ndarray) -> np.ndarray:
    """
    Sector Balanced: equal weight per sector, then optimize within sectors.

    First allocate equal weight to each sector, then optimize to maximize
    Sharpe ratio while respecting sector constraints.
    """
    n = len(symbols)
    sector_map = {}
    for sector, stocks in STOCK_GROUPS.items():
        for stock in stocks:
            if stock in symbols:
                sector_map[symbols.index(stock)] = sector

    # Allocate 25% to each of 4 main sectors, 0% to benchmarks
    sector_weights = {
        'Chip Design': 0.25,
        'Manufacturing & Memory': 0.25,
        'Cloud & Enterprise': 0.40,  # Larger allocation (highest diversity)
        'Consumer Hardware': 0.10,  # Small allocation (single stock)
    }

    weights = np.zeros(n)
    for idx, sector in sector_map.items():
        sector_allocation = sector_weights.get(sector, 0)
        # Count stocks in this sector
        sector_stocks = [i for i, s in sector_map.items() if s == sector]
        # Equal weight within sector
        weight_per_stock = sector_allocation / len(sector_stocks)
        for stock_idx in sector_stocks:
            weights[stock_idx] = weight_per_stock

    return weights / np.sum(weights)  # Normalize


def generate_html_report(
    symbols: List[str],
    returns: np.ndarray,
    volatility: np.ndarray,
    correlation: np.ndarray,
    portfolios: Dict[str, np.ndarray]
) -> str:
    """Generate HTML report with portfolio recommendations."""

    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio Recommendation Report</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 40px 20px;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            background: white;
            padding: 40px;
            border-radius: 12px;
            margin-bottom: 40px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        h1 { color: #2c3e50; margin-bottom: 10px; font-size: 32px; }
        .subtitle { color: #7f8c8d; font-size: 16px; }
        .section {
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        h2 { color: #2c3e50; margin-bottom: 20px; font-size: 24px; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        h3 { color: #34495e; margin-top: 20px; margin-bottom: 10px; font-size: 16px; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }
        th {
            background: #34495e;
            color: white;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
        }
        td { color: #2c3e50; }
        tr:hover { background: #f8f9fa; }
        .metric {
            display: inline-block;
            background: #ecf0f1;
            padding: 10px 15px;
            border-radius: 6px;
            margin: 5px 5px 5px 0;
            font-weight: 600;
            color: #2c3e50;
        }
        .metric-label { font-size: 12px; color: #7f8c8d; text-transform: uppercase; }
        .metric-value { font-size: 18px; color: #3498db; }
        .positive { color: #27ae60; font-weight: 600; }
        .negative { color: #e74c3c; font-weight: 600; }
        .formula {
            background: #f5f7fa;
            padding: 15px;
            border-left: 4px solid #3498db;
            margin: 20px 0;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            overflow-x: auto;
        }
        .recommendation {
            background: #e8f8f5;
            padding: 20px;
            border-left: 4px solid #27ae60;
            margin: 20px 0;
            border-radius: 4px;
        }
        .recommendation h4 { color: #27ae60; margin-bottom: 10px; }
        .note {
            background: #fff3cd;
            padding: 15px;
            border-left: 4px solid #ffc107;
            margin: 20px 0;
            border-radius: 4px;
            color: #856404;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Portfolio Recommendation Report</h1>
            <p class="subtitle">Data-driven recommendations based on performance, risk, and correlations</p>
        </header>
""")

    # Executive Summary
    html_parts.append("""
        <div class="section">
            <h2>Executive Summary</h2>
            <p>This report analyzes 18 stocks across 5 business groups (Chip Design, Manufacturing & Memory, Cloud & Enterprise, Consumer Hardware, and Benchmarks) to recommend optimal portfolio allocations based on:</p>
            <ul style="margin: 15px 0 15px 20px; line-height: 1.8;">
                <li><strong>Performance Metrics:</strong> 1Y, 2Y, 5Y returns, volatility, Sharpe ratio, and alpha</li>
                <li><strong>Risk Factors:</strong> Beta (market sensitivity) and correlation between stocks</li>
                <li><strong>Optimization Strategies:</strong> Five different approaches balancing risk and return</li>
            </ul>
            <div class="note">
                <strong>Key Insight:</strong> Diversification across sectors reduces portfolio risk while maintaining competitive returns. High-correlation stocks (semiconductors) should be balanced with lower-correlation stocks (cloud/platforms).
            </div>
        </div>
""")

    # Correlation Analysis
    html_parts.append("""
        <div class="section">
            <h2>1. Correlation Analysis</h2>
            <p>Understanding stock correlations is crucial for portfolio construction. High correlation (>0.6) means stocks move together, offering little diversification benefit.</p>
""")

    # Find high correlation pairs
    high_corr_pairs = []
    for i in range(len(symbols)):
        for j in range(i+1, len(symbols)):
            if correlation[i, j] > 0.5:
                high_corr_pairs.append((symbols[i], symbols[j], correlation[i, j]))

    if high_corr_pairs:
        high_corr_pairs.sort(key=lambda x: x[2], reverse=True)
        html_parts.append("<h3>High Correlation Pairs (>0.50)</h3><table><tr><th>Stock 1</th><th>Stock 2</th><th>Correlation</th><th>Interpretation</th></tr>")
        for s1, s2, corr in high_corr_pairs[:10]:
            interpretation = "Very High" if corr > 0.7 else "High" if corr > 0.6 else "Moderate"
            html_parts.append(f"<tr><td>{s1}</td><td>{s2}</td><td>{corr:.3f}</td><td>{interpretation} - similar business cycle sensitivity</td></tr>")
        html_parts.append("</table>")

    html_parts.append("""
        <div class="formula">
            <strong>Correlation Definition:</strong><br>
            ρ(X,Y) = Cov(X,Y) / (σ_X × σ_Y)<br>
            Range: -1 (perfectly inverse) to +1 (perfectly aligned)<br>
            Portfolio Benefit: Lower correlations = better diversification
        </div>
        </div>
""")

    # Portfolio Recommendations
    html_parts.append("""
        <div class="section">
            <h2>2. Portfolio Recommendations</h2>
            <p>Five optimization strategies, each with different risk/return profiles:</p>
""")

    portfolio_descriptions = {
        'Equal Weight': {
            'desc': 'Baseline: equal 1/18 allocation to each stock. Simple but may not optimize risk.',
            'best_for': 'Passive investors seeking simplicity and equal exposure'
        },
        'Risk Parity': {
            'desc': 'Each stock contributes equally to portfolio risk. Volatility-weighted inverse allocation.',
            'best_for': 'Risk-conscious investors wanting equal risk contribution'
        },
        'Minimum Variance': {
            'desc': 'Lowest portfolio volatility. Minimizes downside risk but may sacrifice returns.',
            'best_for': 'Conservative investors prioritizing capital preservation'
        },
        'Maximum Sharpe Ratio': {
            'desc': 'Best risk-adjusted returns. Balances return and risk optimally.',
            'best_for': 'Growth-oriented investors seeking efficient portfolio (recommended)'
        },
        'Sector Balanced': {
            'desc': '40% Cloud/Enterprise, 25% Chip Design, 25% Manufacturing, 10% Consumer. Respects business group balance.',
            'best_for': 'Investors wanting strategic sector allocation'
        }
    }

    for portfolio_name, weights in portfolios.items():
        port_return = calculate_portfolio_return(weights, returns)
        port_vol = calculate_portfolio_volatility(weights, correlation, volatility)
        sharpe = calculate_sharpe_ratio(weights, returns, correlation, volatility)

        desc = portfolio_descriptions.get(portfolio_name, {})

        html_parts.append(f"""
        <div style="margin-bottom: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <h3>{portfolio_name}</h3>
            <p style="color: #7f8c8d; margin-bottom: 15px;">{desc.get('desc', '')}</p>

            <div style="margin-bottom: 15px;">
                <div class="metric">
                    <div class="metric-label">Expected Return (1Y)</div>
                    <div class="metric-value"><span class="positive">{port_return:+.2f}%</span></div>
                </div>
                <div class="metric">
                    <div class="metric-label">Volatility</div>
                    <div class="metric-value">{port_vol:.2f}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Sharpe Ratio</div>
                    <div class="metric-value">{sharpe:.3f}</div>
                </div>
            </div>

            <div style="margin-top: 15px;">
                <strong>Top Holdings (>5%):</strong><br>
                <table style="margin-top: 10px;">
                    <tr><th>Stock</th><th>Weight</th><th>Expected Return</th></tr>
""")

        # Sort by weight
        top_holdings = sorted(zip(symbols, weights, returns), key=lambda x: x[1], reverse=True)
        for symbol, weight, ret in top_holdings:
            if weight > 0.05:
                html_parts.append(f"<tr><td><strong>{symbol}</strong></td><td>{weight*100:.1f}%</td><td><span class='{'positive' if ret > 0 else 'negative'}'>{ret:+.1f}%</span></td></tr>")

        html_parts.append("""
                </table>
            </div>
        </div>
""")

    html_parts.append("</div>")

    # Mathematical Formulas
    html_parts.append("""
        <div class="section">
            <h2>6. Mathematical Framework</h2>

            <h3>Portfolio Return</h3>
            <div class="formula">
                E[R_p] = Σ(w_i × R_i)<br>
                where: w_i = weight of asset i, R_i = return of asset i
            </div>

            <h3>Portfolio Variance & Volatility</h3>
            <div class="formula">
                Var(R_p) = w^T × Σ × w<br>
                σ_p = √(Var(R_p))<br>
                where: Σ = covariance matrix, σ = standard deviation
            </div>

            <h3>Sharpe Ratio (Risk-Adjusted Return)</h3>
            <div class="formula">
                SR = (E[R_p] - R_f) / σ_p<br>
                where: R_f = risk-free rate (4%), σ_p = portfolio volatility<br>
                Higher Sharpe ratio = better return per unit of risk taken
            </div>

            <h3>Covariance Matrix from Correlation</h3>
            <div class="formula">
                Σ_ij = ρ_ij × σ_i × σ_j<br>
                where: ρ_ij = correlation between assets i and j
            </div>

            <h3>Optimization Problems</h3>
            <div class="formula">
                <strong>Minimize Variance:</strong><br>
                minimize: w^T × Σ × w<br>
                subject to: Σ(w_i) = 1, w_i ≥ 0<br><br>

                <strong>Maximize Sharpe Ratio:</strong><br>
                maximize: (E[R_p] - R_f) / √(w^T × Σ × w)<br>
                subject to: Σ(w_i) = 1, w_i ≥ 0<br><br>

                <strong>Risk Parity:</strong><br>
                w_i = (1/σ_i) / Σ(1/σ_j)<br>
                Constraint: each asset contributes equally to portfolio risk
            </div>
        </div>
""")

    # Concrete Allocations for $10k Portfolio
    html_parts.append("""
        <div class="section">
            <h2>4. Concrete Allocations for $10,000 Portfolio</h2>
            <p>How to deploy your capital in the two recommended strategies:</p>
""")

    portfolio_size = 10000

    for portfolio_name in ['Maximum Sharpe Ratio', 'Sector Balanced']:
        if portfolio_name not in portfolios:
            continue

        weights = portfolios[portfolio_name]
        port_return = calculate_portfolio_return(weights, returns)
        port_vol = calculate_portfolio_volatility(weights, correlation, volatility)
        expected_gain = (port_return / 100) * portfolio_size

        html_parts.append(f"""
        <div style="margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <h3>{portfolio_name}</h3>
            <p style="color: #7f8c8d; margin-bottom: 15px;"><strong>Expected Return:</strong> {port_return:+.2f}% | <strong>Expected Gain (1Y):</strong> <span class="positive">${expected_gain:,.0f}</span></p>

            <table style="width: 100%; margin-top: 15px;">
                <tr><th>Stock</th><th>Weight</th><th>Allocation</th><th>Expected Return</th><th>Expected Gain</th></tr>
""")

        # Sort by weight
        top_holdings = sorted(zip(symbols, weights, returns), key=lambda x: x[1], reverse=True)

        for symbol, weight, ret in top_holdings:
            if weight > 0.001:  # Show anything > 0.1%
                dollar_amount = weight * portfolio_size
                expected_stock_gain = (ret / 100) * dollar_amount
                html_parts.append(f"""
                <tr>
                    <td><strong>{symbol}</strong></td>
                    <td>{weight*100:.1f}%</td>
                    <td>${dollar_amount:,.0f}</td>
                    <td><span class='{'positive' if ret > 0 else 'negative'}'>{ret:+.1f}%</span></td>
                    <td><span class='{'positive' if expected_stock_gain > 0 else 'negative'}'>${expected_stock_gain:+,.0f}</span></td>
                </tr>
""")

        html_parts.append("""
            </table>
        </div>
""")

    html_parts.append("</div>")

    # Final Recommendation
    html_parts.append("""
        <div class="section">
            <h2>5. Recommended Strategy</h2>
            <div class="recommendation">
                <h4>✓ Use Maximum Sharpe Ratio Portfolio</h4>
                <p><strong>Why:</strong> This portfolio optimally balances risk and return by maximizing return per unit of risk. It's mathematically proven to be the most efficient allocation given your constraints.</p>
                <p><strong>When to use:</strong> If you want the best risk-adjusted returns and are comfortable with moderate optimization.</p>
            </div>

            <div class="recommendation">
                <h4>✓ Secondary: Sector Balanced Portfolio</h4>
                <p><strong>Why:</strong> More intuitive allocation respecting business groups. Ensures you maintain meaningful exposure to each sector's growth opportunity.</p>
                <p><strong>When to use:</strong> If you prefer a strategic sector-based approach that's easier to explain and monitor.</p>
            </div>

            <div class="note">
                <strong>Key Principles:</strong>
                <ul style="margin-left: 20px; margin-top: 10px;">
                    <li>Diversify across uncorrelated asset classes (semiconductors + cloud platforms)</li>
                    <li>Overweight high-Sharpe ratio stocks (best risk-adjusted returns)</li>
                    <li>Reduce correlation drag by selecting stocks with low pairwise correlations</li>
                    <li>Rebalance quarterly to maintain target allocations</li>
                    <li>Monitor beta and alpha; overweight positive alpha stocks</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>7. Risk Considerations</h2>
            <ul style="margin-left: 20px; line-height: 2;">
                <li><strong>Sector Concentration:</strong> Tech/semiconductors represent majority. Consider adding non-tech exposure.</li>
                <li><strong>Market Beta:</strong> All stocks are high-beta (move with market). Add bonds or defensive stocks for lower volatility.</li>
                <li><strong>Correlation Stability:</strong> Correlations change during market stress. Rebalance more frequently during volatility.</li>
                <li><strong>Rebalancing Frequency:</strong> Quarterly rebalancing balances tax efficiency with drift control.</li>
            </ul>
        </div>

        <footer style="text-align: center; color: #7f8c8d; margin-top: 40px; padding: 20px;">
            <p>Generated by Portfolio Analyzer • Data from Yahoo Finance, Polygon.io</p>
        </footer>
    </div>
</body>
</html>
""")

    return '\n'.join(html_parts)


def main():
    """Generate portfolio recommendations."""
    print("Loading watchlist data...")
    data = load_data()

    print("Extracting metrics...")
    symbols, returns, volatility, correlation = extract_metrics(data)

    print(f"Analyzing {len(symbols)} stocks...")
    print(f"Average return (1Y): {returns.mean():.2f}%")
    print(f"Average volatility: {volatility.mean():.2f}%")

    # Calculate portfolios
    print("Optimizing portfolios...")
    portfolios = {
        'Equal Weight': np.array([1/len(symbols)] * len(symbols)),
        'Risk Parity': optimize_risk_parity(correlation, volatility),
        'Minimum Variance': optimize_min_variance(returns, correlation, volatility),
        'Maximum Sharpe Ratio': optimize_max_sharpe(returns, correlation, volatility),
        'Sector Balanced': optimize_sector_balanced(symbols, returns, correlation, volatility),
    }

    # Generate HTML report
    print("Generating HTML report...")
    html_content = generate_html_report(symbols, returns, volatility, correlation, portfolios)

    # Write to file
    with open(OUTPUT_PATH, 'w') as f:
        f.write(html_content)

    print(f"Report written to {OUTPUT_PATH}")
    print("Done!")


if __name__ == '__main__':
    main()
