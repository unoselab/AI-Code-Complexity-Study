#!/usr/bin/env bash
# Freeze and audit the combined FUN+C_FUN file-NPR threshold grid before SonarQube outcomes are joined.
#
# This wrapper is standalone. It reuses the operational structure of the existing D01/H01 threshold-audit
# wrappers but does not call either wrapper. The I02 Python analysis is a separate combined-procedure-body
# implementation that consumes the frozen I01 output.
#
# Versioned delivery files:
#   proc_script_x01/audit_fun_cfun_npr_threshold_grid-v1.py
#   proc_sh_x01/run-x-i02-audit-fun-cfun-npr-threshold-grid-v1.sh
#
# Canonical server paths after deployment:
#   proc_script_x01/audit_fun_cfun_npr_threshold_grid.py
#   proc_sh_x01/run-x-i02-audit-fun-cfun-npr-threshold-grid.sh
#
# Required inputs:
#   repo_x01/run-x-i01/python_fun_cfun_repo_month_file_npr_scores.csv
#       I01 repo-month/Python-file combined FUN+C_FUN NPR artifact. The combined NPR is the
#       scored-space-by-token weighted recomputation across the finite FUN and C_FUN sufficient statistics.
#   repo_x01/run-x-i01/summary.json
#       I01 terminal summary. I02 requires run-x-i01-v1 with zero hard QC failures.
#
# Frozen threshold specification:
#   Primary T: 1.571637
#   Main grid: T + delta, delta=-0.50,-0.45,...,0,...,+0.45,+0.50
#   Legacy anchor: 1.5183
#   Decision rule: file_npr_fun_cfun_space_by_token_weighted > threshold
#   Threshold provenance: reuse the previously frozen SC2-7B FUN detector threshold/grid unchanged.
#   I02 audits transfer to the combined FUN+C_FUN measurement; it does not recalibrate from I01 or quality outcomes.
#
# Frozen I01 production expectations:
#   Repo-month/file rows:                    510,297
#   Finite combined FUN+C_FUN NPR rows:      359,057
#   Unique snapshot/files:                   494,592
#   Finite unique snapshot/files:            347,173
#   Repositories / repo-months:              167 / 1,954
#   Control / treatment repositories:        104 / 63
#   Primary T selected rows:                 17,071
#   Primary T selected unique files:         15,726
#   Primary T selected repositories/months:  123 / 1,411
#
# Treatment timing:
#   treatment_group = event_index > 0
#   event_time_normalized = time_index - event_index for treatment repositories
#   absorbing_treated = event_index > 0 and time_index >= event_index
#   Legacy treatment/post/cursor flags are not used.
#
# Main outputs under repo_x01/run-x-i02/:
#   fun_cfun_npr_threshold_spec.csv
#       Frozen 21-point symmetric grid plus the separately named legacy threshold.
#   fun_cfun_npr_threshold_audit.csv
#       Global selected counts/shares for every threshold.
#   fun_cfun_npr_threshold_by_treatment_timing.csv
#       Threshold audit by control, treatment-pre, treatment-post, and treatment-all.
#   fun_cfun_npr_threshold_repo_month_audit.csv
#       One row per threshold x Model A repo-month for pre-SonarQube sample-composition QC.
#   fun_cfun_npr_distribution_summary.csv
#       Continuous combined FUN+C_FUN NPR distributions before any quality outcome is read.
#   fun_cfun_npr_threshold_checks.csv
#   summary.json
#   metadata.json
#
# Important boundary:
#   I02 reads no SonarQube file burden, no DiD outcome, and no treatment-effect estimate. It only transfers
#   the already frozen detector threshold/grid to the combined continuous NPR measurement and audits support.
#
# Runtime:
#   Python 3.11.x. CPU only; no model/GPU use.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i02"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_fun_cfun_npr_threshold_grid.py}"
I01_INPUT_FILE="${I01_INPUT_FILE:-repo_x01/run-x-i01/python_fun_cfun_repo_month_file_npr_scores.csv}"
I01_SUMMARY_FILE="${I01_SUMMARY_FILE:-repo_x01/run-x-i01/summary.json}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i02}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-fun-cfun-npr-threshold-grid-${RUN_TS}.log}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

PRIMARY_THRESHOLD="1.571637"
GRID_STEP="0.05"
GRID_RADIUS="0.50"
LEGACY_THRESHOLD="1.5183"

EXPECTED_INPUT_ROWS="510297"
EXPECTED_ELIGIBLE_ROWS="359057"
EXPECTED_UNIQUE_SNAPSHOT_FILES="494592"
EXPECTED_ELIGIBLE_UNIQUE_SNAPSHOT_FILES="347173"
EXPECTED_REPO_MONTHS="1954"
EXPECTED_REPOSITORIES="167"
EXPECTED_CONTROL_REPOSITORIES="104"
EXPECTED_TREATMENT_REPOSITORIES="63"
EXPECTED_CONTROL_REPO_MONTHS="1040"
EXPECTED_TREATMENT_PRE_REPO_MONTHS="551"
EXPECTED_TREATMENT_POST_REPO_MONTHS="363"
EXPECTED_PRIMARY_SELECTED_ROWS="17071"
EXPECTED_PRIMARY_SELECTED_UNIQUE_SNAPSHOT_FILES="15726"
EXPECTED_PRIMARY_SELECTED_REPOSITORIES="123"
EXPECTED_PRIMARY_SELECTED_REPO_MONTHS="1411"

for required_file in "${PY_SCRIPT}" "${I01_INPUT_FILE}" "${I01_SUMMARY_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 2
  fi
done

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
  echo "ERROR: I02 requires Python 3.11.x; found ${PYTHON_VERSION}" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
I01_INPUT_SHA256="$(sha256sum "${I01_INPUT_FILE}" | awk '{print $1}')"
I01_SUMMARY_SHA256="$(sha256sum "${I01_SUMMARY_FILE}" | awk '{print $1}')"

exec > >(tee "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
echo "============================================================================"
echo "${RUN_LABEL}: freeze and audit combined FUN+C_FUN file-NPR threshold grid"
echo "Started:                         $(date)"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "I01 input:                       ${I01_INPUT_FILE}"
echo "I01 input SHA256:                ${I01_INPUT_SHA256}"
echo "I01 summary:                     ${I01_SUMMARY_FILE}"
echo "I01 summary SHA256:              ${I01_SUMMARY_SHA256}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Metric:                          file_npr_fun_cfun_space_by_token_weighted"
echo "Primary threshold T:             ${PRIMARY_THRESHOLD}"
echo "Grid:                            T +/- ${GRID_RADIUS} in ${GRID_STEP} increments (21 points)"
echo "Legacy threshold anchor:         ${LEGACY_THRESHOLD}"
echo "Decision rule:                   NPR > threshold"
echo "Treatment timing:                normalized event_index/time_index; legacy flags ignored"
echo "Quality/SonarQube input:         none"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"

echo
echo "** Step 1: Run I02 structural self-test"
echo "----------------------------------------------------------------------------"
if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
else
  echo "Skipped because RUN_SELF_TEST=${RUN_SELF_TEST}"
fi

echo
echo "** Step 2: Compile I02 Python program"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

echo
echo "** Step 3: Audit frozen combined FUN+C_FUN threshold grid"
echo "----------------------------------------------------------------------------"
ARGS=(
  --input-file "${I01_INPUT_FILE}"
  --i01-summary-file "${I01_SUMMARY_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --grid-step "${GRID_STEP}"
  --grid-radius "${GRID_RADIUS}"
  --legacy-threshold "${LEGACY_THRESHOLD}"
  --expected-input-rows "${EXPECTED_INPUT_ROWS}"
  --expected-eligible-rows "${EXPECTED_ELIGIBLE_ROWS}"
  --expected-unique-snapshot-files "${EXPECTED_UNIQUE_SNAPSHOT_FILES}"
  --expected-eligible-unique-snapshot-files "${EXPECTED_ELIGIBLE_UNIQUE_SNAPSHOT_FILES}"
  --expected-repo-months "${EXPECTED_REPO_MONTHS}"
  --expected-repositories "${EXPECTED_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repo-months "${EXPECTED_CONTROL_REPO_MONTHS}"
  --expected-treatment-pre-repo-months "${EXPECTED_TREATMENT_PRE_REPO_MONTHS}"
  --expected-treatment-post-repo-months "${EXPECTED_TREATMENT_POST_REPO_MONTHS}"
  --expected-primary-selected-rows "${EXPECTED_PRIMARY_SELECTED_ROWS}"
  --expected-primary-selected-unique-snapshot-files "${EXPECTED_PRIMARY_SELECTED_UNIQUE_SNAPSHOT_FILES}"
  --expected-primary-selected-repositories "${EXPECTED_PRIMARY_SELECTED_REPOSITORIES}"
  --expected-primary-selected-repo-months "${EXPECTED_PRIMARY_SELECTED_REPO_MONTHS}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  ARGS+=(--strict-expected-counts)
fi

printf 'Command:'
printf ' %q' "${PYTHON_BIN}" "${PY_SCRIPT}" "${ARGS[@]}"
echo
set +e
"${PYTHON_BIN}" "${PY_SCRIPT}" "${ARGS[@]}"
EXIT_CODE=$?
set -e

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
printf -v ELAPSED_TEXT '%02d:%02d:%02d' $((ELAPSED / 3600)) $(((ELAPSED % 3600) / 60)) $((ELAPSED % 60))

echo
echo "** Step 4: Verify I02 output artifacts"
echo "----------------------------------------------------------------------------"
for output_file in \
  fun_cfun_npr_threshold_spec.csv \
  fun_cfun_npr_threshold_audit.csv \
  fun_cfun_npr_threshold_by_treatment_timing.csv \
  fun_cfun_npr_threshold_repo_month_audit.csv \
  fun_cfun_npr_distribution_summary.csv \
  fun_cfun_npr_threshold_checks.csv \
  summary.json \
  metadata.json; do
  if [[ -f "${OUTPUT_DIR}/${output_file}" ]]; then
    if [[ "${output_file}" == *.csv ]]; then
      echo "OK: ${OUTPUT_DIR}/${output_file} ($(wc -l < "${OUTPUT_DIR}/${output_file}") lines including header)"
    else
      echo "OK: ${OUTPUT_DIR}/${output_file}"
    fi
  else
    echo "MISSING: ${OUTPUT_DIR}/${output_file}"
  fi
done

echo
echo "============================================================================"
echo "${RUN_LABEL} execution summary"
echo "Completed:                       $(date)"
echo "Elapsed:                         ${ELAPSED_TEXT}"
echo "Exit code:                       ${EXIT_CODE}"
echo "Threshold audit:                 ${OUTPUT_DIR}/fun_cfun_npr_threshold_audit.csv"
echo "Treatment-timing audit:          ${OUTPUT_DIR}/fun_cfun_npr_threshold_by_treatment_timing.csv"
echo "Distribution summary:            ${OUTPUT_DIR}/fun_cfun_npr_distribution_summary.csv"
echo "QC checks:                       ${OUTPUT_DIR}/fun_cfun_npr_threshold_checks.csv"
echo "Summary:                         ${OUTPUT_DIR}/summary.json"
echo "Metadata:                        ${OUTPUT_DIR}/metadata.json"
echo "Log file:                        ${LOG_FILE}"
echo "Next:                            I03 join frozen combined NPR to existing file-level SonarQube burden"
echo "============================================================================"

exit "${EXIT_CODE}"
