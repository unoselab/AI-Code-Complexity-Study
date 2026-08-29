#!/usr/bin/env bash
# =============================================================================
# run-x-i06-aggregate-ml-fun-cfun-files-v1.sh
#
# Delivery filename: versioned for experiment provenance.
# Canonical server runtime filename:
#   proc_sh_x01/run-x-i06-aggregate-ml-fun-cfun-files.sh
#
# Purpose
# -------
# Build one implementation-level ML AGC-share measurement by combining the
# finalized A04 regular-function file aggregation with the finalized A07
# class-method file aggregation on the same historical Python-file universe.
#
# Reference logic
# ---------------
# This wrapper was copied from the finalized I01 aggregation wrapper and then
# adapted for the ML aggregation. It is standalone and never calls I01, A04,
# A07, or any older shell wrapper. A04/A07 CSV and summary artifacts are
# immutable inputs; only the new I06 Python analysis program is executed.
#
# Inputs
# ------
# From ai_detector/src/app/data_did_agc_analysis/run-x-a04:
#   python_ml_fun_file_scores.csv
#   summary.json
#
# From ai_detector/src/app/data_did_agc_analysis/run-x-a07:
#   python_ml_cfun_file_scores.csv
#   summary.json
#
# Outputs
# -------
# Under repo_x01/run-x-i06:
#   python_ml_fun_cfun_file_scores.csv
#   python_ml_fun_cfun_selected_files_primary.csv
#   python_ml_fun_cfun_threshold_support.csv
#   python_ml_fun_cfun_aggregation_checks.csv
#   summary.json
#   metadata.json
#
# Scientific contract
# -------------------
# * FUN = finalized A04 regular-function file ML aggregation.
# * Class methods = finalized A07 class-method file ML aggregation.
# * Combined share is recomputed from AGC body-token numerator and total
#   body-token denominator; A04/A07 file shares are never averaged directly.
# * Combined primary rule is strict share > 0.50; exact ties are not selected.
# * If only one category is present, combined share equals that category share.
# * If neither category is present, the file remains blank/unclassified.
# * No cross-category source-SHA deduplication is performed because the units
#   are distinct semantic procedure occurrences.
# * No ML inference, SonarQube, quality outcome, or DiD estimation is run here.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DEFAULT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="${PROJECT_ROOT_OVERRIDE:-${PROJECT_ROOT_DEFAULT}}"
cd "${PROJECT_ROOT}"

RUN_VERSION="run-x-i06-v1"
PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/aggregate_ml_fun_cfun_files.py}"
AI_DETECTOR_ROOT="${AI_DETECTOR_ROOT:-${PROJECT_ROOT}/../../ai_detector}"

A04_ROOT="${A04_ROOT:-${AI_DETECTOR_ROOT}/src/app/data_did_agc_analysis/run-x-a04}"
A07_ROOT="${A07_ROOT:-${AI_DETECTOR_ROOT}/src/app/data_did_agc_analysis/run-x-a07}"

A04_FILE="${A04_FILE:-${A04_ROOT}/python_ml_fun_file_scores.csv}"
A04_SUMMARY="${A04_SUMMARY:-${A04_ROOT}/summary.json}"
A07_FILE="${A07_FILE:-${A07_ROOT}/python_ml_cfun_file_scores.csv}"
A07_SUMMARY="${A07_SUMMARY:-${A07_ROOT}/summary.json}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i06}"
LOG_DIR="${LOG_DIR:-logs}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-x-i06-v1-aggregate-ml-fun-cfun-files-${TIMESTAMP}.log}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
EXPECTED_FILE_ROWS="${EXPECTED_FILE_ROWS:-494592}"

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" >&2
  exit 2
fi

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"

# Mirror all console output into the immutable run log.
exec > >(tee "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
START_DISPLAY="$(date)"

echo "============================================================================"
echo "${RUN_VERSION}: aggregate FUN + class-method ML file measurements"
echo "Started:                         ${START_DISPLAY}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "A04 FUN ML root:                 ${A04_ROOT}"
echo "A07 class-method ML root:        ${A07_ROOT}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Combined metric:                 file_ml_fun_cfun_agc_share_space_by_token_weighted"
echo "Combination weighting:           procedure body literal-space token counts"
echo "Primary threshold:               > 0.50 (strict)"
echo "ML inference:                     none"
echo "Quality/SonarQube input:         none"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"
echo

echo "** Step 1: Run I06 structural self-test"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
echo
"${PYTHON_BIN}" "${PY_SCRIPT}" --self-test

echo
echo "** Step 2: Compile I06 Python program"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo
  echo "SELF_TEST_ONLY=1: stopping after self-test and compile."
  exit 0
fi

for required_file in \
  "${A04_FILE}" \
  "${A04_SUMMARY}" \
  "${A07_FILE}" \
  "${A07_SUMMARY}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required input not found: ${required_file}" >&2
    exit 2
  fi
done

echo
echo "** Step 3: Freeze A04/A07 input provenance"
echo "----------------------------------------------------------------------------"
A04_FILE_SHA256="$(sha256sum "${A04_FILE}" | awk '{print $1}')"
A04_SUMMARY_SHA256="$(sha256sum "${A04_SUMMARY}" | awk '{print $1}')"
A07_FILE_SHA256="$(sha256sum "${A07_FILE}" | awk '{print $1}')"
A07_SUMMARY_SHA256="$(sha256sum "${A07_SUMMARY}" | awk '{print $1}')"

echo "A04 file-score SHA256:            ${A04_FILE_SHA256}"
echo "A04 summary SHA256:               ${A04_SUMMARY_SHA256}"
echo "A07 file-score SHA256:            ${A07_FILE_SHA256}"
echo "A07 summary SHA256:               ${A07_SUMMARY_SHA256}"

echo
echo "** Step 4: Recompute combined FUN + class-method ML AGC share"
echo "----------------------------------------------------------------------------"
CMD=(
  "${PYTHON_BIN}" "${PY_SCRIPT}"
  --a04-file "${A04_FILE}"
  --a04-summary "${A04_SUMMARY}"
  --a07-file "${A07_FILE}"
  --a07-summary "${A07_SUMMARY}"
  --output-dir "${OUTPUT_DIR}"
  --expected-file-rows "${EXPECTED_FILE_ROWS}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  CMD+=(--strict-expected-counts)
fi
printf 'Command:'
printf ' %q' "${CMD[@]}"
echo
"${CMD[@]}"

echo
echo "** Step 5: Verify I06 output artifacts"
echo "----------------------------------------------------------------------------"
OUTPUTS=(
  "${OUTPUT_DIR}/python_ml_fun_cfun_file_scores.csv"
  "${OUTPUT_DIR}/python_ml_fun_cfun_selected_files_primary.csv"
  "${OUTPUT_DIR}/python_ml_fun_cfun_threshold_support.csv"
  "${OUTPUT_DIR}/python_ml_fun_cfun_aggregation_checks.csv"
  "${OUTPUT_DIR}/summary.json"
  "${OUTPUT_DIR}/metadata.json"
)
for output_file in "${OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" >&2
    exit 2
  fi
  echo "OK: ${output_file}"
done

FILE_LINES="$(wc -l < "${OUTPUT_DIR}/python_ml_fun_cfun_file_scores.csv")"
SELECTED_LINES="$(wc -l < "${OUTPUT_DIR}/python_ml_fun_cfun_selected_files_primary.csv")"
CHECK_LINES="$(wc -l < "${OUTPUT_DIR}/python_ml_fun_cfun_aggregation_checks.csv")"
EXPECTED_FILE_LINES="$((EXPECTED_FILE_ROWS + 1))"

if [[ "${FILE_LINES}" -ne "${EXPECTED_FILE_LINES}" ]]; then
  echo "ERROR: combined file-score line count ${FILE_LINES} != ${EXPECTED_FILE_LINES}" >&2
  exit 2
fi

echo "Combined file-score lines:       ${FILE_LINES} including header"
echo "Primary-selected lines:          ${SELECTED_LINES} including header"
echo "QC check lines:                  ${CHECK_LINES} including header"
echo

echo "I06 QC checks:"
cat "${OUTPUT_DIR}/python_ml_fun_cfun_aggregation_checks.csv"
echo

echo "I06 threshold support:"
cat "${OUTPUT_DIR}/python_ml_fun_cfun_threshold_support.csv"
echo

echo "I06 summary:"
cat "${OUTPUT_DIR}/summary.json"

END_EPOCH="$(date +%s)"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
HOURS="$((ELAPSED_SECONDS / 3600))"
MINUTES="$(((ELAPSED_SECONDS % 3600) / 60))"
SECONDS="$((ELAPSED_SECONDS % 60))"
printf -v ELAPSED "%02d:%02d:%02d" "${HOURS}" "${MINUTES}" "${SECONDS}"

echo
echo "============================================================================"
echo "${RUN_VERSION} completed successfully."
echo "Completed:                       $(date)"
echo "Elapsed:                         ${ELAPSED}"
echo "Combined ML file scores:         ${OUTPUT_DIR}/python_ml_fun_cfun_file_scores.csv"
echo "Primary-selected files:          ${OUTPUT_DIR}/python_ml_fun_cfun_selected_files_primary.csv"
echo "Threshold support:               ${OUTPUT_DIR}/python_ml_fun_cfun_threshold_support.csv"
echo "QC checks:                       ${OUTPUT_DIR}/python_ml_fun_cfun_aggregation_checks.csv"
echo "Summary:                         ${OUTPUT_DIR}/summary.json"
echo "Metadata:                        ${OUTPUT_DIR}/metadata.json"
echo "Log file:                        ${LOG_FILE}"
echo "Next:                            build combined ML quality-burden analysis input"
echo "============================================================================"
