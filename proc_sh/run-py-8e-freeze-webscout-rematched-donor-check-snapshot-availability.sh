#!/usr/bin/env bash
# ==============================================================================
# run-py-8e: freeze the rematched Webscout donor and check snapshot availability
# ==============================================================================
#
# Purpose:
#   Freeze the rank-1 and rank-2 donor choices produced by run-py-8d before
#   opening any post-adoption AGC outcome, then verify that immutable Git
#   snapshots exist at the ends of 2025-04 and 2025-06.
#
# Inputs:
#   - run-py-8d common donor ranking CSV
#   - local control repository clones
#
# Outputs:
#   - frozen selected/fallback donor manifest with ranking SHA-256
#   - 2025-04 and 2025-06 snapshot availability audit
#   - validation, summary, and PASS/FAIL status files
#
# Safeguards:
#   - No AGC detector output or class-method count is read.
#   - No Difference-in-Differences model is run.
#   - Repository HEAD and working trees are not changed.
#   - The selected donor must be rank 1 and must not be an original control.
#
# This wrapper reuses the execution, logging, validation, and output-checking
# structure of the existing run-py wrappers, but is independent and does not
# call another wrapper.
#
# Typical execution:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8e-freeze-webscout-rematched-donor-check-snapshot-availability.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/freeze_webscout_rematched_donor_check_snapshot_availability.py}"

COMMON_DONOR_RANKING="${COMMON_DONOR_RANKING:-repo_python/run-py-8d/strict/specifications/range100_200/python_snapshot_ncloc/202410_local_control_rematching/webscout_local_control_rematching_common_donor_ranking.csv}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

EXPECTED_SELECTED_DONOR="${EXPECTED_SELECTED_DONOR:-Hack-a-Day/2024-Supercon-8-Add-On-Badge}"
EXPECTED_FALLBACK_DONOR="${EXPECTED_FALLBACK_DONOR:-viktoriasemaan/sa-ai-agent}"
SNAPSHOT_CUTOFF_1="${SNAPSHOT_CUTOFF_1:-2025-04-30T23:59:59+00:00}"
SNAPSHOT_CUTOFF_2="${SNAPSHOT_CUTOFF_2:-2025-06-30T23:59:59+00:00}"
EXCLUDED_DIRS="${EXCLUDED_DIRS:-.git,__pycache__,.venv,venv,env,node_modules,dist,build,.tox,.mypy_cache,.pytest_cache,coverage,.next,.nuxt}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-8e/strict/specifications/range100_200/python_snapshot_ncloc/202410_webscout_rematched_donor_freeze}"
OUTPUT_PREFIX="webscout_rematched_donor"
STATUS_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}_status.txt"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8e}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8e-freeze-webscout-donor-snapshot-availability-${RUN_TS}.log}"
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
  echo "run-py-8e: freeze rematched donor and check Git snapshot availability"
  echo "Started:                    ${STARTED}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Common donor ranking:       ${COMMON_DONOR_RANKING}"
  echo "Control clone root:         ${CONTROL_CLONE_ROOT}"
  echo "Expected selected donor:    ${EXPECTED_SELECTED_DONOR}"
  echo "Expected fallback donor:    ${EXPECTED_FALLBACK_DONOR}"
  echo "Snapshot cutoff 1:          ${SNAPSHOT_CUTOFF_1}"
  echo "Snapshot cutoff 2:          ${SNAPSHOT_CUTOFF_2}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Post-adoption AGC outcomes: NOT READ"
  echo "DiD execution:              NO"
  echo "Interpretation:             noncausal design-stage donor feasibility audit"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"

  require_file "${PY_SCRIPT}" "Python script"
  require_file "${COMMON_DONOR_RANKING}" "Common donor ranking"
  require_dir "${CONTROL_CLONE_ROOT}" "Control clone root"

  echo "Python script SHA:          $(sha256_file "${PY_SCRIPT}")"
  echo "Ranking SHA:                $(sha256_file "${COMMON_DONOR_RANKING}")"
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
    --common-donor-ranking "${COMMON_DONOR_RANKING}" \
    --control-clone-root "${CONTROL_CLONE_ROOT}" \
    --output-dir "${OUTPUT_DIR}" \
    --expected-selected-donor "${EXPECTED_SELECTED_DONOR}" \
    --expected-fallback-donor "${EXPECTED_FALLBACK_DONOR}" \
    --snapshot-cutoff-utc "${SNAPSHOT_CUTOFF_1}" \
    --snapshot-cutoff-utc "${SNAPSHOT_CUTOFF_2}" \
    --excluded-dirs "${EXCLUDED_DIRS}"

  require_file "${STATUS_FILE}" "Status file"
  STATUS_VALUE="$(head -n 1 "${STATUS_FILE}" | tr -d '\r')"
  if [[ "${STATUS_VALUE}" != "PASS" ]]; then
    echo "ERROR: Expected PASS status but found: ${STATUS_VALUE}"
    exit 1
  fi

  EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_freeze_manifest.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_snapshot_availability.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
    "${STATUS_FILE}"
  )
  for path in "${EXPECTED_OUTPUTS[@]}"; do
    require_file "${path}" "Expected output"
  done

  echo ""
  echo "================================================================================"
  echo "run-py-8e PASS"
  echo "Freeze manifest:            ${OUTPUT_DIR}/${OUTPUT_PREFIX}_freeze_manifest.csv"
  echo "Snapshot availability:      ${OUTPUT_DIR}/${OUTPUT_PREFIX}_snapshot_availability.csv"
  echo "Validation:                 ${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
  echo "Summary:                    ${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
  echo "Status:                     ${STATUS_FILE}"
  echo "Next step:                 preserve hashes before any AGC outcome extraction"
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
  echo "run-py-8e execution summary"
  echo "Started:              ${STARTED}"
  echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Elapsed:              ${ELAPSED}"
  echo "Exit code:            ${EXIT_CODE}"
  echo "Output directory:     ${OUTPUT_DIR}"
  echo "Log file:             ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"

exit "${EXIT_CODE}"
