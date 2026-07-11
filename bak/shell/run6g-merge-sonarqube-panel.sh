#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%m%d-%H%M)"
LOG_FILE="logs/run6g-merge-sonarqube-panel-${TS}.log"

{
  echo "============================================================"
  echo "run6g: merge SonarQube metrics into balanced panel"
  echo "Started: $(date)"
  echo "Log file: ${LOG_FILE}"
  echo "============================================================"
  echo

  python proc_scripts/merge-sonarqube-panel.py \
    --panel tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv \
    --treatment-metrics tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv \
    --control-metrics tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv \
    --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
    --qc-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube_qc.csv

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
