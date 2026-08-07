#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b03-b: Audit Cursor adoption month across timezones
# ============================================================
#
# Purpose:
#   Check whether the recorded monthly Cursor adoption event can change because
#   the original repository analyzer converted Git epoch timestamps with the
#   host machine's local timezone before assigning YYYY-MM buckets.
#
# Design:
#   - This wrapper follows the logging, validation, and output-check patterns
#     used by the existing project shell scripts, but it is self-contained and
#     does not call any previous shell script.
#   - The Python program reads the final b02 Python-velocity panel to recover the
#     63 treatment repositories, recorded event months, clone paths, and frozen
#     b02 analysis-tip commits.
#   - The legacy cursor_commits.csv is used as the authoritative list of Cursor-
#     related commit hashes detected by the original implementation.
#   - Exact Git epoch timestamps are then recovered locally and converted under
#     explicit IANA timezones.
#   - The legacy committed_at wall-clock value is also compared with the exact
#     epoch to infer the UTC offset used by the machine that generated the
#     legacy cursor_commits.csv. This avoids guessing the original author's or
#     server's geographic location.
#   - This stage is audit-only. It does not modify treatment timing and does not
#     fit a DiD model. A corrected timing experiment should be created only if
#     this audit finds a material month-boundary discrepancy.
#
# Required inputs:
#   repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   data_baseline_backup/cursor_commits.csv OR data/cursor_commits.csv
#   local treatment repository clones referenced by the b02 panel
#
# Main outputs:
#   repo_x01/run-x-b03-b/cursor_adoption_timezone_commit_audit.csv
#   repo_x01/run-x-b03-b/cursor_adoption_timezone_repo_summary.csv
#   repo_x01/run-x-b03-b/cursor_adoption_timezone_differences.csv
#   repo_x01/run-x-b03-b/cursor_adoption_legacy_offset_summary.csv
#   repo_x01/run-x-b03-b/cursor_adoption_timezone_qc.csv
#
# Compact summary:
#   repo_x01/tmp/run-x-b03-b/cursor_adoption_timezone_summary.csv
#
# Default run:
#   bash proc_sh_x01/run-x-b03-b-audit-cursor-adoption-timezones.sh
#
# Optional overrides:
#   PANEL_FILE=/path/to/final_b02_panel.csv
#   LEGACY_CURSOR_COMMITS_FILE=/path/to/cursor_commits.csv
#   TREATMENT_CLONE_DIR=/path/to/treatment-repos
#   TIMEZONES='UTC,America/Chicago'
#   EXPECTED_TREATMENT_REPOS=63
#   STRICT_EXPECTED_COUNTS=1
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b03-b"
IMPLEMENTATION_VERSION="v1"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-cursor-adoption-timezone-audit-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_cursor_adoption_timezones.py}"

PANEL_FILE="${PANEL_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
TIMEZONES="${TIMEZONES:-UTC,America/Chicago}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-63}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-60}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

COMMIT_OUTPUT="${COMMIT_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_adoption_timezone_commit_audit.csv}"
REPO_OUTPUT="${REPO_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_adoption_timezone_repo_summary.csv}"
DIFFERENCE_OUTPUT="${DIFFERENCE_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_adoption_timezone_differences.csv}"
OFFSET_OUTPUT="${OFFSET_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_adoption_legacy_offset_summary.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_adoption_timezone_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/cursor_adoption_timezone_summary.csv}"

case "${STRICT_EXPECTED_COUNTS}" in
  0|1)
    ;;
  *)
    echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1. Got: ${STRICT_EXPECTED_COUNTS}" >&2
    exit 1
    ;;
esac

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "ERROR: Python audit program not found: ${PY_SCRIPT}" >&2
  exit 1
fi
if [[ ! -f "${PANEL_FILE}" ]]; then
  echo "ERROR: final b02 panel not found: ${PANEL_FILE}" >&2
  exit 1
fi

# Resolve the legacy Cursor-commit file without depending on a previous shell
# wrapper. The baseline backup is preferred because it should preserve the
# original pipeline artifact. The active data directory is a fallback.
if [[ -z "${LEGACY_CURSOR_COMMITS_FILE:-}" ]]; then
  for candidate in \
    "data_baseline_backup/cursor_commits.csv" \
    "data/cursor_commits.csv"
  do
    if [[ -f "${candidate}" ]]; then
      LEGACY_CURSOR_COMMITS_FILE="${candidate}"
      break
    fi
  done
fi

if [[ -z "${LEGACY_CURSOR_COMMITS_FILE:-}" || ! -f "${LEGACY_CURSOR_COMMITS_FILE}" ]]; then
  echo "ERROR: legacy cursor_commits.csv not found." >&2
  echo "Set LEGACY_CURSOR_COMMITS_FILE=/path/to/cursor_commits.csv" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1 || true)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
PANEL_SHA256="$(sha256sum "${PANEL_FILE}" | awk '{print $1}')"
LEGACY_SHA256="$(sha256sum "${LEGACY_CURSOR_COMMITS_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_PREFIX}-${IMPLEMENTATION_VERSION}: Cursor adoption timezone/month-boundary audit"
  echo "Started:                         $(date)"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python audit script:             ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Final b02 panel:                 ${PANEL_FILE}"
  echo "Final b02 panel SHA256:          ${PANEL_SHA256}"
  echo "Legacy cursor commits:           ${LEGACY_CURSOR_COMMITS_FILE}"
  echo "Legacy cursor commits SHA256:    ${LEGACY_SHA256}"
  echo "Treatment clone fallback:        ${TREATMENT_CLONE_DIR}"
  echo "Explicit timezones:              ${TIMEZONES}"
  echo "Expected treatment repos:        ${EXPECTED_TREATMENT_REPOS}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Git timeout seconds:             ${GIT_TIMEOUT_SECONDS}"
  echo "Main output dir:                 ${MAIN_OUTPUT_DIR}"
  echo "Temporary output dir:            ${TMP_OUTPUT_DIR}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
  echo

  echo "** Step 1: Validate Python audit implementation"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test --log-level "${LOG_LEVEL}"
  echo

  echo "** Step 2: Compile Python audit implementation"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"
  echo

  echo "** Step 3: Audit exact Cursor adoption timestamps and timezone month buckets"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --panel-file ${PANEL_FILE} --legacy-cursor-commits-file ${LEGACY_CURSOR_COMMITS_FILE} --timezones ${TIMEZONES} ..."
  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --panel-file "${PANEL_FILE}" \
    --legacy-cursor-commits-file "${LEGACY_CURSOR_COMMITS_FILE}" \
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}" \
    --timezones "${TIMEZONES}" \
    --commit-output "${COMMIT_OUTPUT}" \
    --repo-output "${REPO_OUTPUT}" \
    --difference-output "${DIFFERENCE_OUTPUT}" \
    --offset-output "${OFFSET_OUTPUT}" \
    --qc-output "${QC_OUTPUT}" \
    --summary-output "${SUMMARY_OUTPUT}" \
    --expected-treatment-repos "${EXPECTED_TREATMENT_REPOS}" \
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
    --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}" \
    --log-level "${LOG_LEVEL}"
  echo

  echo "** Step 4: Output checks"
  echo "------------------------------------------------------------"
  for required_output in \
    "${COMMIT_OUTPUT}" \
    "${REPO_OUTPUT}" \
    "${DIFFERENCE_OUTPUT}" \
    "${OFFSET_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  do
    if [[ ! -f "${required_output}" ]]; then
      echo "ERROR: expected output not found: ${required_output}" >&2
      exit 1
    fi
  done

  wc -l \
    "${COMMIT_OUTPUT}" \
    "${REPO_OUTPUT}" \
    "${DIFFERENCE_OUTPUT}" \
    "${OFFSET_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo

  echo "Timezone audit QC:"
  cat "${QC_OUTPUT}"
  echo

  echo "Compact summary:"
  cat "${SUMMARY_OUTPUT}"
  echo

  echo "Legacy inferred UTC offsets:"
  cat "${OFFSET_OUTPUT}"
  echo

  echo "Repositories with timing differences or recorded-event mismatch:"
  if [[ "$(wc -l < "${DIFFERENCE_OUTPUT}")" -le 1 ]]; then
    echo "No repository-level timing differences were found."
  else
    cat "${DIFFERENCE_OUTPUT}"
  fi
  echo

  echo "============================================================"
  echo "${RUN_PREFIX}-${IMPLEMENTATION_VERSION} completed successfully."
  echo "Completed:                       $(date)"
  echo "Repository summary:              ${REPO_OUTPUT}"
  echo "Timezone differences:            ${DIFFERENCE_OUTPUT}"
  echo "Legacy offset summary:           ${OFFSET_OUTPUT}"
  echo "QC:                              ${QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next decision:                   whether a repository-specific corrected adoption month is warranted."
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
