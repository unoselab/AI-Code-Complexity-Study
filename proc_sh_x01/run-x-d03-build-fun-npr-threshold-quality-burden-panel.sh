#!/usr/bin/env bash

set -euo pipefail

# ============================================================================
# run-x-d03 v1: build frozen-threshold FUN-NPR x SonarQube burden panel
# ============================================================================
#
# Purpose:
#   1. Reuse the canonical D02 file-level Quality x FUN-NPR table.
#   2. Reuse the outcome-blind D01 frozen 22-threshold specification.
#   3. Reuse the D02-a pre-specified two-repository scope sensitivity.
#   4. Reuse the D02-b confirmed alias handling policy, which keeps canonical
#      A12 paths and excludes duplicate filesystem-alias issue rows.
#   5. Aggregate selected-file SonarQube issue stock to repository-month rows.
#   6. Emit both the full sample and the pre-specified scope-sensitivity sample
#      in one long-format panel for the downstream D04 Borusyak DiD.
#
# This wrapper was created by copying the established D02-a execution/provenance
# structure and adapting it for D03. It is fully standalone and does not call
# any older experiment wrapper.
#
# Threshold eligibility and selection:
#   eligible = finite(file_npr_fun_space_by_token_weighted)
#   selected = eligible AND file_npr_fun_space_by_token_weighted > threshold
#
# Important semantics:
#   - Non-finite/no-FUN files are unclassified. They are not below-threshold.
#   - Quality outcomes are unresolved SonarQube issue stocks at historical
#     snapshots, restricted to canonical A12-backed file paths.
#   - NPR thresholds were frozen in D01 before SonarQube outcomes were used.
#   - NPR is not inserted as a regression control; thresholded burden is a
#     decomposition/mechanism outcome and NPR may be post-treatment.
#   - Selected-file density is not computed because file-level SonarQube NCLOC
#     is not yet available.
#
# Inputs:
#   repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#   repo_x01/run-x-d01/fun_npr_threshold_spec.csv
#   repo_x01/run-x-d01/fun_npr_threshold_audit.csv
#   repo_x01/run-x-d02-a/quality_npr_scope_sensitivity_spec.csv
#   repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_summary.csv
#   repo_x01/run-x-d02-b/quality_npr_alias_handling_spec.csv
#   repo_x01/run-x-d02-b/python_sonarqube_alias_issue_summary.csv
#
# Main outputs under repo_x01/run-x-d03/:
#   quality_fun_npr_threshold_repo_month_panel.csv.gz
#   quality_fun_npr_threshold_global_audit.csv
#   quality_fun_npr_threshold_by_treatment_timing.csv
#   quality_fun_npr_threshold_sample_summary.csv
#   quality_fun_npr_outcome_spec.csv
#   quality_fun_npr_threshold_checks.csv
#   quality_fun_npr_threshold_summary.csv
#   metadata.json
#
# Full run:
#   bash proc_sh_x01/run-x-d03-build-fun-npr-threshold-quality-burden-panel.sh
#
# Self-test only:
#   SELF_TEST_ONLY=1 bash proc_sh_x01/run-x-d03-build-fun-npr-threshold-quality-burden-panel.sh
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-d03"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-fun-npr-threshold-quality-burden-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/build_fun_npr_threshold_quality_burden_panel.py}"

D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
D02_SUMMARY_FILE="${D02_SUMMARY_FILE:-repo_x01/run-x-d02/python_fun_file_quality_summary.csv}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
THRESHOLD_SPEC_FILE="${THRESHOLD_SPEC_FILE:-repo_x01/run-x-d01/fun_npr_threshold_spec.csv}"
THRESHOLD_AUDIT_FILE="${THRESHOLD_AUDIT_FILE:-repo_x01/run-x-d01/fun_npr_threshold_audit.csv}"
SCOPE_SENSITIVITY_SPEC_FILE="${SCOPE_SENSITIVITY_SPEC_FILE:-repo_x01/run-x-d02-a/quality_npr_scope_sensitivity_spec.csv}"
D02A_SUMMARY_FILE="${D02A_SUMMARY_FILE:-repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_summary.csv}"
ALIAS_HANDLING_SPEC_FILE="${ALIAS_HANDLING_SPEC_FILE:-repo_x01/run-x-d02-b/quality_npr_alias_handling_spec.csv}"
D02B_SUMMARY_FILE="${D02B_SUMMARY_FILE:-repo_x01/run-x-d02-b/python_sonarqube_alias_issue_summary.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-d03}"
PANEL_OUTPUT="${PANEL_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_repo_month_panel.csv.gz}"
GLOBAL_AUDIT_OUTPUT="${GLOBAL_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_global_audit.csv}"
TIMING_AUDIT_OUTPUT="${TIMING_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_by_treatment_timing.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_sample_summary.csv}"
OUTCOME_SPEC_OUTPUT="${OUTCOME_SPEC_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_outcome_spec.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_fun_npr_threshold_summary.csv}"
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
EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_FINITE_FUN_ROWS="${EXPECTED_FINITE_FUN_ROWS:-204508}"

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
  "${EXPECTED_DYNAMIC_ROWS}" "${EXPECTED_D02_ROWS}" "${EXPECTED_FINITE_FUN_ROWS}"; do
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
  echo "ERROR: required D03 Python program not found: ${ANALYSIS_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

{
  echo "============================================================================"
  echo "${RUN_LABEL}: build frozen-threshold Quality x FUN-NPR burden panel"
  echo "Started:                         $(date '+%a %b %d %I:%M:%S %p %Z %Y')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${PYTHON_VERSION})"
  echo "Python script:                   ${ANALYSIS_SCRIPT}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "D02 file-level burden:           ${D02_FILE}"
  echo "B06 quality panel:               ${B06_PANEL_FILE}"
  echo "D01 threshold spec:              ${THRESHOLD_SPEC_FILE}"
  echo "D01 threshold audit:             ${THRESHOLD_AUDIT_FILE}"
  echo "D02-a sensitivity spec:          ${SCOPE_SENSITIVITY_SPEC_FILE}"
  echo "D02-b alias handling:            ${ALIAS_HANDLING_SPEC_FILE}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "NPR metric:                      file_npr_fun_space_by_token_weighted"
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
  "Step 1: Run D03 structural self-test" \
  "${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test

run_command_logged \
  "Step 2: Compile D03 Python program" \
  "${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL} self-tests completed successfully." | tee -a "${LOG_FILE}"
  exit 0
fi

REQUIRED_INPUTS=(
  "${D02_FILE}"
  "${D02_SUMMARY_FILE}"
  "${B06_PANEL_FILE}"
  "${THRESHOLD_SPEC_FILE}"
  "${THRESHOLD_AUDIT_FILE}"
  "${SCOPE_SENSITIVITY_SPEC_FILE}"
  "${D02A_SUMMARY_FILE}"
  "${ALIAS_HANDLING_SPEC_FILE}"
  "${D02B_SUMMARY_FILE}"
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
  echo "D02 file SHA256:                 $(sha256sum "${D02_FILE}" | awk '{print $1}')"
  echo "D02 summary SHA256:              $(sha256sum "${D02_SUMMARY_FILE}" | awk '{print $1}')"
  echo "B06 panel SHA256:                $(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"
  echo "D01 threshold spec SHA256:       $(sha256sum "${THRESHOLD_SPEC_FILE}" | awk '{print $1}')"
  echo "D01 threshold audit SHA256:      $(sha256sum "${THRESHOLD_AUDIT_FILE}" | awk '{print $1}')"
  echo "D02-a sensitivity SHA256:        $(sha256sum "${SCOPE_SENSITIVITY_SPEC_FILE}" | awk '{print $1}')"
  echo "D02-a summary SHA256:            $(sha256sum "${D02A_SUMMARY_FILE}" | awk '{print $1}')"
  echo "D02-b handling SHA256:           $(sha256sum "${ALIAS_HANDLING_SPEC_FILE}" | awk '{print $1}')"
  echo "D02-b summary SHA256:            $(sha256sum "${D02B_SUMMARY_FILE}" | awk '{print $1}')"
} | tee -a "${LOG_FILE}"

D03_COMMAND=(
  "${PYTHON_BIN}"
  "${ANALYSIS_SCRIPT}"
  --d02-file "${D02_FILE}"
  --d02-summary-file "${D02_SUMMARY_FILE}"
  --b06-panel-file "${B06_PANEL_FILE}"
  --threshold-spec-file "${THRESHOLD_SPEC_FILE}"
  --threshold-audit-file "${THRESHOLD_AUDIT_FILE}"
  --scope-sensitivity-spec-file "${SCOPE_SENSITIVITY_SPEC_FILE}"
  --d02a-summary-file "${D02A_SUMMARY_FILE}"
  --alias-handling-spec-file "${ALIAS_HANDLING_SPEC_FILE}"
  --d02b-summary-file "${D02B_SUMMARY_FILE}"
  --panel-output "${PANEL_OUTPUT}"
  --global-audit-output "${GLOBAL_AUDIT_OUTPUT}"
  --timing-audit-output "${TIMING_AUDIT_OUTPUT}"
  --sample-summary-output "${SAMPLE_SUMMARY_OUTPUT}"
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
  --expected-d02-rows "${EXPECTED_D02_ROWS}"
  --expected-finite-fun-rows "${EXPECTED_FINITE_FUN_ROWS}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  D03_COMMAND+=(--strict-expected-counts)
fi

run_command_logged \
  "Step 4: Aggregate frozen FUN-NPR thresholds to repo-month quality burden" \
  "${D03_COMMAND[@]}"

EXPECTED_OUTPUTS=(
  "${PANEL_OUTPUT}"
  "${GLOBAL_AUDIT_OUTPUT}"
  "${TIMING_AUDIT_OUTPUT}"
  "${SAMPLE_SUMMARY_OUTPUT}"
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
  echo "ERROR: D03 QC file contains failed checks." | tee -a "${LOG_FILE}" >&2
  cat "${CHECKS_OUTPUT}" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

GLOBAL_LINES="$(wc -l < "${GLOBAL_AUDIT_OUTPUT}")"
TIMING_LINES="$(wc -l < "${TIMING_AUDIT_OUTPUT}")"
SAMPLE_LINES="$(wc -l < "${SAMPLE_SUMMARY_OUTPUT}")"
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
  echo "ERROR: unexpected sample/outcome specification line counts: sample=${SAMPLE_LINES}, outcome=${OUTCOME_LINES}." | tee -a "${LOG_FILE}" >&2
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
  echo "Outcome spec:                    ${OUTCOME_LINES} lines including header"
  echo "QC checks:                       $(wc -l < "${CHECKS_OUTPUT}") lines including header"
  echo "Summary:                         $(wc -l < "${SUMMARY_OUTPUT}") lines including header"
  echo
  echo "Sample support:"
  cat "${SAMPLE_SUMMARY_OUTPUT}"
  echo
  echo "Primary-threshold global audit:"
  awk -F, 'NR==1 || $2=="primary"' "${GLOBAL_AUDIT_OUTPUT}"
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
  echo "Long D04 input panel:            ${PANEL_OUTPUT}"
  echo "Global threshold audit:          ${GLOBAL_AUDIT_OUTPUT}"
  echo "Treatment-timing audit:          ${TIMING_AUDIT_OUTPUT}"
  echo "Sample summary:                  ${SAMPLE_SUMMARY_OUTPUT}"
  echo "Outcome specification:           ${OUTCOME_SPEC_OUTPUT}"
  echo "QC checks:                       ${CHECKS_OUTPUT}"
  echo "Summary:                         ${SUMMARY_OUTPUT}"
  echo "Metadata:                        ${METADATA_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "Next:                            D04 Borusyak DiD over frozen thresholds and both sample specifications"
  echo "============================================================================"
} | tee -a "${LOG_FILE}"
