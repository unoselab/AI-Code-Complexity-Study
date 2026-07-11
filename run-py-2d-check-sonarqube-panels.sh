#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2d: Check Python merged SonarQube matched panels
# ============================================================
#
# Purpose:
#   Check merged Python SonarQube panels created by run-py-2c.
#
# Inputs:
#   strict:
#     repo_python/run-py-2c/strict/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/run-py-2c/flexible/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=all bash run-py-2d-check-sonarqube-panels.sh
#
# Persistent output:
#   logs/run-py-2d_check_sonarqube_panels_<variant>_<timestamp>.log
#
# Temporary outputs:
#   check_sonarqube_panel.py requires summary and missing-row files.
#   They are created under repo_python/tmp/run-py-2d during validation
#   and removed automatically when the wrapper exits.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_check_sonarqube_panels_${PANEL_VARIANT}_${RUN_TS}.log}"

CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
TMP_PARENT_DIR="${TMP_PARENT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
TMP_WORK_DIR="${TMP_WORK_DIR:-${TMP_PARENT_DIR}/${PANEL_VARIANT}_${RUN_TS}}"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube.csv")
fi

cleanup_tmp_work_dir() {
  rm -rf "${TMP_WORK_DIR}"
  rmdir "${TMP_PARENT_DIR}" 2>/dev/null || true
}
trap cleanup_tmp_work_dir EXIT

mkdir -p "${LOG_DIR}" "${TMP_WORK_DIR}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: check Python merged SonarQube panels"
  echo "Started:          $(date)"
  echo "Script name:      ${SCRIPT_NAME}"
  echo "Run prefix:       ${RUN_PREFIX}"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "Panel input dir:  ${PANEL_INPUT_DIR}"
  echo "Temporary dir:    ${TMP_WORK_DIR}"
  echo "Persistent files: log only"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${CHECK_SCRIPT}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "Complete run-py-2c first for PANEL_VARIANT=${PANEL_LABEL}."
      exit 1
    fi

    SUMMARY_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_check_summary.csv"
    MISSING_OUTPUT="${TMP_WORK_DIR}/${PANEL_LABEL}_missing_analysis_outcomes.csv"

    echo
    echo "============================================================"
    echo "Checking panel: ${PANEL_LABEL}"
    echo "Input:          ${INPUT_FILE}"
    echo "Temporary summary: ${SUMMARY_OUTPUT}"
    echo "Temporary missing: ${MISSING_OUTPUT}"
    echo "============================================================"

    python "${CHECK_SCRIPT}" \
      --input "${INPUT_FILE}" \
      --summary-output "${SUMMARY_OUTPUT}" \
      --missing-output "${MISSING_OUTPUT}"

    echo
    echo "Validation completed for ${PANEL_LABEL}."
    echo "Temporary checker outputs will be removed when the wrapper exits."
  done

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:         $(date)"
  echo "Panel variant:     ${PANEL_VARIANT}"
  echo "Persistent output: ${LOG_FILE}"
  echo "Temporary outputs: removed automatically"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9d-check-sonarqube-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.