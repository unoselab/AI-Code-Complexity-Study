#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-b03-c: Audit Cursor treatment-history consistency
# ============================================================
#
# Purpose:
#   Verify whether each recorded monthly Cursor treatment date is still
#   supported by Cursor-related commits reachable from the exact frozen b02
#   analysis-tip commit used for the Python velocity panel.
#
# Design:
#   - This wrapper was adapted from the b03-b audit wrapper but is fully
#     self-contained and does not call any previous shell script.
#   - The Python program reads treatment repositories, recorded event months,
#     clone paths, and frozen analysis-tip commits from the final b02 panel.
#   - Legacy cursor_commits.csv rows are audited for Git-object resolution and
#     reachability from the frozen analysis tip.
#   - Each frozen reachable history is independently rescanned using the same
#     Cursor path predicate as the original analyzer: .cursorrules,
#     .cursorignore, or any path containing a .cursor component.
#   - Non-root commits are verified against the first parent, matching the
#     original analyzer's Cursor diff semantics.
#   - America/New_York is the default calendar timezone because the preceding
#     b03-b audit reconstructed the legacy runtime wall clock as Eastern-time
#     behavior. Override CALENDAR_TIMEZONE only for a deliberate sensitivity.
#   - This stage is audit-only. It does not rewrite event months and does not
#     fit a DiD model.
#
# Required inputs:
#   repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv
#   data_baseline_backup/cursor_commits.csv OR data/cursor_commits.csv
#   local treatment repository clones referenced by the b02 panel
#
# Main outputs:
#   repo_x01/run-x-b03-c/cursor_treatment_history_current_commit_scan.csv
#   repo_x01/run-x-b03-c/cursor_treatment_history_legacy_commit_audit.csv
#   repo_x01/run-x-b03-c/cursor_treatment_history_repo_summary.csv
#   repo_x01/run-x-b03-c/cursor_treatment_history_inconsistencies.csv
#   repo_x01/run-x-b03-c/cursor_treatment_history_candidate_actions.csv
#   repo_x01/run-x-b03-c/cursor_treatment_history_qc.csv
#
# Compact summary:
#   repo_x01/tmp/run-x-b03-c/cursor_treatment_history_summary.csv
#
# Default run:
#   bash proc_sh_x01/run-x-b03-c-audit-cursor-treatment-history.sh
#
# Optional overrides:
#   PANEL_FILE=/path/to/final_b02_panel.csv
#   LEGACY_CURSOR_COMMITS_FILE=/path/to/cursor_commits.csv
#   TREATMENT_CLONE_DIR=/path/to/treatment-repos
#   CALENDAR_TIMEZONE=America/New_York
#   EXPECTED_TREATMENT_REPOS=63
#   STRICT_EXPECTED_COUNTS=1
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-b03-c"
IMPLEMENTATION_VERSION="v1"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-cursor-treatment-history-audit-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_cursor_treatment_history.py}"

PANEL_FILE="${PANEL_FILE:-repo_x01/run-x-b02/panels/velocity_did_panel_python_added_lines_sonarqube.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CALENDAR_TIMEZONE="${CALENDAR_TIMEZONE:-America/New_York}"
EXPECTED_TREATMENT_REPOS="${EXPECTED_TREATMENT_REPOS:-63}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-120}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CURRENT_COMMIT_OUTPUT="${CURRENT_COMMIT_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_current_commit_scan.csv}"
LEGACY_AUDIT_OUTPUT="${LEGACY_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_legacy_commit_audit.csv}"
REPO_OUTPUT="${REPO_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_repo_summary.csv}"
INCONSISTENCY_OUTPUT="${INCONSISTENCY_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_inconsistencies.csv}"
CANDIDATE_OUTPUT="${CANDIDATE_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_candidate_actions.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/cursor_treatment_history_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/cursor_treatment_history_summary.csv}"

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

# Resolve the original Cursor-commit artifact independently. Prefer the baseline
# backup so the audit compares current frozen history with the original evidence.
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
  echo "${RUN_PREFIX}-${IMPLEMENTATION_VERSION}: Cursor treatment-history consistency audit"
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
  echo "Calendar timezone:               ${CALENDAR_TIMEZONE}"
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

  echo "** Step 3: Audit treatment evidence in frozen repository histories"
  echo "------------------------------------------------------------"
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --panel-file ${PANEL_FILE} --legacy-cursor-commits-file ${LEGACY_CURSOR_COMMITS_FILE} --calendar-timezone ${CALENDAR_TIMEZONE} ..."
  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --panel-file "${PANEL_FILE}" \
    --legacy-cursor-commits-file "${LEGACY_CURSOR_COMMITS_FILE}" \
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}" \
    --calendar-timezone "${CALENDAR_TIMEZONE}" \
    --current-commit-output "${CURRENT_COMMIT_OUTPUT}" \
    --legacy-audit-output "${LEGACY_AUDIT_OUTPUT}" \
    --repo-output "${REPO_OUTPUT}" \
    --inconsistency-output "${INCONSISTENCY_OUTPUT}" \
    --candidate-output "${CANDIDATE_OUTPUT}" \
    --qc-output "${QC_OUTPUT}" \
    --summary-output "${SUMMARY_OUTPUT}" \
    --expected-treatment-repos "${EXPECTED_TREATMENT_REPOS}" \
    --strict-expected-counts "${STRICT_EXPECTED_COUNTS}" \
    --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}" \
    --log-level "${LOG_LEVEL}"
  echo

  echo "** Step 4: Output checks"
  echo "------------------------------------------------------------"
  for path in \
    "${CURRENT_COMMIT_OUTPUT}" \
    "${LEGACY_AUDIT_OUTPUT}" \
    "${REPO_OUTPUT}" \
    "${INCONSISTENCY_OUTPUT}" \
    "${CANDIDATE_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  do
    if [[ ! -f "${path}" ]]; then
      echo "ERROR: expected output not found: ${path}" >&2
      exit 1
    fi
  done

  wc -l \
    "${REPO_OUTPUT}" \
    "${INCONSISTENCY_OUTPUT}" \
    "${CANDIDATE_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "Treatment-history QC:"
  cat "${QC_OUTPUT}"
  echo
  echo "Candidate actions:"
  cat "${CANDIDATE_OUTPUT}"
  echo

  echo "============================================================"
  echo "${RUN_PREFIX}-${IMPLEMENTATION_VERSION} completed successfully."
  echo "Completed:                       $(date)"
  echo "Repository summary:              ${REPO_OUTPUT}"
  echo "Current-history Cursor commits:  ${CURRENT_COMMIT_OUTPUT}"
  echo "Legacy reachability audit:       ${LEGACY_AUDIT_OUTPUT}"
  echo "Inconsistencies:                 ${INCONSISTENCY_OUTPUT}"
  echo "Candidate actions:               ${CANDIDATE_OUTPUT}"
  echo "QC:                              ${QC_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next decision:                   whether evidence-based repository-specific treatment-month correction is warranted."
  echo "============================================================"
} 2>&1 | tee "${LOG_FILE}"
