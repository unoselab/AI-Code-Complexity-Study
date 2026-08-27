#!/usr/bin/env bash

set -euo pipefail

# ================================================================
# run-x-i03 v1: Build file-level Quality x FUN+C_FUN-NPR burden dataset
# ================================================================
#
# Purpose:
#   1. Reuse the frozen I01 repo-month/file FUN+C_FUN-NPR measurement artifact.
#   2. Reuse the complete B05 unresolved Python SonarQube issue rows.
#   3. Join quality burden to NPR at exact historical snapshot + file path.
#   4. Preserve every I01 Python file row, including zero-issue and no-FUN+C_FUN files.
#   5. Record B05 Python issue-bearing files outside the I01 NPR universe as
#      explicit scope exclusions instead of failing the join.
#   6. Reconcile joined + scope-excluded issue sums back to all 1,496 snapshots.
#
# Delivery files use the -v1 suffix. Before server execution, copy them to the
# canonical names without the version suffix:
#   proc_script_x01/build_fun_cfun_npr_file_quality_burden.py
#   proc_sh_x01/run-x-i03-build-fun-cfun-npr-file-quality-burden.sh
#
# This wrapper was copied from the validated D02 FUN file-quality wrapper and
# adapted for I01 FUN+C_FUN. It is standalone and never calls the D02 shell wrapper.
# The Python program is likewise a standalone FUN+C_FUN adaptation.
#
# Exact join:
#   I01.snapshot_id   == B05.snapshot_key
#   I01.relative_path == B05.component_path
#
# Important semantics:
#   - SonarQube values are unresolved issue stocks at historical snapshots.
#   - They are not counts of issues introduced during the repo-month.
#   - I01 defines the NPR analysis file universe. A file absent from raw B05
#     issues receives zero burden only after B05 completeness checks pass.
#   - B05 issue-bearing Python files outside I01 are exported as explicit scope
#     exclusions because they cannot receive an NPR threshold classification.
#   - No NPR threshold is applied in I03. The frozen I02 threshold grid is
#     intentionally applied only in a downstream experiment.
#   - No issue density is computed here. File-level SonarQube NCLOC is required
#     before selected-file density can be constructed correctly.
#
# Required inputs:
#   repo_x01/run-x-i01/
#     python_fun_cfun_repo_month_file_npr_scores.csv
#     summary.json
#   repo_x01/run-x-b05/python_sonarqube_issues.csv.gz
#   repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_qc.csv
#   repo_x01/run-x-b05/python_sonarqube_issue_summary.csv
#
# Python program:
#   proc_script_x01/build_fun_cfun_npr_file_quality_burden.py
#
# Main outputs under repo_x01/run-x-i03/:
#   python_fun_cfun_file_quality_burden.csv.gz
#   python_fun_cfun_file_quality_snapshot_audit.csv
#   python_sonarqube_issue_files_outside_i01.csv
#   python_fun_cfun_file_quality_checks.csv
#   python_fun_cfun_file_quality_summary.csv
#   metadata.json
#
# Full run:
#   bash proc_sh_x01/run-x-i03-build-fun-cfun-npr-file-quality-burden.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-i03-build-fun-cfun-npr-file-quality-burden.sh
#
# Useful overrides:
#   PYTHON_BIN=/path/to/python
#   I01_FILE=...
#   I01_SUMMARY_FILE=...
#   B05_RAW_ISSUES_FILE=...
#   B05_SNAPSHOT_COUNTS_FILE=...
#   OUTPUT_DIR=repo_x01/run-x-i03
#   STRICT_EXPECTED_COUNTS=1
#   SELF_TEST_ONLY=0
# ================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i03"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-fun-cfun-npr-file-quality-burden-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/build_fun_cfun_npr_file_quality_burden.py}"

I01_FILE="${I01_FILE:-repo_x01/run-x-i01/python_fun_cfun_repo_month_file_npr_scores.csv}"
I01_SUMMARY_FILE="${I01_SUMMARY_FILE:-repo_x01/run-x-i01/summary.json}"
B05_RAW_ISSUES_FILE="${B05_RAW_ISSUES_FILE:-repo_x01/run-x-b05/python_sonarqube_issues.csv.gz}"
B05_SNAPSHOT_COUNTS_FILE="${B05_SNAPSHOT_COUNTS_FILE:-repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv}"
B05_QC_FILE="${B05_QC_FILE:-repo_x01/run-x-b05/python_sonarqube_issue_qc.csv}"
B05_SUMMARY_FILE="${B05_SUMMARY_FILE:-repo_x01/run-x-b05/python_sonarqube_issue_summary.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i03}"
JOINED_OUTPUT="${JOINED_OUTPUT:-${OUTPUT_DIR}/python_fun_cfun_file_quality_burden.csv.gz}"
SNAPSHOT_AUDIT_OUTPUT="${SNAPSHOT_AUDIT_OUTPUT:-${OUTPUT_DIR}/python_fun_cfun_file_quality_snapshot_audit.csv}"
OUTSIDE_I01_OUTPUT="${OUTSIDE_I01_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_issue_files_outside_i01.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/python_fun_cfun_file_quality_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_fun_cfun_file_quality_summary.csv}"
METADATA_OUTPUT="${METADATA_OUTPUT:-${OUTPUT_DIR}/metadata.json}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

EXPECTED_I01_ROWS="${EXPECTED_I01_ROWS:-510297}"
EXPECTED_I01_UNIQUE_SNAPSHOT_FILES="${EXPECTED_I01_UNIQUE_SNAPSHOT_FILES:-494592}"
EXPECTED_I01_FINITE_FUN_CFUN_ROWS="${EXPECTED_I01_FINITE_FUN_CFUN_ROWS:-359057}"
EXPECTED_SNAPSHOTS="${EXPECTED_SNAPSHOTS:-1496}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_REPO_MONTHS="${EXPECTED_REPO_MONTHS:-1954}"
EXPECTED_RAW_ISSUE_ROWS="${EXPECTED_RAW_ISSUE_ROWS:-554258}"
EXPECTED_OUTSIDE_I01_ISSUE_BEARING_FILES="${EXPECTED_OUTSIDE_I01_ISSUE_BEARING_FILES:-124}"
EXPECTED_OUTSIDE_I01_ISSUE_ROWS="${EXPECTED_OUTSIDE_I01_ISSUE_ROWS:-774}"

for boolean_name in STRICT_EXPECTED_COUNTS SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${EXPECTED_I01_ROWS}" \
  "${EXPECTED_I01_UNIQUE_SNAPSHOT_FILES}" \
  "${EXPECTED_I01_FINITE_FUN_CFUN_ROWS}" \
  "${EXPECTED_SNAPSHOTS}" \
  "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_REPO_MONTHS}" \
  "${EXPECTED_RAW_ISSUE_ROWS}" \
  "${EXPECTED_OUTSIDE_I01_ISSUE_BEARING_FILES}" \
  "${EXPECTED_OUTSIDE_I01_ISSUE_ROWS}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: expected-count options must contain non-negative integers." >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if [[ ! -f "${ANALYSIS_SCRIPT}" ]]; then
  echo "ERROR: required I03 Python program not found: ${ANALYSIS_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: build file-level Quality x FUN+C_FUN-NPR burden dataset"
  echo "Started:                         $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Python script:                   ${ANALYSIS_SCRIPT}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "I01 NPR input:                   ${I01_FILE}"
  echo "I01 summary:                     ${I01_SUMMARY_FILE}"
  echo "B05 raw issues:                  ${B05_RAW_ISSUES_FILE}"
  echo "B05 snapshot counts:             ${B05_SNAPSHOT_COUNTS_FILE}"
  echo "B05 QC:                          ${B05_QC_FILE}"
  echo "B05 summary:                     ${B05_SUMMARY_FILE}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Quality scope:                   Python file-level unresolved issue stock"
  echo "NPR metric preserved:            file_npr_fun_cfun_space_by_token_weighted"
  echo "Threshold application:           none (frozen I02 grid remains downstream)"
  echo "Density:                         deferred until file-level NCLOC is available"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================================"
} | tee "${LOG_FILE}"

run_command_logged() {
  local step_title="$1"
  shift
  local -a command=("$@")
  {
    echo
    echo "** ${step_title}"
    echo "----------------------------------------------------------------------------"
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n\n'
  } | tee -a "${LOG_FILE}"
  "${command[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

run_command_logged \
  "Step 1: Run I03 structural self-test" \
  "${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile I03 Python program" \
  "${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_input in \
  "${I01_FILE}" \
  "${I01_SUMMARY_FILE}" \
  "${B05_RAW_ISSUES_FILE}" \
  "${B05_SNAPSHOT_COUNTS_FILE}" \
  "${B05_QC_FILE}" \
  "${B05_SUMMARY_FILE}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 3: Freeze input provenance"
  echo "----------------------------------------------------------------------------"
  echo "I01 input SHA256:                $(sha256sum "${I01_FILE}" | awk '{print $1}')"
  echo "I01 summary SHA256:              $(sha256sum "${I01_SUMMARY_FILE}" | awk '{print $1}')"
  echo "B05 raw issues SHA256:           $(sha256sum "${B05_RAW_ISSUES_FILE}" | awk '{print $1}')"
  echo "B05 snapshot counts SHA256:      $(sha256sum "${B05_SNAPSHOT_COUNTS_FILE}" | awk '{print $1}')"
  echo "B05 QC SHA256:                   $(sha256sum "${B05_QC_FILE}" | awk '{print $1}')"
  echo "B05 summary SHA256:              $(sha256sum "${B05_SUMMARY_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

I03_COMMAND=(
  "${PYTHON_BIN}"
  "${ANALYSIS_SCRIPT}"
  --i01-file "${I01_FILE}"
  --i01-summary-file "${I01_SUMMARY_FILE}"
  --b05-raw-issues-file "${B05_RAW_ISSUES_FILE}"
  --b05-snapshot-counts-file "${B05_SNAPSHOT_COUNTS_FILE}"
  --b05-qc-file "${B05_QC_FILE}"
  --b05-summary-file "${B05_SUMMARY_FILE}"
  --output-file "${JOINED_OUTPUT}"
  --snapshot-audit-file "${SNAPSHOT_AUDIT_OUTPUT}"
  --outside-i01-file "${OUTSIDE_I01_OUTPUT}"
  --checks-file "${CHECKS_OUTPUT}"
  --summary-file "${SUMMARY_OUTPUT}"
  --metadata-file "${METADATA_OUTPUT}"
  --expected-i01-rows "${EXPECTED_I01_ROWS}"
  --expected-i01-unique-snapshot-files "${EXPECTED_I01_UNIQUE_SNAPSHOT_FILES}"
  --expected-i01-finite-fun-cfun-rows "${EXPECTED_I01_FINITE_FUN_CFUN_ROWS}"
  --expected-snapshots "${EXPECTED_SNAPSHOTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-repo-months "${EXPECTED_REPO_MONTHS}"
  --expected-raw-issue-rows "${EXPECTED_RAW_ISSUE_ROWS}"
  --expected-outside-i01-issue-bearing-files "${EXPECTED_OUTSIDE_I01_ISSUE_BEARING_FILES}"
  --expected-outside-i01-issue-rows "${EXPECTED_OUTSIDE_I01_ISSUE_ROWS}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  I03_COMMAND+=(--strict-expected-counts)
fi

run_command_logged "Step 4: Build file-level Quality x FUN+C_FUN-NPR burden dataset" "${I03_COMMAND[@]}"

EXPECTED_OUTPUTS=(
  "${JOINED_OUTPUT}"
  "${SNAPSHOT_AUDIT_OUTPUT}"
  "${OUTSIDE_I01_OUTPUT}"
  "${CHECKS_OUTPUT}"
  "${SUMMARY_OUTPUT}"
  "${METADATA_OUTPUT}"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected output missing or empty: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

gzip -t "${JOINED_OUTPUT}"

{
  echo
  echo "** Step 5: Output checks"
  echo "----------------------------------------------------------------------------"
  echo "Joined gzip CSV lines:           $(gzip -cd "${JOINED_OUTPUT}" | wc -l)"
  echo "Snapshot audit lines:            $(wc -l < "${SNAPSHOT_AUDIT_OUTPUT}")"
  echo "Outside-I01 exclusion lines:     $(wc -l < "${OUTSIDE_I01_OUTPUT}")"
  echo "QC check lines:                  $(wc -l < "${CHECKS_OUTPUT}")"
  echo "Summary lines:                   $(wc -l < "${SUMMARY_OUTPUT}")"
  echo
  echo "I03 QC checks:"
  cat "${CHECKS_OUTPUT}"
  echo
  echo "I03 summary:"
  cat "${SUMMARY_OUTPUT}"
  echo
  echo "Snapshot audit preview:"
  head -n 6 "${SNAPSHOT_AUDIT_OUTPUT}"
  echo
  echo "============================================================================"
  echo "${RUN_LABEL} execution summary"
  echo "Completed:                        $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Joined output:                    ${JOINED_OUTPUT}"
  echo "Snapshot audit:                   ${SNAPSHOT_AUDIT_OUTPUT}"
  echo "Outside-I01 scope exclusions:     ${OUTSIDE_I01_OUTPUT}"
  echo "QC checks:                        ${CHECKS_OUTPUT}"
  echo "Summary:                          ${SUMMARY_OUTPUT}"
  echo "Metadata:                         ${METADATA_OUTPUT}"
  echo "Log file:                         ${LOG_FILE}"
  echo "Next:                             I04 apply frozen I02 threshold grid and aggregate quality burden"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
