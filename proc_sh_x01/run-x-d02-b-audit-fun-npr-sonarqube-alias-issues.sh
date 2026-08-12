#!/usr/bin/env bash

set -euo pipefail

# ======================================================================
# run-x-d02-b v1: Audit alias-vs-canonical SonarQube issue duplication
# ======================================================================
#
# Purpose:
#   1. Reuse the successful D02-a filesystem-alias mapping without changing
#      D02 or D02-a.
#   2. Compare B05 SonarQube issues reported on each alias path with issues
#      reported on the canonical A12-backed path in the same snapshot.
#   3. Determine whether alias-side issue stock is a duplicate that should stay
#      excluded, or whether any alias-only issue must be remapped before D03.
#   4. Freeze the alias-handling policy before D03 threshold-specific quality
#      outcomes are constructed.
#
# This wrapper was created by copying the D02-a wrapper and adapting its
# execution/provenance structure. It is standalone and never calls D02-a or any
# other older shell wrapper.
#
# Audit safety:
#   - Reads CSV artifacts only.
#   - Does not inspect or modify Git repositories.
#   - Does not call SonarQube APIs.
#   - Does not rerun SonarScanner.
#   - Does not apply NPR thresholds.
#   - Does not read or estimate D03/D04 causal results.
#
# Required inputs:
#   repo_x01/run-x-b05/python_sonarqube_issues.csv.gz
#   repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_detail.csv
#   repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_checks.csv
#   repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_summary.csv
#
# Python program:
#   proc_script_x01/audit_fun_npr_sonarqube_alias_issues.py
#
# Main outputs under repo_x01/run-x-d02-b/:
#   python_sonarqube_alias_issue_comparison.csv
#   python_sonarqube_alias_issue_signature_differences.csv
#   python_sonarqube_alias_issue_repo_summary.csv
#   quality_npr_alias_handling_spec.csv
#   python_sonarqube_alias_issue_checks.csv
#   python_sonarqube_alias_issue_summary.csv
#   metadata.json
#
# Full run:
#   bash proc_sh_x01/run-x-d02-b-audit-fun-npr-sonarqube-alias-issues.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-d02-b-audit-fun-npr-sonarqube-alias-issues.sh
#
# Useful overrides:
#   PYTHON_BIN=/path/to/python
#   CSV_CHUNKSIZE=100000
#   STRICT_EXPECTED_COUNTS=1
# ======================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d02-b"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-fun-npr-sonarqube-alias-issues-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/audit_fun_npr_sonarqube_alias_issues.py}"

B05_DIR="${B05_DIR:-repo_x01/run-x-b05}"
B05_RAW_ISSUES_FILE="${B05_RAW_ISSUES_FILE:-${B05_DIR}/python_sonarqube_issues.csv.gz}"

D02_A_DIR="${D02_A_DIR:-repo_x01/run-x-d02-a}"
SCOPE_DETAIL_FILE="${SCOPE_DETAIL_FILE:-${D02_A_DIR}/python_sonarqube_outside_a12_scope_detail.csv}"
D02_A_CHECKS_FILE="${D02_A_CHECKS_FILE:-${D02_A_DIR}/python_sonarqube_outside_a12_scope_checks.csv}"
D02_A_SUMMARY_FILE="${D02_A_SUMMARY_FILE:-${D02_A_DIR}/python_sonarqube_outside_a12_scope_summary.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-d02-b}"
COMPARISON_OUTPUT="${COMPARISON_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_alias_issue_comparison.csv}"
SIGNATURE_DIFFERENCES_OUTPUT="${SIGNATURE_DIFFERENCES_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_alias_issue_signature_differences.csv}"
REPO_SUMMARY_OUTPUT="${REPO_SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_alias_issue_repo_summary.csv}"
HANDLING_SPEC_OUTPUT="${HANDLING_SPEC_OUTPUT:-${OUTPUT_DIR}/quality_npr_alias_handling_spec.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_alias_issue_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_alias_issue_summary.csv}"
METADATA_OUTPUT="${METADATA_OUTPUT:-${OUTPUT_DIR}/metadata.json}"

CSV_CHUNKSIZE="${CSV_CHUNKSIZE:-100000}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

# Frozen expectations from D02 v2 and the successful D02-a scope audit.
EXPECTED_ALIAS_ROWS="${EXPECTED_ALIAS_ROWS:-124}"
EXPECTED_ALIAS_ISSUES="${EXPECTED_ALIAS_ISSUES:-774}"
EXPECTED_AFFECTED_SNAPSHOTS="${EXPECTED_AFFECTED_SNAPSHOTS:-21}"
EXPECTED_AFFECTED_REPOSITORIES="${EXPECTED_AFFECTED_REPOSITORIES:-2}"

for boolean_name in STRICT_EXPECTED_COUNTS SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${CSV_CHUNKSIZE}" \
  "${EXPECTED_ALIAS_ROWS}" \
  "${EXPECTED_ALIAS_ISSUES}" \
  "${EXPECTED_AFFECTED_SNAPSHOTS}" \
  "${EXPECTED_AFFECTED_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: numeric options must contain non-negative integers." >&2
    exit 1
  fi
done

if [[ "${CSV_CHUNKSIZE}" == "0" ]]; then
  echo "ERROR: CSV_CHUNKSIZE must be positive." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if [[ ! -f "${ANALYSIS_SCRIPT}" ]]; then
  echo "ERROR: required D02-b Python program not found: ${ANALYSIS_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: audit SonarQube alias-vs-canonical issue duplication"
  echo "Started:                         $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Python script:                   ${ANALYSIS_SCRIPT}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "B05 raw issues:                  ${B05_RAW_ISSUES_FILE}"
  echo "D02-a scope detail:              ${SCOPE_DETAIL_FILE}"
  echo "D02-a checks:                    ${D02_A_CHECKS_FILE}"
  echo "D02-a summary:                   ${D02_A_SUMMARY_FILE}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Comparison unit:                 snapshot + alias path -> canonical A12 path"
  echo "Issue identity:                  D03-relevant semantic multiset; issue_key/path ignored"
  echo "SonarQube API/Scanner:           not used"
  echo "Git inspection:                  not used"
  echo "NPR thresholds:                  not applied"
  echo "Expected alias files/issues:     ${EXPECTED_ALIAS_ROWS} / ${EXPECTED_ALIAS_ISSUES}"
  echo "Expected snapshots/repos:        ${EXPECTED_AFFECTED_SNAPSHOTS} / ${EXPECTED_AFFECTED_REPOSITORIES}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "CSV chunk size:                  ${CSV_CHUNKSIZE}"
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
  "Step 1: Run D02-b structural self-test" \
  "${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile D02-b Python program" \
  "${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_input in \
  "${B05_RAW_ISSUES_FILE}" \
  "${SCOPE_DETAIL_FILE}" \
  "${D02_A_CHECKS_FILE}" \
  "${D02_A_SUMMARY_FILE}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 3: Freeze input provenance"
  echo "----------------------------------------------------------------------------"
  echo "B05 raw issues SHA256:           $(sha256sum "${B05_RAW_ISSUES_FILE}" | awk '{print $1}')"
  echo "D02-a scope detail SHA256:       $(sha256sum "${SCOPE_DETAIL_FILE}" | awk '{print $1}')"
  echo "D02-a checks SHA256:             $(sha256sum "${D02_A_CHECKS_FILE}" | awk '{print $1}')"
  echo "D02-a summary SHA256:            $(sha256sum "${D02_A_SUMMARY_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${ANALYSIS_SCRIPT}"
  --b05-raw-issues-file "${B05_RAW_ISSUES_FILE}"
  --scope-detail-file "${SCOPE_DETAIL_FILE}"
  --d02-a-checks-file "${D02_A_CHECKS_FILE}"
  --d02-a-summary-file "${D02_A_SUMMARY_FILE}"
  --comparison-output "${COMPARISON_OUTPUT}"
  --signature-differences-output "${SIGNATURE_DIFFERENCES_OUTPUT}"
  --repo-summary-output "${REPO_SUMMARY_OUTPUT}"
  --handling-spec-output "${HANDLING_SPEC_OUTPUT}"
  --checks-output "${CHECKS_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --metadata-output "${METADATA_OUTPUT}"
  --csv-chunksize "${CSV_CHUNKSIZE}"
  --expected-alias-rows "${EXPECTED_ALIAS_ROWS}"
  --expected-alias-issues "${EXPECTED_ALIAS_ISSUES}"
  --expected-affected-snapshots "${EXPECTED_AFFECTED_SNAPSHOTS}"
  --expected-affected-repositories "${EXPECTED_AFFECTED_REPOSITORIES}"
)

if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi

run_command_logged \
  "Step 4: Compare alias and canonical SonarQube issue multisets" \
  "${COMMAND[@]}"

{
  echo
  echo "** Step 5: Output checks"
  echo "----------------------------------------------------------------------------"
  echo "Comparison rows:                 $(wc -l < "${COMPARISON_OUTPUT}") lines including header"
  echo "Signature differences:           $(wc -l < "${SIGNATURE_DIFFERENCES_OUTPUT}") lines including header"
  echo "Repository summary:              $(wc -l < "${REPO_SUMMARY_OUTPUT}") lines including header"
  echo "Handling spec:                   $(wc -l < "${HANDLING_SPEC_OUTPUT}") lines including header"
  echo "QC checks:                       $(wc -l < "${CHECKS_OUTPUT}") lines including header"
  echo "Summary:                         $(wc -l < "${SUMMARY_OUTPUT}") lines including header"
  echo
  echo "Repository-level alias issue summary:"
  cat "${REPO_SUMMARY_OUTPUT}"
  echo
  echo "Frozen D03 alias-handling specification:"
  cat "${HANDLING_SPEC_OUTPUT}"
  echo
  echo "QC checks:"
  cat "${CHECKS_OUTPUT}"
  echo
  echo "Summary:"
  cat "${SUMMARY_OUTPUT}"
} | tee -a "${LOG_FILE}"

{
  echo
  echo "============================================================================"
  echo "${RUN_LABEL} completed successfully."
  echo "Completed:                       $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Comparison detail:               ${COMPARISON_OUTPUT}"
  echo "Signature differences:           ${SIGNATURE_DIFFERENCES_OUTPUT}"
  echo "Repository summary:              ${REPO_SUMMARY_OUTPUT}"
  echo "Handling spec:                   ${HANDLING_SPEC_OUTPUT}"
  echo "QC checks:                       ${CHECKS_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            if all alias issues are duplicated, keep D02 v2 and start D03"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
