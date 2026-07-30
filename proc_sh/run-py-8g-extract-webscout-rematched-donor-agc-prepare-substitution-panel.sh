#!/usr/bin/env bash
# ==============================================================================
# run-py-8g: extract frozen donor AGC outcomes and prepare substitution panel
# ==============================================================================
#
# Purpose:
#   Read AGC classifications only after the donor ranking has been frozen by
#   run-py-8e and the target-month commit activity has been audited by run-py-8f.
#   Count class-method AGC unique bodies for the frozen selected and fallback
#   donors in 2025-04 and 2025-06, verify zero-commit/zero-event consistency,
#   and prepare a fixed-sample panel that replaces only HelpingAI/Webscout's
#   target-month class-method increments with the selected donor increments.
#
# Inputs:
#   - run-py-8e freeze manifest
#   - run-py-8f target-month commit-activity audit
#   - run-py-7a event classifications
#   - run-py-7j repository-month method counts
#   - run-py-7n fixed original-positive sample panel
#
# Outputs:
#   - frozen donor target-month AGC outcome audit
#   - Webscout donor-substitution fixed-sample panel
#   - target-month arithmetic and ablation-equivalence audit
#   - validation, provenance, summary, and status files
#
# Safeguards:
#   - The selected donor cannot change after AGC outcomes are opened.
#   - Zero-commit months must have zero function events and zero method AGC.
#   - Repository-month sample membership remains fixed to run-py-7n.
#   - No Difference-in-Differences model is run in this step.
#   - Causal interpretation remains disallowed.
#
# This wrapper copies and adapts the execution and validation structure of the
# existing run-py-8f wrapper, but is independent and does not call it.
#
# Typical execution:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8g-extract-webscout-rematched-donor-agc-prepare-substitution-panel.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/extract_webscout_rematched_donor_agc_prepare_substitution_panel.py}"

RUN_PY_8E_ROOT="${RUN_PY_8E_ROOT:-repo_python/run-py-8e/strict/specifications/range100_200/python_snapshot_ncloc/202410_webscout_rematched_donor_freeze}"
FREEZE_MANIFEST="${FREEZE_MANIFEST:-${RUN_PY_8E_ROOT}/webscout_rematched_donor_freeze_manifest.csv}"

RUN_PY_8F_ROOT="${RUN_PY_8F_ROOT:-repo_python/run-py-8f/strict/specifications/range100_200/python_snapshot_ncloc/202410_webscout_rematched_donor_commit_activity_audit}"
COMMIT_ACTIVITY="${COMMIT_ACTIVITY:-${RUN_PY_8F_ROOT}/webscout_rematched_donor_commit_activity_monthly_commits.csv}"

EVENT_CLASSIFICATIONS="${EVENT_CLASSIFICATIONS:-repo_python/run-py-7a/strict/specifications/range100_200/agc_commit_function_npr_event_classifications.csv}"
REPO_MONTH_COUNTS="${REPO_MONTH_COUNTS:-repo_python/run-py-7j/strict/specifications/range100_200/regular_module_function_and_class_method_agc_unique_body_repo_month_counts.csv}"
FIXED_SAMPLE_PANEL="${FIXED_SAMPLE_PANEL:-repo_python/run-py-7n/strict/specifications/range100_200/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_original_positive_sample_parse_clean.csv}"

EXPECTED_SELECTED_DONOR="${EXPECTED_SELECTED_DONOR:-Hack-a-Day/2024-Supercon-8-Add-On-Badge}"
EXPECTED_FALLBACK_DONOR="${EXPECTED_FALLBACK_DONOR:-viktoriasemaan/sa-ai-agent}"
TARGET_CONTROL="${TARGET_CONTROL:-HelpingAI/Webscout}"
TARGET_MONTH_1="${TARGET_MONTH_1:-2025-04}"
TARGET_MONTH_2="${TARGET_MONTH_2:-2025-06}"
EXPECTED_WEBSCOUT_METHOD_INCREMENT_1="${EXPECTED_WEBSCOUT_METHOD_INCREMENT_1:-18}"
EXPECTED_WEBSCOUT_METHOD_INCREMENT_2="${EXPECTED_WEBSCOUT_METHOD_INCREMENT_2:-30}"

EXPECTED_FIXED_SAMPLE_ROWS="${EXPECTED_FIXED_SAMPLE_ROWS:-487}"
EXPECTED_FIXED_SAMPLE_REPOSITORIES="${EXPECTED_FIXED_SAMPLE_REPOSITORIES:-132}"
EXPECTED_ORIGINAL_HYBRID_TOTAL="${EXPECTED_ORIGINAL_HYBRID_TOTAL:-3075}"
EXPECTED_REMOVED_NET_BODIES="${EXPECTED_REMOVED_NET_BODIES:-48}"
EXPECTED_SUBSTITUTION_TOTAL="${EXPECTED_SUBSTITUTION_TOTAL:-3027}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-8g/strict/specifications/range100_200/python_snapshot_ncloc/calendar_month/parse_clean/original_positive_sample_fixed/webscout_frozen_donor_substitution}"
OUTPUT_PREFIX="webscout_rematched_donor_agc_substitution"
STATUS_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}_status.txt"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
SKIP_FROZEN_COUNT_CHECKS="${SKIP_FROZEN_COUNT_CHECKS:-0}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8g}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8g-webscout-rematched-donor-agc-substitution-${RUN_TS}.log}"
mkdir -p "${LOG_DIR}"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -s "${path}" ]]; then
    echo "ERROR: ${label} not found or empty: ${path}"
    exit 1
  fi
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

for flag_name in RUN_SELF_TEST SKIP_FROZEN_COUNT_CHECKS OVERWRITE_OUTPUT; do
  flag_value="${!flag_name}"
  case "${flag_value}" in
    0|1) ;;
    *)
      echo "ERROR: ${flag_name} must be 0 or 1. Observed: ${flag_value}" >&2
      exit 1
      ;;
  esac
done

START_EPOCH="$(date +%s)"
STARTED="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-8g: frozen donor AGC extraction and Webscout substitution panel"
  echo "Started:                    ${STARTED}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Freeze manifest:            ${FREEZE_MANIFEST}"
  echo "Commit activity audit:      ${COMMIT_ACTIVITY}"
  echo "Event classifications:      ${EVENT_CLASSIFICATIONS}"
  echo "Repository-month counts:    ${REPO_MONTH_COUNTS}"
  echo "Fixed-sample panel:         ${FIXED_SAMPLE_PANEL}"
  echo "Selected donor:             ${EXPECTED_SELECTED_DONOR}"
  echo "Fallback donor:             ${EXPECTED_FALLBACK_DONOR}"
  echo "Target control:             ${TARGET_CONTROL}"
  echo "Target month 1:             ${TARGET_MONTH_1}"
  echo "Target month 2:             ${TARGET_MONTH_2}"
  echo "Expected method increment 1:${EXPECTED_WEBSCOUT_METHOD_INCREMENT_1}"
  echo "Expected method increment 2:${EXPECTED_WEBSCOUT_METHOD_INCREMENT_2}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Skip frozen count checks:   ${SKIP_FROZEN_COUNT_CHECKS}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Post-adoption AGC outcomes: READ IN THIS STEP"
  echo "Donor reselection:          FORBIDDEN"
  echo "DiD execution:              NO"
  echo "Interpretation:             noncausal supplementary fixed-sample sensitivity"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"

  require_file "${PY_SCRIPT}" "Python script"
  require_file "${FREEZE_MANIFEST}" "Freeze manifest"
  require_file "${COMMIT_ACTIVITY}" "Commit activity audit"
  require_file "${EVENT_CLASSIFICATIONS}" "Event classifications"
  require_file "${REPO_MONTH_COUNTS}" "Repository-month counts"
  require_file "${FIXED_SAMPLE_PANEL}" "Fixed-sample panel"

  echo "Python script SHA:          $(sha256_file "${PY_SCRIPT}")"
  echo "Freeze manifest SHA:        $(sha256_file "${FREEZE_MANIFEST}")"
  echo "Commit activity SHA:        $(sha256_file "${COMMIT_ACTIVITY}")"
  echo "Event classifications SHA:  $(sha256_file "${EVENT_CLASSIFICATIONS}")"
  echo "Repository-month counts SHA:$(sha256_file "${REPO_MONTH_COUNTS}")"
  echo "Fixed-sample panel SHA:     $(sha256_file "${FIXED_SAMPLE_PANEL}")"
  echo "================================================================================"

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
  fi

  if [[ -e "${OUTPUT_DIR}" ]]; then
    if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
      rm -rf "${OUTPUT_DIR}"
    else
      echo "ERROR: Output directory already exists."
      echo "       Set OVERWRITE_OUTPUT=1 to replace: ${OUTPUT_DIR}"
      exit 1
    fi
  fi

  ARGS=(
    "${PY_SCRIPT}"
    --freeze-manifest "${FREEZE_MANIFEST}"
    --commit-activity "${COMMIT_ACTIVITY}"
    --event-classifications "${EVENT_CLASSIFICATIONS}"
    --repo-month-counts "${REPO_MONTH_COUNTS}"
    --fixed-sample-panel "${FIXED_SAMPLE_PANEL}"
    --output-dir "${OUTPUT_DIR}"
    --expected-selected-donor "${EXPECTED_SELECTED_DONOR}"
    --expected-fallback-donor "${EXPECTED_FALLBACK_DONOR}"
    --target-control "${TARGET_CONTROL}"
    --target-month "${TARGET_MONTH_1}"
    --target-month "${TARGET_MONTH_2}"
    --expected-webscout-method-increment "${TARGET_MONTH_1}=${EXPECTED_WEBSCOUT_METHOD_INCREMENT_1}"
    --expected-webscout-method-increment "${TARGET_MONTH_2}=${EXPECTED_WEBSCOUT_METHOD_INCREMENT_2}"
    --expected-fixed-sample-rows "${EXPECTED_FIXED_SAMPLE_ROWS}"
    --expected-fixed-sample-repositories "${EXPECTED_FIXED_SAMPLE_REPOSITORIES}"
    --expected-original-hybrid-total "${EXPECTED_ORIGINAL_HYBRID_TOTAL}"
    --expected-removed-net-bodies "${EXPECTED_REMOVED_NET_BODIES}"
    --expected-substitution-total "${EXPECTED_SUBSTITUTION_TOTAL}"
  )

  if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    ARGS+=(--overwrite-output)
  fi
  if [[ "${SKIP_FROZEN_COUNT_CHECKS}" == "1" ]]; then
    ARGS+=(--skip-frozen-count-checks)
  fi

  "${PYTHON_BIN}" "${ARGS[@]}"

  EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_month_outcomes.csv"
    "${OUTPUT_DIR}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_webscout_frozen_donor_substitution_original_positive_sample_parse_clean.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_month_audit.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_ablation_equivalence.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_provenance.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
    "${STATUS_FILE}"
  )
  for path in "${EXPECTED_OUTPUTS[@]}"; do
    require_file "${path}" "Expected output"
  done

  STATUS_VALUE="$(head -n 1 "${STATUS_FILE}" | tr -d '\r')"
  if [[ "${STATUS_VALUE}" != "PASS" ]]; then
    echo "ERROR: Expected PASS status but found: ${STATUS_VALUE}"
    cat "${STATUS_FILE}"
    exit 1
  fi
  if ! grep -Fxq "donor_selection_locked_before_outcome_review=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: Donor freeze guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "post_adoption_agc_outcome_read=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: AGC outcome-read provenance is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "did_executed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: DiD execution guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "sample_membership_unchanged=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: Fixed-sample guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "substitution_equivalent_to_target_month_ablation=TRUE" "${STATUS_FILE}"; then
    echo "ERROR: Ablation-equivalence guard is missing." >&2
    exit 1
  fi
  if ! grep -Fxq "causal_interpretation_allowed=FALSE" "${STATUS_FILE}"; then
    echo "ERROR: Noncausal interpretation guard is missing." >&2
    exit 1
  fi

  echo ""
  echo "================================================================================"
  echo "run-py-8g PASS"
  echo "Donor AGC outcomes:          ${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_month_outcomes.csv"
  echo "Substitution panel:          ${OUTPUT_DIR}/panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_webscout_frozen_donor_substitution_original_positive_sample_parse_clean.csv"
  echo "Month audit:                 ${OUTPUT_DIR}/${OUTPUT_PREFIX}_month_audit.csv"
  echo "Ablation equivalence:        ${OUTPUT_DIR}/${OUTPUT_PREFIX}_ablation_equivalence.csv"
  echo "Validation:                  ${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
  echo "Provenance:                  ${OUTPUT_DIR}/${OUTPUT_PREFIX}_provenance.csv"
  echo "Summary:                     ${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
  echo "Status:                      ${STATUS_FILE}"
  echo "Next step:                   run a separate static Borusyak DiD comparison"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

EXIT_CODE="${PIPESTATUS[0]}"
END_EPOCH="$(date +%s)"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED '%02d:%02d:%02d' \
  "$((ELAPSED_SECONDS / 3600))" \
  "$(((ELAPSED_SECONDS % 3600) / 60))" \
  "$((ELAPSED_SECONDS % 60))"

{
  echo ""
  echo "================================================================================"
  echo "run-py-8g execution summary"
  echo "Started:              ${STARTED}"
  echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Elapsed:              ${ELAPSED}"
  echo "Exit code:            ${EXIT_CODE}"
  echo "Output directory:     ${OUTPUT_DIR}"
  echo "Log file:             ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"

exit "${EXIT_CODE}"
