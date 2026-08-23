#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-g07 v1: plot NPR threshold-sensitivity GMM estimates
# ============================================================
#
# Purpose:
#   Render the run-x-g06 NPR threshold-sensitivity coefficients as a
#   publication-ready point/line plot with 95% confidence intervals.
#
# Inputs:
#   - G06 one-row-per-threshold primary summary
#   - G06 QC and metadata for upstream provenance validation
#
# Outputs:
#   - PDF and PNG figure
#   - Exact plot-data CSV
#   - Plot QC and metadata CSVs
#
# Important:
#   This wrapper is self-contained. It reuses the operational structure of the
#   prior run-x-g06 wrapper but does not call any prior shell wrapper or rerun
#   GMM estimation. G07 reads only finalized G06 outputs.
#
# Run:
#   bash proc_sh_x01/run-x-g07-plot-npr-threshold-sensitivity.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-g07"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-plot-npr-threshold-sensitivity-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/plot_npr_threshold_sensitivity.py}"
G06_SUMMARY="${G06_SUMMARY:-repo_x01/run-x-g06/dynamic_panel_gmm_npr_threshold_primary_summary.csv}"
G06_QC="${G06_QC:-repo_x01/run-x-g06/dynamic_panel_gmm_npr_threshold_qc.csv}"
G06_METADATA="${G06_METADATA:-repo_x01/run-x-g06/dynamic_panel_gmm_npr_threshold_run_metadata.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g07}"

PRIMARY_THRESHOLD="${PRIMARY_THRESHOLD:-1.571637}"
EXPECTED_THRESHOLDS="${EXPECTED_THRESHOLDS:-21}"
DPI="${DPI:-300}"

EXPECTED_G06_SUMMARY_SHA256="${EXPECTED_G06_SUMMARY_SHA256:-4eb528cddd99cfd4165d89d698c00260443f03076e3eaec053803e3c2478511a}"
EXPECTED_G06_QC_SHA256="${EXPECTED_G06_QC_SHA256:-0ec654ac61234329561897c2b721dddf9ca3b8f42f3521f7cee0eab14d73d015}"
EXPECTED_G06_METADATA_SHA256="${EXPECTED_G06_METADATA_SHA256:-6b03d0c83295a7494c7dd7957dfe6bbfe704011d03208c1dab66e5b33dcdf013}"

for required_command in "${PYTHON_BIN}" sha256sum; do
  if ! command -v "${required_command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${required_command}" >&2
    exit 1
  fi
done

for required_file in "${PYTHON_SCRIPT}" "${G06_SUMMARY}" "${G06_QC}" "${G06_METADATA}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

# Check plotting dependencies before creating or overwriting figure outputs.
"${PYTHON_BIN}" -c 'import matplotlib, numpy, pandas' >/dev/null
"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

G06_SUMMARY_SHA256="$(sha256sum "${G06_SUMMARY}" | awk '{print $1}')"
G06_QC_SHA256="$(sha256sum "${G06_QC}" | awk '{print $1}')"
G06_METADATA_SHA256="$(sha256sum "${G06_METADATA}" | awk '{print $1}')"

if [[ "${G06_SUMMARY_SHA256}" != "${EXPECTED_G06_SUMMARY_SHA256}" ]]; then
  echo "ERROR: G06 summary SHA256 mismatch." >&2
  echo "Expected: ${EXPECTED_G06_SUMMARY_SHA256}" >&2
  echo "Observed: ${G06_SUMMARY_SHA256}" >&2
  exit 1
fi
if [[ "${G06_QC_SHA256}" != "${EXPECTED_G06_QC_SHA256}" ]]; then
  echo "ERROR: G06 QC SHA256 mismatch." >&2
  echo "Expected: ${EXPECTED_G06_QC_SHA256}" >&2
  echo "Observed: ${G06_QC_SHA256}" >&2
  exit 1
fi
if [[ "${G06_METADATA_SHA256}" != "${EXPECTED_G06_METADATA_SHA256}" ]]; then
  echo "ERROR: G06 metadata SHA256 mismatch." >&2
  echo "Expected: ${EXPECTED_G06_METADATA_SHA256}" >&2
  echo "Observed: ${G06_METADATA_SHA256}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PYTHON_SCRIPT_SHA256="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: plot NPR threshold-sensitivity GMM estimates"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Experiment role:                 plotting only"
  echo "Upstream experiment:             run-x-g06"
  echo "G06 summary:                     ${G06_SUMMARY}"
  echo "G06 summary SHA256:              ${G06_SUMMARY_SHA256}"
  echo "G06 QC SHA256:                   ${G06_QC_SHA256}"
  echo "G06 metadata SHA256:             ${G06_METADATA_SHA256}"
  echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
  echo "Expected thresholds:             ${EXPECTED_THRESHOLDS}"
  echo "Figure design:                   point + line + 95% CI"
  echo "Horizontal reference:            y = 0"
  echo "Vertical reference:              tau = ${PRIMARY_THRESHOLD}"
  echo "Primary point:                   emphasized filled marker"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Python script SHA256:            ${PYTHON_SCRIPT_SHA256}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}" "${PYTHON_SCRIPT}"
  --summary-file "${G06_SUMMARY}"
  --qc-file "${G06_QC}"
  --metadata-file "${G06_METADATA}"
  --output-dir "${OUTPUT_DIR}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --expected-thresholds "${EXPECTED_THRESHOLDS}"
  --dpi "${DPI}"
)

{
  echo
  echo "** Step 1: Render NPR threshold-sensitivity figure"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/fig_npr_threshold_sensitivity-${IMPLEMENTATION_VERSION}.pdf"
  "${OUTPUT_DIR}/fig_npr_threshold_sensitivity-${IMPLEMENTATION_VERSION}.png"
  "${OUTPUT_DIR}/plot_npr_threshold_sensitivity_data.csv"
  "${OUTPUT_DIR}/plot_npr_threshold_sensitivity_qc.csv"
  "${OUTPUT_DIR}/plot_npr_threshold_sensitivity_metadata.csv"
)

{
  echo
  echo "** Step 2: Verify G07 artifacts and hard QC"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

QC_FILE="${OUTPUT_DIR}/plot_npr_threshold_sensitivity_qc.csv"
if grep -q ',fail$' "${QC_FILE}" || grep -q ',fail,' "${QC_FILE}"; then
  echo "ERROR: G07 plot QC contains one or more hard failures." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

PLOT_ROWS="$(${PYTHON_BIN} -c 'import pandas as pd,sys; print(len(pd.read_csv(sys.argv[1])))' "${OUTPUT_DIR}/plot_npr_threshold_sensitivity_data.csv")"
if [[ "${PLOT_ROWS}" != "${EXPECTED_THRESHOLDS}" ]]; then
  echo "ERROR: expected ${EXPECTED_THRESHOLDS} plot-data rows; observed ${PLOT_ROWS}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo "G07 hard QC:                     PASS"
  echo "Plot-data rows:                  ${PLOT_ROWS}"
  echo "============================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "PDF:                             ${OUTPUT_DIR}/fig_npr_threshold_sensitivity-${IMPLEMENTATION_VERSION}.pdf"
  echo "PNG:                             ${OUTPUT_DIR}/fig_npr_threshold_sensitivity-${IMPLEMENTATION_VERSION}.png"
  echo "Plot data:                       ${OUTPUT_DIR}/plot_npr_threshold_sensitivity_data.csv"
  echo "QC:                              ${QC_FILE}"
  echo "Metadata:                        ${OUTPUT_DIR}/plot_npr_threshold_sensitivity_metadata.csv"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
