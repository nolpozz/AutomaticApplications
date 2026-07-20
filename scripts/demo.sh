#!/usr/bin/env bash
# End-to-end demo: runs the full pipeline offline (mock LLM + sample jobs),
# then prints the review queue and analytics. No API keys required.
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer the installed console script; fall back to a module invocation.
if command -v job-agent >/dev/null 2>&1; then
  AGENT="job-agent"
else
  PY="$(command -v python3 || command -v python)"
  AGENT="$PY -m job_agent.cli"
fi

echo "==> Running the full pipeline (offline, mock provider)"
$AGENT pipeline --formats md

echo
echo "==> Jobs awaiting review"
$AGENT review

echo
echo "==> Analytics"
$AGENT stats

echo
echo "==> Artifacts"
echo "  database : data/job_agent.db"
echo "  workbook : data/job_agent.xlsx"
echo "  documents: data/documents/ ($(find data/documents -type f 2>/dev/null | wc -l) files)"
