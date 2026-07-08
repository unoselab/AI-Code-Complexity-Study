#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2b3: Compare Python pyv2 SonarQube metrics with paper panel
# ============================================================
# Purpose:
#   Diagnose whether the difference between our Python strict quality DiD
#   result and the paper result starts from raw SonarQube metrics.
#
# Inputs:
#   PAPER_PANEL
#     - Paper monthly panel with SonarQube metrics.
#     - Default: data/panel_event_monthly.csv
#
#   TREATMENT_SCAN
#     - Our treatment SonarQube scan output.
#     - Default: repo_python/sonarqube_input/strict/treatment/data/ts_repos_monthly_scanned_pyv2.csv
#
#   CONTROL_SCAN
#     - Our control SonarQube scan output.
#     - Default: repo_python/sonarqube_input/strict/control/data/ts_repos_monthly_scanned_pyv2.csv
#
# Outputs:
#   OUTPUT_DIR/sonarqube_metric_overlap_summary.csv
#   OUTPUT_DIR/sonarqube_metric_difference_summary.csv
#   OUTPUT_DIR/sonarqube_metric_difference_by_group.csv
#   OUTPUT_DIR/sonarqube_metric_row_level_comparison.csv
#   OUTPUT_DIR/sonarqube_metric_wide_comparison.csv
#   OUTPUT_DIR/sonarqube_metric_large_differences.csv
#   OUTPUT_DIR/sonarqube_missing_in_paper.csv
#   OUTPUT_DIR/sonarqube_missing_in_ours.csv
#   OUTPUT_DIR/sonarqube_static_warning_comparison.csv
#   OUTPUT_DIR/sonarqube_compare_notes.md
#
# Typical usage:
#   PANEL_VARIANT=strict SCAN_SUFFIX=pyv2 bash run-py-2b3-compare-sonarqube-pyv2-with-paper.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2b3_compare_sonarqube_pyv2_with_paper_${RUN_TS}.log}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
SCAN_SUFFIX="${SCAN_SUFFIX:-pyv2}"

PAPER_PANEL="${PAPER_PANEL:-data/panel_event_monthly.csv}"
PY_SCRIPT="${PY_SCRIPT:-compare/py/compare-sonarqube-with-paper.py}"

TREATMENT_SCAN="${TREATMENT_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/treatment/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"
CONTROL_SCAN="${CONTROL_SCAN:-repo_python/sonarqube_input/${PANEL_VARIANT}/control/data/ts_repos_monthly_scanned_${SCAN_SUFFIX}.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/sonarqube_compare_paper/${PANEL_VARIANT}_${SCAN_SUFFIX}}"
TOLERANCE="${TOLERANCE:-1e-9}"
TOP_N="${TOP_N:-500}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

{
  echo "============================================================"
  echo "run-py-2b3: Compare Python pyv2 SonarQube metrics with paper panel"
  echo "Started:          $(date)"
  echo "Project root:     $(pwd)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Scan suffix:      ${SCAN_SUFFIX}"
  echo "Paper panel:      ${PAPER_PANEL}"
  echo "Treatment scan:   ${TREATMENT_SCAN}"
  echo "Control scan:     ${CONTROL_SCAN}"
  echo "Python script:    ${PY_SCRIPT}"
  echo "Output dir:       ${OUTPUT_DIR}"
  echo "Tolerance:        ${TOLERANCE}"
  echo "Top N:            ${TOP_N}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo
} | tee "${LOG_FILE}"

if [[ ! -f "${PAPER_PANEL}" ]]; then
  echo "ERROR: paper panel not found: ${PAPER_PANEL}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${TREATMENT_SCAN}" ]]; then
  echo "ERROR: treatment scan not found: ${TREATMENT_SCAN}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${CONTROL_SCAN}" ]]; then
  echo "ERROR: control scan not found: ${CONTROL_SCAN}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python comparison script not found: ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
  echo "Create it first under compare/py/." | tee -a "${LOG_FILE}"
  exit 1
fi

python "${PY_SCRIPT}" \
  --paper-panel "${PAPER_PANEL}" \
  --treatment-scan "${TREATMENT_SCAN}" \
  --control-scan "${CONTROL_SCAN}" \
  --output-dir "${OUTPUT_DIR}" \
  --panel-variant "${PANEL_VARIANT}" \
  --scan-suffix "${SCAN_SUFFIX}" \
  --tolerance "${TOLERANCE}" \
  --top-n "${TOP_N}" \
  2>&1 | tee -a "${LOG_FILE}"

status=${PIPESTATUS[0]}

{
  echo
  echo "============================================================"
  echo "run-py-2b3 finished with exit code: ${status}"
  echo "Completed:        $(date)"
  echo "Output dir:       ${OUTPUT_DIR}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"

exit "${status}"
