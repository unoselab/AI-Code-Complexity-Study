#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-c04d v1: Persist and inspect unresolved C04 snapshots
# ============================================================
#
# Purpose:
#   Preserve the five unresolved C04 historical snapshots under the external
#   temporary disk before changing the production C04 analyzer.
#
# Inputs:
#   repo_x01/run-x-c04/python_primary_whole_repo_cloc_failures.csv
#     Expected to contain exactly five failed snapshot rows from C04 v2.
#
# Outputs:
#   /mnt/samsung850ev/tmp/run-x-c04d-missing-snapshots-<timestamp>/
#     diagnostic_summary.csv
#     diagnostic_status_counts.csv
#     one persistent directory per unresolved snapshot containing:
#       snapshot.tar
#       tree/
#       git-ls-tree.txt
#       file-inventory.csv
#       extension-summary.csv
#       system and Python tar diagnostics
#       cloc summary/by-file/stdout CSV files when created
#       cloc stdout/stderr files
#
# Safety:
#   - The cloned repositories are read only.
#   - Existing C04 outputs are read only.
#   - No checkout, fetch, pull, reset, clean, or worktree command is used.
#   - All diagnostic artifacts are kept for manual inspection.
#
# Run:
#   bash proc_sh_x01/run-x-c04d-diagnose-missing-snapshots.sh
#
# Optional overrides:
#   DIAGNOSTIC_BASE_ROOT=/mnt/samsung850ev/tmp
#   DIAGNOSTIC_ROOT=/custom/path
#   CLOC_BIN=cloc
#   GIT_TIMEOUT_SECONDS=600
#   CLOC_TIMEOUT_SECONDS=900
#   EXPECTED_FAILURES=5
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-c04d"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-diagnose-missing-snapshots-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
CLOC_BIN="${CLOC_BIN:-cloc}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/diagnose_c04_missing_snapshots.py}"
FAILURE_FILE="${FAILURE_FILE:-repo_x01/run-x-c04/python_primary_whole_repo_cloc_failures.csv}"
DIAGNOSTIC_BASE_ROOT="${DIAGNOSTIC_BASE_ROOT:-/mnt/samsung850ev/tmp}"
DIAGNOSTIC_ROOT="${DIAGNOSTIC_ROOT:-${DIAGNOSTIC_BASE_ROOT}/${RUN_PREFIX}-missing-snapshots-${RUN_TS}}"
GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-600}"
CLOC_TIMEOUT_SECONDS="${CLOC_TIMEOUT_SECONDS:-900}"
EXPECTED_FAILURES="${EXPECTED_FAILURES:-5}"

for numeric_value in "${GIT_TIMEOUT_SECONDS}" "${CLOC_TIMEOUT_SECONDS}" "${EXPECTED_FAILURES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]] || [[ "${numeric_value}" -lt 1 ]]; then
    echo "ERROR: timeout and count options must be positive integers." >&2
    exit 1
  fi
done

for required_file in "${PY_SCRIPT}" "${FAILURE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for required_command in git tar "${CLOC_BIN}"; do
  if ! command -v "${required_command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${required_command}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${DIAGNOSTIC_BASE_ROOT}"

exec > >(tee -a "${LOG_FILE}") 2>&1

printf '%s\n' "============================================================"
printf '%-32s %s\n' "${RUN_LABEL}:" "persist and inspect unresolved C04 snapshots"
printf '%-32s %s\n' "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '%-32s %s\n' "Project root:" "${PROJECT_ROOT}"
printf '%-32s %s\n' "Python:" "${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
printf '%-32s %s\n' "cloc:" "${CLOC_BIN} ($(${CLOC_BIN} --version 2>&1 | head -n 1))"
printf '%-32s %s\n' "Failure file:" "${FAILURE_FILE}"
printf '%-32s %s\n' "Expected failures:" "${EXPECTED_FAILURES}"
printf '%-32s %s\n' "Diagnostic root:" "${DIAGNOSTIC_ROOT}"
printf '%-32s %s\n' "Log file:" "${LOG_FILE}"
printf '%s\n' "============================================================"

"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --failure-file "${FAILURE_FILE}" \
  --diagnostic-root "${DIAGNOSTIC_ROOT}" \
  --project-root "${PROJECT_ROOT}" \
  --cloc-bin "${CLOC_BIN}" \
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}" \
  --cloc-timeout-seconds "${CLOC_TIMEOUT_SECONDS}" \
  --expected-failures "${EXPECTED_FAILURES}"

printf '\n%s\n' "============================================================"
printf '%s\n' "${RUN_LABEL} completed."
printf '%-32s %s\n' "Completed:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '%-32s %s\n' "Diagnostic root:" "${DIAGNOSTIC_ROOT}"
printf '%-32s %s\n' "Summary:" "${DIAGNOSTIC_ROOT}/diagnostic_summary.csv"
printf '%-32s %s\n' "Status counts:" "${DIAGNOSTIC_ROOT}/diagnostic_status_counts.csv"
printf '%-32s %s\n' "Log file:" "${LOG_FILE}"
printf '%s\n' "Next step: inspect the five persistent trees and raw cloc diagnostics"
printf '%s\n' "============================================================"
