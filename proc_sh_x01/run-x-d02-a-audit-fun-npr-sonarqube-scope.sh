#!/usr/bin/env bash

set -euo pipefail

# ======================================================================
# run-x-d02-a v1: Audit SonarQube paths outside the frozen A12 NPR scope
# ======================================================================
#
# Purpose:
#   1. Reuse the D02 v2 scope-exclusion artifact without changing D02.
#   2. Inspect the exact historical Git tree for every B05 issue-bearing
#      Python path that was outside the frozen A12 file universe.
#   3. Determine whether each path is a filesystem alias created by a tracked
#      symbolic link, a tracked regular file unexpectedly absent from A12, a
#      case/path-normalization difference, or an unresolved scope mismatch.
#   4. Compare resolved Git target paths and content SHA256 values with A12.
#   5. Freeze the repository-level exclusion sensitivity specification before
#      D03 constructs threshold-specific quality outcomes.
#
# This wrapper reuses the execution/provenance structure of the D02 and B04
# wrappers, but it is standalone and never calls an older wrapper.
#
# Audit safety:
#   - Uses git ls-tree and git cat-file only.
#   - Does not checkout or modify repositories.
#   - Does not call SonarQube APIs.
#   - Does not rerun SonarScanner.
#   - Does not apply any NPR threshold.
#   - Does not read or estimate any D03/D04 causal result.
#
# Required inputs:
#   repo_x01/run-x-d02/python_sonarqube_issue_files_outside_a12.csv
#   repo_x01/run-x-d02/python_fun_file_quality_checks.csv
#   repo_x01/run-x-d02/python_fun_file_quality_summary.csv
#   ../../detect_code_gpt/output/snapshot_npr/run-x-a12/
#     python_fun_repo_month_file_npr_scores.csv
#   ../treatment-repos/
#   ../control-repos/
#
# Python program:
#   proc_script_x01/audit_fun_npr_sonarqube_scope.py
#
# Main outputs under repo_x01/run-x-d02-a/:
#   python_sonarqube_outside_a12_scope_detail.csv
#   python_sonarqube_outside_a12_symlink_evidence.csv
#   python_sonarqube_outside_a12_scope_snapshot_summary.csv
#   python_sonarqube_outside_a12_scope_repo_summary.csv
#   quality_npr_scope_sensitivity_spec.csv
#   python_sonarqube_outside_a12_scope_checks.csv
#   python_sonarqube_outside_a12_scope_summary.csv
#   metadata.json
#
# Full run:
#   bash proc_sh_x01/run-x-d02-a-audit-fun-npr-sonarqube-scope.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-d02-a-audit-fun-npr-sonarqube-scope.sh
#
# Useful overrides:
#   PYTHON_BIN=/path/to/python
#   TREATMENT_REPOS_DIR=../treatment-repos
#   CONTROL_REPOS_DIR=../control-repos
#   GIT_TIMEOUT_SECONDS=120
#   STRICT_EXPECTED_COUNTS=1
# ======================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d02-a"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-fun-npr-sonarqube-scope-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/audit_fun_npr_sonarqube_scope.py}"

D02_DIR="${D02_DIR:-repo_x01/run-x-d02}"
OUTSIDE_A12_FILE="${OUTSIDE_A12_FILE:-${D02_DIR}/python_sonarqube_issue_files_outside_a12.csv}"
D02_CHECKS_FILE="${D02_CHECKS_FILE:-${D02_DIR}/python_fun_file_quality_checks.csv}"
D02_SUMMARY_FILE="${D02_SUMMARY_FILE:-${D02_DIR}/python_fun_file_quality_summary.csv}"
A12_FILE="${A12_FILE:-../../detect_code_gpt/output/snapshot_npr/run-x-a12/python_fun_repo_month_file_npr_scores.csv}"

# These repository roots match the historical Git-inspection pipeline used in
# this workspace. Repositories are addressed as owner_repo directory names.
TREATMENT_REPOS_DIR="${TREATMENT_REPOS_DIR:-../treatment-repos}"
CONTROL_REPOS_DIR="${CONTROL_REPOS_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-d02-a}"
DETAIL_OUTPUT="${DETAIL_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_scope_detail.csv}"
SYMLINK_EVIDENCE_OUTPUT="${SYMLINK_EVIDENCE_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_symlink_evidence.csv}"
SNAPSHOT_SUMMARY_OUTPUT="${SNAPSHOT_SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_scope_snapshot_summary.csv}"
REPO_SUMMARY_OUTPUT="${REPO_SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_scope_repo_summary.csv}"
SENSITIVITY_SPEC_OUTPUT="${SENSITIVITY_SPEC_OUTPUT:-${OUTPUT_DIR}/quality_npr_scope_sensitivity_spec.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_scope_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/python_sonarqube_outside_a12_scope_summary.csv}"
METADATA_OUTPUT="${METADATA_OUTPUT:-${OUTPUT_DIR}/metadata.json}"

GIT_TIMEOUT_SECONDS="${GIT_TIMEOUT_SECONDS:-120}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"

# Frozen expectations from the successful D02 v2 scope accounting.
EXPECTED_OUTSIDE_ROWS="${EXPECTED_OUTSIDE_ROWS:-124}"
EXPECTED_OUTSIDE_ISSUES="${EXPECTED_OUTSIDE_ISSUES:-774}"
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
  "${GIT_TIMEOUT_SECONDS}" \
  "${EXPECTED_OUTSIDE_ROWS}" \
  "${EXPECTED_OUTSIDE_ISSUES}" \
  "${EXPECTED_AFFECTED_SNAPSHOTS}" \
  "${EXPECTED_AFFECTED_REPOSITORIES}"; do
  if ! [[ "${numeric_value}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: numeric options must contain non-negative integers." >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git executable not found." >&2
  exit 1
fi
if [[ ! -f "${ANALYSIS_SCRIPT}" ]]; then
  echo "ERROR: required D02-a Python program not found: ${ANALYSIS_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
GIT_VERSION="$(git --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: audit SonarQube paths outside frozen A12 NPR scope"
  echo "Started:                         $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Git:                             ${GIT_VERSION}"
  echo "Python script:                   ${ANALYSIS_SCRIPT}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "D02 outside-A12 input:           ${OUTSIDE_A12_FILE}"
  echo "D02 checks:                      ${D02_CHECKS_FILE}"
  echo "D02 summary:                     ${D02_SUMMARY_FILE}"
  echo "A12 NPR file universe:           ${A12_FILE}"
  echo "Treatment repository root:      ${TREATMENT_REPOS_DIR}"
  echo "Control repository root:        ${CONTROL_REPOS_DIR}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Git inspection:                  ls-tree + cat-file only; no checkout"
  echo "SonarQube API/Scanner:           not used"
  echo "NPR thresholds:                  not applied"
  echo "D03 sensitivity policy:          exclude entire affected repositories"
  echo "Expected outside files/issues:  ${EXPECTED_OUTSIDE_ROWS} / ${EXPECTED_OUTSIDE_ISSUES}"
  echo "Expected snapshots/repos:        ${EXPECTED_AFFECTED_SNAPSHOTS} / ${EXPECTED_AFFECTED_REPOSITORIES}"
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
  "Step 1: Run D02-a structural self-test" \
  "${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile D02-a Python program" \
  "${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

for required_input in \
  "${OUTSIDE_A12_FILE}" \
  "${D02_CHECKS_FILE}" \
  "${D02_SUMMARY_FILE}" \
  "${A12_FILE}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

for required_dir in "${TREATMENT_REPOS_DIR}" "${CONTROL_REPOS_DIR}"; do
  if [[ ! -d "${required_dir}" ]]; then
    echo "ERROR: required repository root not found: ${required_dir}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 3: Freeze input provenance"
  echo "----------------------------------------------------------------------------"
  echo "D02 outside-A12 SHA256:          $(sha256sum "${OUTSIDE_A12_FILE}" | awk '{print $1}')"
  echo "D02 checks SHA256:               $(sha256sum "${D02_CHECKS_FILE}" | awk '{print $1}')"
  echo "D02 summary SHA256:              $(sha256sum "${D02_SUMMARY_FILE}" | awk '{print $1}')"
  echo "A12 file-universe SHA256:        $(sha256sum "${A12_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}"
  "${ANALYSIS_SCRIPT}"
  --outside-a12-file "${OUTSIDE_A12_FILE}"
  --a12-file "${A12_FILE}"
  --d02-checks-file "${D02_CHECKS_FILE}"
  --d02-summary-file "${D02_SUMMARY_FILE}"
  --treatment-repos-dir "${TREATMENT_REPOS_DIR}"
  --control-repos-dir "${CONTROL_REPOS_DIR}"
  --detail-output "${DETAIL_OUTPUT}"
  --symlink-evidence-output "${SYMLINK_EVIDENCE_OUTPUT}"
  --snapshot-summary-output "${SNAPSHOT_SUMMARY_OUTPUT}"
  --repo-summary-output "${REPO_SUMMARY_OUTPUT}"
  --sensitivity-spec-output "${SENSITIVITY_SPEC_OUTPUT}"
  --checks-output "${CHECKS_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --metadata-output "${METADATA_OUTPUT}"
  --git-timeout-seconds "${GIT_TIMEOUT_SECONDS}"
  --expected-outside-rows "${EXPECTED_OUTSIDE_ROWS}"
  --expected-outside-issues "${EXPECTED_OUTSIDE_ISSUES}"
  --expected-affected-snapshots "${EXPECTED_AFFECTED_SNAPSHOTS}"
  --expected-affected-repositories "${EXPECTED_AFFECTED_REPOSITORIES}"
)

if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi

run_command_logged \
  "Step 4: Audit exact Git paths and symbolic-link aliases" \
  "${COMMAND[@]}"

{
  echo
  echo "** Step 5: Output checks"
  echo "----------------------------------------------------------------------------"
  echo "Detail rows:                     $(wc -l < "${DETAIL_OUTPUT}") lines including header"
  echo "Symlink evidence:                $(wc -l < "${SYMLINK_EVIDENCE_OUTPUT}") lines including header"
  echo "Snapshot summary:                $(wc -l < "${SNAPSHOT_SUMMARY_OUTPUT}") lines including header"
  echo "Repository summary:              $(wc -l < "${REPO_SUMMARY_OUTPUT}") lines including header"
  echo "Sensitivity spec:                $(wc -l < "${SENSITIVITY_SPEC_OUTPUT}") lines including header"
  echo "QC checks:                       $(wc -l < "${CHECKS_OUTPUT}") lines including header"
  echo "Summary:                         $(wc -l < "${SUMMARY_OUTPUT}") lines including header"
  echo
  echo "Repository-level cause summary:"
  cat "${REPO_SUMMARY_OUTPUT}"
  echo
  echo "Frozen D03/D04 scope sensitivity specification:"
  cat "${SENSITIVITY_SPEC_OUTPUT}"
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
  echo "Detail:                          ${DETAIL_OUTPUT}"
  echo "Symlink evidence:                ${SYMLINK_EVIDENCE_OUTPUT}"
  echo "Repository summary:              ${REPO_SUMMARY_OUTPUT}"
  echo "Sensitivity spec:                ${SENSITIVITY_SPEC_OUTPUT}"
  echo "QC checks:                       ${CHECKS_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            review scope causes, then D03 threshold-specific quality burden"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
