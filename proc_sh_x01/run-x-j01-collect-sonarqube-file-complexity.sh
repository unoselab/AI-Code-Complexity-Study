#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-j01 v1: Collect file-level SonarQube complexity metrics
# ============================================================
#
# Purpose:
#   Retrieve file-level cognitive_complexity and ncloc from the existing
#   run-x-b01-sonarqube historical projects. This wrapper reuses the validated
#   run-x-b01 SonarQube environment, logging, filtering, and QC conventions,
#   but it is fully standalone and never calls an older experiment wrapper.
#
# Important:
#   - This is API retrieval only. SonarScanner is NOT executed.
#   - Existing SonarQube projects are read but never modified.
#   - One B01 historical SonarQube project corresponds to one frozen snapshot.
#
# Required environment:
#   SONAR_HOST=http://localhost:9000
#   SONAR_TOKEN=<token>
#
# Required input:
#   repo_x01/run-x-b01-sonarqube/
#     model_c_ncloc_py_sonarqube_completed_manifest.csv
#
# Main outputs:
#   repo_x01/run-x-j01/python_sonarqube_file_complexity.csv.gz
#   repo_x01/run-x-j01/python_sonarqube_complexity_snapshot_counts.csv
#   repo_x01/run-x-j01/python_sonarqube_complexity_unresolved.csv
#   repo_x01/run-x-j01/python_sonarqube_complexity_qc.csv
#
# Summary output:
#   repo_x01/tmp/run-x-j01/python_sonarqube_complexity_summary.csv
#
# Recommended first run (one-snapshot smoke test):
#   LIMIT=1 bash proc_sh_x01/run-x-j01-collect-sonarqube-file-complexity.sh
#
# Full production run:
#   bash proc_sh_x01/run-x-j01-collect-sonarqube-file-complexity-v1.sh
#
# Optional filters/controls:
#   PYTHON_BIN=python
#   START_ORDER=1
#   LIMIT=0
#   DATASET_SOURCE=treatment|control
#   REPO_NAME=owner/repository
#   PAGE_SIZE=500
#   REQUEST_TIMEOUT_SECONDS=60
#   MAX_RETRIES=4
#   RETRY_BACKOFF_SECONDS=1
#   SLEEP_BETWEEN_PROJECTS_SECONDS=0
#   PROGRESS_EVERY=25
#   DRY_RUN=0
#   FAIL_ON_UNRESOLVED=1
#   STRICT_EXPECTED_COUNTS=1
#   STRICT_METRIC_RECONCILIATION=0
#   LOG_LEVEL=INFO
#
# Output semantics:
#   cognitive_complexity and ncloc are actual SonarQube file-component
#   measures. A missing cognitive_complexity measure on a file is retained as
#   zero with cognitive_complexity_measure_present=0, because SonarQube may
#   omit an explicit zero-valued measure from a component payload.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

# Load the same project-local SonarQube environment convention used by B01/B05.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

RUN_PREFIX="run-x-j01"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-collect-sonarqube-file-complexity-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/collect_sonarqube_file_complexity.py}"
INPUT_MANIFEST_FILE="${INPUT_MANIFEST_FILE:-repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_completed_manifest.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

FILE_OUTPUT="${FILE_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_file_complexity.csv.gz}"
SNAPSHOT_OUTPUT="${SNAPSHOT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_complexity_snapshot_counts.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_complexity_unresolved.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_complexity_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/python_sonarqube_complexity_summary.csv}"

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
PAGE_SIZE="${PAGE_SIZE:-500}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-60}"
MAX_RETRIES="${MAX_RETRIES:-4}"
RETRY_BACKOFF_SECONDS="${RETRY_BACKOFF_SECONDS:-1}"
SLEEP_BETWEEN_PROJECTS_SECONDS="${SLEEP_BETWEEN_PROJECTS_SECONDS:-0}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_UNRESOLVED="${FAIL_ON_UNRESOLVED:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
STRICT_METRIC_RECONCILIATION="${STRICT_METRIC_RECONCILIATION:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_TREATMENT_SNAPSHOTS="${EXPECTED_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_CONTROL_SNAPSHOTS="${EXPECTED_CONTROL_SNAPSHOTS:-706}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"

for numeric_value in \
  "${PAGE_SIZE}" \
  "${REQUEST_TIMEOUT_SECONDS}" \
  "${MAX_RETRIES}" \
  "${PROGRESS_EVERY}" \
  "${START_ORDER}" \
  "${LIMIT}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${START_ORDER}" -lt 1 ]]; then
  echo "ERROR: START_ORDER must be at least 1." >&2
  exit 1
fi

if [[ "${PAGE_SIZE}" -lt 1 || "${PAGE_SIZE}" -gt 500 ]]; then
  echo "ERROR: PAGE_SIZE must be between 1 and 500." >&2
  exit 1
fi

for decimal_value in "${RETRY_BACKOFF_SECONDS}" "${SLEEP_BETWEEN_PROJECTS_SECONDS}"; do
  if ! [[ "${decimal_value}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "ERROR: retry/sleep options must be non-negative numbers." >&2
    exit 1
  fi
done

for boolean_name in \
  DRY_RUN \
  FAIL_ON_UNRESOLVED \
  STRICT_EXPECTED_COUNTS \
  STRICT_METRIC_RECONCILIATION; do
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

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python analysis script not found: ${PY_SCRIPT}" >&2
  exit 1
fi
if [[ ! -f "${INPUT_MANIFEST_FILE}" ]]; then
  echo "ERROR: input manifest not found: ${INPUT_MANIFEST_FILE}" >&2
  exit 1
fi
if [[ -z "${SONAR_TOKEN:-}" && "${DRY_RUN}" != "1" ]]; then
  echo "ERROR: SONAR_TOKEN is not set. Load it through .env or the environment." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="$(sha256sum "${INPUT_MANIFEST_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: collect file-level SonarQube cognitive complexity"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Input B01 completed manifest:     ${INPUT_MANIFEST_FILE}"
  echo "Input SHA256:                    ${INPUT_SHA256}"
  echo "SonarQube host:                  ${SONAR_HOST}"
  echo "Retrieval mode:                  existing-project API only; no rescan"
  echo "Metrics:                         cognitive_complexity,ncloc"
  echo "File output:                     ${FILE_OUTPUT}"
  echo "Snapshot output:                 ${SNAPSHOT_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Page size:                       ${PAGE_SIZE}"
  echo "Request timeout seconds:         ${REQUEST_TIMEOUT_SECONDS}"
  echo "Max retries:                     ${MAX_RETRIES}"
  echo "Retry backoff seconds:           ${RETRY_BACKOFF_SECONDS}"
  echo "Sleep between projects seconds:  ${SLEEP_BETWEEN_PROJECTS_SECONDS}"
  echo "Progress every:                  ${PROGRESS_EVERY}"
  echo "Start order:                     ${START_ORDER}"
  echo "Limit:                           ${LIMIT}"
  echo "Dataset-source filter:           ${DATASET_SOURCE:-<all>}"
  echo "Repository filter:               ${REPO_NAME:-<all>}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on unresolved:              ${FAIL_ON_UNRESOLVED}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Strict metric reconciliation:    ${STRICT_METRIC_RECONCILIATION}"
  echo "Expected snapshots:              ${EXPECTED_SNAPSHOTS}"
  echo "Expected treatment/control:      ${EXPECTED_TREATMENT_SNAPSHOTS}/${EXPECTED_CONTROL_SNAPSHOTS}"
  echo "Expected repositories:           ${EXPECTED_REPOSITORIES}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --input-manifest-file "${INPUT_MANIFEST_FILE}"
  --file-output "${FILE_OUTPUT}"
  --snapshot-output "${SNAPSHOT_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --sonar-host "${SONAR_HOST}"
  --metrics "cognitive_complexity,ncloc"
  --page-size "${PAGE_SIZE}"
  --request-timeout-seconds "${REQUEST_TIMEOUT_SECONDS}"
  --max-retries "${MAX_RETRIES}"
  --retry-backoff-seconds "${RETRY_BACKOFF_SECONDS}"
  --sleep-between-projects-seconds "${SLEEP_BETWEEN_PROJECTS_SECONDS}"
  --progress-every "${PROGRESS_EVERY}"
  --start-order "${START_ORDER}"
  --limit "${LIMIT}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-treatment-snapshots "${EXPECTED_TREATMENT_SNAPSHOTS}"
  --expected-control-snapshots "${EXPECTED_CONTROL_SNAPSHOTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --log-level "${LOG_LEVEL}"
)

if [[ -n "${DATASET_SOURCE}" ]]; then
  COMMAND+=(--dataset-source "${DATASET_SOURCE}")
fi
if [[ -n "${REPO_NAME}" ]]; then
  COMMAND+=(--repo-name "${REPO_NAME}")
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
if [[ "${STRICT_METRIC_RECONCILIATION}" == "1" ]]; then
  COMMAND+=(--strict-metric-reconciliation)
fi

{
  echo
  echo "** Step 1: Retrieve file-level cognitive complexity and NCLOC"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in \
  "${FILE_OUTPUT}" \
  "${SNAPSHOT_OUTPUT}" \
  "${UNRESOLVED_OUTPUT}" \
  "${QC_OUTPUT}" \
  "${SUMMARY_OUTPUT}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  ls -lh "${FILE_OUTPUT}" "${SNAPSHOT_OUTPUT}" "${UNRESOLVED_OUTPUT}" "${QC_OUTPUT}" "${SUMMARY_OUTPUT}"
  echo
  echo "Snapshot reconciliation preview:"
  head -n 11 "${SNAPSHOT_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "File-level complexity:           ${FILE_OUTPUT}"
  echo "Snapshot reconciliation:        ${SNAPSHOT_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       join file-level complexity with NPR/ML file-selection universes"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
