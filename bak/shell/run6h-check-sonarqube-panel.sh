#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%m%d-%H%M)"
LOG_FILE="logs/run6h-check-sonarqube-panel-${TS}.log"

{
  echo "============================================================"
  echo "run6h: check merged SonarQube panel"
  echo "Started: $(date)"
  echo "Log file: ${LOG_FILE}"
  echo "============================================================"
  echo

  python proc_scripts/check-sonarqube-panel.py \
    --input tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
    --summary-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_summary.csv \
    --missing-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_missing_analysis_outcomes.csv

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
