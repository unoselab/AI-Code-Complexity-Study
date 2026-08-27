#!/usr/bin/env bash

set -euo pipefail

# ============================================================================
# run-x-i04 v1: build frozen-threshold FUN+C_FUN-NPR x SonarQube burden panel
# ============================================================================
#
# This wrapper is a standalone adaptation of the validated D03 execution logic.
# It does not call D03 or any other prior shell wrapper.
#
# Delivery filenames keep the version suffix:
#   proc_script_x01/build_fun_cfun_npr_threshold_quality_burden_panel-v1.py
#   proc_sh_x01/run-x-i04-build-fun-cfun-npr-threshold-quality-burden-panel-v1.sh
#
# Canonical server filenames remove the version suffix:
#   proc_script_x01/build_fun_cfun_npr_threshold_quality_burden_panel.py
#   proc_sh_x01/run-x-i04-build-fun-cfun-npr-threshold-quality-burden-panel.sh
#
# Inputs:
#   I03 file-level FUN+C_FUN-NPR x SonarQube burden table
#   I03 summary and explicit outside-I01 scope exclusions
#   I02 frozen threshold specification, threshold audit, and summary
#   B06 authoritative 1,954-row SonarQube quality DiD base panel
#
# Threshold eligibility and selection:
#   eligible = finite(file_npr_fun_cfun_space_by_token_weighted)
#   selected = eligible AND file_npr_fun_cfun_space_by_token_weighted > threshold
#
# Sample specifications:
#   full_sample
#   exclude_scope_mismatch_repos
#
# The sensitivity repositories are derived deterministically from the frozen I03
# outside-I01 scope-exclusion artifact before any DiD model is fit. I04 does not
# use outcome effect estimates to choose repositories or thresholds.
#
# Quality outcomes:
#   unresolved SonarQube issue stock in threshold-selected Python files.
#   Selected-file density is intentionally deferred because file-level SonarQube
#   NCLOC is not part of the current frozen I03 contract.
#
# Full run:
#   bash proc_sh_x01/run-x-i04-build-fun-cfun-npr-threshold-quality-burden-panel.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-i04-build-fun-cfun-npr-threshold-quality-burden-panel.sh
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i04"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-fun-cfun-npr-threshold-quality-burden-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/build_fun_cfun_npr_threshold_quality_burden_panel.py}"

I03_FILE="${I03_FILE:-repo_x01/run-x-i03/python_fun_cfun_file_quality_burden.csv.gz}"
I03_SUMMARY_FILE="${I03_SUMMARY_FILE:-repo_x01/run-x-i03/python_fun_cfun_file_quality_summary.csv}"
I03_OUTSIDE_SCOPE_FILE="${I03_OUTSIDE_SCOPE_FILE:-repo_x01/run-x-i03/python_sonarqube_issue_files_outside_i01.csv}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
I02_SUMMARY_FILE="${I02_SUMMARY_FILE:-repo_x01/run-x-i02/summary.json}"
THRESHOLD_SPEC_FILE="${THRESHOLD_SPEC_FILE:-repo_x01/run-x-i02/fun_cfun_npr_threshold_spec.csv}"
THRESHOLD_AUDIT_FILE="${THRESHOLD_AUDIT_FILE:-repo_x01/run-x-i02/fun_cfun_npr_threshold_audit.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i04}"
PANEL_OUTPUT="${PANEL_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_repo_month_panel.csv.gz}"
GLOBAL_AUDIT_OUTPUT="${GLOBAL_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_global_audit.csv}"
TIMING_AUDIT_OUTPUT="${TIMING_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_by_treatment_timing.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_sample_summary.csv}"
SCOPE_SENSITIVITY_OUTPUT="${SCOPE_SENSITIVITY_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_scope_sensitivity_spec.csv}"
OUTCOME_SPEC_OUTPUT="${OUTCOME_SPEC_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_outcome_spec.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_fun_cfun_npr_threshold_summary.csv}"
METADATA_OUTPUT="${METADATA_OUTPUT:-${OUTPUT_DIR}/metadata.json}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1954}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_UNTREATED_ROWS="${EXPECTED_UNTREATED_ROWS:-1591}"
EXPECTED_TREATED_ROWS="${EXPECTED_TREATED_ROWS:-363}"
EXPECTED_DYNAMIC_ROWS="${EXPECTED_DYNAMIC_ROWS:-343}"
EXPECTED_I03_ROWS="${EXPECTED_I03_ROWS:-510297}"
EXPECTED_FINITE_FUN_CFUN_ROWS="${EXPECTED_FINITE_FUN_CFUN_ROWS:-359057}"
EXPECTED_SCOPE_REPOSITORIES="${EXPECTED_SCOPE_REPOSITORIES:-2}"
EXPECTED_SCOPE_REPO_MONTH_ROWS="${EXPECTED_SCOPE_REPO_MONTH_ROWS:-1915}"
EXPECTED_PRIMARY_SELECTED_FILES="${EXPECTED_PRIMARY_SELECTED_FILES:-17071}"
EXPECTED_PRIMARY_SELECTED_ISSUES="${EXPECTED_PRIMARY_SELECTED_ISSUES:-14809}"
EXPECTED_PRIMARY_SELECTED_CODE_SMELL="${EXPECTED_PRIMARY_SELECTED_CODE_SMELL:-14318}"
EXPECTED_PRIMARY_SENSITIVITY_SELECTED_FILES="${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_FILES:-16885}"
EXPECTED_PRIMARY_SENSITIVITY_SELECTED_ISSUES="${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_ISSUES:-14748}"

for boolean_name in STRICT_EXPECTED_COUNTS SELF_TEST_ONLY; do
  boolean_value="${!boolean_name}"
  if [[ "${boolean_value}" != "0" && "${boolean_value}" != "1" ]]; then
    echo "ERROR: ${boolean_name} must be 0 or 1." >&2
    exit 1
  fi
done

for numeric_value in \
  "${EXPECTED_PANEL_ROWS}" "${EXPECTED_REPOSITORIES}" \
  "${EXPECTED_TREATMENT_REPOSITORIES}" "${EXPECTED_CONTROL_REPOSITORIES}" \
  "${EXPECTED_UNTREATED_ROWS}" "${EXPECTED_TREATED_ROWS}" \
  "${EXPECTED_DYNAMIC_ROWS}" "${EXPECTED_I03_ROWS}" \
  "${EXPECTED_FINITE_FUN_CFUN_ROWS}" "${EXPECTED_SCOPE_REPOSITORIES}" \
  "${EXPECTED_SCOPE_REPO_MONTH_ROWS}" "${EXPECTED_PRIMARY_SELECTED_FILES}" \
  "${EXPECTED_PRIMARY_SELECTED_ISSUES}" "${EXPECTED_PRIMARY_SELECTED_CODE_SMELL}" \
  "${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_FILES}" "${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_ISSUES}"; do
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
  echo "ERROR: required I04 Python program not found: ${ANALYSIS_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: build frozen-threshold Quality x FUN+C_FUN-NPR burden panel"
  echo "Started:                         $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Python script:                   ${ANALYSIS_SCRIPT}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "I03 file-level burden:           ${I03_FILE}"
  echo "I03 summary:                     ${I03_SUMMARY_FILE}"
  echo "I03 outside-I01 scope:           ${I03_OUTSIDE_SCOPE_FILE}"
  echo "B06 quality panel:               ${B06_PANEL_FILE}"
  echo "I02 summary:                     ${I02_SUMMARY_FILE}"
  echo "I02 threshold spec:              ${THRESHOLD_SPEC_FILE}"
  echo "I02 threshold audit:             ${THRESHOLD_AUDIT_FILE}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "NPR metric:                      file_npr_fun_cfun_space_by_token_weighted"
  echo "Comparison operator:             strict >"
  echo "Primary threshold:               1.571637"
  echo "Threshold specifications:        21 grid + 1 legacy anchor"
  echo "Sample specifications:           full + exclude_scope_mismatch_repos"
  echo "Quality outcome:                 selected-file unresolved issue stock"
  echo "Density:                         not computed"
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
  "Step 1: Run I04 structural self-test" \
  "${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile I04 Python program" \
  "${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

REQUIRED_INPUTS=(
  "${I03_FILE}"
  "${I03_SUMMARY_FILE}"
  "${I03_OUTSIDE_SCOPE_FILE}"
  "${B06_PANEL_FILE}"
  "${I02_SUMMARY_FILE}"
  "${THRESHOLD_SPEC_FILE}"
  "${THRESHOLD_AUDIT_FILE}"
)
for required_input in "${REQUIRED_INPUTS[@]}"; do
  if [[ ! -f "${required_input}" ]]; then
    echo "ERROR: required input not found: ${required_input}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
done

{
  echo
  echo "** Step 3: Freeze input provenance"
  echo "----------------------------------------------------------------------------"
  echo "I03 file SHA256:                 $(sha256sum "${I03_FILE}" | awk '{print $1}')"
  echo "I03 summary SHA256:              $(sha256sum "${I03_SUMMARY_FILE}" | awk '{print $1}')"
  echo "I03 outside scope SHA256:        $(sha256sum "${I03_OUTSIDE_SCOPE_FILE}" | awk '{print $1}')"
  echo "B06 panel SHA256:                $(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"
  echo "I02 summary SHA256:              $(sha256sum "${I02_SUMMARY_FILE}" | awk '{print $1}')"
  echo "I02 threshold spec SHA256:       $(sha256sum "${THRESHOLD_SPEC_FILE}" | awk '{print $1}')"
  echo "I02 threshold audit SHA256:      $(sha256sum "${THRESHOLD_AUDIT_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

I04_COMMAND=(
  "${PYTHON_BIN}"
  "${ANALYSIS_SCRIPT}"
  --i03-file "${I03_FILE}"
  --i03-summary-file "${I03_SUMMARY_FILE}"
  --i03-outside-scope-file "${I03_OUTSIDE_SCOPE_FILE}"
  --b06-panel-file "${B06_PANEL_FILE}"
  --i02-summary-file "${I02_SUMMARY_FILE}"
  --threshold-spec-file "${THRESHOLD_SPEC_FILE}"
  --threshold-audit-file "${THRESHOLD_AUDIT_FILE}"
  --panel-output "${PANEL_OUTPUT}"
  --global-audit-output "${GLOBAL_AUDIT_OUTPUT}"
  --timing-audit-output "${TIMING_AUDIT_OUTPUT}"
  --sample-summary-output "${SAMPLE_SUMMARY_OUTPUT}"
  --scope-sensitivity-output "${SCOPE_SENSITIVITY_OUTPUT}"
  --outcome-spec-output "${OUTCOME_SPEC_OUTPUT}"
  --checks-output "${CHECKS_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --metadata-output "${METADATA_OUTPUT}"
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-untreated-rows "${EXPECTED_UNTREATED_ROWS}"
  --expected-treated-rows "${EXPECTED_TREATED_ROWS}"
  --expected-dynamic-rows "${EXPECTED_DYNAMIC_ROWS}"
  --expected-i03-rows "${EXPECTED_I03_ROWS}"
  --expected-finite-fun-cfun-rows "${EXPECTED_FINITE_FUN_CFUN_ROWS}"
  --expected-scope-repositories "${EXPECTED_SCOPE_REPOSITORIES}"
  --expected-scope-repo-month-rows "${EXPECTED_SCOPE_REPO_MONTH_ROWS}"
  --expected-primary-selected-files "${EXPECTED_PRIMARY_SELECTED_FILES}"
  --expected-primary-selected-issues "${EXPECTED_PRIMARY_SELECTED_ISSUES}"
  --expected-primary-selected-code-smell "${EXPECTED_PRIMARY_SELECTED_CODE_SMELL}"
  --expected-primary-sensitivity-selected-files "${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_FILES}"
  --expected-primary-sensitivity-selected-issues "${EXPECTED_PRIMARY_SENSITIVITY_SELECTED_ISSUES}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  I04_COMMAND+=(--strict-expected-counts)
fi

run_command_logged \
  "Step 4: Aggregate frozen FUN+C_FUN-NPR thresholds to repo-month quality burden" \
  "${I04_COMMAND[@]}"

EXPECTED_OUTPUTS=(
  "${PANEL_OUTPUT}"
  "${GLOBAL_AUDIT_OUTPUT}"
  "${TIMING_AUDIT_OUTPUT}"
  "${SAMPLE_SUMMARY_OUTPUT}"
  "${SCOPE_SENSITIVITY_OUTPUT}"
  "${OUTCOME_SPEC_OUTPUT}"
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

if grep -q ',fail,' "${CHECKS_OUTPUT}" || grep -q ',fail$' "${CHECKS_OUTPUT}"; then
  echo "ERROR: I04 QC file contains failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${CHECKS_OUTPUT}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

GLOBAL_LINES="$(wc -l < "${GLOBAL_AUDIT_OUTPUT}")"
TIMING_LINES="$(wc -l < "${TIMING_AUDIT_OUTPUT}")"
SAMPLE_LINES="$(wc -l < "${SAMPLE_SUMMARY_OUTPUT}")"
SCOPE_LINES="$(wc -l < "${SCOPE_SENSITIVITY_OUTPUT}")"
OUTCOME_LINES="$(wc -l < "${OUTCOME_SPEC_OUTPUT}")"
LONG_PANEL_ROWS="$(awk -F, '$1=="long_panel_rows" {print $2}' "${SUMMARY_OUTPUT}")"
PANEL_LINES="$(gzip -cd "${PANEL_OUTPUT}" | wc -l)"
EXPECTED_PANEL_LINES="$((LONG_PANEL_ROWS + 1))"

if [[ "${GLOBAL_LINES}" -ne 45 ]]; then
  echo "ERROR: expected 45 lines in global audit; observed ${GLOBAL_LINES}." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if [[ "${TIMING_LINES}" -ne 221 ]]; then
  echo "ERROR: expected 221 lines in treatment-timing audit; observed ${TIMING_LINES}." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if [[ "${SAMPLE_LINES}" -ne 3 || "${OUTCOME_LINES}" -ne 9 ]]; then
  echo "ERROR: unexpected sample/outcome line counts: sample=${SAMPLE_LINES}, outcome=${OUTCOME_LINES}." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if [[ "${SCOPE_LINES}" -ne "$((EXPECTED_SCOPE_REPOSITORIES + 1))" ]]; then
  echo "ERROR: unexpected scope-sensitivity line count: ${SCOPE_LINES}." | tee -a "${LOG_FILE}" >&2
  exit 1
fi
if [[ "${PANEL_LINES}" -ne "${EXPECTED_PANEL_LINES}" ]]; then
  echo "ERROR: compressed panel line count mismatch: observed=${PANEL_LINES}, expected=${EXPECTED_PANEL_LINES}." | tee -a "${LOG_FILE}" >&2
  exit 1
fi

{
  echo
  echo "** Step 5: Output checks"
  echo "----------------------------------------------------------------------------"
  echo "Long panel rows:                 ${LONG_PANEL_ROWS}"
  echo "Long panel lines:                ${PANEL_LINES} including header"
  echo "Global audit:                    ${GLOBAL_LINES} lines including header"
  echo "Timing audit:                    ${TIMING_LINES} lines including header"
  echo "Sample summary:                  ${SAMPLE_LINES} lines including header"
  echo "Scope sensitivity:               ${SCOPE_LINES} lines including header"
  echo "Outcome spec:                    ${OUTCOME_LINES} lines including header"
  echo "QC checks:                       $(wc -l < "${CHECKS_OUTPUT}") lines including header"
  echo "Summary:                         $(wc -l < "${SUMMARY_OUTPUT}") lines including header"
  echo
  echo "Sample support:"
  cat "${SAMPLE_SUMMARY_OUTPUT}"
  echo
  echo "Scope-sensitivity repositories:"
  cat "${SCOPE_SENSITIVITY_OUTPUT}"
  echo
  echo "Primary-threshold global audit:"
  awk -F, 'NR==1 || $3=="primary"' "${GLOBAL_AUDIT_OUTPUT}"
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
  echo "Long I05 input panel:            ${PANEL_OUTPUT}"
  echo "Global threshold audit:          ${GLOBAL_AUDIT_OUTPUT}"
  echo "Treatment-timing audit:          ${TIMING_AUDIT_OUTPUT}"
  echo "Sample summary:                  ${SAMPLE_SUMMARY_OUTPUT}"
  echo "Scope sensitivity spec:          ${SCOPE_SENSITIVITY_OUTPUT}"
  echo "Outcome specification:           ${OUTCOME_SPEC_OUTPUT}"
  echo "QC checks:                       ${CHECKS_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Metadata:                        ${METADATA_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            I05 Borusyak DiD over frozen thresholds and both sample specifications"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
