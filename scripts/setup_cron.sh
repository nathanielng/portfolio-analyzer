#!/usr/bin/env bash
# setup_cron.sh — install daily portfolio report cron job
#
# Run once from any directory:
#   bash /path/to/portfolio-analyzer/scripts/setup_cron.sh
#
# What it does:
#   • Adds a cron job to run daily_report.py at 8:00 AM (system local time)
#   • Creates ~/portfolio-reports/ for log output
#   • Idempotent — safe to run multiple times, won't add duplicates
#
# Timezone note:
#   Cron uses the system clock. If your Mac is set to Singapore Time (SGT = UTC+8),
#   "0 8 * * *" fires at 8:00 AM SGT. Verify with: sudo systemsetup -gettimezone
#
# To remove the job later:  crontab -e  and delete the matching line.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${HOME}/.venv/bin/python"
REPORT_SCRIPT="${REPO_DIR}/scripts/daily_report.py"
SNAPSHOT_SCRIPT="${REPO_DIR}/scripts/portfolio_snapshot.py"
LOG_DIR="${HOME}/portfolio-reports"
LOG_FILE="${LOG_DIR}/daily.log"
CRON_TAG="portfolio-analyzer"   # shared marker; both jobs carry it for idempotency

# ── Validate environment ────────────────────────────────────────────────────
if [ ! -f "${VENV_PYTHON}" ]; then
    echo "ERROR: Python venv not found at ${VENV_PYTHON}"
    echo "       Create it with: python3 -m venv ~/.venv && ~/.venv/bin/pip install -r requirements.txt"
    exit 1
fi

for s in "${REPORT_SCRIPT}" "${SNAPSHOT_SCRIPT}"; do
    if [ ! -f "${s}" ]; then echo "ERROR: Script not found at ${s}"; exit 1; fi
done

# ── Create log directory ────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
echo "Log directory ready: ${LOG_DIR}"

# ── Build cron lines ────────────────────────────────────────────────────────
# Two jobs, staggered to avoid hammering yfinance simultaneously:
#   08:00  daily_report.py     → valuation snapshot + macro + Telegram (refreshes portfolio_snapshot.json)
#   08:10  portfolio_snapshot.py → full data + correlation matrix       (refreshes portfolio_data.json)
# Both write a freshness marker (data/.refresh.json) so interactive skill
# invocations the same day skip the slow refresh.
REPORT_LINE="0 8 * * * cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${REPORT_SCRIPT}\" >> \"${LOG_FILE}\" 2>&1  # ${CRON_TAG}/daily_report"
SNAPSHOT_LINE="10 8 * * * cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${SNAPSHOT_SCRIPT}\" >> \"${LOG_FILE}\" 2>&1  # ${CRON_TAG}/portfolio_snapshot"

# ── Install (idempotent) ────────────────────────────────────────────────────
# Strip any existing portfolio-analyzer lines, then add the current pair.
EXISTING_CRON=$(crontab -l 2>/dev/null || true)
CLEANED=$(echo "${EXISTING_CRON}" | grep -vF "${CRON_TAG}/" || true)

printf '%s\n%s\n%s\n' "${CLEANED}" "${REPORT_LINE}" "${SNAPSHOT_LINE}" | grep -v '^$' | crontab -

echo ""
echo "Cron jobs installed:"
crontab -l 2>/dev/null | grep "${CRON_TAG}/"
echo ""
echo "Test them now with:"
echo "  cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${REPORT_SCRIPT}\" --no-telegram"
echo "  cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${SNAPSHOT_SCRIPT}\""
echo ""
echo "View logs with:  tail -f ${LOG_FILE}"
