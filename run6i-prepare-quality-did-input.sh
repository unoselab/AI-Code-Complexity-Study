#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%m%d-%H%M)"
LOG_FILE="logs/run6i-prepare-quality-did-input-${TS}.log"

{
  echo "============================================================"
  echo "run6i: prepare quality DiD input"
  echo "Started: $(date)"
  echo "Log file: ${LOG_FILE}"
  echo "============================================================"
  echo

  python proc_scripts/prepare-quality-did-input.py \
    --input tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_with_sonarqube.csv \
    --output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input.csv \
    --qc-output tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced_quality_did_input_qc.csv

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
