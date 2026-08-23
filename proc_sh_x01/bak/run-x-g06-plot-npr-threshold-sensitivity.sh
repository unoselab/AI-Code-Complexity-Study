#!/usr/bin/env bash
# Plot the run-x-g06 NPR-threshold sensitivity coefficient figure.
#
# This wrapper is standalone. It does not call any previous experiment wrapper.
# It only consumes the completed run-x-g06 primary-summary CSV and invokes the
# dedicated publication plotting program.
#
# Input:
#   repo_x01/run-x-g06/dynamic_panel_gmm_npr_threshold_primary_summary.csv
#
# Outputs:
#   repo_x01/run-x-g06/plots/fig_npr_threshold_sensitivity-v1.pdf
#   repo_x01/run-x-g06/plots/fig_npr_threshold_sensitivity-v1.png
#   repo_x01/run-x-g06/plots/fig_npr_threshold_sensitivity_qc.csv
#   repo_x01/run-x-g06/plots/fig_npr_threshold_sensitivity_metadata.csv
#   repo_x01/run-x-g06/plots/fig_npr_threshold_sensitivity_plot_data.csv
#
# Optional overrides:
#   PROJECT_ROOT, PYTHON_BIN, PY_SCRIPT, INPUT_CSV, OUTPUT_DIR, OUTPUT_PREFIX,
#   PRIMARY_THRESHOLD, WIDTH_INCHES, HEIGHT_INCHES, DPI, LOG_DIR, LOG_FILE

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RUN_PREFIX="run-x-g06"
RUN_NAME="plot-npr-threshold-sensitivity"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}-${RUN_NAME}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/plot_npr_threshold_sensitivity.py}"
INPUT_CSV="${INPUT_CSV:-repo_x01/run-x-g06/dynamic_panel_gmm_npr_threshold_primary_summary.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g06/plots}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-fig_npr_threshold_sensitivity-v1}"
PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.571637}"
WIDTH_INCHES="${WIDTH_INCHES:-3.35}"
HEIGHT_INCHES="${HEIGHT_INCHES:-2.35}"
DPI="${DPI:-300}"

LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-${RUN_TS}.log}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

exec > >(tee "${LOG_FILE}") 2>&1

printf '%s\n' "============================================================"
printf '%-32s %s\n' "${RUN_PREFIX}-${IMPLEMENTATION_VERSION}:" "NPR threshold-sensitivity paper figure"
printf '%-32s %s\n' "Started:" "$(date)"
printf '%-32s %s\n' "Project root:" "${PROJECT_ROOT}"
printf '%-32s %s\n' "Python:" "$(${PYTHON_BIN} --version 2>&1)"
printf '%-32s %s\n' "Python script:" "${PY_SCRIPT}"
printf '%-32s %s\n' "Input summary:" "${INPUT_CSV}"
printf '%-32s %s\n' "Output directory:" "${OUTPUT_DIR}"
printf '%-32s %s\n' "Output prefix:" "${OUTPUT_PREFIX}"
printf '%-32s %s\n' "Primary threshold:" "${PRIMARY_THRESHOLD}"
printf '%-32s %s\n' "Figure size:" "${WIDTH_INCHES} x ${HEIGHT_INCHES} inches"
printf '%-32s %s\n' "DPI:" "${DPI}"
printf '%-32s %s\n' "Log file:" "${LOG_FILE}"
printf '%s\n' "============================================================"

echo
echo "** Step 1: Validate inputs"
echo "------------------------------------------------------------"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python plotting script not found: ${PY_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${INPUT_CSV}" ]]; then
  echo "ERROR: run-x-g06 primary-summary CSV not found: ${INPUT_CSV}" >&2
  exit 1
fi

printf '%-32s %s\n' "Python script:" "OK"
printf '%-32s %s\n' "Input CSV:" "OK"

echo
echo "** Step 2: Compile plotting program"
echo "------------------------------------------------------------"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

echo
echo "** Step 3: Generate publication figure"
echo "------------------------------------------------------------"
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --input-csv "${INPUT_CSV}" \
  --output-dir "${OUTPUT_DIR}" \
  --output-prefix "${OUTPUT_PREFIX}" \
  --primary-threshold "${PRIMARY_THRESHOLD}" \
  --width-inches "${WIDTH_INCHES}" \
  --height-inches "${HEIGHT_INCHES}" \
  --dpi "${DPI}"

PDF_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}.pdf"
PNG_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}.png"
QC_FILE="${OUTPUT_DIR}/fig_npr_threshold_sensitivity_qc.csv"
METADATA_FILE="${OUTPUT_DIR}/fig_npr_threshold_sensitivity_metadata.csv"
PLOT_DATA_FILE="${OUTPUT_DIR}/fig_npr_threshold_sensitivity_plot_data.csv"

echo
echo "** Step 4: Verify outputs"
echo "------------------------------------------------------------"
for file in \
  "${PDF_FILE}" \
  "${PNG_FILE}" \
  "${QC_FILE}" \
  "${METADATA_FILE}" \
  "${PLOT_DATA_FILE}"; do
  if [[ ! -s "${file}" ]]; then
    echo "ERROR: Expected output is missing or empty: ${file}" >&2
    exit 1
  fi
  echo "OK: ${file}"
done

echo
printf '%s\n' "============================================================"
printf '%-32s %s\n' "${RUN_PREFIX}-${IMPLEMENTATION_VERSION}:" "SUCCESS"
printf '%-32s %s\n' "Finished:" "$(date)"
printf '%-32s %s\n' "Primary threshold:" "${PRIMARY_THRESHOLD}"
printf '%-32s %s\n' "PDF:" "${PDF_FILE}"
printf '%-32s %s\n' "PNG:" "${PNG_FILE}"
printf '%-32s %s\n' "QC:" "${QC_FILE}"
printf '%-32s %s\n' "Metadata:" "${METADATA_FILE}"
printf '%-32s %s\n' "Plot data:" "${PLOT_DATA_FILE}"
printf '%-32s %s\n' "Log file:" "${LOG_FILE}"
printf '%s\n' "============================================================"
