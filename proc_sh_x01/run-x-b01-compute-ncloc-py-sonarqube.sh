#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b01-sonarqube v2: Compute Python-only NCLOC for Model C
# ============================================================
#
# Purpose:
#   Compute SonarQube NCLOC from Python files only for every historical
#   repository-commit snapshot in the run-x-a05 Model C manifest.
#
# Analysis design:
#   - Preserve the 1,954-row Model A estimable sample created by run-x-a01
#     through run-x-a05.
#   - Deduplicate that panel into 1,496 historical snapshots.
#   - Scan only Python files with sonar.inclusions=**/*.py.
#   - Save one ncloc_py_sonarqube value per snapshot.
#   - Join each SonarQube result with the completed local cloc result.
#
# Safety:
#   The Python implementation creates detached temporary Git worktrees.
#   It does not checkout, reset, clean, or otherwise change the main
#   treatment/control clone working trees.
#
# Required environment:
#   SONAR_HOST=http://localhost:9000
#   SONAR_TOKEN=<token>
#   SONAR_PATH=/path/to/sonar-scanner
#     or SONAR_SCANNER_PATH=/path/to/sonar-scanner
#
# Required input:
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#
# Main outputs:
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_manifest.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_snapshot_results.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_completed_manifest.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_unresolved.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_vs_cloc.csv
#   repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_scan_qc.csv
#
# Summary output:
#   repo_x01/tmp/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_summary.csv
#
# Full run:
#   bash proc_sh_x01/run-x-b01-compute-ncloc-py-sonarqube.sh
#
# Manifest and output-format dry run:
#   DRY_RUN=1 bash proc_sh_x01/run-x-b01-compute-ncloc-py-sonarqube.sh
#
# One-snapshot smoke test:
#   LIMIT=1 bash proc_sh_x01/run-x-b01-compute-ncloc-py-sonarqube.sh
#
# Resume:
#   Re-run the same command. Successful snapshot_key rows are skipped.
#   Failed or pending snapshots are attempted again.
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   SONAR_PYTHON_VERSION=3.12
#   CLOC_RESULTS_FILE=repo_x01/run-x-b01/model_c_ncloc_py_snapshot_results.csv
#   START_ORDER=1
#   LIMIT=0
#   DATASET_SOURCE=treatment|control
#   REPO_NAME=owner/repository
#   ANALYSIS_AGAIN=0
#   KEEP_WORKTREES=0
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=0
#   STRICT_EXPECTED_COUNTS=1
#   SERVER_TIMEOUT_SECONDS=300
#   SCANNER_TIMEOUT_SECONDS=1800
#   COMPUTE_TIMEOUT_SECONDS=900
#   POLL_INTERVAL_SECONDS=5
#   SLEEP_BETWEEN_SCANS_SECONDS=0
#   PROGRESS_EVERY=10
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

# Load the project SonarQube configuration while preserving the same behavior
# used by the prior run-x SonarQube wrapper family.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

RUN_PREFIX="run-x-b01-sonarqube"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-compute-ncloc-py-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/compute_ncloc_python_sonarqube.py}"
INPUT_MANIFEST_FILE="${INPUT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
WORKTREE_ROOT="${WORKTREE_ROOT:-${TMP_OUTPUT_DIR}/worktrees}"
SCANNER_LOG_DIR="${SCANNER_LOG_DIR:-${MAIN_OUTPUT_DIR}/scanner_logs}"

SNAPSHOT_MANIFEST_OUTPUT="${SNAPSHOT_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_snapshot_manifest.csv}"
SNAPSHOT_RESULTS_OUTPUT="${SNAPSHOT_RESULTS_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_snapshot_results.csv}"
COMPLETED_MANIFEST_OUTPUT="${COMPLETED_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_completed_manifest.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_unresolved.csv}"
SCAN_QC_OUTPUT="${SCAN_QC_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_scan_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_summary.csv}"
CLOC_RESULTS_FILE="${CLOC_RESULTS_FILE:-repo_x01/run-x-b01/model_c_ncloc_py_snapshot_results.csv}"
COMPARISON_OUTPUT="${COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/model_c_ncloc_py_sonarqube_vs_cloc.csv}"

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
SONAR_SCANNER_BIN="${SONAR_PATH:-${SONAR_SCANNER_PATH:-sonar-scanner}}"
SONAR_PYTHON_VERSION="${SONAR_PYTHON_VERSION:-3.12}"
PROJECT_KEY_PREFIX="${PROJECT_KEY_PREFIX:-b01_ncloc_py_sonarqube_v2_}"
SERVER_TIMEOUT_SECONDS="${SERVER_TIMEOUT_SECONDS:-300}"
SCANNER_TIMEOUT_SECONDS="${SCANNER_TIMEOUT_SECONDS:-1800}"
COMPUTE_TIMEOUT_SECONDS="${COMPUTE_TIMEOUT_SECONDS:-900}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"
SLEEP_BETWEEN_SCANS_SECONDS="${SLEEP_BETWEEN_SCANS_SECONDS:-0}"
PROGRESS_EVERY="${PROGRESS_EVERY:-10}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
ANALYSIS_AGAIN="${ANALYSIS_AGAIN:-0}"
KEEP_WORKTREES="${KEEP_WORKTREES:-0}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
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
  "${SERVER_TIMEOUT_SECONDS}" \
  "${SCANNER_TIMEOUT_SECONDS}" \
  "${COMPUTE_TIMEOUT_SECONDS}" \
  "${POLL_INTERVAL_SECONDS}" \
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

if ! [[ "${SLEEP_BETWEEN_SCANS_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: SLEEP_BETWEEN_SCANS_SECONDS must be a non-negative number." >&2
  exit 1
fi

for boolean_name in \
  ANALYSIS_AGAIN \
  KEEP_WORKTREES \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  STRICT_EXPECTED_COUNTS; do
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

for required_file in "${PY_SCRIPT}" "${INPUT_MANIFEST_FILE}" "${CLOC_RESULTS_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1 && [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ -z "${SONAR_PYTHON_VERSION}" ]]; then
  echo "ERROR: SONAR_PYTHON_VERSION must not be empty." >&2
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
  "${WORKTREE_ROOT}" \
  "${SCANNER_LOG_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_MANIFEST_FILE}" | awk '{print $1}')"
CLOC_RESULTS_SHA256="$(sha256sum "${CLOC_RESULTS_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: compute Python-only NCLOC for Model C"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Input manifest:                  ${INPUT_MANIFEST_FILE}"
  echo "Input SHA256:                    ${INPUT_SHA256}"
  echo "Local cloc results:              ${CLOC_RESULTS_FILE}"
  echo "Local cloc SHA256:               ${CLOC_RESULTS_SHA256}"
  echo "Snapshot manifest output:        ${SNAPSHOT_MANIFEST_OUTPUT}"
  echo "Snapshot results output:         ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Completed manifest output:       ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "Scan QC output:                  ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "SonarQube vs cloc comparison:    ${COMPARISON_OUTPUT}"
  echo "Worktree root:                   ${WORKTREE_ROOT}"
  echo "Scanner log directory:           ${SCANNER_LOG_DIR}"
  echo "SonarQube host:                  ${SONAR_HOST}"
  echo "SonarScanner:                    ${SONAR_SCANNER_BIN}"
  echo "Sonar Python version:            ${SONAR_PYTHON_VERSION}"
  echo "Sonar scope:                     sonar.inclusions=**/*.py"
  echo "Project key prefix:              ${PROJECT_KEY_PREFIX}"
  echo "Server timeout seconds:          ${SERVER_TIMEOUT_SECONDS}"
  echo "Scanner timeout seconds:         ${SCANNER_TIMEOUT_SECONDS}"
  echo "Compute timeout seconds:         ${COMPUTE_TIMEOUT_SECONDS}"
  echo "Poll interval seconds:           ${POLL_INTERVAL_SECONDS}"
  echo "Sleep between scans seconds:     ${SLEEP_BETWEEN_SCANS_SECONDS}"
  echo "Progress every:                  ${PROGRESS_EVERY}"
  echo "Start order:                     ${START_ORDER}"
  echo "Limit:                           ${LIMIT}"
  echo "Dataset-source filter:           ${DATASET_SOURCE:-<all>}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Analysis again:                  ${ANALYSIS_AGAIN}"
  echo "Keep worktrees:                  ${KEEP_WORKTREES}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
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
  --completed-manifest-output "${COMPLETED_MANIFEST_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --scan-qc-output "${SCAN_QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --cloc-results-file "${CLOC_RESULTS_FILE}"
  --comparison-output "${COMPARISON_OUTPUT}"
  --worktree-root "${WORKTREE_ROOT}"
  --scanner-log-dir "${SCANNER_LOG_DIR}"
  --sonar-host "${SONAR_HOST}"
  --sonar-scanner "${SONAR_SCANNER_BIN}"
  --sonar-python-version "${SONAR_PYTHON_VERSION}"
  --project-key-prefix "${PROJECT_KEY_PREFIX}"
  --server-timeout-seconds "${SERVER_TIMEOUT_SECONDS}"
  --scanner-timeout-seconds "${SCANNER_TIMEOUT_SECONDS}"
  --compute-timeout-seconds "${COMPUTE_TIMEOUT_SECONDS}"
  --poll-interval-seconds "${POLL_INTERVAL_SECONDS}"
  --sleep-between-scans-seconds "${SLEEP_BETWEEN_SCANS_SECONDS}"
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

if [[ -n "${DATASET_SOURCE}" ]]; then
  COMMAND+=(--dataset-source "${DATASET_SOURCE}")
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
fi
if [[ "${ANALYSIS_AGAIN}" == "1" ]]; then
  COMMAND+=(--analysis-again)
fi
if [[ "${KEEP_WORKTREES}" == "1" ]]; then
  COMMAND+=(--keep-worktrees)
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

{
  echo
  echo "** Step 1: Compute Python-only NCLOC for historical snapshots"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${SNAPSHOT_MANIFEST_OUTPUT}" \
  "${SNAPSHOT_RESULTS_OUTPUT}" \
  "${COMPLETED_MANIFEST_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${SCAN_QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}" \
  "${COMPARISON_OUTPUT}"; do
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
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SNAPSHOT_MANIFEST_OUTPUT}" \
    "${SNAPSHOT_RESULTS_OUTPUT}" \
    "${COMPLETED_MANIFEST_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${SCAN_QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}" \
    "${COMPARISON_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${SCAN_QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "SonarQube vs cloc comparison preview:"
  head -n 11 "${COMPARISON_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Snapshot results:                ${SNAPSHOT_RESULTS_OUTPUT}"
  echo "Completed manifest:              ${COMPLETED_MANIFEST_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${SCAN_QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "SonarQube vs cloc comparison:    ${COMPARISON_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       review SonarQube-vs-cloc differences, then increase LIMIT"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
