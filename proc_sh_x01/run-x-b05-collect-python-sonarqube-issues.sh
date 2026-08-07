#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b05 v1: Collect full Python-only SonarQube issue stocks
# ============================================================
#
# Purpose:
#   Collect snapshot-level Python static-analysis quality measurements from
#   the 1,496 independent SonarQube projects created by run-x-b01.
#
# Design:
#   - Do not run SonarScanner again.
#   - Reuse the successful run-x-b01 Python-only SonarQube manifest.
#   - Query every independent snapshot project with the SonarQube Web API.
#   - Count unresolved issues present in each historical Python snapshot.
#   - Preserve type, severity, rule, Clean Code attribute, and software-quality
#     impact metadata for later quality-outcome construction and robustness.
#   - Verify project/version/analysis/NCLOC identity and Python component scope.
#   - Use temporary per-snapshot checkpoints so an interrupted full run can
#     resume without depending on any earlier shell script.
#
# Interpretation:
#   issue_total_py_sonarqube is a static-analysis issue STOCK for the source
#   snapshot. SonarQube creationDate records the later B01 scan execution time;
#   it is not the historical date when a defect was introduced.
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
#   repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv
#   repo_x01/run-x-b05/python_sonarqube_issues.csv.gz
#   repo_x01/run-x-b05/python_sonarqube_issue_rule_counts.csv.gz
#   repo_x01/run-x-b05/python_sonarqube_issue_rule_definitions.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_unresolved.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_qc.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_summary.csv
#
# Full run:
#   bash proc_sh_x01/run-x-b05-collect-python-sonarqube-issues.sh
#
# One-snapshot smoke test:
#   LIMIT=1 STRICT_EXPECTED_COUNTS=0 \
#     bash proc_sh_x01/run-x-b05-collect-python-sonarqube-issues.sh
#
# Resume:
#   Re-run the same command after an interruption. Successful temporary
#   checkpoints are reused. Failed snapshots are queried again.
#
# Offline implementation self-test:
#   SELF_TEST_ONLY=1 \
#     bash proc_sh_x01/run-x-b05-collect-python-sonarqube-issues.sh
#
# Optional overrides:
#   PYTHON_BIN=python
#   START_ORDER=1
#   LIMIT=0
#   DATASET_SOURCE=treatment|control
#   REPO_NAME=owner/repository
#   FORCE=0
#   KEEP_CHECKPOINTS=0
#   SERVER_TIMEOUT_SECONDS=60
#   MAX_RETRIES=2
#   RETRY_SLEEP_SECONDS=1
#   PAGE_SIZE=500
#   MAX_RESULT_WINDOW=10000
#   PROGRESS_EVERY=25
#   STRICT=1
#   STRICT_EXPECTED_COUNTS=1
#   SELF_TEST_ONLY=0
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

# Load the project-local SonarQube configuration while remaining independent
# from all earlier run-x wrappers.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

RUN_PREFIX="run-x-b05"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-collect-python-sonarqube-issues-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/collect_python_sonarqube_issues.py}"
COMPLETED_MANIFEST_FILE="${COMPLETED_MANIFEST_FILE:-repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_completed_manifest.csv}"

MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-repo_x01/run-x-b05}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-repo_x01/tmp/run-x-b05}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-${TMP_OUTPUT_DIR}/checkpoints}"
SNAPSHOT_COUNTS_OUTPUT="${SNAPSHOT_COUNTS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_snapshot_counts.csv}"
ISSUES_OUTPUT="${ISSUES_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issues.csv.gz}"
RULE_COUNTS_OUTPUT="${RULE_COUNTS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_rule_counts.csv.gz}"
RULE_DEFINITIONS_OUTPUT="${RULE_DEFINITIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_rule_definitions.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_unresolved.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_summary.csv}"

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
START_ORDER="${START_ORDER:-1}"
LIMIT="${LIMIT:-0}"
DATASET_SOURCE="${DATASET_SOURCE:-}"
REPO_NAME="${REPO_NAME:-}"
FORCE="${FORCE:-0}"
KEEP_CHECKPOINTS="${KEEP_CHECKPOINTS:-0}"
SERVER_TIMEOUT_SECONDS="${SERVER_TIMEOUT_SECONDS:-60}"
MAX_RETRIES="${MAX_RETRIES:-2}"
RETRY_SLEEP_SECONDS="${RETRY_SLEEP_SECONDS:-1}"
PAGE_SIZE="${PAGE_SIZE:-500}"
MAX_RESULT_WINDOW="${MAX_RESULT_WINDOW:-10000}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
STRICT="${STRICT:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT="${EXPECTED_TREATMENT:-790}"
EXPECTED_CONTROL="${EXPECTED_CONTROL:-706}"

for integer_name in \
  START_ORDER \
  LIMIT \
  SERVER_TIMEOUT_SECONDS \
  MAX_RETRIES \
  PAGE_SIZE \
  MAX_RESULT_WINDOW \
  PROGRESS_EVERY \
  EXPECTED_SNAPSHOTS \
  EXPECTED_REPOSITORIES \
  EXPECTED_TREATMENT \
  EXPECTED_CONTROL; do
  integer_value="${!integer_name}"
  if ! [[ "${integer_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: ${integer_name} must be a non-negative integer." >&2
    exit 1
  fi
done

if [[ "${START_ORDER}" -lt 1 ]]; then
  echo "ERROR: START_ORDER must be at least 1." >&2
  exit 1
fi
if [[ "${SERVER_TIMEOUT_SECONDS}" -lt 1 ]]; then
  echo "ERROR: SERVER_TIMEOUT_SECONDS must be at least 1." >&2
  exit 1
fi
if [[ "${PAGE_SIZE}" -lt 1 || "${PAGE_SIZE}" -gt 500 ]]; then
  echo "ERROR: PAGE_SIZE must be between 1 and 500." >&2
  exit 1
fi
if [[ "${MAX_RESULT_WINDOW}" -lt "${PAGE_SIZE}" ]]; then
  echo "ERROR: MAX_RESULT_WINDOW must be at least PAGE_SIZE." >&2
  exit 1
fi
if [[ "${PROGRESS_EVERY}" -lt 1 ]]; then
  echo "ERROR: PROGRESS_EVERY must be at least 1." >&2
  exit 1
fi
if ! [[ "${RETRY_SLEEP_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: RETRY_SLEEP_SECONDS must be a non-negative number." >&2
  exit 1
fi

for boolean_name in FORCE KEEP_CHECKPOINTS STRICT STRICT_EXPECTED_COUNTS SELF_TEST_ONLY; do
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
  echo "ERROR: Python script not found: ${PY_SCRIPT}" >&2
  exit 1
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1 && [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}" "${CHECKPOINT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="not_checked_in_self_test"
if [[ "${SELF_TEST_ONLY}" == "0" ]]; then
  if [[ ! -f "${COMPLETED_MANIFEST_FILE}" ]]; then
    echo "ERROR: B01 completed manifest not found: ${COMPLETED_MANIFEST_FILE}" >&2
    exit 1
  fi
  if [[ -z "${SONAR_TOKEN:-}" ]]; then
    echo "ERROR: SONAR_TOKEN must be set in .env or the environment." >&2
    exit 1
  fi
  INPUT_SHA256="$(sha256sum "${COMPLETED_MANIFEST_FILE}" | awk '{print $1}')"
fi

{
  echo "============================================================"
  echo "${RUN_LABEL}: collect full Python-only SonarQube issue stocks"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python collection script:         ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "B01 completed manifest:           ${COMPLETED_MANIFEST_FILE}"
  echo "B01 manifest SHA256:              ${INPUT_SHA256}"
  echo "SonarQube host:                   ${SONAR_HOST}"
  echo "Sonar token:                      <redacted>"
  echo "Primary quality stock:            unresolved SonarQube issues in Python-only snapshot project"
  echo "Raw issue date interpretation:    B01 scan time, not historical defect introduction time"
  echo "Start order:                      ${START_ORDER}"
  echo "Limit:                            ${LIMIT}"
  echo "Dataset-source filter:            ${DATASET_SOURCE:-<all>}"
  echo "Repository filter:                ${REPO_NAME:-<all>}"
  echo "Force API refresh:                ${FORCE}"
  echo "Keep temporary checkpoints:       ${KEEP_CHECKPOINTS}"
  echo "Server timeout seconds:           ${SERVER_TIMEOUT_SECONDS}"
  echo "Max retries:                      ${MAX_RETRIES}"
  echo "Retry sleep seconds:              ${RETRY_SLEEP_SECONDS}"
  echo "Issue API page size:              ${PAGE_SIZE}"
  echo "Issue API max result window:      ${MAX_RESULT_WINDOW}"
  echo "Progress every:                   ${PROGRESS_EVERY}"
  echo "Strict QC:                        ${STRICT}"
  echo "Strict expected counts:           ${STRICT_EXPECTED_COUNTS}"
  echo "Expected snapshots:               ${EXPECTED_SNAPSHOTS}"
  echo "Expected repositories:            ${EXPECTED_REPOSITORIES}"
  echo "Expected treatment/control:       ${EXPECTED_TREATMENT}/${EXPECTED_CONTROL}"
  echo "Self-test only:                   ${SELF_TEST_ONLY}"
  echo "Snapshot counts output:           ${SNAPSHOT_COUNTS_OUTPUT}"
  echo "Compressed issues output:         ${ISSUES_OUTPUT}"
  echo "Compressed rule counts output:    ${RULE_COUNTS_OUTPUT}"
  echo "Rule definitions output:          ${RULE_DEFINITIONS_OUTPUT}"
  echo "Unresolved output:                ${UNRESOLVED_OUTPUT}"
  echo "QC output:                        ${QC_OUTPUT}"
  echo "Summary output:                   ${SUMMARY_OUTPUT}"
  echo "Checkpoint directory:             ${CHECKPOINT_DIR}"
  echo "Log file:                         ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  COMMAND=("${PYTHON_BIN}" "${PY_SCRIPT}" --self-test --log-level "${LOG_LEVEL}")
else
  COMMAND=(
    "${PYTHON_BIN}"
    "${PY_SCRIPT}"
    --completed-manifest-file "${COMPLETED_MANIFEST_FILE}"
    --snapshot-counts-output "${SNAPSHOT_COUNTS_OUTPUT}"
    --issues-output "${ISSUES_OUTPUT}"
    --rule-counts-output "${RULE_COUNTS_OUTPUT}"
    --rule-definitions-output "${RULE_DEFINITIONS_OUTPUT}"
    --unresolved-output "${UNRESOLVED_OUTPUT}"
    --qc-output "${QC_OUTPUT}"
    --summary-output "${SUMMARY_OUTPUT}"
    --checkpoint-dir "${CHECKPOINT_DIR}"
    --sonar-host "${SONAR_HOST}"
    --server-timeout-seconds "${SERVER_TIMEOUT_SECONDS}"
    --max-retries "${MAX_RETRIES}"
    --retry-sleep-seconds "${RETRY_SLEEP_SECONDS}"
    --page-size "${PAGE_SIZE}"
    --max-result-window "${MAX_RESULT_WINDOW}"
    --start-order "${START_ORDER}"
    --limit "${LIMIT}"
    --progress-every "${PROGRESS_EVERY}"
    --expected-snapshots "${EXPECTED_SNAPSHOTS}"
    --expected-repositories "${EXPECTED_REPOSITORIES}"
    --expected-treatment "${EXPECTED_TREATMENT}"
    --expected-control "${EXPECTED_CONTROL}"
    --log-level "${LOG_LEVEL}"
  )
  if [[ -n "${DATASET_SOURCE}" ]]; then
    COMMAND+=(--dataset-source "${DATASET_SOURCE}")
  fi
  if [[ -n "${REPO_NAME}" ]]; then
    COMMAND+=(--repo-name "${REPO_NAME}")
  fi
  if [[ "${FORCE}" == "1" ]]; then
    COMMAND+=(--force)
  fi
  if [[ "${KEEP_CHECKPOINTS}" == "1" ]]; then
    COMMAND+=(--keep-checkpoints)
  fi
  if [[ "${STRICT}" == "1" ]]; then
    COMMAND+=(--strict)
  fi
  if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
    COMMAND+=(--strict-expected-counts)
  fi
fi

{
  echo
  echo "** Step 1: Collect Python-only SonarQube issue stocks"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  {
    echo
    echo "============================================================"
    echo "${RUN_LABEL} offline self-test completed."
    echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "Log file:                        ${LOG_FILE}"
    echo "============================================================"
  } | tee -a "${LOG_FILE}"
  exit 0
fi

for output_file in \
  "${SNAPSHOT_COUNTS_OUTPUT}" \
  "${ISSUES_OUTPUT}" \
  "${RULE_COUNTS_OUTPUT}" \
  "${RULE_DEFINITIONS_OUTPUT}" \
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
  echo "Snapshot counts rows including header: $(wc -l < "${SNAPSHOT_COUNTS_OUTPUT}")"
  echo "Raw issue rows including header:        $(gzip -cd "${ISSUES_OUTPUT}" | wc -l)"
  echo "Rule-count rows including header:       $(gzip -cd "${RULE_COUNTS_OUTPUT}" | wc -l)"
  echo "Rule definitions rows incl. header:     $(wc -l < "${RULE_DEFINITIONS_OUTPUT}")"
  echo "Unresolved rows including header:       $(wc -l < "${UNRESOLVED_OUTPUT}")"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Snapshot-count preview:"
  head -n 8 "${SNAPSHOT_COUNTS_OUTPUT}"
  echo
  echo "Output sizes:"
  du -h \
    "${SNAPSHOT_COUNTS_OUTPUT}" \
    "${ISSUES_OUTPUT}" \
    "${RULE_COUNTS_OUTPUT}" \
    "${RULE_DEFINITIONS_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Primary snapshot output:          ${SNAPSHOT_COUNTS_OUTPUT}"
  echo "Compressed raw issues:            ${ISSUES_OUTPUT}"
  echo "Compressed rule counts:           ${RULE_COUNTS_OUTPUT}"
  echo "QC output:                        ${QC_OUTPUT}"
  echo "Summary output:                   ${SUMMARY_OUTPUT}"
  echo "Log file:                         ${LOG_FILE}"
  echo "Next step:                        run-x-b06 prepares the Python quality DiD panel after B05 review"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
