#!/usr/bin/env bash
# Freeze and audit the combined regular-function + class-method ML threshold grid.
#
# This wrapper was derived from the existing run-x-i02 threshold-audit wrapper,
# but it is a standalone I07 implementation and does not call I02 or any other
# experiment shell script.
#
# Versioned delivery files:
#   proc_script_x01/audit_ml_fun_cfun_threshold_grid-v2.py
#   proc_sh_x01/run-x-i07-audit-ml-fun-cfun-threshold-grid-v2.sh
#
# Canonical runtime copies after deployment:
#   proc_script_x01/audit_ml_fun_cfun_threshold_grid.py
#   proc_sh_x01/run-x-i07-audit-ml-fun-cfun-threshold-grid.sh
#
# Required inputs:
#   repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv
#       One row per unique historical Python file. The primary continuous metric
#       is recomputed in I06 from regular-function + class-method AGC body-token
#       numerators divided by the corresponding combined body-token denominator.
#   repo_x01/run-x-i06/summary.json
#       I06 terminal summary. I07 requires run-x-i06-v1 with zero hard failures.
#
# Frozen ML threshold specification:
#   Metric: file_ml_fun_cfun_agc_share_space_by_token_weighted
#   Grid:   0.10, 0.14, ..., 0.50, ..., 0.86, 0.90 (21 points)
#   Primary threshold: 0.50
#   Decision rule: combined ML AGC share > threshold (strict)
#   Boundary implementation: exact integer AGC-token / total-token comparison.
#   Equality is never selected.
#   The grid is reused from the finalized FUN ML threshold-sensitivity design;
#   it is not calibrated from I06, SonarQube, or any treatment-effect result.
#
# Frozen I06 production expectations:
#   Historical Python files:             494,592
#   Prepared files:                      494,332
#   Eligible combined files:             347,562
#   Control / treatment files:            71,998 / 422,594
#   Control / treatment eligible:         54,765 / 292,797
#   Primary >0.50 selected files:         62,319
#   Exact 0.50 ties:                         842
#   Control / treatment primary selected:  8,790 / 53,529
#
# I07 output boundary:
#   I06 is a historical-file artifact rather than a repo-month/file expansion.
#   Therefore I07 freezes threshold support at the historical-file level by
#   dataset source and procedure-presence pattern. It intentionally does not
#   reconstruct treatment timing here. Repo-month expansion is deferred to the
#   downstream quality-burden panel, where authoritative B06 timing is joined.
#
# Main outputs under repo_x01/run-x-i07/:
#   ml_fun_cfun_threshold_spec.csv
#       Exact 21-point frozen ML threshold grid.
#   ml_fun_cfun_threshold_audit.csv
#       Global historical-file selection/support at every threshold.
#   ml_fun_cfun_threshold_by_dataset.csv
#       Control/treatment selection/support at every threshold.
#   ml_fun_cfun_threshold_by_presence.csv
#       FUN-only, class-method-only, both, and neither composition at every threshold.
#   ml_fun_cfun_distribution_summary.csv
#       Combined continuous ML-score distribution before any quality outcome is read.
#   ml_fun_cfun_threshold_checks.csv
#   summary.json
#   metadata.json
#
# Important boundary:
#   I07 reads no SonarQube burden, no B06 timing, no DiD outcome, and no treatment-
#   effect estimate. It only applies the frozen threshold grid to I06 and audits
#   detector support/composition.
#
# Runtime:
#   Python 3.11.x. CPU only; no model/GPU use.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i07"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_ml_fun_cfun_threshold_grid.py}"
I06_INPUT_FILE="${I06_INPUT_FILE:-repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv}"
I06_SUMMARY_FILE="${I06_SUMMARY_FILE:-repo_x01/run-x-i06/summary.json}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i07}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-ml-fun-cfun-threshold-grid-${RUN_TS}.log}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
OVERWRITE="${OVERWRITE:-0}"

EXPECTED_FILE_ROWS="494592"
EXPECTED_PREPARED_ROWS="494332"
EXPECTED_ELIGIBLE_ROWS="347562"
EXPECTED_CONTROL_FILE_ROWS="71998"
EXPECTED_TREATMENT_FILE_ROWS="422594"
EXPECTED_CONTROL_ELIGIBLE_ROWS="54765"
EXPECTED_TREATMENT_ELIGIBLE_ROWS="292797"
EXPECTED_PRIMARY_SELECTED_ROWS="62319"
EXPECTED_PRIMARY_EXACT_TIES="842"
EXPECTED_CONTROL_PRIMARY_SELECTED_ROWS="8790"
EXPECTED_TREATMENT_PRIMARY_SELECTED_ROWS="53529"

for required_file in "${PY_SCRIPT}" "${I06_INPUT_FILE}" "${I06_SUMMARY_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 2
  fi
done

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
  echo "ERROR: I07 requires Python 3.11.x; found ${PYTHON_VERSION}" >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"
if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally replacing I07-v1 with corrected I07-v2." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
I06_INPUT_SHA256="$(sha256sum "${I06_INPUT_FILE}" | awk '{print $1}')"
I06_SUMMARY_SHA256="$(sha256sum "${I06_SUMMARY_FILE}" | awk '{print $1}')"

exec > >(tee "${LOG_FILE}") 2>&1

START_EPOCH="$(date +%s)"
echo "============================================================================"
echo "${RUN_LABEL}: freeze and audit combined ML threshold grid"
echo "Started:                         $(date)"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "I06 input:                       ${I06_INPUT_FILE}"
echo "I06 input SHA256:                ${I06_INPUT_SHA256}"
echo "I06 summary:                     ${I06_SUMMARY_FILE}"
echo "I06 summary SHA256:              ${I06_SUMMARY_SHA256}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Metric:                          file_ml_fun_cfun_agc_share_space_by_token_weighted"
echo "Threshold grid:                  0.10:0.90 by 0.04 (21 points)"
echo "Primary threshold:               > 0.50 (strict)"
echo "Threshold recalibration:         none"
echo "Repo-month timing input:         none"
echo "Quality/SonarQube input:         none"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"

echo
echo "** Step 1: Run I07 structural self-test"
echo "----------------------------------------------------------------------------"
if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  echo "Command: ${PYTHON_BIN} ${PY_SCRIPT} --self-test"
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
else
  echo "Skipped because RUN_SELF_TEST=${RUN_SELF_TEST}"
fi

echo
echo "** Step 2: Compile I07 Python program"
echo "----------------------------------------------------------------------------"
echo "Command: ${PYTHON_BIN} -m py_compile ${PY_SCRIPT}"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

echo
echo "** Step 3: Freeze I06 input provenance"
echo "----------------------------------------------------------------------------"
echo "I06 file-score SHA256:            ${I06_INPUT_SHA256}"
echo "I06 summary SHA256:               ${I06_SUMMARY_SHA256}"

echo
echo "** Step 4: Audit frozen combined-ML threshold grid"
echo "----------------------------------------------------------------------------"
ARGS=(
  --input-file "${I06_INPUT_FILE}"
  --i06-summary-file "${I06_SUMMARY_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --expected-file-rows "${EXPECTED_FILE_ROWS}"
  --expected-prepared-rows "${EXPECTED_PREPARED_ROWS}"
  --expected-eligible-rows "${EXPECTED_ELIGIBLE_ROWS}"
  --expected-control-file-rows "${EXPECTED_CONTROL_FILE_ROWS}"
  --expected-treatment-file-rows "${EXPECTED_TREATMENT_FILE_ROWS}"
  --expected-control-eligible-rows "${EXPECTED_CONTROL_ELIGIBLE_ROWS}"
  --expected-treatment-eligible-rows "${EXPECTED_TREATMENT_ELIGIBLE_ROWS}"
  --expected-primary-selected-rows "${EXPECTED_PRIMARY_SELECTED_ROWS}"
  --expected-primary-exact-ties "${EXPECTED_PRIMARY_EXACT_TIES}"
  --expected-control-primary-selected-rows "${EXPECTED_CONTROL_PRIMARY_SELECTED_ROWS}"
  --expected-treatment-primary-selected-rows "${EXPECTED_TREATMENT_PRIMARY_SELECTED_ROWS}"
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
echo "** Step 5: Verify I07 output artifacts"
echo "----------------------------------------------------------------------------"
for output_file in \
  ml_fun_cfun_threshold_spec.csv \
  ml_fun_cfun_threshold_audit.csv \
  ml_fun_cfun_threshold_by_dataset.csv \
  ml_fun_cfun_threshold_by_presence.csv \
  ml_fun_cfun_distribution_summary.csv \
  ml_fun_cfun_threshold_checks.csv \
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
echo "I07 QC checks:"
cat "${OUTPUT_DIR}/ml_fun_cfun_threshold_checks.csv"

echo
echo "I07 threshold audit:"
cat "${OUTPUT_DIR}/ml_fun_cfun_threshold_audit.csv"

echo
echo "I07 summary:"
cat "${OUTPUT_DIR}/summary.json"

echo
echo "============================================================================"
echo "${RUN_LABEL} execution summary"
echo "Completed:                       $(date)"
echo "Elapsed:                         ${ELAPSED_TEXT}"
echo "Exit code:                       ${EXIT_CODE}"
echo "Threshold audit:                 ${OUTPUT_DIR}/ml_fun_cfun_threshold_audit.csv"
echo "Dataset audit:                   ${OUTPUT_DIR}/ml_fun_cfun_threshold_by_dataset.csv"
echo "Presence audit:                  ${OUTPUT_DIR}/ml_fun_cfun_threshold_by_presence.csv"
echo "Distribution summary:            ${OUTPUT_DIR}/ml_fun_cfun_distribution_summary.csv"
echo "QC checks:                       ${OUTPUT_DIR}/ml_fun_cfun_threshold_checks.csv"
echo "Summary:                         ${OUTPUT_DIR}/summary.json"
echo "Metadata:                        ${OUTPUT_DIR}/metadata.json"
echo "Log file:                        ${LOG_FILE}"
echo "Next:                            build combined ML threshold quality-burden panel using frozen I07 grid"
echo "============================================================================"

exit "${EXIT_CODE}"
