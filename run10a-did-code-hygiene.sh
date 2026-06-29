#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run10a_did_code_hygiene_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/did_code_hygiene.py}"

PANEL_FILE="${PANEL_FILE:-tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input.csv}"

WARNING_INPUT="${WARNING_INPUT:-}"

OUT_DIR="${OUT_DIR:-tmp_jsts_test/data/jsts_did_final/warning_category_did/code_hygiene}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"

CATEGORY="${CATEGORY:-Code Hygiene}"

{
  echo "============================================================"
  echo "run10a: Borusyak DiD for Code Hygiene warnings"
  echo "Started:       $(date)"
  echo "Python script: ${PY_SCRIPT}"
  echo "Panel file:    ${PANEL_FILE}"
  echo "Warning input: ${WARNING_INPUT:-AUTO-DETECT}"
  echo "Output dir:    ${OUT_DIR}"
  echo "Helper file:   ${HELPER_FILE}"
  echo "Category:      ${CATEGORY}"
  echo "Log file:      ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -f "${PANEL_FILE}" ]]; then
    echo "ERROR: Panel file not found: ${PANEL_FILE}"
    exit 1
  fi

  if [[ ! -f "${HELPER_FILE}" ]]; then
    echo "ERROR: R helper file not found: ${HELPER_FILE}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  if [[ -n "${WARNING_INPUT}" ]]; then
    python "${PY_SCRIPT}" \
      --panel "${PANEL_FILE}" \
      --warnings "${WARNING_INPUT}" \
      --category "${CATEGORY}" \
      --out-dir "${OUT_DIR}" \
      --helper "${HELPER_FILE}"
  else
    python "${PY_SCRIPT}" \
      --panel "${PANEL_FILE}" \
      --category "${CATEGORY}" \
      --out-dir "${OUT_DIR}" \
      --helper "${HELPER_FILE}"
  fi

  echo
  echo "============================================================"
  echo "run10a completed successfully."
  echo "Completed:     $(date)"
  echo "Output dir:    ${OUT_DIR}"
  echo "Log file:      ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
