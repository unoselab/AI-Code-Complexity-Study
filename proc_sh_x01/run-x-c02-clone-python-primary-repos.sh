#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-c02-v1: clone Appendix Python-scope repositories
# ============================================================
#
# Input:
#   repo_x01/run-x-c01/python_primary_clone_manifest.csv
#
#   The C01 manifest contains 121 Appendix Python treatment repositories and
#   127 paper-selected control repositories. The seven treatments that do not
#   have a treatment row in matching.csv remain included because they are part
#   of the Appendix Python treatment sample.
#
# Clone destinations:
#   ../treatment-python-primary-repo
#   ../control-python-primary-repo
#
# Outputs:
#   - One final status row for every manifest repository.
#   - One row for every actual Git clone attempt.
#   - A failure-only table with classified reasons.
#   - Manifest and clone-availability QC.
#   - A compact execution summary.
#
# Safety and reproducibility:
#   - Full Git history is cloned; no --depth or partial-clone filter is used.
#   - Existing valid clones are inspected and skipped without pull/reset/clean.
#   - Invalid existing paths are not modified unless a repair option is set.
#   - New clones are created in temporary sibling paths and renamed only after
#     Git and HEAD validation succeeds.
#   - Git credential prompts are disabled so unavailable repositories do not
#     block the experiment indefinitely.
#
# This wrapper follows the logging and output-check structure of existing
# project wrappers, but it does not call or depend on an earlier shell script.

PROJECT_ROOT="$(pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
IMPLEMENTATION_VERSION="v1"

MANIFEST_FILE="${MANIFEST_FILE:-repo_x01/run-x-c01/python_primary_clone_manifest.csv}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/clone_python_primary_repos.py}"

TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-python-primary-repo}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-python-primary-repo}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-c02}"
STATUS_OUTPUT="${STATUS_OUTPUT:-${OUTPUT_DIR}/python_primary_clone_status.csv}"
ATTEMPTS_OUTPUT="${ATTEMPTS_OUTPUT:-${OUTPUT_DIR}/python_primary_clone_attempts.csv}"
FAILURES_OUTPUT="${FAILURES_OUTPUT:-${OUTPUT_DIR}/python_primary_clone_failures.csv}"
QC_OUTPUT="${QC_OUTPUT:-${OUTPUT_DIR}/python_primary_clone_availability_qc.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-repo_x01/tmp/run-x-c02/python_primary_clone_summary.csv}"

WORKERS="${WORKERS:-4}"
RETRY_COUNT="${RETRY_COUNT:-2}"
RETRY_DELAY_SECONDS="${RETRY_DELAY_SECONDS:-5}"
CLONE_TIMEOUT_SECONDS="${CLONE_TIMEOUT_SECONDS:-1800}"
REPAIR_INVALID_EXISTING="${REPAIR_INVALID_EXISTING:-0}"
REPAIR_ORIGIN_MISMATCH="${REPAIR_ORIGIN_MISMATCH:-0}"
SKIP_LFS_SMUDGE="${SKIP_LFS_SMUDGE:-1}"
MEASURE_DISK_USAGE="${MEASURE_DISK_USAGE:-1}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_ON_CLONE_FAILURE="${FAIL_ON_CLONE_FAILURE:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-248}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-121}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-127}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run-x-c02-v1-clone-python-primary-repos-${TIMESTAMP}.log}"

mkdir -p \
  "$(dirname "${LOG_FILE}")" \
  "${OUTPUT_DIR}" \
  "$(dirname "${SUMMARY_OUTPUT}")" \
  "${TREATMENT_CLONE_DIR}" \
  "${CONTROL_CLONE_DIR}"

for required_file in "${MANIFEST_FILE}" "${PYTHON_SCRIPT}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

command -v git >/dev/null 2>&1 || {
  echo "ERROR: git command is not available." >&2
  exit 1
}

"${PYTHON_BIN}" -c 'import pandas' >/dev/null

python_version="$(${PYTHON_BIN} --version 2>&1)"
git_version="$(git --version)"
script_sha256="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
manifest_sha256="$(sha256sum "${MANIFEST_FILE}" | awk '{print $1}')"

{
  echo "============================================================"
  echo "run-x-c02-v1: clone Python-primary experiment repositories"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          ${PYTHON_BIN} (${python_version})"
  echo "Git:                             ${git_version}"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Python clone script:             ${PYTHON_SCRIPT}"
  echo "Python script SHA256:             ${script_sha256}"
  echo "C01 clone manifest:              ${MANIFEST_FILE}"
  echo "Manifest SHA256:                 ${manifest_sha256}"
  echo "Treatment clone directory:       ${TREATMENT_CLONE_DIR}"
  echo "Control clone directory:         ${CONTROL_CLONE_DIR}"
  echo "Expected repositories:           ${EXPECTED_REPOSITORIES}"
  echo "Expected treatment repositories: ${EXPECTED_TREATMENT_REPOSITORIES}"
  echo "Expected control repositories:   ${EXPECTED_CONTROL_REPOSITORIES}"
  echo "Workers:                         ${WORKERS}"
  echo "Retry count:                     ${RETRY_COUNT}"
  echo "Clone timeout seconds:           ${CLONE_TIMEOUT_SECONDS}"
  echo "Skip Git LFS smudge:             ${SKIP_LFS_SMUDGE}"
  echo "Repair invalid existing paths:   ${REPAIR_INVALID_EXISTING}"
  echo "Repair origin mismatch:          ${REPAIR_ORIGIN_MISMATCH}"
  echo "Dry run:                         ${DRY_RUN}"
  echo "Fail on repository failure:      ${FAIL_ON_CLONE_FAILURE}"
  echo "Status output:                   ${STATUS_OUTPUT}"
  echo "Attempts output:                 ${ATTEMPTS_OUTPUT}"
  echo "Failures output:                 ${FAILURES_OUTPUT}"
  echo "QC output:                       ${QC_OUTPUT}"
  echo "Summary output:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                        ${LOG_FILE}"
  echo "============================================================"
  echo
  echo "** Step 1: Clone or resume C01 manifest repositories"
  echo "------------------------------------------------------------"
} | tee "${LOG_FILE}"

command=(
  "${PYTHON_BIN}" "${PYTHON_SCRIPT}"
  --manifest-file "${MANIFEST_FILE}"
  --status-output "${STATUS_OUTPUT}"
  --attempts-output "${ATTEMPTS_OUTPUT}"
  --failures-output "${FAILURES_OUTPUT}"
  --qc-output "${QC_OUTPUT}"
  --summary-output "${SUMMARY_OUTPUT}"
  --implementation-version "${IMPLEMENTATION_VERSION}"
  --workers "${WORKERS}"
  --retry-count "${RETRY_COUNT}"
  --retry-delay-seconds "${RETRY_DELAY_SECONDS}"
  --clone-timeout-seconds "${CLONE_TIMEOUT_SECONDS}"
  --repair-invalid-existing "${REPAIR_INVALID_EXISTING}"
  --repair-origin-mismatch "${REPAIR_ORIGIN_MISMATCH}"
  --skip-lfs-smudge "${SKIP_LFS_SMUDGE}"
  --measure-disk-usage "${MEASURE_DISK_USAGE}"
  --dry-run "${DRY_RUN}"
  --fail-on-clone-failure "${FAIL_ON_CLONE_FAILURE}"
  --strict-expected-counts "${STRICT_EXPECTED_COUNTS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
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
  echo "ERROR: run-x-c02-v1 failed with status ${run_status}." | tee -a "${LOG_FILE}"
  exit "${run_status}"
fi

{
  echo
  echo "** Step 2: Output checks"
  echo "------------------------------------------------------------"
} | tee -a "${LOG_FILE}"

output_files=(
  "${STATUS_OUTPUT}"
  "${ATTEMPTS_OUTPUT}"
  "${FAILURES_OUTPUT}"
  "${QC_OUTPUT}"
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
echo "QC checks:" | tee -a "${LOG_FILE}"
cat "${QC_OUTPUT}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Summary:" | tee -a "${LOG_FILE}"
cat "${SUMMARY_OUTPUT}" | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "Failure preview:" | tee -a "${LOG_FILE}"
head -n 21 "${FAILURES_OUTPUT}" | tee -a "${LOG_FILE}"

{
  echo
  echo "============================================================"
  echo "run-x-c02-v1 completed."
  echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Clone status:                    ${STATUS_OUTPUT}"
  echo "Clone attempts:                  ${ATTEMPTS_OUTPUT}"
  echo "Clone failures:                  ${FAILURES_OUTPUT}"
  echo "Clone availability QC:          ${QC_OUTPUT}"
  echo "Clone summary:                  ${SUMMARY_OUTPUT}"
  echo "Log file:                       ${LOG_FILE}"
  echo "Next step:                      inspect unavailable repositories, resume transient failures, then prepare C03 history panel"
  echo "============================================================"
} | tee -a "${LOG_FILE}"
