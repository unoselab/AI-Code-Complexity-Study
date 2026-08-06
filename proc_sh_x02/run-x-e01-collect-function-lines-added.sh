#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-e01 v1: Collect lines added inside Python function bodies
# ============================================================
#
# Purpose:
#   Reproduce the monthly Git flow semantics used by run-x-a/run-x-b and
#   decompose repository-level lines_added into Python-specific categories.
#
# Primary metric:
#   lines_added_py_function_body
#
# Definition:
#   Sum, over all commits assigned to a repository-month, of physical lines
#   added inside post-change Python function implementation bodies.
#
# Design decisions:
#   - Input sample is the final 1,954-row run-x-a05 Model A panel.
#   - Commit month uses committed time in America/Chicago by default.
#   - Merge commits are compared with their first parent only.
#   - Root-commit additions are excluded, matching the original A/B logic.
#   - Module functions, methods, async functions, and nested functions are
#     included. An added line is attributed to the innermost function.
#   - Decorators, function headers, and leading function docstrings are
#     excluded from the primary metric.
#   - Comment-only and blank physical lines inside function bodies are counted.
#   - One-line functions count as one body line when the line is added.
#   - Code state may be carried forward, but monthly activity is never carried
#     forward. A no-commit month has a primary value of zero.
#   - The 100-200 token category is intentionally not used in run-x-e01.
#
# D01 reuse:
#   Safe exact-blob boundaries can be reused from D01/D01a/D01b metadata when
#   the body-store root exists and no nested named definition was recorded.
#   D01 inputs are indexed once in a persistent SQLite file. Unsafe or unseen
#   blobs are parsed with AST_PYTHON_BIN and cached by Git blob OID.
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#
# Main outputs:
#   repo_x02/run-x-e01/lines_added_py_function_body_repo_month.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_commit.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_file.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_function.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_issues.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_reconciliation.csv
#   repo_x02/run-x-e01/lines_added_py_function_body_qc.csv
#   repo_x02/tmp/run-x-e01/lines_added_py_function_body_summary.csv
#
# Full run:
#   bash proc_sh_x02/run-x-e01-collect-function-lines-added.sh
#
# One-repository smoke test:
#   LIMIT_REPOS=1 STRICT_EXPECTED_COUNTS=0 \
#     bash proc_sh_x02/run-x-e01-collect-function-lines-added.sh
#
# Resume:
#   Re-run the same command. Completed repositories are skipped when their
#   input fingerprint and implementation version match. Set ANALYSIS_AGAIN=1
#   to rebuild selected repositories.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   AST_PYTHON_BIN=/path/to/python3.12
#   BASE_PANEL_FILE=/path/to/panel.csv
#   ANALYSIS_TIMEZONE=America/Chicago
#   REUSE_D01_BOUNDARIES=1
#   D01_FUNCTION_DETAILS_FILES=file1.csv:file2.csv:file3.csv
#   D01_BODY_STORE_ROOT=/absolute/path/to/py-fun-body
#   BOUNDARY_CACHE_ROOT=/absolute/path/to/py-fun-line-added
#   START_REPO_ORDER=1
#   LIMIT_REPOS=0
#   DATASET_SOURCE=treatment|control|empty
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   DRY_RUN=0
#   STRICT_EXPECTED_COUNTS=1
#   SKIP_SELF_TEST=0
#   GIT_TIMEOUT_SECONDS=300
#   AST_WORKER_TIMEOUT_SECONDS=300
#   PROGRESS_EVERY_REPOS=5
#   PROGRESS_EVERY_COMMITS=250
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-e01"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-collect-function-lines-added-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
AST_PYTHON_BIN="${AST_PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x02/collect_function_lines_added.py}"
BASE_PANEL_FILE="${BASE_PANEL_FILE:-repo_x01/run-x-a05/velocity_did_panel_model_a.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
CACHE_DIR="${CACHE_DIR:-${TMP_OUTPUT_DIR}/repo-cache}"

REPO_MONTH_OUTPUT="${REPO_MONTH_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_repo_month.csv}"
COMMIT_OUTPUT="${COMMIT_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_commit.csv}"
FILE_OUTPUT="${FILE_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_file.csv}"
FUNCTION_OUTPUT="${FUNCTION_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_function.csv}"
ISSUES_OUTPUT="${ISSUES_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_issues.csv}"
RECONCILIATION_OUTPUT="${RECONCILIATION_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_reconciliation.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/lines_added_py_function_body_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/lines_added_py_function_body_summary.csv}"

D01_BODY_STORE_ROOT="${D01_BODY_STORE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/py-fun-body}"
BOUNDARY_CACHE_ROOT="${BOUNDARY_CACHE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/py-fun-line-added}"
D01_INDEX_DB="${D01_INDEX_DB:-${BOUNDARY_CACHE_ROOT}/d01-boundaries-v1.sqlite}"
D01_FUNCTION_DETAILS_FILES="${D01_FUNCTION_DETAILS_FILES:-repo_x02/run-x-d01/model_c_token_py_function_details.csv:repo_x02/run-x-d01a/model_c_token_py_recovered_function_details.csv:repo_x02/run-x-d01b/model_c_token_py_recovered_function_details.csv}"
REUSE_D01_BOUNDARIES="${REUSE_D01_BOUNDARIES:-1}"

ANALYSIS_TIMEZONE="${ANALYSIS_TIMEZONE:-America/Chicago}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
AST_WORKER_TIMEOUT_SECONDS="${AST_WORKER_TIMEOUT_SECONDS:-300}"
START_REPO_ORDER="${START_REPO_ORDER:-1}"
LIMIT_REPOS="${LIMIT_REPOS:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
DRY_RUN="${DRY_RUN:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SKIP_SELF_TEST="${SKIP_SELF_TEST:-0}"
PROGRESS_EVERY_REPOS="${PROGRESS_EVERY_REPOS:-5}"
PROGRESS_EVERY_COMMITS="${PROGRESS_EVERY_COMMITS:-250}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_ROWS="${EXPECTED_TREATMENT_ROWS:-914}"
EXPECTED_CONTROL_ROWS="${EXPECTED_CONTROL_ROWS:-1040}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"

for boolean_name in \
  REUSE_D01_BOUNDARIES \
  ANALYSIS_AGAIN \
  DRY_RUN \
  STRICT_EXPECTED_COUNTS \
  SKIP_SELF_TEST; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${GIT_TIMEOUT_SECONDS}" \
  "${AST_WORKER_TIMEOUT_SECONDS}" \
  "${START_REPO_ORDER}" \
  "${LIMIT_REPOS}" \
  "${PROGRESS_EVERY_REPOS}" \
  "${PROGRESS_EVERY_COMMITS}" \
  "${EXPECTED_PANEL_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_ROWS}" \
  "${EXPECTED_CONTROL_ROWS}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${START_REPO_ORDER}" -lt 1 ]]; then
  echo "ERROR: START_REPO_ORDER must be at least 1." >&2
  exit 1
fi

if [[ -n "${DATASET_SOURCE}" && "${DATASET_SOURCE}" != "treatment" && "${DATASET_SOURCE}" != "control" ]]; then
  echo "ERROR: DATASET_SOURCE must be treatment, control, or empty." >&2
  exit 1
fi

if [[ "${BOUNDARY_CACHE_ROOT}" != /* || "${D01_BODY_STORE_ROOT}" != /* ]]; then
  echo "ERROR: BOUNDARY_CACHE_ROOT and D01_BODY_STORE_ROOT must be absolute paths." >&2
  exit 1
fi

for required_file in "${PY_SCRIPT}" "${BASE_PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: main Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v "${AST_PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: AST Python executable not found: ${AST_PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import numpy, pandas; from zoneinfo import ZoneInfo; ZoneInfo("America/Chicago")' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy, pandas, and timezone data." >&2
  exit 1
fi

mkdir -p \
  "${LOG_DIR}" \
  "${MAIN_OUTPUT_DIR}" \
  "${TMP_OUTPUT_DIR}" \
  "${CACHE_DIR}" \
  "${BOUNDARY_CACHE_ROOT}"

OUTPUT_FILES=(
  "${REPO_MONTH_OUTPUT}"
  "${COMMIT_OUTPUT}"
  "${FILE_OUTPUT}"
  "${FUNCTION_OUTPUT}"
  "${ISSUES_OUTPUT}"
  "${RECONCILIATION_OUTPUT}"
  "${QC_OUTPUT}"
)

EXISTING_OUTPUTS=()
for output_file in "${OUTPUT_FILES[@]}"; do
  if [[ -f "${output_file}" ]]; then
    EXISTING_OUTPUTS+=("${output_file}")
  fi
done

if [[ "${#EXISTING_OUTPUTS[@]}" -gt 0 ]]; then
  BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-${IMPLEMENTATION_VERSION}-backup-${RUN_TS}"
  mkdir -p "${BACKUP_DIR}"
  for output_file in "${EXISTING_OUTPUTS[@]}"; do
    mv "${output_file}" "${BACKUP_DIR}/"
  done
  MIGRATION_NOTE="moved previous E01 final outputs to ${BACKUP_DIR}; repository cache was retained"
else
  MIGRATION_NOTE="none"
fi

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
AST_PYTHON_VERSION="$("${AST_PYTHON_BIN}" --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
BASE_PANEL_SHA256="$(sha256sum "${BASE_PANEL_FILE}" | awk '{print $1}')"

D01_ARGS=()
D01_HASH_LINES=()
IFS=':' read -r -a D01_CANDIDATES <<< "${D01_FUNCTION_DETAILS_FILES}"
for candidate in "${D01_CANDIDATES[@]}"; do
  if [[ -f "${candidate}" ]]; then
    D01_ARGS+=(--d01-function-details-file "${candidate}")
    D01_HASH_LINES+=("${candidate}=$(sha256sum "${candidate}" | awk '{print $1}')")
  fi
done
D01_FILE_COUNT=$(( ${#D01_ARGS[@]} / 2 ))

{
  echo "============================================================"
  echo "${RUN_LABEL}: collect Python function-body lines added"
  echo "Started:                              $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                         ${PROJECT_ROOT}"
  echo "Python:                               ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "AST Python:                           ${AST_PYTHON_BIN} (${AST_PYTHON_VERSION})"
  echo "Implementation version:              ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:              ${PY_SCRIPT}"
  echo "Python script SHA256:                 ${PY_SCRIPT_SHA256}"
  echo "Base Model A panel:                   ${BASE_PANEL_FILE}"
  echo "Base panel SHA256:                    ${BASE_PANEL_SHA256}"
  echo "Analysis timezone:                    ${ANALYSIS_TIMEZONE}"
  echo "Primary metric:                       lines_added_py_function_body"
  echo "Token-size category:                  not used in run-x-e01"
  echo "D01 boundary reuse:                   ${REUSE_D01_BOUNDARIES}"
  echo "D01 metadata files found:             ${D01_FILE_COUNT}"
  echo "D01 body store root:                  ${D01_BODY_STORE_ROOT}"
  echo "D01 SQLite index:                     ${D01_INDEX_DB}"
  echo "Boundary cache root:                  ${BOUNDARY_CACHE_ROOT}"
  echo "Repository cache:                     ${CACHE_DIR}"
  echo "Repo-month output:                    ${REPO_MONTH_OUTPUT}"
  echo "Commit output:                        ${COMMIT_OUTPUT}"
  echo "File output:                          ${FILE_OUTPUT}"
  echo "Function output:                      ${FUNCTION_OUTPUT}"
  echo "Issues output:                        ${ISSUES_OUTPUT}"
  echo "Reconciliation output:                ${RECONCILIATION_OUTPUT}"
  echo "QC output:                            ${QC_OUTPUT}"
  echo "Summary output:                       ${SUMMARY_OUTPUT}"
  echo "Expected rows/repositories:           ${EXPECTED_PANEL_ROWS}/${EXPECTED_REPOSITORIES}"
  echo "Expected treatment/control rows:      ${EXPECTED_TREATMENT_ROWS}/${EXPECTED_CONTROL_ROWS}"
  echo "Expected treatment/control repos:     ${EXPECTED_TREATMENT_REPOSITORIES}/${EXPECTED_CONTROL_REPOSITORIES}"
  echo "Repository selection:                 start=${START_REPO_ORDER}; limit=${LIMIT_REPOS}; source=${DATASET_SOURCE:-all}; repo=${REPO_NAME:-all}"
  echo "Analysis again / dry run:             ${ANALYSIS_AGAIN}/${DRY_RUN}"
  echo "Strict expected counts:               ${STRICT_EXPECTED_COUNTS}"
  echo "Migration note:                       ${MIGRATION_NOTE}"
  echo "Log file:                             ${LOG_FILE}"
  if [[ "${#D01_HASH_LINES[@]}" -gt 0 ]]; then
    echo "D01 input SHA256 values:"
    printf '  %s\n' "${D01_HASH_LINES[@]}"
  fi
  echo "============================================================"
} | tee "${LOG_FILE}"

if [[ "${SKIP_SELF_TEST}" == "0" ]]; then
  {
    echo
    echo "** Step 1: Run structural self-test"
    echo "------------------------------------------------------------"
  } | tee -a "${LOG_FILE}"
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"
fi

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --panel-file "${BASE_PANEL_FILE}"
  --repo-month-output "${REPO_MONTH_OUTPUT}"
  --commit-output "${COMMIT_OUTPUT}"
  --file-output "${FILE_OUTPUT}"
  --function-output "${FUNCTION_OUTPUT}"
  --issues-output "${ISSUES_OUTPUT}"
  --reconciliation-output "${RECONCILIATION_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --cache-dir "${CACHE_DIR}"
  --boundary-cache-root "${BOUNDARY_CACHE_ROOT}"
  --d01-body-store-root "${D01_BODY_STORE_ROOT}"
  --d01-index-db "${D01_INDEX_DB}"
  --reuse-d01-boundaries "${REUSE_D01_BOUNDARIES}"
  --ast-python-bin "${AST_PYTHON_BIN}"
  --analysis-timezone "${ANALYSIS_TIMEZONE}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --ast-worker-timeout-seconds "${AST_WORKER_TIMEOUT_SECONDS}"
  --start-repo-order "${START_REPO_ORDER}"
  --limit-repos "${LIMIT_REPOS}"
  --dataset-source "${DATASET_SOURCE}"
  --repo-name "${REPO_NAME}"
  --analysis-again "${ANALYSIS_AGAIN}"
  --dry-run "${DRY_RUN}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-rows "${EXPECTED_TREATMENT_ROWS}"
  --expected-control-rows "${EXPECTED_CONTROL_ROWS}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --progress-every-repos "${PROGRESS_EVERY_REPOS}"
  --progress-every-commits "${PROGRESS_EVERY_COMMITS}"
  --log-level "${LOG_LEVEL}"
  "${D01_ARGS[@]}"
)

{
  echo
  echo "** Step 2: Collect commit, file, function, and repo-month metrics"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

set +e
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"
STATUS=${PIPESTATUS[0]}
set -e

if [[ "${STATUS}" -ne 0 ]]; then
  echo "ERROR: ${RUN_LABEL} failed with status ${STATUS}." | tee -a "${LOG_FILE}" >&2
  exit "${STATUS}"
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${RUN_LABEL} dry run completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

EXPECTED_OUTPUTS=(
  "${REPO_MONTH_OUTPUT}"
  "${COMMIT_OUTPUT}"
  "${FILE_OUTPUT}"
  "${FUNCTION_OUTPUT}"
  "${ISSUES_OUTPUT}"
  "${RECONCILIATION_OUTPUT}"
  "${QC_OUTPUT}"
  "${SUMMARY_OUTPUT}"
)

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

if awk -F, 'NR > 1 && $2 == "fail" { found=1 } END { exit(found ? 0 : 1) }' "${QC_OUTPUT}"; then
  echo "ERROR: QC contains one or more failures." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 3: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${REPO_MONTH_OUTPUT}" \
    "${COMMIT_OUTPUT}" \
    "${FILE_OUTPUT}" \
    "${FUNCTION_OUTPUT}" \
    "${ISSUES_OUTPUT}" \
    "${RECONCILIATION_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Repo-month preview:"
  head -n 11 "${REPO_MONTH_OUTPUT}"
  echo
  echo "Reconciliation mismatches preview:"
  awk -F, 'NR == 1 || $11 == 0 || $12 == 0 { print }' "${RECONCILIATION_OUTPUT}" | head -n 11
  echo
  echo "Issues preview:"
  head -n 11 "${ISSUES_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                            $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary repo-month metric:            ${REPO_MONTH_OUTPUT}"
  echo "Commit audit:                         ${COMMIT_OUTPUT}"
  echo "File audit:                           ${FILE_OUTPUT}"
  echo "Function attribution:                 ${FUNCTION_OUTPUT}"
  echo "History reconciliation:               ${RECONCILIATION_OUTPUT}"
  echo "Issues:                               ${ISSUES_OUTPUT}"
  echo "QC output:                            ${QC_OUTPUT}"
  echo "Summary output:                       ${SUMMARY_OUTPUT}"
  echo "Log file:                             ${LOG_FILE}"
  echo "Next step:                            inspect E01 completeness before building run-x-e02"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
