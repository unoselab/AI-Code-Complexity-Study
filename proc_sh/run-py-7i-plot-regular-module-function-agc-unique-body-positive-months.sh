#!/usr/bin/env bash
set -euo pipefail

# run-py-7i: Create a paper-style event-study graph for the run-py-7h
# positive-outcome-month sensitivity analysis.
#
# This wrapper is independent. It reads the dynamic-effects CSV created by
# run-py-7h and calls a new Python plotting script. It does not call or depend
# on the run-py-7h shell wrapper.
#
# Input:
#   repo_python/run-py-7h/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#     positive_outcome_months_only/
#     borusyak_regular_module_function_agc_unique_body_positive_months_dynamic_effects.csv
#
# Outputs:
#   The same run-py-7h result directory receives:
#     borusyak_regular_module_function_agc_unique_body_positive_months_dynamic_effects.pdf
#     borusyak_regular_module_function_agc_unique_body_positive_months_dynamic_effects.png
#
# Optional environment variables:
#   PYTHON_BIN       Python executable. Default: python
#   PY_SCRIPT        Plotting script path.
#   DYNAMIC_FILE     Dynamic-effects CSV path.
#   OUT_DIR          Output directory.
#   OUTPUT_STEM      Output filename stem.
#   FIGURE_WIDTH     Figure width in inches. Default: 6.8
#   FIGURE_HEIGHT    Figure height in inches. Default: 3.8
#   PNG_DPI          PNG resolution. Default: 300
#   OVERWRITE_OUTPUT 0 or 1. Default: 0
#   RUN_SELF_TEST    0 or 1. Default: 0
#
# Usage:
#   OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7i-plot-regular-module-function-agc-unique-body-positive-months.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/plot_regular_module_function_agc_unique_body_positive_months.py}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"

OUT_DIR="${OUT_DIR:-repo_python/run-py-7h/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/positive_outcome_months_only}"
PREFIX="borusyak_regular_module_function_agc_unique_body_positive_months"
DYNAMIC_FILE="${DYNAMIC_FILE:-${OUT_DIR}/${PREFIX}_dynamic_effects.csv}"
OUTPUT_STEM="${OUTPUT_STEM:-${PREFIX}_dynamic_effects}"
OUTPUT_PDF="${OUTPUT_PDF:-${OUT_DIR}/${OUTPUT_STEM}.pdf}"
OUTPUT_PNG="${OUTPUT_PNG:-${OUT_DIR}/${OUTPUT_STEM}.png}"

FIGURE_WIDTH="${FIGURE_WIDTH:-6.8}"
FIGURE_HEIGHT="${FIGURE_HEIGHT:-3.8}"
PNG_DPI="${PNG_DPI:-300}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-0}"

FIGURE_TITLE="${FIGURE_TITLE:-AGC-Like Regular-Function Unique Bodies}"
FIGURE_SUBTITLE="${FIGURE_SUBTITLE:-Positive-outcome repository-months only}"
FIGURE_CAPTION="${FIGURE_CAPTION:-Filled dots: 95% CI excludes 0 (significant). Hollow dots: 95% CI includes 0 (non-significant). Supplementary selected-sample sensitivity analysis.}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-7i}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7i-plot-positive-agc-months-${SPECIFICATION_NAME}-${RUN_TS}.log}"

case "${OVERWRITE_OUTPUT}" in
  0|1) ;;
  *)
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
    exit 1
    ;;
esac

case "${RUN_SELF_TEST}" in
  0|1) ;;
  *)
    echo "ERROR: RUN_SELF_TEST must be 0 or 1." >&2
    exit 1
    ;;
esac

if [[ ! -s "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script is missing or empty: ${PY_SCRIPT}" >&2
  exit 1
fi
if [[ ! -s "${DYNAMIC_FILE}" ]]; then
  echo "ERROR: Dynamic-effects CSV is missing or empty: ${DYNAMIC_FILE}" >&2
  exit 1
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python command not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ "${OVERWRITE_OUTPUT}" == "0" ]]; then
  for output_file in "${OUTPUT_PDF}" "${OUTPUT_PNG}"; do
    if [[ -e "${output_file}" ]]; then
      echo "ERROR: Output exists and OVERWRITE_OUTPUT=0: ${output_file}" >&2
      exit 1
    fi
  done
fi

mkdir -p "${OUT_DIR}" "${LOG_DIR}"

start_epoch="$(date +%s)"
start_display="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-7i: paper-style graph for positive-outcome-month AGC DiD"
  echo "Started:              ${start_display}"
  echo "Project root:         ${PROJECT_ROOT}"
  echo "Python:               $(command -v "${PYTHON_BIN}")"
  echo "Python version:       $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:        ${PY_SCRIPT}"
  echo "Python script SHA:    $(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
  echo "Dynamic input:        ${DYNAMIC_FILE}"
  echo "Dynamic input SHA:    $(sha256sum "${DYNAMIC_FILE}" | awk '{print $1}')"
  echo "Output PDF:           ${OUTPUT_PDF}"
  echo "Output PNG:           ${OUTPUT_PNG}"
  echo "Figure size:          ${FIGURE_WIDTH} x ${FIGURE_HEIGHT} inches"
  echo "PNG DPI:              ${PNG_DPI}"
  echo "Overwrite output:     ${OVERWRITE_OUTPUT}"
  echo "Run self-test:        ${RUN_SELF_TEST}"
  echo "Interpretation:       supplementary selected-sample sensitivity"
  echo "Log file:             ${LOG_FILE}"
  echo "================================================================================"
  echo

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
  fi

  overwrite_args=()
  if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    overwrite_args+=(--overwrite-output)
  fi

  MPLBACKEND=Agg "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --input-file "${DYNAMIC_FILE}" \
    --output-pdf "${OUTPUT_PDF}" \
    --output-png "${OUTPUT_PNG}" \
    --title "${FIGURE_TITLE}" \
    --subtitle "${FIGURE_SUBTITLE}" \
    --caption "${FIGURE_CAPTION}" \
    --width "${FIGURE_WIDTH}" \
    --height "${FIGURE_HEIGHT}" \
    --dpi "${PNG_DPI}" \
    --strict-event-times \
    "${overwrite_args[@]}"

  for expected_file in "${OUTPUT_PDF}" "${OUTPUT_PNG}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty graph output: ${expected_file}" >&2
      exit 1
    fi
  done

  echo
  echo "================================================================================"
  echo "run-py-7i PASS"
  echo "Input:                ${DYNAMIC_FILE}"
  echo "PDF:                  ${OUTPUT_PDF}"
  echo "PNG:                  ${OUTPUT_PNG}"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

end_epoch="$(date +%s)"
elapsed="$((end_epoch - start_epoch))"
printf -v elapsed_display '%02d:%02d:%02d' \
  "$((elapsed / 3600))" \
  "$(((elapsed % 3600) / 60))" \
  "$((elapsed % 60))"

cat <<EOF

================================================================================
run-py-7i execution summary
Started:              ${start_display}
Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')
Elapsed:              ${elapsed_display}
Exit code:            0
Output PDF:           ${OUTPUT_PDF}
Output PNG:           ${OUTPUT_PNG}
Log file:             ${LOG_FILE}
================================================================================
EOF
