#!/usr/bin/env bash
set -euo pipefail

# run-py-7n: prepare a fixed-sample hybrid AGC unique-body DiD input.
#
# The base sample is the regular module-function positive-month sample used by
# run-py-7h. Class-method counts are appended only for the five repositories
# identified by run-py-7m. Months that are positive only because of class
# methods are not added, so sample membership remains fixed.
#
# Inputs:
#   repo_python/run-py-7e/strict/specifications/range100_200/
#     panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv
#   repo_python/run-py-7j/strict/specifications/range100_200/
#     regular_module_function_and_class_method_agc_unique_body_repo_month_counts.csv
#   proc_scripts/prepare_regfun_selected_classmethod_agc_uniquebody_did_input.py
#
# Primary output for run-py-7o:
#   repo_python/run-py-7n/strict/specifications/range100_200/
#     panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_
#     original_positive_sample_parse_clean.csv
#
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-7n-prepare-regfun-selected-classmethod-agc-uniquebody-did-input.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_regfun_selected_classmethod_agc_uniquebody_did_input.py}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
BASE_PANEL="${BASE_PANEL:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"
REPO_MONTH_COUNTS="${REPO_MONTH_COUNTS:-repo_python/run-py-7j/strict/specifications/${SPECIFICATION_NAME}/regular_module_function_and_class_method_agc_unique_body_repo_month_counts.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7n/strict/specifications/${SPECIFICATION_NAME}}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-0}"
SKIP_FROZEN_COUNT_CHECKS="${SKIP_FROZEN_COUNT_CHECKS:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-7n}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7n-regfun-selected-classmethod-agc-uniquebody-${SPECIFICATION_NAME}-${RUN_TS}.log}"

SELECTED_REPOSITORIES=(
  "DataScienceUIBK/Rankify"
  "pieces-app/cli-agent"
  "HelpingAI/Webscout"
  "whiteducksoftware/flock"
  "getsentry/sentry"
)

NEXT_INPUT="${OUTPUT_DIR}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv"
CHECKS_FILE="${OUTPUT_DIR}/qc/regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv"
SUMMARY_FILE="${OUTPUT_DIR}/qc/regfun_selected_classmethod_agc_uniquebody_did_input_summary.json"
STATUS_FILE="${OUTPUT_DIR}/regfun_selected_classmethod_agc_uniquebody_status.txt"

case "${OVERWRITE_OUTPUT}" in
  0|1) ;;
  *)
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
    exit 1
    ;;
esac

case "${RUN_SELF_TEST}" in
  0|1) ;;
  *)
    echo "ERROR: RUN_SELF_TEST must be 0 or 1." >&2
    exit 1
    ;;
esac

case "${SKIP_FROZEN_COUNT_CHECKS}" in
  0|1) ;;
  *)
    echo "ERROR: SKIP_FROZEN_COUNT_CHECKS must be 0 or 1." >&2
    exit 1
    ;;
esac

for required_file in "${PY_SCRIPT}" "${BASE_PANEL}" "${REPO_MONTH_COUNTS}"; do
  if [[ ! -s "${required_file}" ]]; then
    echo "ERROR: Required file is missing or empty: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python command not found: ${PYTHON_BIN}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
start_epoch="$(date +%s)"
start_display="$(date '+%Y-%m-%d %H:%M:%S %Z')"

python_args=(
  "${PY_SCRIPT}"
  --base-panel "${BASE_PANEL}"
  --repo-month-counts "${REPO_MONTH_COUNTS}"
  --output-dir "${OUTPUT_DIR}"
  --specification-name "${SPECIFICATION_NAME}"
)

for repo_name in "${SELECTED_REPOSITORIES[@]}"; do
  python_args+=(--selected-repo "${repo_name}")
done

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
  python_args+=(--overwrite-output)
fi
if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  python_args+=(--self-test)
fi
if [[ "${SKIP_FROZEN_COUNT_CHECKS}" == "1" ]]; then
  python_args+=(--skip-frozen-count-checks)
fi

{
  echo "================================================================================"
  echo "run-py-7n: prepare fixed-sample selected class-method panel"
  echo "Started:                    ${start_display}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Python script SHA:          $(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
  echo "Specification:              ${SPECIFICATION_NAME}"
  echo "Base outcome:               module_function AGC unique bodies"
  echo "Appended scope:             method AGC unique bodies for selected repos only"
  echo "Sample membership:          original module-function outcome > 0"
  echo "Method-only positive rows:  excluded to preserve the original sample"
  echo "Selected repositories:      ${#SELECTED_REPOSITORIES[@]}"
  for repo_name in "${SELECTED_REPOSITORIES[@]}"; do
    echo "  - ${repo_name}"
  done
  echo "Base panel:                 ${BASE_PANEL}"
  echo "Repository-month counts:    ${REPO_MONTH_COUNTS}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Skip frozen count checks:   ${SKIP_FROZEN_COUNT_CHECKS}"
  echo "Interpretation:             supplementary fixed-sample influence debugging"
  echo "Causal primary use:         NO"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"

  "${PYTHON_BIN}" "${python_args[@]}"

  for expected_file in \
    "${NEXT_INPUT}" \
    "${CHECKS_FILE}" \
    "${SUMMARY_FILE}" \
    "${STATUS_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
      exit 1
    fi
  done

  if ! grep -Fxq "status=PASS" "${STATUS_FILE}"; then
    echo "ERROR: run-py-7n status is not PASS." >&2
    cat "${STATUS_FILE}" >&2
    exit 1
  fi
  if ! grep -Fxq "sample_membership_fixed_to_run_py_7h=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: Fixed-sample guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "method_only_positive_months_added=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Method-only positive-month exclusion guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "causal_interpretation_allowed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Noncausal debugging guard is missing." >&2
    exit 1
  fi

  echo
  echo "================================================================================"
  echo "run-py-7n PASS"
  echo "Next-stage input:        ${NEXT_INPUT}"
  echo "Checks:                  ${CHECKS_FILE}"
  echo "Summary:                 ${SUMMARY_FILE}"
  echo "Status:                  ${STATUS_FILE}"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

end_epoch="$(date +%s)"
elapsed="$((end_epoch - start_epoch))"
printf -v elapsed_display '%02d:%02d:%02d' \
  "$((elapsed / 3600))" \
  "$(((elapsed % 3600) / 60))" \
  "$((elapsed % 60))"

cat <<EOF

================================================================================
run-py-7n execution summary
Started:              ${start_display}
Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')
Elapsed:              ${elapsed_display}
Exit code:            0
Output directory:     ${OUTPUT_DIR}
Next-stage input:     ${NEXT_INPUT}
Log file:             ${LOG_FILE}
================================================================================
EOF
