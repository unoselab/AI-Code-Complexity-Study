#!/usr/bin/env bash
set -euo pipefail

# run-py-8a: diagnose repository-month class-method additions for the two
# influential control repositories identified by run-py-7p:
#   - pieces-app/cli-agent
#   - HelpingAI/Webscout
#
# This wrapper independently reuses the execution and validation structure of
# earlier project wrappers. It does not call any prior shell script.
#
# Inputs:
#   run-py-7p target repository-month audit CSV
#   run-py-7p comparison-to-baseline CSV
#
# Outputs:
#   filtered repository-month audit, repository summaries, spike ranking,
#   calendar-month comparison, diagnostic findings, validation, and status.
#
# Interpretation:
#   Supplementary fixed-sample influence debugging only. The analysis does not
#   justify removing either repository and is not a primary causal estimand.
#
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8a-analyze-cliagent-webscout-classmethod-months.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_cliagent_webscout_classmethod_months.py}"
SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"
TARGET_REPOSITORIES="${TARGET_REPOSITORIES:-pieces-app/cli-agent|HelpingAI/Webscout}"

RUN7P_ROOT="${RUN7P_ROOT:-repo_python/run-py-7p/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/one_repository_at_a_time}"
INPUT_PREFIX="borusyak_regfun_each_selected_classmethod_agc_uniquebody_fixed_sample"
AUDIT_CSV="${AUDIT_CSV:-${RUN7P_ROOT}/${INPUT_PREFIX}_target_repo_month_audit.csv}"
COMPARISON_CSV="${COMPARISON_CSV:-${RUN7P_ROOT}/${INPUT_PREFIX}_comparison_to_baseline.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-8a/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/cliagent_webscout_month_diagnosis}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SKIP_FROZEN_COUNT_CHECKS="${SKIP_FROZEN_COUNT_CHECKS:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8a}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8a-cliagent-webscout-classmethod-months-${SPECIFICATION_NAME}-${RUN_TS}.log}"

PREFIX="cliagent_webscout_classmethod_months"
MONTH_AUDIT_FILE="${OUT_DIR}/${PREFIX}_repo_month_audit.csv"
SUMMARY_FILE="${OUT_DIR}/${PREFIX}_repo_summary.csv"
SPIKE_FILE="${OUT_DIR}/${PREFIX}_month_spike_ranking.csv"
CALENDAR_FILE="${OUT_DIR}/${PREFIX}_calendar_month_comparison.csv"
FINDINGS_FILE="${OUT_DIR}/${PREFIX}_diagnostic_findings.csv"
VALIDATION_FILE="${OUT_DIR}/${PREFIX}_validation.csv"
METADATA_FILE="${OUT_DIR}/${PREFIX}_metadata.json"
STATUS_FILE="${OUT_DIR}/${PREFIX}_status.txt"

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

case "${OVERWRITE_OUTPUT}" in
  0|1) ;;
  *)
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1." >&2
    exit 1
    ;;
esac

for required_file in "${PY_SCRIPT}" "${AUDIT_CSV}" "${COMPARISON_CSV}"; do
  if [[ ! -s "${required_file}" ]]; then
    echo "ERROR: Required file is missing or empty: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: Python command not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ -d "${OUT_DIR}" ]]; then
  if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    rm -rf "${OUT_DIR}"
  else
    echo "ERROR: Output directory exists and OVERWRITE_OUTPUT=0: ${OUT_DIR}" >&2
    exit 1
  fi
fi

mkdir -p "${OUT_DIR}" "${LOG_DIR}"

start_epoch="$(date +%s)"
start_display="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-8a: cli-agent and Webscout class-method month diagnosis"
  echo "Started:                    ${start_display}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Python script SHA:          $(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
  echo "Target repositories:        ${TARGET_REPOSITORIES}"
  echo "Input month audit:          ${AUDIT_CSV}"
  echo "Input audit SHA:            $(sha256sum "${AUDIT_CSV}" | awk '{print $1}')"
  echo "Comparison to baseline:     ${COMPARISON_CSV}"
  echo "Comparison SHA:             $(sha256sum "${COMPARISON_CSV}" | awk '{print $1}')"
  echo "Output directory:           ${OUT_DIR}"
  echo "Analysis focus:             monthly spikes and temporal concentration"
  echo "Interpretation:             supplementary fixed-sample influence debugging"
  echo "Causal primary use:         NO"
  echo "Repository removal:         NOT JUSTIFIED"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Skip frozen count checks:   ${SKIP_FROZEN_COUNT_CHECKS}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"
  echo

  if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
  fi

  args=(
    "${PY_SCRIPT}"
    --audit-csv "${AUDIT_CSV}"
    --comparison-csv "${COMPARISON_CSV}"
    --output-dir "${OUT_DIR}"
    --target-repositories "${TARGET_REPOSITORIES}"
  )
  if [[ "${SKIP_FROZEN_COUNT_CHECKS}" == "1" ]]; then
    args+=(--skip-frozen-count-checks)
  fi
  "${PYTHON_BIN}" "${args[@]}"

  for expected_file in \
    "${MONTH_AUDIT_FILE}" \
    "${SUMMARY_FILE}" \
    "${SPIKE_FILE}" \
    "${CALENDAR_FILE}" \
    "${FINDINGS_FILE}" \
    "${VALIDATION_FILE}" \
    "${METADATA_FILE}" \
    "${STATUS_FILE}"; do
    if [[ ! -s "${expected_file}" ]]; then
      echo "ERROR: Missing or empty expected output: ${expected_file}" >&2
      exit 1
    fi
  done

  if ! grep -Fxq "status=PASS" "${STATUS_FILE}"; then
    echo "ERROR: Analysis status is not PASS: ${STATUS_FILE}" >&2
    cat "${STATUS_FILE}" >&2
    exit 1
  fi

  if ! grep -Fxq "causal_interpretation_allowed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Noncausal debugging guard is missing." >&2
    exit 1
  fi

  if ! grep -Fxq "repository_removal_justified=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Repository-removal guard is missing." >&2
    exit 1
  fi

  echo
  echo "================================================================================"
  echo "run-py-8a PASS"
  echo "Repository-month audit:    ${MONTH_AUDIT_FILE}"
  echo "Repository summary:        ${SUMMARY_FILE}"
  echo "Month spike ranking:       ${SPIKE_FILE}"
  echo "Calendar comparison:       ${CALENDAR_FILE}"
  echo "Diagnostic findings:       ${FINDINGS_FILE}"
  echo "Validation:                ${VALIDATION_FILE}"
  echo "Status:                    ${STATUS_FILE}"
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
run-py-8a execution summary
Started:              ${start_display}
Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')
Elapsed:              ${elapsed_display}
Exit code:            0
Output directory:     ${OUT_DIR}
Log file:             ${LOG_FILE}
================================================================================

EOF
