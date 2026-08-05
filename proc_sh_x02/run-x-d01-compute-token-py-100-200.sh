#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-d01 v2: Compute raw Python function-body token metrics
# ============================================================
#
# Purpose:
#   Compute snapshot-level token_py_100_200 over the same historical
#   repository snapshots used by run-x-b. The metric is the sum of token
#   counts for eligible raw Python function bodies whose individual token
#   counts are between 100 and 200, inclusive.
#
# Token definition:
#   token_count = len(raw_body_text.split(" "))
#
#   The implementation intentionally counts empty fields created by leading,
#   trailing, or repeated literal ASCII spaces. It does not strip, dedent, or
#   normalize the raw function body. Newlines and tabs are not separators.
#
# Function scope:
#   - Include module-level functions and async functions.
#   - Include class methods and async methods.
#   - Do not count nested functions as separate occurrences.
#   - Keep nested-function source inside the outer function's raw body.
#   - Count every tracked path and every eligible function occurrence.
#   - Do not deduplicate equal function bodies.
#
# Raw-body extraction:
#   - Exclude decorators and the function header.
#   - For block functions, begin at the physical line immediately after the
#     complete header, preserving comments, blank lines, and indentation.
#   - For one-line functions, begin at the first body statement and exclude
#     only separator spaces between the header colon and that statement.
#   - When a leading docstring exists, begin immediately after the physical
#     line containing the end of the docstring.
#   - End at the complete physical line reported by the function AST node.
#
# Python runtimes:
#   - PYTHON_BIN runs the overall pandas/Git workflow and may remain Python 3.11.
#   - AST_PYTHON_BIN is invoked only as a stdlib AST worker and must be 3.12+.
#
# Historical Git access:
#   - git ls-tree lists tracked Python blobs at the requested commit.
#   - git cat-file --batch reads original blob contents.
#   - The main clone checkout is never changed.
#
# Reusable extracted-body store:
#   Every successfully extracted raw body is saved as a UTF-8 .txt file under
#   BODY_STORE_ROOT. Each snapshot gets a stable subdirectory. The function
#   details CSV records the body key, relative path, absolute path, token count,
#   source location, and whether the body qualifies for the 100-200 range.
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#
# Main outputs:
#   repo_x02/run-x-d01/model_c_token_py_snapshot_manifest.csv
#   repo_x02/run-x-d01/model_c_token_py_snapshot_results.csv
#   repo_x02/run-x-d01/model_c_token_py_function_details.csv
#   repo_x02/run-x-d01/model_c_token_py_file_issues.csv
#   repo_x02/run-x-d01/model_c_token_py_unresolved.csv
#   repo_x02/run-x-d01/model_c_token_py_scan_qc.csv
#   repo_x02/tmp/run-x-d01/model_c_token_py_summary.csv
#
# Full run:
#   bash proc_sh_x02/run-x-d01-compute-token-py-100-200.sh
#
# Structural dry run:
#   DRY_RUN=1 bash proc_sh_x02/run-x-d01-compute-token-py-100-200.sh
#
# One-snapshot smoke test:
#   LIMIT=1 bash proc_sh_x02/run-x-d01-compute-token-py-100-200.sh
#
# Resume:
#   Re-run the same command. A successful snapshot is skipped only when its
#   expected extracted-body directory is also present. Set ANALYSIS_AGAIN=1 to
#   rebuild selected snapshots and replace their body directories.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/current-analysis-python
#   AST_PYTHON_BIN=/path/to/python3.12
#   AST_WORKER_TIMEOUT_SECONDS=300
#   INPUT_MANIFEST_FILE=/path/to/manifest.csv
#   BODY_STORE_ROOT=/absolute/path/to/py-fun-body
#   BODY_SAVE_SCOPE=all|qualifying
#   RESOLUTION_DECISIONS_FILE=/path/to/resolution.csv
#   START_ORDER=1
#   LIMIT=0
#   DATASET_SOURCE=treatment|control
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=0
#   STRICT_EXPECTED_COUNTS=1
#   SKIP_SELF_TEST=0
#   GIT_TIMEOUT_SECONDS=300
#   PROGRESS_EVERY=25
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d01"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-compute-token-py-100-200-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
AST_PYTHON_BIN="${AST_PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x02/compute_token_py_100_200.py}"
INPUT_MANIFEST_FILE="${INPUT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

SNAPSHOT_MANIFEST_OUTPUT="${SNAPSHOT_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_manifest.csv}"
SNAPSHOT_RESULTS_OUTPUT="${SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_results.csv}"
FUNCTION_DETAILS_OUTPUT="${FUNCTION_DETAILS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_function_details.csv}"
FILE_ISSUES_OUTPUT="${FILE_ISSUES_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_file_issues.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_unresolved.csv}"
SCAN_QC_OUTPUT="${SCAN_QC_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_scan_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/model_c_token_py_summary.csv}"

BODY_STORE_ROOT="${BODY_STORE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/py-fun-body}"
BODY_SAVE_SCOPE="${BODY_SAVE_SCOPE:-all}"
RESOLUTION_DECISIONS_FILE="${RESOLUTION_DECISIONS_FILE:-}"

GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
AST_WORKER_TIMEOUT_SECONDS="${AST_WORKER_TIMEOUT_SECONDS:-300}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SKIP_SELF_TEST="${SKIP_SELF_TEST:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-706}"
EXPECTED_REPO_MONTH_ROWS="${EXPECTED_REPO_MONTH_ROWS:-1954}"
EXPECTED_TREATMENT_REPO_MONTH_ROWS="${EXPECTED_TREATMENT_REPO_MONTH_ROWS:-914}"
EXPECTED_CONTROL_REPO_MONTH_ROWS="${EXPECTED_CONTROL_REPO_MONTH_ROWS:-1040}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"

for numeric_value in \
  "${GIT_TIMEOUT_SECONDS}" \
  "${AST_WORKER_TIMEOUT_SECONDS}" \
  "${PROGRESS_EVERY}" \
  "${START_ORDER}" \
  "${LIMIT}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPO_MONTH_ROWS}" \
  "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}" \
  "${EXPECTED_CONTROL_REPO_MONTH_ROWS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${START_ORDER}" -lt 1 ]]; then
  echo "ERROR: START_ORDER must be at least 1." >&2
  exit 1
fi

for boolean_name in \
  ANALYSIS_AGAIN \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  STRICT_EXPECTED_COUNTS \
  SKIP_SELF_TEST; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ -n "${DATASET_SOURCE}" && "${DATASET_SOURCE}" != "treatment" && "${DATASET_SOURCE}" != "control" ]]; then
  echo "ERROR: DATASET_SOURCE must be treatment, control, or empty." >&2
  exit 1
fi

if [[ "${BODY_SAVE_SCOPE}" != "all" && "${BODY_SAVE_SCOPE}" != "qualifying" ]]; then
  echo "ERROR: BODY_SAVE_SCOPE must be all or qualifying." >&2
  exit 1
fi

if [[ "${BODY_STORE_ROOT}" != /* ]]; then
  echo "ERROR: BODY_STORE_ROOT must be an absolute path." >&2
  exit 1
fi

for required_file in "${PY_SCRIPT}" "${INPUT_MANIFEST_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if [[ -n "${RESOLUTION_DECISIONS_FILE}" && ! -f "${RESOLUTION_DECISIONS_FILE}" ]]; then
  echo "ERROR: resolution decisions file not found: ${RESOLUTION_DECISIONS_FILE}" >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: main Python executable was not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v "${AST_PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: AST Python executable was not found: ${AST_PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

mkdir -p \
  "${LOG_DIR}" \
  "${MAIN_OUTPUT_DIR}" \
  "${TMP_OUTPUT_DIR}" \
  "${BODY_STORE_ROOT}"

# Preserve v1 CSV outputs because v2 delegates AST parsing to an external
# Python 3.12 worker and records different runtime provenance. Existing body
# directories remain under BODY_STORE_ROOT and are replaced per snapshot.
MIGRATION_NOTE="none"
if [[ -f "${SNAPSHOT_RESULTS_OUTPUT}" && -s "${SNAPSHOT_RESULTS_OUTPUT}" ]]; then
  if grep -q 'local_git_python312_ast_raw_body_split_space' "${SNAPSHOT_RESULTS_OUTPUT}"; then
    V1_BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-v1-backup-${RUN_TS}"
    mkdir -p "${V1_BACKUP_DIR}"
    for old_output in \
      "${SNAPSHOT_MANIFEST_OUTPUT}" \
      "${SNAPSHOT_RESULTS_OUTPUT}" \
      "${FUNCTION_DETAILS_OUTPUT}" \
      "${FILE_ISSUES_OUTPUT}" \
      "${UNRESOLVED_OUTPUT}" \
      "${SCAN_QC_OUTPUT}"; do
      if [[ -f "${old_output}" ]]; then
        mv "${old_output}" "${V1_BACKUP_DIR}/$(basename "${old_output}")"
      fi
    done
    if [[ -f "${SUMMARY_OUTPUT}" ]]; then
      mv "${SUMMARY_OUTPUT}" "${V1_BACKUP_DIR}/$(basename "${SUMMARY_OUTPUT}")"
    fi
    MIGRATION_NOTE="moved run-x-d01 v1 CSV outputs to ${V1_BACKUP_DIR}"
  fi
fi

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
AST_PYTHON_VERSION="$("${AST_PYTHON_BIN}" --version 2>&1 || true)"
AST_PYTHON_VERSION_OK="$("${AST_PYTHON_BIN}" -c 'import sys; print(int(sys.version_info >= (3, 12)))')"
if [[ "${AST_PYTHON_VERSION_OK}" != "1" ]]; then
  echo "ERROR: AST_PYTHON_BIN must be Python 3.12 or later: ${AST_PYTHON_BIN} (${AST_PYTHON_VERSION})" >&2
  exit 1
fi
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_MANIFEST_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: compute raw Python function-body token metrics"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Main Python:                     ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "AST Python:                      ${AST_PYTHON_BIN} (${AST_PYTHON_VERSION})"
  echo "AST worker timeout seconds:      ${AST_WORKER_TIMEOUT_SECONDS}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Old-output migration:            ${MIGRATION_NOTE}"
  echo "Input manifest:                  ${INPUT_MANIFEST_FILE}"
  echo "Input SHA256:                    ${INPUT_SHA256}"
  echo "Snapshot manifest output:        ${SNAPSHOT_MANIFEST_OUTPUT}"
  echo "Snapshot results output:         ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Function details output:         ${FUNCTION_DETAILS_OUTPUT}"
  echo "File issues output:              ${FILE_ISSUES_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "Scan QC output:                  ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Extracted-body root:             ${BODY_STORE_ROOT}"
  echo "Body save scope:                 ${BODY_SAVE_SCOPE}"
  echo "Body output encoding:            UTF-8"
  echo "Resolution decisions:            ${RESOLUTION_DECISIONS_FILE:-<none>}"
  echo "Count backend:                   local_git_external_python312_ast_raw_body_split_space"
  echo "Primary metric:                  token_py_100_200"
  echo "Token range:                     100:200 inclusive"
  echo "Token separator:                 literal ASCII space only"
  echo "Empty split fields counted:      yes"
  echo "Strip/dedent/normalization:      none"
  echo "Nested functions:                retained in outer body, not separate"
  echo "Function-body deduplication:     none"
  echo "Tracked-path deduplication:      none"
  echo "Git file listing:                git ls-tree"
  echo "Git blob reader:                 git cat-file --batch"
  echo "Checkout/worktree creation:      none"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "Progress every:                  ${PROGRESS_EVERY}"
  echo "Start order:                     ${START_ORDER}"
  echo "Limit:                           ${LIMIT}"
  echo "Dataset-source filter:           ${DATASET_SOURCE:-<all>}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Analysis again:                  ${ANALYSIS_AGAIN}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Skip internal self-test:         ${SKIP_SELF_TEST}"
  echo "Expected snapshots:              ${EXPECTED_SNAPSHOTS}"
  echo "Expected treatment/control:      ${EXPECTED_TREATMENT_SNAPSHOTS}/${EXPECTED_CONTROL_SNAPSHOTS}"
  echo "Expected repo-month coverage:    ${EXPECTED_REPO_MONTH_ROWS}"
  echo "Expected repositories:           ${EXPECTED_REPOSITORIES}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --input-manifest-file "${INPUT_MANIFEST_FILE}"
  --snapshot-manifest-output "${SNAPSHOT_MANIFEST_OUTPUT}"
  --snapshot-results-output "${SNAPSHOT_RESULTS_OUTPUT}"
  --function-details-output "${FUNCTION_DETAILS_OUTPUT}"
  --file-issues-output "${FILE_ISSUES_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --scan-qc-output "${SCAN_QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --body-store-root "${BODY_STORE_ROOT}"
  --body-save-scope "${BODY_SAVE_SCOPE}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --ast-python-bin "${AST_PYTHON_BIN}"
  --ast-worker-timeout-seconds "${AST_WORKER_TIMEOUT_SECONDS}"
  --progress-every "${PROGRESS_EVERY}"
  --start-order "${START_ORDER}"
  --limit "${LIMIT}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --expected-repo-month-rows "${EXPECTED_REPO_MONTH_ROWS}"
  --expected-treatment-repo-month-rows "${EXPECTED_TREATMENT_REPO_MONTH_ROWS}"
  --expected-control-repo-month-rows "${EXPECTED_CONTROL_REPO_MONTH_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)

if [[ -n "${RESOLUTION_DECISIONS_FILE}" ]]; then
  COMMAND+=(--resolution-decisions-file "${RESOLUTION_DECISIONS_FILE}")
fi
if [[ -n "${DATASET_SOURCE}" ]]; then
  COMMAND+=(--dataset-source "${DATASET_SOURCE}")
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  COMMAND+=(--analysis-again)
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi
if [[ "${SKIP_SELF_TEST}" == "1" ]]; then
  COMMAND+=(--skip-self-test)
fi

{
  echo
  echo "** Step 1: Compute token_py_100_200 and save raw function bodies"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${SNAPSHOT_MANIFEST_OUTPUT}" \
  "${SNAPSHOT_RESULTS_OUTPUT}" \
  "${FUNCTION_DETAILS_OUTPUT}" \
  "${FILE_ISSUES_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${SCAN_QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks and overall summary"
  echo "------------------------------------------------------------"
  wc -l \
    "${SNAPSHOT_MANIFEST_OUTPUT}" \
    "${SNAPSHOT_RESULTS_OUTPUT}" \
    "${FUNCTION_DETAILS_OUTPUT}" \
    "${FILE_ISSUES_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${SCAN_QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${SCAN_QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  if [[ "${DRY_RUN}" == "0" ]]; then
    echo "Extracted-body directory summary:"
    echo "Root: ${BODY_STORE_ROOT}"
    echo "Saved .txt files: $(find "${BODY_STORE_ROOT}" -type f -name '*.txt' | wc -l)"
    du -sh "${BODY_STORE_ROOT}" || true
    echo
  fi
  echo "Function-detail preview:"
  head -n 6 "${FUNCTION_DETAILS_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Function details:                ${FUNCTION_DETAILS_OUTPUT}"
  echo "Extracted bodies:                ${BODY_STORE_ROOT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       review unresolved snapshots, then prepare the repo-month panel"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
