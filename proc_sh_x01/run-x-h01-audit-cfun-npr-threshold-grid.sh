#!/usr/bin/env bash
# Freeze and audit the C_FUN file-NPR threshold grid before SonarQube outcomes are joined in the C_FUN analysis.
#
# This wrapper is standalone. It was copied from the existing run-x-d01 FUN threshold-audit
# wrapper and then adapted for the CPU-only H01 C_FUN threshold audit. It does not call any
# previous shell wrapper.
#
# Versioned delivery files:
#   proc_script_x01/audit_cfun_npr_threshold_grid-v1.py
#   proc_sh_x01/run-x-h01-audit-cfun-npr-threshold-grid-v1.sh
#
# Canonical server paths after deployment:
#   proc_script_x01/audit_cfun_npr_threshold_grid.py
#   proc_sh_x01/run-x-h01-audit-cfun-npr-threshold-grid.sh
#
# Required inputs:
#   ../../detect_code_gpt/output/snapshot_npr/run-x-a15/python_cfun_repo_month_file_npr_scores.csv
#       A15 repo-month/Python-file C_FUN NPR artifact. The default relative path assumes this
#       wrapper runs from the ai-code-complexity-study project root described below.
#   ../../detect_code_gpt/output/snapshot_npr/run-x-a15/summary.json
#       A15 terminal summary. H01 requires run-x-a15-v1 with zero hard QC failures.
#
# Frozen threshold specification:
#   Primary T: 1.571637
#   Main grid: T + delta, delta=-0.50,-0.45,...,0,...,+0.45,+0.50
#   Legacy anchor: 1.5183
#   Decision rule: file_npr_cfun_space_by_token_weighted > threshold
#   Threshold provenance: reuse the previously frozen SC2-7B FUN detector threshold/grid unchanged.
#   H01 audits transfer to C_FUN; it does not recalibrate thresholds from C_FUN or SonarQube outcomes.
#
# Treatment timing:
#   treatment_group = event_index > 0
#   event_time_normalized = time_index - event_index for treatment repositories
#   absorbing_treated = event_index > 0 and time_index >= event_index
#   Legacy is_treatment/post_event/cursor flags are not used.
#
# Main outputs under repo_x01/run-x-h01/:
#   cfun_npr_threshold_spec.csv
#       Frozen 21-point symmetric grid plus the separately named legacy threshold.
#   cfun_npr_threshold_audit.csv
#       Global selected counts/shares for every threshold.
#   cfun_npr_threshold_by_treatment_timing.csv
#       Threshold audit by control, treatment-pre, treatment-post, and treatment-all.
#   cfun_npr_threshold_repo_month_audit.csv
#       One row per threshold x Model A repo-month for pre-SonarQube sample-composition QC.
#   cfun_npr_distribution_summary.csv
#       Continuous C_FUN NPR distribution summaries before any quality outcome is read.
#   cfun_npr_threshold_checks.csv
#   summary.json
#   metadata.json
#
# Important boundary:
#   H01 does not read SonarQube or any quality outcome. It transfers the already frozen detector
#   threshold/grid to C_FUN before the C_FUN-specific SonarQube join, avoiding C_FUN outcome-driven tuning.
#
# Runtime:
#   Python 3.11.x. CPU only; no model/GPU use.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-h01"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_cfun_npr_threshold_grid.py}"
A15_INPUT_FILE="${A15_INPUT_FILE:-../../detect_code_gpt/output/snapshot_npr/run-x-a15/python_cfun_repo_month_file_npr_scores.csv}"
A15_SUMMARY_FILE="${A15_SUMMARY_FILE:-../../detect_code_gpt/output/snapshot_npr/run-x-a15/summary.json}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-h01}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-cfun-npr-threshold-grid-${RUN_TS}.log}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

PRIMARY_THRESHOLD="1.571637"
GRID_STEP="0.05"
GRID_RADIUS="0.50"
LEGACY_THRESHOLD="1.5183"

for required_file in "${PY_SCRIPT}" "${A15_INPUT_FILE}" "${A15_SUMMARY_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 2
  fi
done

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
  echo "ERROR: H01 requires Python 3.11.x; found ${PYTHON_VERSION}" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
A15_INPUT_SHA256="$(sha256sum "${A15_INPUT_FILE}" | awk '{print $1}')"
A15_SUMMARY_SHA256="$(sha256sum "${A15_SUMMARY_FILE}" | awk '{print $1}')"

exec > >(tee "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
echo "============================================================================"
echo "${RUN_LABEL}: freeze and audit C_FUN file-NPR threshold grid"
echo "Started:                         $(date)"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "A15 input:                       ${A15_INPUT_FILE}"
echo "A15 input SHA256:                ${A15_INPUT_SHA256}"
echo "A15 summary:                     ${A15_SUMMARY_FILE}"
echo "A15 summary SHA256:              ${A15_SUMMARY_SHA256}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Metric:                          file_npr_cfun_space_by_token_weighted"
echo "Primary threshold T:             ${PRIMARY_THRESHOLD}"
echo "Grid:                            T +/- ${GRID_RADIUS} in ${GRID_STEP} increments (21 points)"
echo "Legacy threshold anchor:         ${LEGACY_THRESHOLD}"
echo "Decision rule:                   NPR > threshold"
echo "Treatment timing:                normalized event_index/time_index; legacy flags ignored"
echo "Quality/SonarQube input:         none"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
fi

ARGS=(
  --input-file "${A15_INPUT_FILE}"
  --a15-summary-file "${A15_SUMMARY_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --primary-threshold "${PRIMARY_THRESHOLD}"
  --grid-step "${GRID_STEP}"
  --grid-radius "${GRID_RADIUS}"
  --legacy-threshold "${LEGACY_THRESHOLD}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  ARGS+=(--strict-expected-counts)
fi

set +e
"${PYTHON_BIN}" "${PY_SCRIPT}" "${ARGS[@]}"
EXIT_CODE=$?
set -e

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
printf -v ELAPSED_TEXT '%02d:%02d:%02d' $((ELAPSED / 3600)) $(((ELAPSED % 3600) / 60)) $((ELAPSED % 60))

echo
echo "============================================================================"
echo "${RUN_LABEL} execution summary"
echo "Completed:        $(date)"
echo "Elapsed:          ${ELAPSED_TEXT}"
echo "Exit code:        ${EXIT_CODE}"
echo "Output directory: ${OUTPUT_DIR}"
echo "Log file:         ${LOG_FILE}"
for output_file in \
  cfun_npr_threshold_spec.csv \
  cfun_npr_threshold_audit.csv \
  cfun_npr_threshold_by_treatment_timing.csv \
  cfun_npr_threshold_repo_month_audit.csv \
  cfun_npr_distribution_summary.csv \
  cfun_npr_threshold_checks.csv; do
  if [[ -f "${OUTPUT_DIR}/${output_file}" ]]; then
    echo "${output_file}: $(wc -l < "${OUTPUT_DIR}/${output_file}") lines"
  fi
done
echo "============================================================================"

exit "${EXIT_CODE}"
