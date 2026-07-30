#!/usr/bin/env bash
# ==============================================================================
# run-py-8f: audit frozen donor commit activity in 2025-04 and 2025-06
# ==============================================================================
#
# Purpose:
#   Preserve the run-py-8e frozen donor choice and determine whether the selected
#   and fallback donors have actual Git commits inside the two target months.
#   This is a non-outcome feasibility audit before any AGC extraction.
#
# Inputs:
#   - run-py-8e frozen donor manifest
#   - run-py-8e snapshot availability audit
#   - local control repository clones
#
# Outputs:
#   - donor-by-month commit counts and first/last commit timestamps
#   - freeze/input provenance with SHA-256 hashes
#   - validation, summary, and PASS/FAIL status files
#
# Safeguards:
#   - No AGC detector output or class-method count is read.
#   - No Difference-in-Differences model is run.
#   - Repository HEAD and working trees are not changed.
#   - A month with zero commits is recorded as inactive, not treated as failure.
#
# This wrapper copies and adapts the logging and validation structure of
# run-py-8e, but it is independent and does not call any earlier wrapper.
#
# Typical execution:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8f-audit-webscout-rematched-donor-monthly-commit-activity.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/audit_webscout_rematched_donor_monthly_commit_activity.py}"

RUN_PY_8E_ROOT="${RUN_PY_8E_ROOT:-repo_python/run-py-8e/strict/specifications/range100_200/python_snapshot_ncloc/202410_webscout_rematched_donor_freeze}"
FREEZE_MANIFEST="${FREEZE_MANIFEST:-${RUN_PY_8E_ROOT}/webscout_rematched_donor_freeze_manifest.csv}"
SNAPSHOT_AVAILABILITY="${SNAPSHOT_AVAILABILITY:-${RUN_PY_8E_ROOT}/webscout_rematched_donor_snapshot_availability.csv}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

EXPECTED_SELECTED_DONOR="${EXPECTED_SELECTED_DONOR:-Hack-a-Day/2024-Supercon-8-Add-On-Badge}"
EXPECTED_FALLBACK_DONOR="${EXPECTED_FALLBACK_DONOR:-viktoriasemaan/sa-ai-agent}"
TARGET_MONTH_1="${TARGET_MONTH_1:-2025-04}"
TARGET_MONTH_2="${TARGET_MONTH_2:-2025-06}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-8f/strict/specifications/range100_200/python_snapshot_ncloc/202410_webscout_rematched_donor_commit_activity_audit}"
OUTPUT_PREFIX="webscout_rematched_donor_commit_activity"
STATUS_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}_status.txt"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8f}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8f-webscout-donor-monthly-commit-activity-${RUN_TS}.log}"
mkdir -p "${LOG_DIR}"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}"
    exit 1
  fi
}

require_dir() {
  local path="$1"
  local label="$2"
  if [[ ! -d "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}"
    exit 1
  fi
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

START_EPOCH="$(date +%s)"
STARTED="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-8f: audit frozen donor target-month Git commit activity"
  echo "Started:                    ${STARTED}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Freeze manifest:            ${FREEZE_MANIFEST}"
  echo "Snapshot availability:      ${SNAPSHOT_AVAILABILITY}"
  echo "Control clone root:         ${CONTROL_CLONE_ROOT}"
  echo "Expected selected donor:    ${EXPECTED_SELECTED_DONOR}"
  echo "Expected fallback donor:    ${EXPECTED_FALLBACK_DONOR}"
  echo "Target month 1:             ${TARGET_MONTH_1}"
  echo "Target month 2:             ${TARGET_MONTH_2}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Post-adoption AGC outcomes: NOT READ"
  echo "DiD execution:              NO"
  echo "Interpretation:             noncausal design-stage donor feasibility audit"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"

  require_file "${PY_SCRIPT}" "Python script"
  require_file "${FREEZE_MANIFEST}" "Freeze manifest"
  require_file "${SNAPSHOT_AVAILABILITY}" "Snapshot availability"
  require_dir "${CONTROL_CLONE_ROOT}" "Control clone root"

  echo "Python script SHA:          $(sha256_file "${PY_SCRIPT}")"
  echo "Freeze manifest SHA:        $(sha256_file "${FREEZE_MANIFEST}")"
  echo "Snapshot availability SHA:  $(sha256_file "${SNAPSHOT_AVAILABILITY}")"
  echo "================================================================================"

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
  fi

  if [[ -e "${OUTPUT_DIR}" ]]; then
    if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
      rm -rf "${OUTPUT_DIR}"
    else
      echo "ERROR: Output directory already exists."
      echo "       Set OVERWRITE_OUTPUT=1 to replace: ${OUTPUT_DIR}"
      exit 1
    fi
  fi
  mkdir -p "${OUTPUT_DIR}"

  "${PYTHON_BIN}" "${PY_SCRIPT}" \
    --freeze-manifest "${FREEZE_MANIFEST}" \
    --snapshot-availability "${SNAPSHOT_AVAILABILITY}" \
    --control-clone-root "${CONTROL_CLONE_ROOT}" \
    --output-dir "${OUTPUT_DIR}" \
    --expected-selected-donor "${EXPECTED_SELECTED_DONOR}" \
    --expected-fallback-donor "${EXPECTED_FALLBACK_DONOR}" \
    --target-month "${TARGET_MONTH_1}" \
    --target-month "${TARGET_MONTH_2}"

  require_file "${STATUS_FILE}" "Status file"
  STATUS_VALUE="$(head -n 1 "${STATUS_FILE}" | tr -d '\r')"
  if [[ "${STATUS_VALUE}" != "PASS" ]]; then
    echo "ERROR: Expected PASS status but found: ${STATUS_VALUE}"
    exit 1
  fi

  EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_monthly_commits.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_provenance.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
    "${STATUS_FILE}"
  )
  for path in "${EXPECTED_OUTPUTS[@]}"; do
    require_file "${path}" "Expected output"
  done

  echo ""
  echo "================================================================================"
  echo "run-py-8f PASS"
  echo "Monthly commits:            ${OUTPUT_DIR}/${OUTPUT_PREFIX}_monthly_commits.csv"
  echo "Provenance:                 ${OUTPUT_DIR}/${OUTPUT_PREFIX}_provenance.csv"
  echo "Validation:                 ${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
  echo "Summary:                    ${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
  echo "Status:                     ${STATUS_FILE}"
  echo "Next step:                 interpret active/inactive target months before AGC extraction"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

EXIT_CODE="${PIPESTATUS[0]}"
END_EPOCH="$(date +%s)"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED '%02d:%02d:%02d' \
  "$((ELAPSED_SECONDS / 3600))" \
  "$(((ELAPSED_SECONDS % 3600) / 60))" \
  "$((ELAPSED_SECONDS % 60))"

{
  echo ""
  echo "================================================================================"
  echo "run-py-8f execution summary"
  echo "Started:              ${STARTED}"
  echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Elapsed:              ${ELAPSED}"
  echo "Exit code:            ${EXIT_CODE}"
  echo "Output directory:     ${OUTPUT_DIR}"
  echo "Log file:             ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"

exit "${EXIT_CODE}"
