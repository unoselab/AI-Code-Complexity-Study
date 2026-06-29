#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run9g_summarize_borusyak_quality_${RUN_TS}.log}"

INPUT_DIR="${INPUT_DIR:-tmp_jsts_test/data/jsts_did_final/quality_did_borusyak}"
OUTPUT_DIR="${OUTPUT_DIR:-${INPUT_DIR}/summary}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/summarize_borusyak_quality_outputs.py}"
MAIN_PANEL="${MAIN_PANEL:-main_balanced}"

{
  echo "============================================================"
  echo "run9g: summarize Borusyak quality DiD outputs"
  echo "Started:     $(date)"
  echo "Python:      ${PY_SCRIPT}"
  echo "Input dir:   ${INPUT_DIR}"
  echo "Output dir:  ${OUTPUT_DIR}"
  echo "Main panel:  ${MAIN_PANEL}"
  echo "Log file:    ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "ERROR: Input directory not found: ${INPUT_DIR}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  python "${PY_SCRIPT}" \
    --input-dir "${INPUT_DIR}" \
    --output-dir "${OUTPUT_DIR}" \
    --main-panel "${MAIN_PANEL}"

  echo
  echo "============================================================"
  echo "run9g completed successfully."
  echo "Completed:   $(date)"
  echo "Output dir:  ${OUTPUT_DIR}"
  echo "Log file:    ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
