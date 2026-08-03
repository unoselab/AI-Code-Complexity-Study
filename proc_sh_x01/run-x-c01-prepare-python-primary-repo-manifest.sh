#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c01-v4: prepare the Python-primary repository manifest
# ============================================================
#
# Inputs:
#   1. matching.csv
#      Paper treatment-to-control assignments.
#   2. repos.csv
#      Repository metadata containing repo_primary_language.
#   3. panel_event_monthly.csv
#      Paper repository-month panel used to reproduce the Appendix language
#      subset and its event-window restrictions.
#   4. Existing treatment/control clone directories
#      Inspected with read-only Git commands. No repository is changed.
#
# Outputs:
#   - Appendix Python-treatment list.
#   - Strict matched-treatment list and unmatched-treatment audit.
#   - Matched-control list and slot-level assignment audit.
#   - Appendix-faithful 121-treatment plus 127-control clone manifest.
#   - Existing local clone availability audit, counts, and QC.
#
# This wrapper reuses the input/output and logging structure of earlier
# project wrappers, but it does not call or depend on any existing shell script.

PROJECT_ROOT="$(pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
IMPLEMENTATION_VERSION="v4"

MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"
REPOS_FILE="${REPOS_FILE:-data_baseline_backup/repos.csv}"
PANEL_FILE="${PANEL_FILE:-data_baseline_backup/panel_event_monthly.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-python-primary-repo}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-python-primary-repo}"

PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/prepare_python_primary_repo_manifest.py}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-c01}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-repo_x01/tmp/run-x-c01/python_primary_repo_manifest_summary.csv}"

TARGET_LANGUAGE="${TARGET_LANGUAGE:-Python}"
MIN_TREATMENT_EVENT="${MIN_TREATMENT_EVENT:-202408}"
MAX_TREATMENT_EVENT="${MAX_TREATMENT_EVENT:-202503}"
EXPECTED_PAPER_TREATMENT_REPOS="${EXPECTED_PAPER_TREATMENT_REPOS:-121}"
EXPECTED_PAPER_CONTROL_REPOS="${EXPECTED_PAPER_CONTROL_REPOS:-127}"
EXPECTED_MATCHED_TREATMENT_REPOS="${EXPECTED_MATCHED_TREATMENT_REPOS:-114}"
EXPECTED_TREATMENT_REPOS_WITHOUT_MATCHING="${EXPECTED_TREATMENT_REPOS_WITHOUT_MATCHING:-7}"
EXPECTED_CLONE_TARGET_REPOS="${EXPECTED_CLONE_TARGET_REPOS:-248}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
INSPECT_LOCAL_CLONES="${INSPECT_LOCAL_CLONES:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run-x-c01-v4-prepare-python-primary-repo-manifest-${TIMESTAMP}.log}"

mkdir -p \
  "$(dirname "${LOG_FILE}")" \
  "${OUTPUT_DIR}" \
  "$(dirname "${SUMMARY_OUTPUT}")" \
  "${TREATMENT_CLONE_DIR}" \
  "${CONTROL_CLONE_DIR}"

for required_file in "${MATCHING_FILE}" "${REPOS_FILE}" "${PANEL_FILE}" "${PYTHON_SCRIPT}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

"${PYTHON_BIN}" -c 'import pandas' >/dev/null

python_version="$(${PYTHON_BIN} --version 2>&1)"
script_sha256="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
matching_sha256="$(sha256sum "${MATCHING_FILE}" | awk '{print $1}')"
repos_sha256="$(sha256sum "${REPOS_FILE}" | awk '{print $1}')"
panel_sha256="$(sha256sum "${PANEL_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "run-x-c01-v4: prepare Python-primary repository manifest"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${python_version})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python analysis script:          ${PYTHON_SCRIPT}"
  echo "Python script SHA256:             ${script_sha256}"
  echo "Matching input:                  ${MATCHING_FILE}"
  echo "Matching SHA256:                 ${matching_sha256}"
  echo "Repository metadata:             ${REPOS_FILE}"
  echo "Repository metadata SHA256:      ${repos_sha256}"
  echo "Paper event panel:               ${PANEL_FILE}"
  echo "Paper event panel SHA256:        ${panel_sha256}"
  echo "Treatment clone directory:       ${TREATMENT_CLONE_DIR}"
  echo "Control clone directory:         ${CONTROL_CLONE_DIR}"
  echo "Target primary language:         ${TARGET_LANGUAGE}"
  echo "Treatment event window:          ${MIN_TREATMENT_EVENT}:${MAX_TREATMENT_EVENT}"
  echo "Expected paper treatment repos:  ${EXPECTED_PAPER_TREATMENT_REPOS}"
  echo "Expected paper control repos:    ${EXPECTED_PAPER_CONTROL_REPOS}"
  echo "Expected matched treatment repos:${EXPECTED_MATCHED_TREATMENT_REPOS}"
  echo "Expected treatments w/o match:   ${EXPECTED_TREATMENT_REPOS_WITHOUT_MATCHING}"
  echo "Expected clone targets:          ${EXPECTED_CLONE_TARGET_REPOS}"
  echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
  echo "Inspect existing clones:         ${INSPECT_LOCAL_CLONES}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Build the paper-aligned Python repository manifest"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

command=(
  "${PYTHON_BIN}" "${PYTHON_SCRIPT}"
  --matching-file "${MATCHING_FILE}"
  --repos-file "${REPOS_FILE}"
  --panel-file "${PANEL_FILE}"
  --treatment-clone-dir "${TREATMENT_CLONE_DIR}"
  --control-clone-dir "${CONTROL_CLONE_DIR}"
  --output-dir "${OUTPUT_DIR}"
  --summary-output "${SUMMARY_OUTPUT}"
  --target-language "${TARGET_LANGUAGE}"
  --min-treatment-event "${MIN_TREATMENT_EVENT}"
  --max-treatment-event "${MAX_TREATMENT_EVENT}"
  --expected-paper-treatment-repos "${EXPECTED_PAPER_TREATMENT_REPOS}"
  --expected-paper-control-repos "${EXPECTED_PAPER_CONTROL_REPOS}"
  --expected-matched-treatment-repos "${EXPECTED_MATCHED_TREATMENT_REPOS}"
  --expected-treatment-repos-without-matching "${EXPECTED_TREATMENT_REPOS_WITHOUT_MATCHING}"
  --expected-clone-target-repos "${EXPECTED_CLONE_TARGET_REPOS}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --inspect-local-clones "${INSPECT_LOCAL_CLONES}"
  --log-level "${LOG_LEVEL}"
)

printf 'Command:' | tee -a "${LOG_FILE}"
printf ' %q' "${command[@]}" | tee -a "${LOG_FILE}"
printf '\n\n' | tee -a "${LOG_FILE}"

set +e
"${command[@]}" 2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "ERROR: run-x-c01-v4 failed with status ${run_status}." | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

output_files=(
  "${OUTPUT_DIR}/python_primary_treatment_repos.csv"
  "${OUTPUT_DIR}/python_primary_matched_treatment_repos.csv"
  "${OUTPUT_DIR}/python_primary_treatments_absent_from_matching.csv"
  "${OUTPUT_DIR}/python_primary_matched_control_repos.csv"
  "${OUTPUT_DIR}/python_primary_clone_manifest.csv"
  "${OUTPUT_DIR}/python_primary_matching_language_audit.csv"
  "${OUTPUT_DIR}/python_primary_language_metadata_unresolved.csv"
  "${OUTPUT_DIR}/python_primary_clone_availability_audit.csv"
  "${OUTPUT_DIR}/python_primary_repo_counts.csv"
  "${OUTPUT_DIR}/python_primary_manifest_qc.csv"
  "${OUTPUT_DIR}/python_primary_repo_metadata_conflicts.csv"
  "${OUTPUT_DIR}/python_primary_scope_issues.csv"
  "${SUMMARY_OUTPUT}"
)

for output_file in "${output_files[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output not found: ${output_file}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

wc -l "${output_files[@]}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Repository counts:" | tee -a "${LOG_FILE}"
cat "${OUTPUT_DIR}/python_primary_repo_counts.csv" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "QC checks:" | tee -a "${LOG_FILE}"
cat "${OUTPUT_DIR}/python_primary_manifest_qc.csv" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Clone manifest preview:" | tee -a "${LOG_FILE}"
head -n 11 "${OUTPUT_DIR}/python_primary_clone_manifest.csv" | tee -a "${LOG_FILE}"

{
  echo
  echo "============================================================"
  echo "run-x-c01-v4 completed successfully."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Appendix Python treatments:     ${OUTPUT_DIR}/python_primary_treatment_repos.csv"
  echo "Matched Python treatments:      ${OUTPUT_DIR}/python_primary_matched_treatment_repos.csv"
  echo "Treatments absent from match:   ${OUTPUT_DIR}/python_primary_treatments_absent_from_matching.csv"
  echo "Matched control repositories:   ${OUTPUT_DIR}/python_primary_matched_control_repos.csv"
  echo "Clone manifest:                 ${OUTPUT_DIR}/python_primary_clone_manifest.csv"
  echo "Language audit:                 ${OUTPUT_DIR}/python_primary_matching_language_audit.csv"
  echo "Clone availability audit:       ${OUTPUT_DIR}/python_primary_clone_availability_audit.csv"
  echo "Counts:                         ${OUTPUT_DIR}/python_primary_repo_counts.csv"
  echo "QC:                             ${OUTPUT_DIR}/python_primary_manifest_qc.csv"
  echo "Summary:                        ${SUMMARY_OUTPUT}"
  echo "Log file:                       ${LOG_FILE}"
  echo "Next step:                      review Appendix-faithful 121-treatment/127-control clone scope before C02 cloning"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
