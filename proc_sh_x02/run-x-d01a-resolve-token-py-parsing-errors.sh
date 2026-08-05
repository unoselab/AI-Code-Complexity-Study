#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-d01a v1: Resolve D01 parsing and boundary issues
# ============================================================
#
# Purpose:
#   Review the final run-x-d01 file-level issues at blob level, recover
#   missing raw function bodies from the original historical source, and
#   produce corrected snapshot metrics without overwriting run-x-d01.
#
# Recovery order:
#   1. Parse the original source with Python 3.12 AST and compute all function
#      boundaries in the same Python 3.12 worker.
#   2. If AST parsing fails, use a complete Python token stream over the
#      original source. This supports templates and Python 2 grammar while
#      preserving the original raw body text.
#   3. Confirm zero metric impact when the source contains no named function
#      declarations.
#   4. Keep layout-preserving counterfactual repairs as review-only results
#      unless APPLY_COUNTERFACTUAL=1 is explicitly set.
#
# Inputs:
#   repo_x02/run-x-d01/model_c_token_py_snapshot_manifest.csv
#   repo_x02/run-x-d01/model_c_token_py_snapshot_results.csv
#   repo_x02/run-x-d01/model_c_token_py_function_details.csv
#   repo_x02/run-x-d01/model_c_token_py_file_issues.csv
#
# Outputs:
#   repo_x02/run-x-d01a/model_c_token_py_blob_resolution_review.csv
#   repo_x02/run-x-d01a/model_c_token_py_recovered_function_details.csv
#   repo_x02/run-x-d01a/model_c_token_py_file_resolutions.csv
#   repo_x02/run-x-d01a/model_c_token_py_snapshot_corrections.csv
#   repo_x02/run-x-d01a/model_c_token_py_snapshot_results_resolved.csv
#   repo_x02/run-x-d01a/model_c_token_py_resolution_decisions.csv
#   repo_x02/run-x-d01a/model_c_token_py_unresolved_after_d01a.csv
#   repo_x02/run-x-d01a/model_c_token_py_resolution_qc.csv
#   repo_x02/tmp/run-x-d01a/model_c_token_py_resolution_summary.csv
#
# Extracted-body store:
#   Recovered bodies are added to the existing py-fun-body snapshot
#   directories. Existing body files are verified before reuse and are never
#   silently overwritten with different content.
#
# Full run:
#   bash proc_sh_x02/run-x-d01a-resolve-token-py-parsing-errors.sh
#
# One-blob smoke test:
#   LIMIT=1 bash proc_sh_x02/run-x-d01a-resolve-token-py-parsing-errors.sh
#
# Repository-specific test:
#   REPO_NAME=believethehype/nostrdvm \
#     bash proc_sh_x02/run-x-d01a-resolve-token-py-parsing-errors.sh
#
# Optional overrides:
#   PYTHON_BIN=python
#   AST_PYTHON_BIN=/home/user1-system12/miniconda3/envs/agcparse312/bin/python
#   PYTHON2_BIN=/home/user1-system12/miniconda3/envs/agcparse2/bin/python
#   REQUIRE_PYTHON2_BIN=0
#   BODY_STORE_ROOT=/absolute/path/to/py-fun-body
#   BODY_SAVE_SCOPE=all|qualifying
#   APPLY_COUNTERFACTUAL=0
#   REPO_NAME=owner/repository
#   BLOB_OID=<40-character-oid>
#   LIMIT=0
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=0
#   SKIP_SELF_TEST=0
#   GIT_TIMEOUT_SECONDS=300
#   WORKER_TIMEOUT_SECONDS=600
#   PYTHON2_TIMEOUT_SECONDS=60
#   WORKER_BATCH_BYTES=20000000
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d01a"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-resolve-token-py-parsing-errors-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
AST_PYTHON_BIN="${AST_PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON2_BIN="${PYTHON2_BIN:-/home/user1-system12/miniconda3/envs/agcparse2/bin/python}"
REQUIRE_PYTHON2_BIN="${REQUIRE_PYTHON2_BIN:-0}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x02/resolve_token_py_parsing_errors.py}"

D01_DIR="${D01_DIR:-repo_x02/run-x-d01}"
D01_TMP_DIR="${D01_TMP_DIR:-repo_x02/tmp/run-x-d01}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-${D01_DIR}/model_c_token_py_snapshot_manifest.csv}"
SNAPSHOT_RESULTS_FILE="${SNAPSHOT_RESULTS_FILE:-${D01_DIR}/model_c_token_py_snapshot_results.csv}"
FUNCTION_DETAILS_FILE="${FUNCTION_DETAILS_FILE:-${D01_DIR}/model_c_token_py_function_details.csv}"
FILE_ISSUES_FILE="${FILE_ISSUES_FILE:-${D01_DIR}/model_c_token_py_file_issues.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

BLOB_REVIEW_OUTPUT="${BLOB_REVIEW_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_blob_resolution_review.csv}"
RECOVERED_FUNCTION_DETAILS_OUTPUT="${RECOVERED_FUNCTION_DETAILS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_recovered_function_details.csv}"
FILE_RESOLUTION_OUTPUT="${FILE_RESOLUTION_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_file_resolutions.csv}"
SNAPSHOT_CORRECTIONS_OUTPUT="${SNAPSHOT_CORRECTIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_corrections.csv}"
RESOLVED_SNAPSHOT_RESULTS_OUTPUT="${RESOLVED_SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_snapshot_results_resolved.csv}"
RESOLUTION_DECISIONS_OUTPUT="${RESOLUTION_DECISIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_resolution_decisions.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_unresolved_after_d01a.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_token_py_resolution_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/model_c_token_py_resolution_summary.csv}"

BODY_STORE_ROOT="${BODY_STORE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/py-fun-body}"
BODY_SAVE_SCOPE="${BODY_SAVE_SCOPE:-all}"
APPLY_COUNTERFACTUAL="${APPLY_COUNTERFACTUAL:-0}"
REPO_NAME="${REPO_NAME:-}"
BLOB_OID="${BLOB_OID:-}"
LIMIT="${LIMIT:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
SKIP_SELF_TEST="${SKIP_SELF_TEST:-0}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-300}"
WORKER_TIMEOUT_SECONDS="${WORKER_TIMEOUT_SECONDS:-600}"
PYTHON2_TIMEOUT_SECONDS="${PYTHON2_TIMEOUT_SECONDS:-60}"
WORKER_BATCH_BYTES="${WORKER_BATCH_BYTES:-20000000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for numeric_value in \
  "${LIMIT}" \
  "${GIT_TIMEOUT_SECONDS}" \
  "${WORKER_TIMEOUT_SECONDS}" \
  "${PYTHON2_TIMEOUT_SECONDS}" \
  "${WORKER_BATCH_BYTES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: numeric options must contain non-negative integers." >&2
    exit 1
  fi
done

for boolean_name in \
  REQUIRE_PYTHON2_BIN \
  APPLY_COUNTERFACTUAL \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  SKIP_SELF_TEST; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ "${BODY_SAVE_SCOPE}" != "all" && "${BODY_SAVE_SCOPE}" != "qualifying" ]]; then
  echo "ERROR: BODY_SAVE_SCOPE must be all or qualifying." >&2
  exit 1
fi

if [[ "${BODY_STORE_ROOT}" != /* ]]; then
  echo "ERROR: BODY_STORE_ROOT must be an absolute path." >&2
  exit 1
fi

for required_file in \
  "${PY_SCRIPT}" \
  "${SNAPSHOT_MANIFEST_FILE}" \
  "${SNAPSHOT_RESULTS_FILE}" \
  "${FUNCTION_DETAILS_FILE}" \
  "${FILE_ISSUES_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: main Python executable was not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -x "${AST_PYTHON_BIN}" ]] && ! command -v "${AST_PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: AST Python executable was not found: ${AST_PYTHON_BIN}" >&2
  exit 1
fi

PYTHON2_NOTE="available"
if [[ ! -x "${PYTHON2_BIN}" ]] && ! command -v "${PYTHON2_BIN}" >/dev/null 2>&1; then
  if [[ "${REQUIRE_PYTHON2_BIN}" == "1" ]]; then
    echo "ERROR: Python 2 executable was not found: ${PYTHON2_BIN}" >&2
    exit 1
  fi
  PYTHON2_NOTE="not available; Python 2 validation will be skipped"
  PYTHON2_BIN=""
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but was not found in PATH." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${BODY_STORE_ROOT}"

MIGRATION_NOTE="none"
if [[ -f "${BLOB_REVIEW_OUTPUT}" && -s "${BLOB_REVIEW_OUTPUT}" ]]; then
  BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-${IMPLEMENTATION_VERSION}-backup-${RUN_TS}"
  mkdir -p "${BACKUP_DIR}"
  for output_file in \
    "${BLOB_REVIEW_OUTPUT}" \
    "${RECOVERED_FUNCTION_DETAILS_OUTPUT}" \
    "${FILE_RESOLUTION_OUTPUT}" \
    "${SNAPSHOT_CORRECTIONS_OUTPUT}" \
    "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}" \
    "${RESOLUTION_DECISIONS_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${QC_OUTPUT}"; do
    if [[ -f "${output_file}" ]]; then
      mv "${output_file}" "${BACKUP_DIR}/$(basename "${output_file}")"
    fi
  done
  if [[ -f "${SUMMARY_OUTPUT}" ]]; then
    mv "${SUMMARY_OUTPUT}" "${BACKUP_DIR}/$(basename "${SUMMARY_OUTPUT}")"
  fi
  MIGRATION_NOTE="moved previous D01a outputs to ${BACKUP_DIR}"
fi

MAIN_PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
AST_PYTHON_VERSION="$("${AST_PYTHON_BIN}" --version 2>&1 || true)"
PYTHON2_VERSION="not available"
if [[ -n "${PYTHON2_BIN}" ]]; then
  PYTHON2_VERSION="$("${PYTHON2_BIN}" --version 2>&1 || true)"
fi
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
FILE_ISSUES_SHA256="$(sha256sum "${FILE_ISSUES_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: resolve D01 parsing and boundary issues"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Main Python:                     ${PYTHON_BIN} (${MAIN_PYTHON_VERSION})"
  echo "AST Python:                      ${AST_PYTHON_BIN} (${AST_PYTHON_VERSION})"
  echo "Python 2 validation:             ${PYTHON2_BIN:-<none>} (${PYTHON2_VERSION})"
  echo "Python 2 note:                   ${PYTHON2_NOTE}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python script:                   ${PY_SCRIPT}"
  echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
  echo "Snapshot manifest:               ${SNAPSHOT_MANIFEST_FILE}"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_FILE}"
  echo "Function details:                ${FUNCTION_DETAILS_FILE}"
  echo "File issues:                     ${FILE_ISSUES_FILE}"
  echo "File issues SHA256:              ${FILE_ISSUES_SHA256}"
  echo "Body store root:                 ${BODY_STORE_ROOT}"
  echo "Body save scope:                ${BODY_SAVE_SCOPE}"
  echo "Apply counterfactual:            ${APPLY_COUNTERFACTUAL}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Blob filter:                     ${BLOB_OID:-<all>}"
  echo "Unique-blob limit:               ${LIMIT}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Skip self-test:                  ${SKIP_SELF_TEST}"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "Worker timeout seconds:          ${WORKER_TIMEOUT_SECONDS}"
  echo "Python 2 timeout seconds:        ${PYTHON2_TIMEOUT_SECONDS}"
  echo "Worker batch bytes:              ${WORKER_BATCH_BYTES}"
  echo "Blob review output:              ${BLOB_REVIEW_OUTPUT}"
  echo "Recovered details output:        ${RECOVERED_FUNCTION_DETAILS_OUTPUT}"
  echo "File resolution output:          ${FILE_RESOLUTION_OUTPUT}"
  echo "Snapshot corrections output:     ${SNAPSHOT_CORRECTIONS_OUTPUT}"
  echo "Resolved snapshot results:       ${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}"
  echo "Resolution decisions:            ${RESOLUTION_DECISIONS_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Previous-output migration:       ${MIGRATION_NOTE}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --snapshot-results-file "${SNAPSHOT_RESULTS_FILE}"
  --function-details-file "${FUNCTION_DETAILS_FILE}"
  --file-issues-file "${FILE_ISSUES_FILE}"
  --body-store-root "${BODY_STORE_ROOT}"
  --body-save-scope "${BODY_SAVE_SCOPE}"
  --blob-review-output "${BLOB_REVIEW_OUTPUT}"
  --recovered-function-details-output "${RECOVERED_FUNCTION_DETAILS_OUTPUT}"
  --file-resolution-output "${FILE_RESOLUTION_OUTPUT}"
  --snapshot-corrections-output "${SNAPSHOT_CORRECTIONS_OUTPUT}"
  --resolved-snapshot-results-output "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}"
  --resolution-decisions-output "${RESOLUTION_DECISIONS_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --ast-python-bin "${AST_PYTHON_BIN}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --worker-timeout-seconds "${WORKER_TIMEOUT_SECONDS}"
  --python2-timeout-seconds "${PYTHON2_TIMEOUT_SECONDS}"
  --worker-batch-bytes "${WORKER_BATCH_BYTES}"
  --limit "${LIMIT}"
  --log-level "${LOG_LEVEL}"
)

if [[ -n "${PYTHON2_BIN}" ]]; then
  COMMAND+=(--python2-bin "${PYTHON2_BIN}")
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ -n "${BLOB_OID}" ]]; then
  COMMAND+=(--blob-oid "${BLOB_OID}")
fi
if [[ "${APPLY_COUNTERFACTUAL}" == "1" ]]; then
  COMMAND+=(--apply-counterfactual)
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  COMMAND+=(--dry-run)
fi
if [[ "${FAIL_ON_UNRESOLVED}" == "1" ]]; then
  COMMAND+=(--fail-on-unresolved)
fi
if [[ "${SKIP_SELF_TEST}" == "1" ]]; then
  COMMAND+=(--skip-self-test)
fi

{
  echo
  echo "** Step 1: Resolve unique issue blobs and apply snapshot corrections"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${BLOB_REVIEW_OUTPUT}" \
  "${RECOVERED_FUNCTION_DETAILS_OUTPUT}" \
  "${FILE_RESOLUTION_OUTPUT}" \
  "${SNAPSHOT_CORRECTIONS_OUTPUT}" \
  "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}" \
  "${RESOLUTION_DECISIONS_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${BLOB_REVIEW_OUTPUT}" \
    "${RECOVERED_FUNCTION_DETAILS_OUTPUT}" \
    "${FILE_RESOLUTION_OUTPUT}" \
    "${SNAPSHOT_CORRECTIONS_OUTPUT}" \
    "${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}" \
    "${RESOLUTION_DECISIONS_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Blob review preview:"
  head -n 11 "${BLOB_REVIEW_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Blob review:                    ${BLOB_REVIEW_OUTPUT}"
  echo "Recovered function details:     ${RECOVERED_FUNCTION_DETAILS_OUTPUT}"
  echo "File resolutions:               ${FILE_RESOLUTION_OUTPUT}"
  echo "Snapshot corrections:           ${SNAPSHOT_CORRECTIONS_OUTPUT}"
  echo "Resolved snapshot results:      ${RESOLVED_SNAPSHOT_RESULTS_OUTPUT}"
  echo "Unresolved after D01a:          ${UNRESOLVED_OUTPUT}"
  echo "QC output:                      ${QC_OUTPUT}"
  echo "Summary output:                 ${SUMMARY_OUTPUT}"
  echo "Log file:                       ${LOG_FILE}"
  echo "Next step:                      review any remaining D01a rows, then prepare the repo-month panel"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
