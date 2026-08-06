#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# run-x-d02 v1: Prepare token-py repository-month panel
# ============================================================
#
# Purpose:
#   Join the fully classified run-x-d01b-v2 snapshot metric to the final
#   run-x-a05 Model A repository-month panel.
#
# Analysis design:
#   - preserve every Model A outcome, covariate, repository identifier,
#     calendar index, and treatment-timing field;
#   - validate the 1,954-row panel against the 1,496-snapshot Model C manifest;
#   - join by normalized dataset source, repository name, and exact commit SHA;
#   - retain the 1,495 metric-available snapshots covering 1,953 repo-months;
#   - keep the manually reviewed TradeMind snapshot in explicit exclusion
#     outputs without imputing or accepting its partial metric;
#   - require zero unclassified unresolved snapshots;
#   - verify that all 63 treatment repositories remain Borusyak-estimable after
#     the single explicit repo-month exclusion;
#   - create log1p and companion metric columns for the later D03 DiD analysis.
#
# Required inputs:
#   repo_x01/run-x-a05/velocity_did_panel_model_a.csv
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#   repo_x02/run-x-d01b/model_c_token_py_snapshot_results_resolved.csv
#   repo_x02/run-x-d01b/model_c_token_py_excluded_after_manual_review.csv
#
# Main outputs:
#   repo_x02/run-x-d02/velocity_did_panel_token_py_100_200_all_rows.csv
#   repo_x02/run-x-d02/velocity_did_panel_token_py_100_200.csv
#   repo_x02/run-x-d02/token_py_100_200_snapshot_join_audit.csv
#   repo_x02/run-x-d02/token_py_100_200_repo_month_exclusions.csv
#   repo_x02/run-x-d02/token_py_100_200_panel_unresolved.csv
#   repo_x02/run-x-d02/token_py_100_200_treatment_estimability.csv
#   repo_x02/run-x-d02/token_py_100_200_panel_qc.csv
#
# Summary output:
#   repo_x02/tmp/run-x-d02/token_py_100_200_panel_summary.csv
#
# Run:
#   bash proc_sh_x02/run-x-d02-prepare-token-py-repo-month-panel.sh
#
# Optional overrides:
#   PYTHON_BIN=/path/to/python
#   BASE_PANEL_FILE=...
#   SNAPSHOT_MANIFEST_FILE=...
#   RESOLVED_SNAPSHOT_RESULTS_FILE=...
#   EXPLICIT_EXCLUSIONS_FILE=...
#   STRICT_EXPECTED_COUNTS=1
#   LOG_LEVEL=INFO
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d02"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-prepare-token-py-repo-month-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x02/prepare_token_py_repo_month_panel-v1.py}"

BASE_PANEL_FILE="${BASE_PANEL_FILE:-repo_x01/run-x-a05/velocity_did_panel_model_a.csv}"
SNAPSHOT_MANIFEST_FILE="${SNAPSHOT_MANIFEST_FILE:-repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv}"
RESOLVED_SNAPSHOT_RESULTS_FILE="${RESOLVED_SNAPSHOT_RESULTS_FILE:-repo_x02/run-x-d01b/model_c_token_py_snapshot_results_resolved.csv}"
EXPLICIT_EXCLUSIONS_FILE="${EXPLICIT_EXCLUSIONS_FILE:-repo_x02/run-x-d01b/model_c_token_py_excluded_after_manual_review.csv}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_x02}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_OUTPUT_DIR="${TMP_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

ALL_ROWS_PANEL_OUTPUT="${ALL_ROWS_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_token_py_100_200_all_rows.csv}"
USABLE_PANEL_OUTPUT="${USABLE_PANEL_OUTPUT:-${MAIN_OUTPUT_DIR}/velocity_did_panel_token_py_100_200.csv}"
SNAPSHOT_AUDIT_OUTPUT="${SNAPSHOT_AUDIT_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_snapshot_join_audit.csv}"
REPO_MONTH_EXCLUSIONS_OUTPUT="${REPO_MONTH_EXCLUSIONS_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_repo_month_exclusions.csv}"
UNRESOLVED_OUTPUT="${UNRESOLVED_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_panel_unresolved.csv}"
TREATMENT_ESTIMABILITY_OUTPUT="${TREATMENT_ESTIMABILITY_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_treatment_estimability.csv}"
QC_OUTPUT="${QC_OUTPUT:-${MAIN_OUTPUT_DIR}/token_py_100_200_panel_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${TMP_OUTPUT_DIR}/token_py_100_200_panel_summary.csv}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_INPUT_PANEL_ROWS="${EXPECTED_INPUT_PANEL_ROWS:-1954}"
EXPECTED_INPUT_SNAPSHOTS="${EXPECTED_INPUT_SNAPSHOTS:-1496}"
EXPECTED_INPUT_TREATMENT_PANEL_ROWS="${EXPECTED_INPUT_TREATMENT_PANEL_ROWS:-914}"
EXPECTED_INPUT_CONTROL_PANEL_ROWS="${EXPECTED_INPUT_CONTROL_PANEL_ROWS:-1040}"
EXPECTED_INPUT_TREATMENT_SNAPSHOTS="${EXPECTED_INPUT_TREATMENT_SNAPSHOTS:-790}"
EXPECTED_INPUT_CONTROL_SNAPSHOTS="${EXPECTED_INPUT_CONTROL_SNAPSHOTS:-706}"
EXPECTED_OUTPUT_PANEL_ROWS="${EXPECTED_OUTPUT_PANEL_ROWS:-1953}"
EXPECTED_OUTPUT_SNAPSHOTS="${EXPECTED_OUTPUT_SNAPSHOTS:-1495}"
EXPECTED_OUTPUT_TREATMENT_PANEL_ROWS="${EXPECTED_OUTPUT_TREATMENT_PANEL_ROWS:-913}"
EXPECTED_OUTPUT_CONTROL_PANEL_ROWS="${EXPECTED_OUTPUT_CONTROL_PANEL_ROWS:-1040}"
EXPECTED_OUTPUT_TREATMENT_SNAPSHOTS="${EXPECTED_OUTPUT_TREATMENT_SNAPSHOTS:-789}"
EXPECTED_OUTPUT_CONTROL_SNAPSHOTS="${EXPECTED_OUTPUT_CONTROL_SNAPSHOTS:-706}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_EXPLICIT_EXCLUDED_SNAPSHOTS="${EXPECTED_EXPLICIT_EXCLUDED_SNAPSHOTS:-1}"
EXPECTED_EXPLICIT_EXCLUDED_PANEL_ROWS="${EXPECTED_EXPLICIT_EXCLUDED_PANEL_ROWS:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import numpy, pandas' >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON_BIN} must provide numpy and pandas." >&2
  exit 1
fi

if [[ "${STRICT_EXPECTED_COUNTS}" != "0" && "${STRICT_EXPECTED_COUNTS}" != "1" ]]; then
  echo "ERROR: STRICT_EXPECTED_COUNTS must be 0 or 1." >&2
  exit 1
fi

for numeric_value in \
  "${EXPECTED_INPUT_PANEL_ROWS}" \
  "${EXPECTED_INPUT_SNAPSHOTS}" \
  "${EXPECTED_INPUT_TREATMENT_PANEL_ROWS}" \
  "${EXPECTED_INPUT_CONTROL_PANEL_ROWS}" \
  "${EXPECTED_INPUT_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_INPUT_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_OUTPUT_PANEL_ROWS}" \
  "${EXPECTED_OUTPUT_SNAPSHOTS}" \
  "${EXPECTED_OUTPUT_TREATMENT_PANEL_ROWS}" \
  "${EXPECTED_OUTPUT_CONTROL_PANEL_ROWS}" \
  "${EXPECTED_OUTPUT_TREATMENT_SNAPSHOTS}" \
  "${EXPECTED_OUTPUT_CONTROL_SNAPSHOTS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" \
  "${EXPECTED_CONTROL_REPOSITORIES}" \
  "${EXPECTED_EXPLICIT_EXCLUDED_SNAPSHOTS}" \
  "${EXPECTED_EXPLICIT_EXCLUDED_PANEL_ROWS}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: expected-count options must contain non-negative integers." >&2
    exit 1
  fi
done

for required_file in \
  "${PY_SCRIPT}" \
  "${BASE_PANEL_FILE}" \
  "${SNAPSHOT_MANIFEST_FILE}" \
  "${RESOLVED_SNAPSHOT_RESULTS_FILE}" \
  "${EXPLICIT_EXCLUSIONS_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_OUTPUT_DIR}"

if find "${MAIN_OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -type f -print -quit | grep -q .; then
  BACKUP_DIR="${MAIN_OUTPUT_DIR}/local-${IMPLEMENTATION_VERSION}-backup-${RUN_TS}"
  mkdir -p "${BACKUP_DIR}"
  find "${MAIN_OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -type f -exec mv -t "${BACKUP_DIR}" {} +
  MIGRATION_NOTE="moved previous D02 outputs to ${BACKUP_DIR}"
else
  MIGRATION_NOTE="none"
fi

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
BASE_PANEL_SHA256="$(sha256sum "${BASE_PANEL_FILE}" | awk '{print $1}')"
SNAPSHOT_MANIFEST_SHA256="$(sha256sum "${SNAPSHOT_MANIFEST_FILE}" | awk '{print $1}')"
RESOLVED_RESULTS_SHA256="$(sha256sum "${RESOLVED_SNAPSHOT_RESULTS_FILE}" | awk '{print $1}')"
EXCLUSIONS_SHA256="$(sha256sum "${EXPLICIT_EXCLUSIONS_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "${RUN_LABEL}: prepare token-py repository-month panel"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PY_SCRIPT}"
  echo "Python script SHA256:             ${PY_SCRIPT_SHA256}"
  echo "Base Model A panel:              ${BASE_PANEL_FILE}"
  echo "Base panel SHA256:               ${BASE_PANEL_SHA256}"
  echo "Snapshot manifest:               ${SNAPSHOT_MANIFEST_FILE}"
  echo "Snapshot manifest SHA256:        ${SNAPSHOT_MANIFEST_SHA256}"
  echo "Resolved D01b results:           ${RESOLVED_SNAPSHOT_RESULTS_FILE}"
  echo "Resolved results SHA256:         ${RESOLVED_RESULTS_SHA256}"
  echo "Explicit exclusions:             ${EXPLICIT_EXCLUSIONS_FILE}"
  echo "Explicit exclusions SHA256:      ${EXCLUSIONS_SHA256}"
  echo "All-row panel output:            ${ALL_ROWS_PANEL_OUTPUT}"
  echo "Usable panel output:             ${USABLE_PANEL_OUTPUT}"
  echo "Snapshot audit output:           ${SNAPSHOT_AUDIT_OUTPUT}"
  echo "Repo-month exclusions output:    ${REPO_MONTH_EXCLUSIONS_OUTPUT}"
  echo "Unresolved output:               ${UNRESOLVED_OUTPUT}"
  echo "Treatment estimability output:   ${TREATMENT_ESTIMABILITY_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Expected input rows/snapshots:   ${EXPECTED_INPUT_PANEL_ROWS}/${EXPECTED_INPUT_SNAPSHOTS}"
  echo "Expected usable rows/snapshots:  ${EXPECTED_OUTPUT_PANEL_ROWS}/${EXPECTED_OUTPUT_SNAPSHOTS}"
  echo "Expected input T/C rows:         ${EXPECTED_INPUT_TREATMENT_PANEL_ROWS}/${EXPECTED_INPUT_CONTROL_PANEL_ROWS}"
  echo "Expected usable T/C rows:        ${EXPECTED_OUTPUT_TREATMENT_PANEL_ROWS}/${EXPECTED_OUTPUT_CONTROL_PANEL_ROWS}"
  echo "Expected explicit exclusions:    ${EXPECTED_EXPLICIT_EXCLUDED_SNAPSHOTS} snapshot, ${EXPECTED_EXPLICIT_EXCLUDED_PANEL_ROWS} row"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Migration note:                  ${MIGRATION_NOTE}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${PY_SCRIPT}"
  --base-panel-file "${BASE_PANEL_FILE}"
  --snapshot-manifest-file "${SNAPSHOT_MANIFEST_FILE}"
  --resolved-snapshot-results-file "${RESOLVED_SNAPSHOT_RESULTS_FILE}"
  --explicit-exclusions-file "${EXPLICIT_EXCLUSIONS_FILE}"
  --all-rows-panel-output "${ALL_ROWS_PANEL_OUTPUT}"
  --usable-panel-output "${USABLE_PANEL_OUTPUT}"
  --snapshot-audit-output "${SNAPSHOT_AUDIT_OUTPUT}"
  --repo-month-exclusions-output "${REPO_MONTH_EXCLUSIONS_OUTPUT}"
  --unresolved-output "${UNRESOLVED_OUTPUT}"
  --treatment-estimability-output "${TREATMENT_ESTIMABILITY_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-input-panel-rows "${EXPECTED_INPUT_PANEL_ROWS}"
  --expected-input-snapshots "${EXPECTED_INPUT_SNAPSHOTS}"
  --expected-input-treatment-panel-rows "${EXPECTED_INPUT_TREATMENT_PANEL_ROWS}"
  --expected-input-control-panel-rows "${EXPECTED_INPUT_CONTROL_PANEL_ROWS}"
  --expected-input-treatment-snapshots "${EXPECTED_INPUT_TREATMENT_SNAPSHOTS}"
  --expected-input-control-snapshots "${EXPECTED_INPUT_CONTROL_SNAPSHOTS}"
  --expected-output-panel-rows "${EXPECTED_OUTPUT_PANEL_ROWS}"
  --expected-output-snapshots "${EXPECTED_OUTPUT_SNAPSHOTS}"
  --expected-output-treatment-panel-rows "${EXPECTED_OUTPUT_TREATMENT_PANEL_ROWS}"
  --expected-output-control-panel-rows "${EXPECTED_OUTPUT_CONTROL_PANEL_ROWS}"
  --expected-output-treatment-snapshots "${EXPECTED_OUTPUT_TREATMENT_SNAPSHOTS}"
  --expected-output-control-snapshots "${EXPECTED_OUTPUT_CONTROL_SNAPSHOTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-explicit-excluded-snapshots "${EXPECTED_EXPLICIT_EXCLUDED_SNAPSHOTS}"
  --expected-explicit-excluded-panel-rows "${EXPECTED_EXPLICIT_EXCLUDED_PANEL_ROWS}"
  --log-level "${LOG_LEVEL}"
)

{
  echo
  echo "** Step 1: Join resolved snapshot metrics to the Model A panel"
  echo "------------------------------------------------------------"
  printf 'Command:'
  printf ' %q' "${COMMAND[@]}"
  printf '\n\n'
} | tee -a "${LOG_FILE}"

"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${ALL_ROWS_PANEL_OUTPUT}"
  "${USABLE_PANEL_OUTPUT}"
  "${SNAPSHOT_AUDIT_OUTPUT}"
  "${REPO_MONTH_EXCLUSIONS_OUTPUT}"
  "${UNRESOLVED_OUTPUT}"
  "${TREATMENT_ESTIMABILITY_OUTPUT}"
  "${QC_OUTPUT}"
  "${SUMMARY_OUTPUT}"
)

for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output was not created: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output is empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

if awk -F, 'NR > 1 && $2 == "fail" { found=1 } END { exit(found ? 0 : 1) }' "${QC_OUTPUT}"; then
  echo "ERROR: QC contains one or more failures." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
  wc -l \
    "${ALL_ROWS_PANEL_OUTPUT}" \
    "${USABLE_PANEL_OUTPUT}" \
    "${SNAPSHOT_AUDIT_OUTPUT}" \
    "${REPO_MONTH_EXCLUSIONS_OUTPUT}" \
    "${UNRESOLVED_OUTPUT}" \
    "${TREATMENT_ESTIMABILITY_OUTPUT}" \
    "${QC_OUTPUT}" \
    "${SUMMARY_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${QC_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Explicit exclusion preview:"
  head -n 11 "${REPO_MONTH_EXCLUSIONS_OUTPUT}"
  echo
  echo "Unresolved preview:"
  head -n 11 "${UNRESOLVED_OUTPUT}"
  echo
  echo "============================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Usable repo-month panel:         ${USABLE_PANEL_OUTPUT}"
  echo "All-row audit panel:             ${ALL_ROWS_PANEL_OUTPUT}"
  echo "Snapshot join audit:             ${SNAPSHOT_AUDIT_OUTPUT}"
  echo "Explicit exclusions:             ${REPO_MONTH_EXCLUSIONS_OUTPUT}"
  echo "Treatment estimability:          ${TREATMENT_ESTIMABILITY_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next step:                       prepare run-x-d03 Borusyak DiD using log_token_py_100_200"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
