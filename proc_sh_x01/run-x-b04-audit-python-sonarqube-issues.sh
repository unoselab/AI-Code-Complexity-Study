#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b04 v1: Audit Python-only SonarQube issue recoverability
# ============================================================
#
# Purpose:
#   Test whether the 1,496 independent Python-only SonarQube projects created
#   by run-x-b01 can still provide reproducible snapshot-specific issue data.
#
# Design:
#   - Do not run SonarScanner again.
#   - Reuse the completed run-x-b01 SonarQube manifest as the source of truth.
#   - Select paired early/late snapshots from size-diverse treatment and
#     control repositories.
#   - Verify project existence, expected project version, analysis identity,
#     NCLOC consistency, issues API availability, and Python component scope.
#   - Save issue metadata samples only for audit purposes; do not build the
#     final quality panel in this step.
#
# Why this is separate from the older warning collector:
#   The original warning collector reused one SonarQube project per repository
#   and therefore could not precisely recover all historical issue states.
#   B01 instead created a unique SonarQube project_key for every historical
#   snapshot. B04 tests whether that newer architecture permits exact
#   snapshot-level quality recovery before B05 performs full collection.
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
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_manifest.csv
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_sample.csv
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_issue_samples.csv
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_pair_comparison.csv
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_qc.csv
#   repo_x01/run-x-b04/python_sonarqube_issue_audit_summary.csv
#
# Default sample:
#   6 control repositories x 2 snapshots + 6 treatment repositories x 2
#   snapshots = 24 snapshots from 12 repositories.
#
# Full audit run:
#   bash proc_sh_x01/run-x-b04-audit-python-sonarqube-issues.sh
#
# Offline implementation self-test:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-b04-audit-python-sonarqube-issues.sh
#
# Optional overrides:
#   PYTHON_BIN=python
#   REPOS_PER_GROUP=6
#   ISSUES_PER_SNAPSHOT=25
#   SERVER_TIMEOUT_SECONDS=60
#   MAX_RETRIES=2
#   RETRY_SLEEP_SECONDS=1
#   STRICT=1
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

# Preserve the same project-local environment loading behavior used by the
# prior run-x SonarQube wrappers without calling those wrappers directly.
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

RUN_PREFIX="run-x-b04"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-python-sonarqube-issues-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_python_sonarqube_issues.py}"
COMPLETED_MANIFEST_FILE="${COMPLETED_MANIFEST_FILE:-repo_x01/run-x-b01-sonarqube/model_c_ncloc_py_sonarqube_completed_manifest.csv}"

MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-repo_x01/run-x-b04}"
SAMPLE_MANIFEST_OUTPUT="${SAMPLE_MANIFEST_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_manifest.csv}"
AUDIT_OUTPUT="${AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_sample.csv}"
ISSUE_SAMPLES_OUTPUT="${ISSUE_SAMPLES_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_issue_samples.csv}"
PAIR_COMPARISON_OUTPUT="${PAIR_COMPARISON_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_pair_comparison.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${MAIN_OUTPUT_DIR}/python_sonarqube_issue_audit_summary.csv}"

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
REPOS_PER_GROUP="${REPOS_PER_GROUP:-6}"
ISSUES_PER_SNAPSHOT="${ISSUES_PER_SNAPSHOT:-25}"
SERVER_TIMEOUT_SECONDS="${SERVER_TIMEOUT_SECONDS:-60}"
MAX_RETRIES="${MAX_RETRIES:-2}"
RETRY_SLEEP_SECONDS="${RETRY_SLEEP_SECONDS:-1}"
STRICT="${STRICT:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

for numeric_value in \
  "${REPOS_PER_GROUP}" \
  "${ISSUES_PER_SNAPSHOT}" \
  "${SERVER_TIMEOUT_SECONDS}" \
  "${MAX_RETRIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: integer options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${REPOS_PER_GROUP}" -lt 1 ]]; then
  echo "ERROR: REPOS_PER_GROUP must be at least 1." >&2
  exit 1
fi
if [[ "${SERVER_TIMEOUT_SECONDS}" -lt 1 ]]; then
  echo "ERROR: SERVER_TIMEOUT_SECONDS must be at least 1." >&2
  exit 1
fi
if ! [[ "${RETRY_SLEEP_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: RETRY_SLEEP_SECONDS must be a non-negative number." >&2
  exit 1
fi
for boolean_name in STRICT SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python script not found: ${PY_SCRIPT}" >&2
  exit 1
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1 && [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
INPUT_SHA256="not_checked_in_self_test"
if [[ "${SELF_TEST_ONLY}" == "0" ]]; then
  if [[ ! -f "${COMPLETED_MANIFEST_FILE}" ]]; then
    echo "ERROR: completed B01 manifest not found: ${COMPLETED_MANIFEST_FILE}" >&2
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
  echo "${RUN_LABEL}: audit Python-only SonarQube issue recoverability"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python audit script:              ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "B01 completed manifest:           ${COMPLETED_MANIFEST_FILE}"
  echo "B01 manifest SHA256:              ${INPUT_SHA256}"
  echo "SonarQube host:                   ${SONAR_HOST}"
  echo "Sonar token:                      <redacted>"
  echo "Repositories per group:           ${REPOS_PER_GROUP}"
  echo "Issue sample rows per snapshot:   ${ISSUES_PER_SNAPSHOT}"
  echo "Server timeout seconds:           ${SERVER_TIMEOUT_SECONDS}"
  echo "Max retries:                      ${MAX_RETRIES}"
  echo "Retry sleep seconds:              ${RETRY_SLEEP_SECONDS}"
  echo "Strict QC:                        ${STRICT}"
  echo "Self-test only:                   ${SELF_TEST_ONLY}"
  echo "Sample manifest output:           ${SAMPLE_MANIFEST_OUTPUT}"
  echo "Audit output:                     ${AUDIT_OUTPUT}"
  echo "Issue samples output:             ${ISSUE_SAMPLES_OUTPUT}"
  echo "Pair comparison output:           ${PAIR_COMPARISON_OUTPUT}"
  echo "QC output:                        ${QC_OUTPUT}"
  echo "Summary output:                   ${SUMMARY_OUTPUT}"
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
    --sample-manifest-output "${SAMPLE_MANIFEST_OUTPUT}"
    --audit-output "${AUDIT_OUTPUT}"
    --issue-samples-output "${ISSUE_SAMPLES_OUTPUT}"
    --pair-comparison-output "${PAIR_COMPARISON_OUTPUT}"
    --qc-output "${QC_OUTPUT}"
    --summary-output "${SUMMARY_OUTPUT}"
    --sonar-host "${SONAR_HOST}"
    --repos-per-group "${REPOS_PER_GROUP}"
    --issues-per-snapshot "${ISSUES_PER_SNAPSHOT}"
    --server-timeout-seconds "${SERVER_TIMEOUT_SECONDS}"
    --max-retries "${MAX_RETRIES}"
    --retry-sleep-seconds "${RETRY_SLEEP_SECONDS}"
    --log-level "${LOG_LEVEL}"
  )
  if [[ "${STRICT}" == "1" ]]; then
    COMMAND+=(--strict)
  fi
fi

{
  echo
  echo "** Step 1: Run B04 issue recoverability audit"
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
  "${SAMPLE_MANIFEST_OUTPUT}" \
  "${AUDIT_OUTPUT}" \
  "${ISSUE_SAMPLES_OUTPUT}" \
  "${PAIR_COMPARISON_OUTPUT}" \
  "${QC_OUTPUT}" \
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
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${SAMPLE_MANIFEST_OUTPUT}" \
    "${AUDIT_OUTPUT}" \
    "${ISSUE_SAMPLES_OUTPUT}" \
    "${PAIR_COMPARISON_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Audit preview:"
  head -n 13 "${AUDIT_OUTPUT}"
  echo
  echo "Pair comparison:"
  cat "${PAIR_COMPARISON_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Audit output:                     ${AUDIT_OUTPUT}"
  echo "Issue samples output:             ${ISSUE_SAMPLES_OUTPUT}"
  echo "Pair comparison output:           ${PAIR_COMPARISON_OUTPUT}"
  echo "QC output:                        ${QC_OUTPUT}"
  echo "Summary output:                   ${SUMMARY_OUTPUT}"
  echo "Log file:                         ${LOG_FILE}"
  echo "Next step:                        inspect B04 results before run-x-b05 full collection"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
