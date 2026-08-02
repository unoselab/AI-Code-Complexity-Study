#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-a01: Audit cloned repositories against matching.csv
# ============================================================
#
# Purpose:
#   Check whether the currently cloned treatment repositories are present as
#   treatment rows in the paper's matching.csv and whether their assigned
#   matched controls are available as valid Git repositories under the local
#   control clone directory.
#
# Design:
#   - This wrapper follows the validation, logging, and output-check pattern of
#     the existing Python experiment wrappers.
#   - It is independent and does not call an existing shell wrapper.
#   - All matching and clone-inspection logic is implemented in the Python
#     script passed through PY_SCRIPT.
#   - Repositories are inspected with read-only Git commands. No checkout,
#     reset, clean, pull, or other repository modification is performed.
#
# Required inputs:
#   data_baseline_backup/matching.csv
#   ../treatment-repos/
#   ../control-repos/
#
# Main outputs:
#   repo_x01/run-x-a01/clonedrepo_matching_alignment.csv
#     Repository-level alignment for cloned treatments, expected matched
#     controls, and extra control clones.
#
#   repo_x01/run-x-a01/clonedrepo_matching_pairs.csv
#     One row for each cloned treatment and each original matching slot 1-3.
#
# QC output:
#   repo_x01/tmp/run-x-a01/clonedrepo_matching_summary.csv
#
# Usage:
#   bash proc_sh_x01/run-x-a01-repo-matching.sh
#
# Strict validation:
#   FAIL_ON_MISMATCH=1 bash proc_sh_x01/run-x-a01-repo-matching.sh
#
# Optional path overrides:
#   MATCHING_FILE=/path/to/matching.csv
#   TREATMENT_CLONE_DIR=/path/to/treatment-repos
#   CONTROL_CLONE_DIR=/path/to/control-repos
#   OUTPUT_BASE_DIR=/path/to/output-root
#   PYTHON_BIN=/path/to/python
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-a01"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}-repo-matching-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/clonedrepo_matching.py}"

MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x01}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

ALIGNMENT_OUTPUT="${ALIGNMENT_OUTPUT:-${MAIN_OUTPUT_DIR}/clonedrepo_matching_alignment.csv}"
PAIRS_OUTPUT="${PAIRS_OUTPUT:-${MAIN_OUTPUT_DIR}/clonedrepo_matching_pairs.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/clonedrepo_matching_summary.csv}"

FAIL_ON_MISMATCH="${FAIL_ON_MISMATCH:-0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

case "${FAIL_ON_MISMATCH}" in
  0|1)
    ;;
  *)
    echo "ERROR: FAIL_ON_MISMATCH must be 0 or 1. Got: ${FAIL_ON_MISMATCH}" >&2
    exit 1
    ;;
esac

for required_file in "${PY_SCRIPT}" "${MATCHING_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

for required_dir in "${TREATMENT_CLONE_DIR}" "${CONTROL_CLONE_DIR}"; do
  if [[ ! -d "${required_dir}" ]]; then
    echo "ERROR: required directory not found: ${required_dir}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: audit cloned repositories against matching.csv"
  echo "Started:                     $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                ${PROJECT_ROOT}"
  echo "Python:                      ${PYTHON_BIN}"
  echo "Python script:               ${PY_SCRIPT}"
  echo "Matching file:               ${MATCHING_FILE}"
  echo "Treatment clone directory:   ${TREATMENT_CLONE_DIR}"
  echo "Control clone directory:     ${CONTROL_CLONE_DIR}"
  echo "Alignment output:            ${ALIGNMENT_OUTPUT}"
  echo "Pair output:                 ${PAIRS_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Fail on mismatch:            ${FAIL_ON_MISMATCH}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --matching-file "${MATCHING_FILE}"
  --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
  --control-clone-dir "${CONTROL_CLONE_DIR}"
  --alignment-output "${ALIGNMENT_OUTPUT}"
  --pairs-output "${PAIRS_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --log-level "${LOG_LEVEL}"
)

if [[ "${FAIL_ON_MISMATCH}" == "1" ]]; then
  COMMAND+=(--fail-on-mismatch)
fi

{
  echo
  echo "** Step 1: Run repository-matching alignment audit"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

for output_file in "${ALIGNMENT_OUTPUT}" "${PAIRS_OUTPUT}" "${SUMMARY_OUTPUT}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output was not created: ${output_file}" \
      | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l "${ALIGNMENT_OUTPUT}" "${PAIRS_OUTPUT}" "${SUMMARY_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:                   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Alignment output:            ${ALIGNMENT_OUTPUT}"
  echo "Pair output:                 ${PAIRS_OUTPUT}"
  echo "Summary output:              ${SUMMARY_OUTPUT}"
  echo "Log file:                    ${LOG_FILE}"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
