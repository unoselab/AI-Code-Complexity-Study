#!/bin/bash

# Prepare and analyze the run-py-8c supplementary sensitivity specification.
#
# Inputs:
#   - run-py-7n original positive-outcome fixed panel
#   - run-py-7e zero-inclusive parse-clean panel
#   - original 1:3 treatment-control pair manifest
#   - run-py-7h baseline static result
#   - run-py-7p one-repository-at-a-time static results
#   - Borusyak helper functions
#
# Outputs:
#   1. Pair-balanced monthly-support panel and support diagnostics.
#   2. Pooled Webscout 2025-04+2025-06 joint-ablation result.
#   3. Pooled versus pair-balanced static DiD comparison.
#
# Pair balance is applied to sample construction only. Pair IDs are not passed
# directly to the Borusyak estimator. All results remain noncausal selected-
# sample sensitivity because the source panel is conditioned on positive outcomes.
#
# Usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8c-webscout-joint-ablation-pair-balanced-sensitivity.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_pair_balanced_monthly_support_sensitivity.py}"
R_SCRIPT="${R_SCRIPT:-proc_r/did_webscout_joint_ablation_pair_balanced_sensitivity.R}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"

SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
NCLOC_SPEC="${NCLOC_SPEC:-python_snapshot}"
TIME_MODE="${TIME_MODE:-calendar_month}"
PARSE_MODE="${PARSE_MODE:-parse_clean}"
MIN_TREATMENT_COHORT="${MIN_TREATMENT_COHORT:-202408}"
MAX_TREATMENT_COHORT="${MAX_TREATMENT_COHORT:-202503}"
REPRO_TOLERANCE="${REPRO_TOLERANCE:-0.000001}"

RUN7N_ROOT="${RUN7N_ROOT:-repo_python/run-py-7n/strict/specifications/${SPECIFICATION_NAME}}"
POOLED_PANEL_PATH="${POOLED_PANEL_PATH:-${RUN7N_ROOT}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv}"
RUN7N_CHECKS_PATH="${RUN7N_CHECKS_PATH:-${RUN7N_ROOT}/qc/regfun_selected_classmethod_agc_uniquebody_did_input_checks.csv}"

ZERO_PANEL_PATH="${ZERO_PANEL_PATH:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"
MATCHED_PAIRS_PATH="${MATCHED_PAIRS_PATH:-repo_python/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv}"

REFERENCE_BASELINE_PATH="${REFERENCE_BASELINE_PATH:-repo_python/run-py-7h/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/positive_outcome_months_only/borusyak_regular_module_function_agc_unique_body_positive_months_static_effects.csv}"
RUN7P_ROOT="${RUN7P_ROOT:-repo_python/run-py-7p/strict/specifications/${SPECIFICATION_NAME}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/one_repository_at_a_time}"
RUN7P_PREFIX="borusyak_regfun_each_selected_classmethod_agc_uniquebody_fixed_sample"
REFERENCE_RUN7P_PATH="${REFERENCE_RUN7P_PATH:-${RUN7P_ROOT}/${RUN7P_PREFIX}_static_results.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_python/run-py-8c/strict/specifications/${SPECIFICATION_NAME}}"
OUT_DIR="${OUT_DIR:-${OUTPUT_ROOT}/${NCLOC_SPEC}_ncloc/${TIME_MODE}/${PARSE_MODE}/original_positive_sample_fixed/webscout_joint_ablation_pair_balanced_sensitivity}"

PAIR_PREFIX="pair_balanced_monthly_support"
MODEL_PREFIX="borusyak_webscout_joint_ablation_pair_balanced_sensitivity"
PAIR_PANEL_PATH="${PAIR_PANEL_PATH:-${OUT_DIR}/${PAIR_PREFIX}_panel.csv}"
PAIR_VALIDATION_PATH="${PAIR_VALIDATION_PATH:-${OUT_DIR}/${PAIR_PREFIX}_validation.csv}"
PAIR_STATUS_PATH="${PAIR_STATUS_PATH:-${OUT_DIR}/${PAIR_PREFIX}_status.txt}"
MODEL_STATUS_PATH="${MODEL_STATUS_PATH:-${OUT_DIR}/${MODEL_PREFIX}_status.txt}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SKIP_FROZEN_COUNT_CHECKS="${SKIP_FROZEN_COUNT_CHECKS:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8c}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8c-webscout-joint-ablation-pair-balanced-${SPECIFICATION_NAME}-${RUN_TS}.log}"

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
  "${POOLED_PANEL_PATH}" \
  "${RUN7N_CHECKS_PATH}" \
  "${ZERO_PANEL_PATH}" \
  "${MATCHED_PAIRS_PATH}" \
  "${REFERENCE_BASELINE_PATH}" \
  "${REFERENCE_RUN7P_PATH}"
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

PY_SCRIPT_SHA="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
R_SCRIPT_SHA="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
HELPER_SHA="$(sha256sum "${HELPER_FILE}" | awk '{print $1}')"
POOLED_PANEL_SHA="$(sha256sum "${POOLED_PANEL_PATH}" | awk '{print $1}')"
PAIR_FILE_SHA="$(sha256sum "${MATCHED_PAIRS_PATH}" | awk '{print $1}')"

cat <<EOF
================================================================================
run-py-8c: Webscout joint ablation and pair-balanced monthly-support sensitivity
Started:                    ${START_TEXT}
Project root:               ${PROJECT_ROOT}
Python:                     $(command -v "${PYTHON_BIN}")
Python version:             $("${PYTHON_BIN}" --version 2>&1)
Python preparation script:  ${PY_SCRIPT}
Python script SHA:          ${PY_SCRIPT_SHA}
Rscript:                    $(command -v "${RSCRIPT_BIN}")
R version:                  $("${RSCRIPT_BIN}" --version 2>&1 | head -n 1)
R analysis script:          ${R_SCRIPT}
R script SHA:               ${R_SCRIPT_SHA}
Helper:                     ${HELPER_FILE}
Helper SHA:                 ${HELPER_SHA}
Pooled fixed panel:         ${POOLED_PANEL_PATH}
Pooled panel SHA:           ${POOLED_PANEL_SHA}
Zero-inclusive panel:       ${ZERO_PANEL_PATH}
Matched pairs:              ${MATCHED_PAIRS_PATH}
Matched-pair SHA:           ${PAIR_FILE_SHA}
Reference baseline:         ${REFERENCE_BASELINE_PATH}
Reference run-py-7p:        ${REFERENCE_RUN7P_PATH}
Output directory:           ${OUT_DIR}
Joint ablation:             HelpingAI/Webscout 2025-04 and 2025-06
Pair-balance rule:          retain rows with at least one original matched counterpart in the same calendar month
Pair IDs in estimator:      NO; sample construction only
Primary replication:        unchanged pooled matched-control DiD
Interpretation:             noncausal supplementary selected-sample sensitivity
Run self-test:              ${RUN_SELF_TEST}
Skip frozen checks:         ${SKIP_FROZEN_COUNT_CHECKS}
Overwrite output:           ${OVERWRITE_OUTPUT}
Log file:                   ${LOG_FILE}
================================================================================
EOF

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
fi

PY_ARGS=(
  --fixed-panel "${POOLED_PANEL_PATH}"
  --zero-panel "${ZERO_PANEL_PATH}"
  --matched-pairs "${MATCHED_PAIRS_PATH}"
  --output-dir "${OUT_DIR}"
  --ncloc-spec "${NCLOC_SPEC}"
)
if [[ "${SKIP_FROZEN_COUNT_CHECKS}" == "1" ]]; then
  PY_ARGS+=(--skip-frozen-count-checks)
fi

"${PYTHON_BIN}" "${PY_SCRIPT}" "${PY_ARGS[@]}"

if [[ ! -f "${PAIR_STATUS_PATH}" ]]; then
  echo "ERROR: pair-panel status file was not created: ${PAIR_STATUS_PATH}" >&2
  exit 3
fi
if ! grep -qx "PASS" <(head -n 1 "${PAIR_STATUS_PATH}"); then
  echo "ERROR: pair-panel status is not PASS" >&2
  cat "${PAIR_STATUS_PATH}" >&2
  exit 3
fi

export PROJECT_ROOT
export POOLED_PANEL_PATH
export PAIR_PANEL_PATH
export PAIR_VALIDATION_PATH
export RUN7N_CHECKS_PATH
export REFERENCE_BASELINE_PATH
export REFERENCE_RUN7P_PATH
export HELPER_FILE
export OUT_DIR
export NCLOC_SPEC
export TIME_MODE
export MIN_TREATMENT_COHORT
export MAX_TREATMENT_COHORT
export REPRO_TOLERANCE
export SKIP_FROZEN_COUNT_CHECKS

"${RSCRIPT_BIN}" "${R_SCRIPT}"

if [[ ! -f "${MODEL_STATUS_PATH}" ]]; then
  echo "ERROR: model status file was not created: ${MODEL_STATUS_PATH}" >&2
  exit 4
fi
if ! grep -qx "PASS" <(head -n 1 "${MODEL_STATUS_PATH}"); then
  echo "ERROR: model status is not PASS" >&2
  cat "${MODEL_STATUS_PATH}" >&2
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
run-py-8c PASS
Pair-balanced panel:       ${PAIR_PANEL_PATH}
Pair-month manifest:       ${OUT_DIR}/${PAIR_PREFIX}_pair_month_manifest.csv
Pair row support:          ${OUT_DIR}/${PAIR_PREFIX}_row_support.csv
Pair exclusions:           ${OUT_DIR}/${PAIR_PREFIX}_excluded_fixed_rows.csv
Webscout support audit:    ${OUT_DIR}/${PAIR_PREFIX}_webscout_diagnostic_months.csv
Static results:            ${OUT_DIR}/${MODEL_PREFIX}_static_results.csv
Key comparisons:           ${OUT_DIR}/${MODEL_PREFIX}_key_comparisons.csv
Sample summary:            ${OUT_DIR}/${MODEL_PREFIX}_sample_summary.csv
Sample comparison:         ${OUT_DIR}/${MODEL_PREFIX}_sample_comparison.csv
Validation:                ${OUT_DIR}/${MODEL_PREFIX}_validation.csv
Pair IDs in estimator:     NO; sample construction only
Causal primary use:        NO
================================================================================

================================================================================
run-py-8c execution summary
Started:                   ${START_TEXT}
Completed:                 ${END_TEXT}
Elapsed:                   ${ELAPSED_TEXT}
Exit code:                 0
Output directory:          ${OUT_DIR}
Log file:                  ${LOG_FILE}
================================================================================
EOF
