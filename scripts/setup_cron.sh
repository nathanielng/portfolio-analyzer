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
SCRIPT="${REPO_DIR}/scripts/daily_report.py"
LOG_DIR="${HOME}/portfolio-reports"
LOG_FILE="${LOG_DIR}/daily.log"
CRON_TAG="portfolio-analyzer/daily_report"   # unique marker for idempotency check

# ── Validate environment ────────────────────────────────────────────────────
if [ ! -f "${VENV_PYTHON}" ]; then
    echo "ERROR: Python venv not found at ${VENV_PYTHON}"
    echo "       Create it with: python3 -m venv ~/.venv && ~/.venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "${SCRIPT}" ]; then
    echo "ERROR: Script not found at ${SCRIPT}"
    exit 1
fi

# ── Create log directory ────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
echo "Log directory ready: ${LOG_DIR}"

# ── Build cron line ─────────────────────────────────────────────────────────
# 0 8 * * * = 8:00 AM every day (local system time)
CRON_LINE="0 8 * * * cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${SCRIPT}\" >> \"${LOG_FILE}\" 2>&1  # ${CRON_TAG}"

# ── Install (idempotent) ────────────────────────────────────────────────────
# Note: crontab -l exits non-zero when no crontab exists; use || true to handle.
EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if echo "${EXISTING_CRON}" | grep -qF "${CRON_TAG}"; then
    echo "Cron job already installed:"
    echo "${EXISTING_CRON}" | grep "${CRON_TAG}"
    echo ""
    echo "Nothing changed. To update it, remove the existing line with: crontab -e"
    exit 0
fi

(echo "${EXISTING_CRON}"; echo "${CRON_LINE}") | crontab -

echo ""
echo "Cron job installed successfully:"
crontab -l 2>/dev/null | grep "${CRON_TAG}"
echo ""
echo "Test it now with:"
echo "  cd \"${REPO_DIR}\" && \"${VENV_PYTHON}\" \"${SCRIPT}\" --no-telegram"
echo ""
echo "View logs with:"
echo "  tail -f ${LOG_FILE}"
