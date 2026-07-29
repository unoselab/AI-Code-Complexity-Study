#!/usr/bin/env bash
set -euo pipefail

# run-py-8b: fixed-sample class-method spike-month ablation plus matched-pair
# calendar-alignment audit for:
#   - pieces-app/cli-agent
#   - HelpingAI/Webscout
#
# This wrapper independently reuses the execution and validation structure of
# earlier project wrappers. It does not call any prior shell script.
#
# Inputs:
#   - run-py-7n original-positive fixed-sample panel
#   - run-py-7e zero-inclusive parse-clean regular-function panel
#   - run-py-7p target repository-month audit
#   - strict treatment-control pair manifest
#   - treatment adoption metadata
#   - run-py-7h reference static result
#   - Borusyak helper functions
#
# Outputs:
#   1. Pair-calendar alignment diagnostics.
#   2. Ten fixed-sample static DiD scenarios covering baseline, all methods,
#      and spike-month method-increment ablations.
#
# Important:
#   - Ablation sets selected method increments to zero but retains all rows.
#   - Pair IDs are audited but are not passed to the current static estimator.
#   - Results are supplementary debugging only and do not justify dropping
#     repositories or months.
#
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8b-ablate-cliagent-webscout-months-check-pairs.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/analyze_cliagent_webscout_pair_alignment.py}"
R_SCRIPT="${R_SCRIPT:-proc_r/did_cliagent_webscout_month_ablation_fixed_sample.R}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"

SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"
MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT:-202408}"
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT:-202503}"
MINIMUM_EVENT_TIME="${MINIMUM_EVENT_TIME:--6}"
MAXIMUM_EVENT_TIME="${MAXIMUM_EVENT_TIME:-6}"
REPRO_TOLERANCE="${REPRO_TOLERANCE:-0.000001}"
TARGET_REPOSITORIES="${TARGET_REPOSITORIES:-pieces-app/cli-agent|HelpingAI/Webscout}"

RUN7N_ROOT="${RUN7N_ROOT:-repo_python/run-py-7n/strict/specifications/${SPECIFICATION_NAME}}"
PANEL_PATH="${PANEL_PATH:-${RUN7N_ROOT}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv}"
RUN7N_CHECKS_PATH="${RUN7N_CHECKS_PATH:-${RUN7N_ROOT}/qc/regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv}"

ZERO_PANEL_PATH="${ZERO_PANEL_PATH:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"

RUN7P_ROOT="${RUN7P_ROOT:-repo_python/run-py-7p/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/one_repository_at_a_time}"
RUN7P_PREFIX="borusyak_regfun_each_selected_classmethod_agc_uniquebody_fixed_sample"
MONTH_AUDIT_PATH="${MONTH_AUDIT_PATH:-${RUN7P_ROOT}/${RUN7P_PREFIX}_target_repo_month_audit.csv}"

MATCHED_PAIRS_PATH="${MATCHED_PAIRS_PATH:-repo_python/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv}"
TREATMENT_META_PATH="${TREATMENT_META_PATH:-repo_python/run-py-1f/treatment_python_sample_main_118.csv}"

REFERENCE_STATIC_PATH="${REFERENCE_STATIC_PATH:-repo_python/run-py-7h/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/positive_outcome_months_only/borusyak_regular_module_function_agc_unique_body_positive_months_static_effects.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-8b/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/month_ablation_pair_alignment}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SKIP_FROZEN_COUNT_CHECKS="${SKIP_FROZEN_COUNT_CHECKS:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8b}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8b-cliagent-webscout-month-ablation-pair-alignment-${SPECIFICATION_NAME}-${RUN_TS}.log}"

PAIR_PREFIX="cliagent_webscout_pair_alignment"
ABLATION_PREFIX="cliagent_webscout_classmethod_month_ablation_fixed_sample"
PAIR_STATUS_FILE="${OUT_DIR}/${PAIR_PREFIX}_status.txt"
ABLATION_STATUS_FILE="${OUT_DIR}/${ABLATION_PREFIX}_status.txt"

case "${RUN_SELF_TEST}" in
  0|1) ;;
  *) echo "ERROR: RUN_SELF_TEST must be 0 or 1" >&2; exit 2 ;;
esac
case "${SKIP_FROZEN_COUNT_CHECKS}" in
  0|1) ;;
  *) echo "ERROR: SKIP_FROZEN_COUNT_CHECKS must be 0 or 1" >&2; exit 2 ;;
esac
case "${OVERWRITE_OUTPUT}" in
  0|1) ;;
  *) echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1" >&2; exit 2 ;;
esac

for required_file in \
  "${PY_SCRIPT}" \
  "${R_SCRIPT}" \
  "${HELPER_FILE}" \
  "${PANEL_PATH}" \
  "${RUN7N_CHECKS_PATH}" \
  "${ZERO_PANEL_PATH}" \
  "${MONTH_AUDIT_PATH}" \
  "${MATCHED_PAIRS_PATH}" \
  "${TREATMENT_META_PATH}" \
  "${REFERENCE_STATIC_PATH}"
do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 2
  fi
done

if [[ -d "${OUT_DIR}" && "${OVERWRITE_OUTPUT}" != "1" ]]; then
  echo "ERROR: output directory already exists: ${OUT_DIR}" >&2
  echo "Set OVERWRITE_OUTPUT=1 to replace it." >&2
  exit 2
fi

if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
  rm -rf "${OUT_DIR}"
fi
mkdir -p "${OUT_DIR}" "${LOG_DIR}"

START_EPOCH="$(date +%s)"
START_TEXT="$(date '+%Y-%m-%d %H:%M:%S %Z')"

exec > >(tee -a "${LOG_FILE}") 2>&1

cat <<EOF
================================================================================
run-py-8b: spike-month ablation and matched-pair calendar-alignment audit
Started:                    ${START_TEXT}
Project root:               ${PROJECT_ROOT}
Python:                     $(command -v "${PYTHON_BIN}")
Python version:             $("${PYTHON_BIN}" --version 2>&1)
Python pair script:         ${PY_SCRIPT}
Rscript:                    $(command -v "${RSCRIPT_BIN}")
R version:                  $("${RSCRIPT_BIN}" --version 2>&1 | head -n 1)
R ablation script:          ${R_SCRIPT}
Helper:                     ${HELPER_FILE}
Fixed-sample panel:         ${PANEL_PATH}
Zero-inclusive panel:       ${ZERO_PANEL_PATH}
Month audit:                ${MONTH_AUDIT_PATH}
Matched pairs:              ${MATCHED_PAIRS_PATH}
Treatment metadata:         ${TREATMENT_META_PATH}
Reference static result:    ${REFERENCE_STATIC_PATH}
Output directory:           ${OUT_DIR}
Target controls:            ${TARGET_REPOSITORIES}
Ablation rule:              set selected method increment to zero; retain row
Pair audit rule:            align control calendar month to each matched treatment cohort
Static model pair IDs:      NOT USED DIRECTLY
Interpretation:             supplementary fixed-sample debugging
Causal primary use:         NO
Repository/month removal:   NOT JUSTIFIED
Run self-test:              ${RUN_SELF_TEST}
Skip frozen count checks:   ${SKIP_FROZEN_COUNT_CHECKS}
Overwrite output:           ${OVERWRITE_OUTPUT}
Log file:                   ${LOG_FILE}
================================================================================
EOF

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
fi

PAIR_ARGS=(
  --fixed-panel "${PANEL_PATH}"
  --zero-panel "${ZERO_PANEL_PATH}"
  --month-audit "${MONTH_AUDIT_PATH}"
  --matched-pairs "${MATCHED_PAIRS_PATH}"
  --treatment-meta "${TREATMENT_META_PATH}"
  --output-dir "${OUT_DIR}"
  --target-repositories "${TARGET_REPOSITORIES}"
  --minimum-event-time "${MINIMUM_EVENT_TIME}"
  --maximum-event-time "${MAXIMUM_EVENT_TIME}"
)
if [[ "${SKIP_FROZEN_COUNT_CHECKS}" == "1" ]]; then
  PAIR_ARGS+=(--skip-frozen-count-checks)
fi

"${PYTHON_BIN}" "${PY_SCRIPT}" "${PAIR_ARGS[@]}"

if [[ ! -f "${PAIR_STATUS_FILE}" ]]; then
  echo "ERROR: pair-alignment status file was not created: ${PAIR_STATUS_FILE}" >&2
  exit 3
fi
if ! grep -qx "PASS" <(head -n 1 "${PAIR_STATUS_FILE}"); then
  echo "ERROR: pair-alignment status is not PASS" >&2
  cat "${PAIR_STATUS_FILE}" >&2
  exit 3
fi

export PROJECT_ROOT
export PANEL_PATH
export RUN7N_CHECKS_PATH
export REFERENCE_STATIC_PATH
export HELPER_FILE
export OUT_DIR
export NCLOC_SPEC
export TIME_MODE
export MIN_TREATMENT_COHORT
export MAX_TREATMENT_COHORT
export REPRO_TOLERANCE
export SKIP_FROZEN_COUNT_CHECKS

"${RSCRIPT_BIN}" "${R_SCRIPT}"

if [[ ! -f "${ABLATION_STATUS_FILE}" ]]; then
  echo "ERROR: month-ablation status file was not created: ${ABLATION_STATUS_FILE}" >&2
  exit 4
fi
if ! grep -qx "PASS" <(head -n 1 "${ABLATION_STATUS_FILE}"); then
  echo "ERROR: month-ablation status is not PASS" >&2
  cat "${ABLATION_STATUS_FILE}" >&2
  exit 4
fi

END_EPOCH="$(date +%s)"
END_TEXT="$(date '+%Y-%m-%d %H:%M:%S %Z')"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_TEXT '%02d:%02d:%02d' \
  "$((ELAPSED_SECONDS / 3600))" \
  "$(((ELAPSED_SECONDS % 3600) / 60))" \
  "$((ELAPSED_SECONDS % 60))"

cat <<EOF

================================================================================
run-py-8b PASS
Pair manifest:             ${OUT_DIR}/${PAIR_PREFIX}_target_pair_manifest.csv
Pair spike alignment:      ${OUT_DIR}/${PAIR_PREFIX}_spike_month_alignment.csv
Pair alignment summary:    ${OUT_DIR}/${PAIR_PREFIX}_spike_month_alignment_summary.csv
Control pair summary:      ${OUT_DIR}/${PAIR_PREFIX}_control_pair_summary.csv
Pair diagnostic findings:  ${OUT_DIR}/${PAIR_PREFIX}_diagnostic_findings.csv
Ablation static results:   ${OUT_DIR}/${ABLATION_PREFIX}_static_results.csv
Ablation comparison:       ${OUT_DIR}/${ABLATION_PREFIX}_comparison.csv
Ablation ranking:          ${OUT_DIR}/${ABLATION_PREFIX}_root_cause_ranking.csv
Ablation month audit:      ${OUT_DIR}/${ABLATION_PREFIX}_scenario_month_audit.csv
Pair IDs in estimator:     NO; audited separately
Causal primary use:        NO
================================================================================

================================================================================
run-py-8b execution summary
Started:                   ${START_TEXT}
Completed:                 ${END_TEXT}
Elapsed:                   ${ELAPSED_TEXT}
Exit code:                 0
Output directory:          ${OUT_DIR}
Log file:                  ${LOG_FILE}
================================================================================
EOF
