#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-x-h05 v1: build ML C_FUN-selected Python SonarQube quality-burden panel
# =============================================================================
#
# Purpose:
#   1. Reuse frozen run-x-a07 ML file classifications from the ai_detector
#      workspace. Do not rerun ML inference or change the > 0.50 primary rule.
#   2. Reuse the canonical run-x-d02 historical Python file-level SonarQube
#      burden table. Do not rerun SonarQube or recollect B05 issues.
#   3. Join A07 to D02 exactly by snapshot_id + relative_path + file_sha256.
#   4. Require the unique historical snapshot/file universe to reconcile at
#      494,592 rows on both sides.
#   5. Aggregate the frozen primary ML-selected files to the canonical B06
#      1,954-row repository-month quality panel.
#   6. Emit two repository sample specifications and two ML mapping specs:
#        - full_sample
#        - exclude_scope_mismatch_repos
#        - all_ml_files (primary)
#        - exclude_mapping_warning_files (pre-specified robustness)
#   7. Preserve unresolved historical SonarQube issue stock semantics.
#   8. Stop before causal estimation. H06 will run the Borusyak DiD.
#
# Important semantics:
#   - A07 no_ml_cfun and file_not_prepared rows remain unclassified. They are
#     never imputed as HWC.
#   - Primary file selection is frozen upstream:
#       file_ml_cfun_agc_share_space_by_token_weighted > 0.50
#   - H05 does not select a new threshold from SonarQube outcomes.
#   - H05 does not compute selected-file issue density because file-level
#     SonarQube NCLOC is not part of the frozen input contract.
#   - B06 ncloc_py_sonarqube is retained only as the same whole-snapshot
#     covariate used by the validated adjusted quality-burden design.
#
# Development files:
#   proc_script_x01/build_ml_cfun_quality_burden_panel-v1.py
#   proc_sh_x01/run-x-h05-build-ml-cfun-quality-burden-panel-v1.sh
#
# Canonical server deployment names after removing the version suffix:
#   proc_script_x01/build_ml_cfun_quality_burden_panel.py
#   proc_sh_x01/run-x-h05-build-ml-cfun-quality-burden-panel.sh
#
# This wrapper was created by copying the established run-x-d05 wrapper and
# adapting its standalone execution/provenance/QC pattern for H05. It does not
# call any older experiment shell wrapper.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-h05"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-ml-cfun-quality-burden-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-proc_script_x01/build_ml_cfun_quality_burden_panel.py}"

# Frozen A07 ML C_FUN file classification from the sibling ai_detector workspace.
A07_ROOT="${A07_ROOT:-${PROJECT_ROOT}/../../ai_detector/src/app/data_did_agc_analysis/run-x-a07}"
A07_FILE="${A07_FILE:-${A07_ROOT}/python_ml_cfun_file_scores.csv}"
A07_SUMMARY_FILE="${A07_SUMMARY_FILE:-${A07_ROOT}/summary.json}"
A07_CHECKS_FILE="${A07_CHECKS_FILE:-${A07_ROOT}/checks.csv}"

# Canonical SonarQube file burden and quality-panel inputs in this workspace.
# NOTE: the D02 filename contains "fun" for historical lineage only; D02 is the
# detector-neutral historical Python file-quality burden table reused by H05.
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
D02_SUMMARY_FILE="${D02_SUMMARY_FILE:-repo_x01/run-x-d02/python_fun_file_quality_summary.csv}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
SCOPE_SENSITIVITY_SPEC_FILE="${SCOPE_SENSITIVITY_SPEC_FILE:-repo_x01/run-x-d02-a/quality_npr_scope_sensitivity_spec.csv}"
D02A_SUMMARY_FILE="${D02A_SUMMARY_FILE:-repo_x01/run-x-d02-a/python_sonarqube_outside_a12_scope_summary.csv}"
ALIAS_HANDLING_SPEC_FILE="${ALIAS_HANDLING_SPEC_FILE:-repo_x01/run-x-d02-b/quality_npr_alias_handling_spec.csv}"
D02B_SUMMARY_FILE="${D02B_SUMMARY_FILE:-repo_x01/run-x-d02-b/python_sonarqube_alias_issue_summary.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-h05}"
PANEL_OUTPUT="${PANEL_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_repo_month_panel.csv.gz}"
GLOBAL_AUDIT_OUTPUT="${GLOBAL_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_global_audit.csv}"
TIMING_AUDIT_OUTPUT="${TIMING_AUDIT_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_by_treatment_timing.csv}"
SAMPLE_SUMMARY_OUTPUT="${SAMPLE_SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_sample_summary.csv}"
OUTCOME_SPEC_OUTPUT="${OUTCOME_SPEC_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_outcome_spec.csv}"
CHECKS_OUTPUT="${CHECKS_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_checks.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${OUTPUT_DIR}/quality_ml_cfun_summary.csv}"
METADATA_OUTPUT="${METADATA_OUTPUT:-${OUTPUT_DIR}/metadata.json}"

STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE="${OVERWRITE:-0}"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}" >&2
    exit 1
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command_name}" >&2
    exit 1
  fi
}

if [[ "${SELF_TEST_ONLY}" != "0" && "${SELF_TEST_ONLY}" != "1" ]]; then
  echo "ERROR: SELF_TEST_ONLY must be 0 or 1" >&2
  exit 2
fi
if [[ "${OVERWRITE}" != "0" && "${OVERWRITE}" != "1" ]]; then
  echo "ERROR: OVERWRITE must be 0 or 1" >&2
  exit 2
fi

require_command "${PYTHON_BIN}"
require_file "${ANALYSIS_SCRIPT}" "H05 Python program"
mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

if [[ "${SELF_TEST_ONLY}" == "0" && "${OVERWRITE}" != "1" && -e "${PANEL_OUTPUT}" ]]; then
  echo "ERROR: output already exists: ${PANEL_OUTPUT}" >&2
  echo "Set OVERWRITE=1 only when intentionally rebuilding H05." >&2
  exit 1
fi

exec > >(tee "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
START_TEXT="$(date)"
PYTHON_VERSION="$(${PYTHON_BIN} -c 'import sys; print(sys.version.split()[0])')"
SCRIPT_SHA256="$(sha256sum "${ANALYSIS_SCRIPT}" | awk '{print $1}')"

echo "============================================================================"
echo "${RUN_LABEL}: build ML C_FUN-selected Python SonarQube quality-burden panel"
echo "Started:                         ${START_TEXT}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${ANALYSIS_SCRIPT}"
echo "Python script SHA256:            ${SCRIPT_SHA256}"
echo "A07 file scores:                 ${A07_FILE}"
echo "D02 canonical file burden:       ${D02_FILE}"
echo "B06 quality panel:               ${B06_PANEL_FILE}"
echo "Primary ML metric:               file_ml_cfun_agc_share_space_by_token_weighted"
echo "Primary ML rule:                 > 0.50"
echo "No-C_FUN policy:                   unclassified; never HWC"
echo "Primary mapping spec:            all_ml_files"
echo "Mapping robustness:              exclude_mapping_warning_files"
echo "Scope robustness:                exclude_scope_mismatch_repos"
echo "SonarQube rerun:                 disabled"
echo "DiD estimation:                  disabled (H06)"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"
echo

echo "** Step 1: Run H05 structural self-test"
echo "----------------------------------------------------------------------------"
"${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" --self-test
echo

echo "** Step 2: Compile H05 Python program"
echo "----------------------------------------------------------------------------"
"${PYTHON_BIN}" -m py_compile "${ANALYSIS_SCRIPT}"
echo

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "SELF_TEST_ONLY=1: stopping after self-test and compile checks."
  exit 0
fi

for input_path in \
  "${A07_FILE}" \
  "${A07_SUMMARY_FILE}" \
  "${A07_CHECKS_FILE}" \
  "${D02_FILE}" \
  "${D02_SUMMARY_FILE}" \
  "${B06_PANEL_FILE}" \
  "${SCOPE_SENSITIVITY_SPEC_FILE}" \
  "${D02A_SUMMARY_FILE}" \
  "${ALIAS_HANDLING_SPEC_FILE}" \
  "${D02B_SUMMARY_FILE}"; do
  require_file "${input_path}" "required H05 input"
done

echo "** Step 3: Freeze exact input provenance"
echo "----------------------------------------------------------------------------"
echo "A07 file SHA256:                 $(sha256sum "${A07_FILE}" | awk '{print $1}')"
echo "A07 summary SHA256:              $(sha256sum "${A07_SUMMARY_FILE}" | awk '{print $1}')"
echo "A07 checks SHA256:               $(sha256sum "${A07_CHECKS_FILE}" | awk '{print $1}')"
echo "D02 file SHA256:                 $(sha256sum "${D02_FILE}" | awk '{print $1}')"
echo "D02 summary SHA256:              $(sha256sum "${D02_SUMMARY_FILE}" | awk '{print $1}')"
echo "B06 panel SHA256:                $(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"
echo "D02-a sensitivity SHA256:        $(sha256sum "${SCOPE_SENSITIVITY_SPEC_FILE}" | awk '{print $1}')"
echo "D02-a summary SHA256:            $(sha256sum "${D02A_SUMMARY_FILE}" | awk '{print $1}')"
echo "D02-b alias spec SHA256:         $(sha256sum "${ALIAS_HANDLING_SPEC_FILE}" | awk '{print $1}')"
echo "D02-b summary SHA256:            $(sha256sum "${D02B_SUMMARY_FILE}" | awk '{print $1}')"
echo

echo "** Step 4: Build H05 repo-month panel"
echo "----------------------------------------------------------------------------"
ARGS=(
  --a07-file "${A07_FILE}"
  --a07-summary-file "${A07_SUMMARY_FILE}"
  --a07-checks-file "${A07_CHECKS_FILE}"
  --d02-file "${D02_FILE}"
  --d02-summary-file "${D02_SUMMARY_FILE}"
  --b06-panel-file "${B06_PANEL_FILE}"
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
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  ARGS+=(--strict-expected-counts)
fi
"${PYTHON_BIN}" "${ANALYSIS_SCRIPT}" "${ARGS[@]}"
echo

echo "** Step 5: Verify written artifacts"
echo "----------------------------------------------------------------------------"
for output_path in \
  "${PANEL_OUTPUT}" \
  "${GLOBAL_AUDIT_OUTPUT}" \
  "${TIMING_AUDIT_OUTPUT}" \
  "${SAMPLE_SUMMARY_OUTPUT}" \
  "${OUTCOME_SPEC_OUTPUT}" \
  "${CHECKS_OUTPUT}" \
  "${SUMMARY_OUTPUT}" \
  "${METADATA_OUTPUT}"; do
  require_file "${output_path}" "H05 output"
done

gzip -t "${PANEL_OUTPUT}"
FAILED_CHECKS="$(awk -F',' 'NR > 1 && $4 != "pass" {n++} END {print n+0}' "${CHECKS_OUTPUT}")"
if [[ "${FAILED_CHECKS}" != "0" ]]; then
  echo "ERROR: H05 checks contain ${FAILED_CHECKS} failures" >&2
  exit 1
fi

SUMMARY_STATUS="$(awk -F',' '$1 == "status" {print $2}' "${SUMMARY_OUTPUT}" | tail -n 1 | tr -d '\r')"
if [[ "${SUMMARY_STATUS}" != "PASS" ]]; then
  echo "ERROR: H05 summary status is not PASS: ${SUMMARY_STATUS}" >&2
  exit 1
fi

echo "H05 output verification: PASS"
echo "Panel compressed size:           $(du -h "${PANEL_OUTPUT}" | awk '{print $1}')"
echo "Panel rows incl. header:         $(gzip -cd "${PANEL_OUTPUT}" | wc -l)"
echo "Failed hard checks:              ${FAILED_CHECKS}"
echo

END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_FMT '%02d:%02d:%02d' "$((ELAPSED / 3600))" "$(((ELAPSED % 3600) / 60))" "$((ELAPSED % 60))"

echo "============================================================================"
echo "${RUN_LABEL} execution summary"
echo "Started:          ${START_TEXT}"
echo "Completed:        $(date)"
echo "Elapsed:          ${ELAPSED_FMT}"
echo "Exit code:        0"
echo "Output directory: ${OUTPUT_DIR}"
echo "Panel:            ${PANEL_OUTPUT}"
echo "Log file:         ${LOG_FILE}"
echo "============================================================================"
