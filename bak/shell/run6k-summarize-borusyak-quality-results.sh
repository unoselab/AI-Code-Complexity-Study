#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

TS="$(date +%m%d-%H%M)"
LOG_FILE="logs/run6k-summarize-borusyak-quality-results-${TS}.log"

OUT_DIR="tmp_adoption_test/data/python_did_test/quality_did_borusyak_v2"

{
  echo "============================================================"
  echo "run6k: summarize Borusyak quality DiD results"
  echo "Started: $(date)"
  echo "Log file: ${LOG_FILE}"
  echo "============================================================"
  echo

  python proc_scripts/summarize-borusyak-quality-results.py \
    --static-effects "${OUT_DIR}/borusyak_quality_v2_static_effects.csv" \
    --dynamic-effects "${OUT_DIR}/borusyak_quality_v2_dynamic_effects.csv" \
    --panel-checks "${OUT_DIR}/borusyak_quality_v2_panel_checks.csv" \
    --output-summary "${OUT_DIR}/borusyak_quality_v2_report_summary.csv" \
    --output-static "${OUT_DIR}/borusyak_quality_v2_static_effects_with_pct.csv" \
    --output-dynamic-summary "${OUT_DIR}/borusyak_quality_v2_dynamic_pretrend_summary.csv"

  echo
  echo "============================================================"
  echo "Completed: $(date)"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
