#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-f07 v1: plot NPR-vs-ML AGC detector-mapping Sankey
# ============================================================
#
# Purpose
# -------
# Render the validated run-x-f06 detector mapping as a publication-ready
# Sankey-style PDF and PNG. Flow width represents repo-month historical
# Python file occurrences selected by at least one frozen AGC detector.
#
# Inputs
# ------
# run-x-f06 Sankey edges:
#   Both, NPR-only, and ML-only file-occurrence flows.
# run-x-f06 summary:
#   Union support and Jaccard overlap metric.
# run-x-f06 QC:
#   Must contain no hard-QC failures before plotting.
# run-x-f06 metadata:
#   Frozen detector-rule provenance.
#
# Outputs
# -------
# fig_agc_detector_mapping_sankey-v1.pdf
#   Vector figure for the paper.
# fig_agc_detector_mapping_sankey-v1.png
#   300-dpi raster preview.
# agc_detector_mapping_plot_qc.csv
#   Plot-input and output-file QC.
# agc_detector_mapping_plot_metadata.csv
#   Figure provenance and rendering settings.
#
# This wrapper is standalone. It follows the run-x-f06 wrapper structure but
# does not call any existing experiment shell script.
# ============================================================

RUN_PREFIX="run-x-f07"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/plot_agc_detector_mapping_sankey.py}"

F06_DIR="${F06_DIR:-repo_x01/run-x-f06-detector-mapping-figure}"
EDGES_FILE="${EDGES_FILE:-${F06_DIR}/agc_detector_mapping_sankey_edges.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${F06_DIR}/agc_detector_mapping_summary.csv}"
QC_FILE="${QC_FILE:-${F06_DIR}/agc_detector_mapping_qc.csv}"
METADATA_FILE="${METADATA_FILE:-${F06_DIR}/agc_detector_mapping_metadata.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-f07-detector-mapping-figure}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-fig_agc_detector_mapping_sankey-v1}"
LOG_DIR="${LOG_DIR:-logs}"

WIDTH_INCHES="${WIDTH_INCHES:-3.35}"
HEIGHT_INCHES="${HEIGHT_INCHES:-2.70}"
DPI="${DPI:-300}"

EXPECTED_UNION="${EXPECTED_UNION:-53445}"
EXPECTED_BOTH="${EXPECTED_BOTH:-3619}"
EXPECTED_NPR_ONLY="${EXPECTED_NPR_ONLY:-10120}"
EXPECTED_ML_ONLY="${EXPECTED_ML_ONLY:-39706}"
EXPECTED_JACCARD="${EXPECTED_JACCARD:-0.06771447282252784}"

PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-plot-agc-detector-mapping-sankey-${TIMESTAMP}.log"

for required_file in \
  "${PY_SCRIPT}" \
  "${EDGES_FILE}" \
  "${SUMMARY_FILE}" \
  "${QC_FILE}" \
  "${METADATA_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PY_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
EDGES_SHA256="$(sha256sum "${EDGES_FILE}" | awk '{print $1}')"
SUMMARY_SHA256="$(sha256sum "${SUMMARY_FILE}" | awk '{print $1}')"
QC_SHA256="$(sha256sum "${QC_FILE}" | awk '{print $1}')"
METADATA_SHA256="$(sha256sum "${METADATA_FILE}" | awk '{print $1}')"

cat <<EOF
============================================================
${RUN_LABEL}: plot AGC detector-mapping Sankey
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})
Implementation version:          ${IMPLEMENTATION_VERSION}
Figure type:                     Sankey-style detector mapping
Primary flow unit:               repo-month Python file occurrence
Figure universe:                 NPR selected OR ML selected
Input directory:                 ${F06_DIR}
Edges SHA256:                    ${EDGES_SHA256}
Summary SHA256:                  ${SUMMARY_SHA256}
QC SHA256:                       ${QC_SHA256}
Metadata SHA256:                 ${METADATA_SHA256}
Python script SHA256:            ${PY_SHA256}
Figure size:                     ${WIDTH_INCHES} x ${HEIGHT_INCHES} inches
PNG DPI:                         ${DPI}
Output directory:                ${OUTPUT_DIR}
Output prefix:                   ${OUTPUT_PREFIX}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Validate run-x-f06 inputs and render Sankey\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --edges-file "${EDGES_FILE}" \
  --summary-file "${SUMMARY_FILE}" \
  --qc-file "${QC_FILE}" \
  --metadata-file "${METADATA_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --output-prefix "${OUTPUT_PREFIX}" \
  --width-inches "${WIDTH_INCHES}" \
  --height-inches "${HEIGHT_INCHES}" \
  --dpi "${DPI}" \
  --expected-union "${EXPECTED_UNION}" \
  --expected-both "${EXPECTED_BOTH}" \
  --expected-npr-only "${EXPECTED_NPR_ONLY}" \
  --expected-ml-only "${EXPECTED_ML_ONLY}" \
  --expected-jaccard "${EXPECTED_JACCARD}"

printf '\n** Step 2: Verify figure artifacts and plot QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/${OUTPUT_PREFIX}.pdf"
  "${OUTPUT_DIR}/${OUTPUT_PREFIX}.png"
  "${OUTPUT_DIR}/agc_detector_mapping_plot_qc.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_plot_metadata.csv"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}/agc_detector_mapping_plot_qc.csv" <<'PY'
import csv
import sys

path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
failed = [row for row in rows if row.get("status") == "fail"]
if failed:
    raise SystemExit(f"Plot QC failure in {path}: {failed}")
print("Plot QC: PASS")
PY

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
Figure universe:                 NPR > 1.571637 OR ML > 0.50
Flow unit:                       repo-month Python file occurrence
Both:                            ${EXPECTED_BOTH}
NPR-only:                        ${EXPECTED_NPR_ONLY}
ML-only:                         ${EXPECTED_ML_ONLY}
Union:                           ${EXPECTED_UNION}
Jaccard:                         ${EXPECTED_JACCARD}
PDF:                             ${OUTPUT_DIR}/${OUTPUT_PREFIX}.pdf
PNG:                             ${OUTPUT_DIR}/${OUTPUT_PREFIX}.png
Plot QC:                         PASS
Log file:                        ${LOG_FILE}
============================================================
EOF
