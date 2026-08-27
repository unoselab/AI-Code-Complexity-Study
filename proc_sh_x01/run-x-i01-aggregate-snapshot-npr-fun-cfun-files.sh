#!/usr/bin/env bash
# =============================================================================
# run-x-i01-aggregate-snapshot-npr-fun-cfun-files-v1.sh
#
# Delivery filename: versioned for experiment provenance.
# Canonical server runtime filename:
#   proc_sh_x01/run-x-i01-aggregate-snapshot-npr-fun-cfun-files.sh
#
# Purpose
# -------
# Build a combined procedure-body NPR measurement by recomputing FUN + C_FUN
# file-level sufficient statistics from finalized A12 and A15 outputs.
#
# Reference logic
# ---------------
# This wrapper reuses the execution/provenance structure of the finalized A12
# aggregation wrapper but is standalone: it never calls A12, A15, or any older
# shell wrapper. A12/A15 CSV artifacts are immutable inputs.
#
# Inputs
# ------
# From detect_code_gpt/output/snapshot_npr/run-x-a12:
#   python_fun_file_npr_scores.csv
#   python_fun_repo_month_file_npr_scores.csv
#   summary.json
#
# From detect_code_gpt/output/snapshot_npr/run-x-a15:
#   python_cfun_file_npr_scores.csv
#   python_cfun_repo_month_file_npr_scores.csv
#   summary.json
#
# Outputs
# -------
# Under repo_x01/run-x-i01:
#   python_fun_cfun_file_npr_scores.csv
#   python_fun_cfun_repo_month_file_npr_scores.csv
#   python_fun_cfun_aggregation_checks.csv
#   summary.json
#   metadata.json
#
# Scientific contract
# -------------------
# * FUN = A12 primary regular-function bodies.
# * C_FUN = A15 primary class-method bodies.
# * Combined NPR is recomputed with scored space-by-token counts as weights.
# * Weighted original/perturbed components are recomputed and pooled NPR is
#   retained separately.
# * If only one category has finite NPR, combined NPR equals that category.
# * If neither category has finite NPR, combined NPR is blank, never zero.
# * Cross-category SHA values are not deduplicated because the unit of the
#   combined measurement is the semantic procedure-body occurrence.
# * No threshold/classification is applied in I01.
# * No SonarQube or quality outcome is consumed in I01.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DEFAULT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="${PROJECT_ROOT_OVERRIDE:-${PROJECT_ROOT_DEFAULT}}"
cd "${PROJECT_ROOT}"

RUN_VERSION="run-x-i01-v1"
PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/aggregate_snapshot_npr_fun_cfun_files.py}"
DETECT_CODE_GPT_ROOT="${DETECT_CODE_GPT_ROOT:-${PROJECT_ROOT}/../../detect_code_gpt}"

A12_ROOT="${A12_ROOT:-${DETECT_CODE_GPT_ROOT}/output/snapshot_npr/run-x-a12}"
A15_ROOT="${A15_ROOT:-${DETECT_CODE_GPT_ROOT}/output/snapshot_npr/run-x-a15}"

A12_FILE="${A12_FILE:-${A12_ROOT}/python_fun_file_npr_scores.csv}"
A12_REPO_MONTH_FILE="${A12_REPO_MONTH_FILE:-${A12_ROOT}/python_fun_repo_month_file_npr_scores.csv}"
A12_SUMMARY="${A12_SUMMARY:-${A12_ROOT}/summary.json}"

A15_FILE="${A15_FILE:-${A15_ROOT}/python_cfun_file_npr_scores.csv}"
A15_REPO_MONTH_FILE="${A15_REPO_MONTH_FILE:-${A15_ROOT}/python_cfun_repo_month_file_npr_scores.csv}"
A15_SUMMARY="${A15_SUMMARY:-${A15_ROOT}/summary.json}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i01}"
LOG_DIR="${LOG_DIR:-logs}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-x-i01-v1-aggregate-snapshot-npr-fun-cfun-files-${TIMESTAMP}.log}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

EXPECTED_FILE_ROWS="${EXPECTED_FILE_ROWS:-494592}"
EXPECTED_REPO_MONTH_FILE_ROWS="${EXPECTED_REPO_MONTH_FILE_ROWS:-510297}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_REPO_MONTHS="${EXPECTED_REPO_MONTHS:-1954}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"

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
echo "${RUN_VERSION}: aggregate FUN + C_FUN procedure-body file NPR"
echo "Started:                         ${START_DISPLAY}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "A12 FUN root:                    ${A12_ROOT}"
echo "A15 C_FUN root:                  ${A15_ROOT}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Combined metric:                 file_npr_fun_cfun_space_by_token_weighted"
echo "Combination weighting:           scored space-by-token counts"
echo "Threshold application:           none"
echo "Quality/SonarQube input:         none"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"
echo

echo "** Step 1: Run I01 structural self-test"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
echo
"${PYTHON_BIN}" "${PY_SCRIPT}" --self-test

echo
echo "** Step 2: Compile I01 Python program"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo
  echo "SELF_TEST_ONLY=1: stopping after self-test and compile."
  exit 0
fi

for required_file in \
  "${A12_FILE}" \
  "${A12_REPO_MONTH_FILE}" \
  "${A12_SUMMARY}" \
  "${A15_FILE}" \
  "${A15_REPO_MONTH_FILE}" \
  "${A15_SUMMARY}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required input not found: ${required_file}" >&2
    exit 2
  fi
done

echo
echo "** Step 3: Freeze A12/A15 input provenance"
echo "----------------------------------------------------------------------------"
A12_FILE_SHA256="$(sha256sum "${A12_FILE}" | awk '{print $1}')"
A12_REPO_MONTH_SHA256="$(sha256sum "${A12_REPO_MONTH_FILE}" | awk '{print $1}')"
A12_SUMMARY_SHA256="$(sha256sum "${A12_SUMMARY}" | awk '{print $1}')"
A15_FILE_SHA256="$(sha256sum "${A15_FILE}" | awk '{print $1}')"
A15_REPO_MONTH_SHA256="$(sha256sum "${A15_REPO_MONTH_FILE}" | awk '{print $1}')"
A15_SUMMARY_SHA256="$(sha256sum "${A15_SUMMARY}" | awk '{print $1}')"

echo "A12 snapshot/file SHA256:        ${A12_FILE_SHA256}"
echo "A12 repo-month/file SHA256:      ${A12_REPO_MONTH_SHA256}"
echo "A12 summary SHA256:              ${A12_SUMMARY_SHA256}"
echo "A15 snapshot/file SHA256:        ${A15_FILE_SHA256}"
echo "A15 repo-month/file SHA256:      ${A15_REPO_MONTH_SHA256}"
echo "A15 summary SHA256:              ${A15_SUMMARY_SHA256}"

echo
echo "** Step 4: Recompute combined FUN + C_FUN NPR"
echo "----------------------------------------------------------------------------"
CMD=(
  "${PYTHON_BIN}" "${PY_SCRIPT}"
  --a12-file "${A12_FILE}"
  --a12-repo-month-file "${A12_REPO_MONTH_FILE}"
  --a12-summary "${A12_SUMMARY}"
  --a15-file "${A15_FILE}"
  --a15-repo-month-file "${A15_REPO_MONTH_FILE}"
  --a15-summary "${A15_SUMMARY}"
  --output-dir "${OUTPUT_DIR}"
  --expected-file-rows "${EXPECTED_FILE_ROWS}"
  --expected-repo-month-file-rows "${EXPECTED_REPO_MONTH_FILE_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-repo-months "${EXPECTED_REPO_MONTHS}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  CMD+=(--strict-expected-counts)
fi
printf 'Command:'
printf ' %q' "${CMD[@]}"
echo
"${CMD[@]}"

echo
echo "** Step 5: Verify I01 output artifacts"
echo "----------------------------------------------------------------------------"
OUTPUTS=(
  "${OUTPUT_DIR}/python_fun_cfun_file_npr_scores.csv"
  "${OUTPUT_DIR}/python_fun_cfun_repo_month_file_npr_scores.csv"
  "${OUTPUT_DIR}/python_fun_cfun_aggregation_checks.csv"
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

FILE_LINES="$(wc -l < "${OUTPUT_DIR}/python_fun_cfun_file_npr_scores.csv")"
REPO_MONTH_LINES="$(wc -l < "${OUTPUT_DIR}/python_fun_cfun_repo_month_file_npr_scores.csv")"
CHECK_LINES="$(wc -l < "${OUTPUT_DIR}/python_fun_cfun_aggregation_checks.csv")"
EXPECTED_FILE_LINES="$((EXPECTED_FILE_ROWS + 1))"
EXPECTED_REPO_MONTH_LINES="$((EXPECTED_REPO_MONTH_FILE_ROWS + 1))"

if [[ "${FILE_LINES}" -ne "${EXPECTED_FILE_LINES}" ]]; then
  echo "ERROR: snapshot/file line count ${FILE_LINES} != ${EXPECTED_FILE_LINES}" >&2
  exit 2
fi
if [[ "${REPO_MONTH_LINES}" -ne "${EXPECTED_REPO_MONTH_LINES}" ]]; then
  echo "ERROR: repo-month/file line count ${REPO_MONTH_LINES} != ${EXPECTED_REPO_MONTH_LINES}" >&2
  exit 2
fi

echo "Snapshot/file lines:             ${FILE_LINES} including header"
echo "Repo-month/file lines:           ${REPO_MONTH_LINES} including header"
echo "QC check lines:                  ${CHECK_LINES} including header"
echo

echo "I01 QC checks:"
cat "${OUTPUT_DIR}/python_fun_cfun_aggregation_checks.csv"
echo

echo "I01 summary:"
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
echo "Snapshot/file combined NPR:      ${OUTPUT_DIR}/python_fun_cfun_file_npr_scores.csv"
echo "Repo-month/file combined NPR:    ${OUTPUT_DIR}/python_fun_cfun_repo_month_file_npr_scores.csv"
echo "QC checks:                       ${OUTPUT_DIR}/python_fun_cfun_aggregation_checks.csv"
echo "Summary:                         ${OUTPUT_DIR}/summary.json"
echo "Metadata:                        ${OUTPUT_DIR}/metadata.json"
echo "Log file:                        ${LOG_FILE}"
echo "Next:                            I02 audit/freeze combined FUN+C_FUN NPR threshold grid"
echo "============================================================================"
