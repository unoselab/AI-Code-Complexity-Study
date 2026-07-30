#!/usr/bin/env bash
# ==============================================================================
# run-py-8d: rematch HelpingAI/Webscout with local Python controls
# ==============================================================================
#
# Purpose:
#   Rank locally cloned Python never-treated repositories as possible
#   replacements for HelpingAI/Webscout for the six 2024-10 treatment
#   repositories that originally used Webscout as control rank 3.
#
# Analysis only:
#   - Build candidate eligibility from local control clones.
#   - Fit P0 using the paper-derived pre-adoption PSM features.
#   - Fit P1 using P0 plus Python-only NCLOC level/change/mean.
#   - Produce per-treatment and common-donor rankings.
#
# Explicitly not performed:
#   - No 2025-04 or 2025-06 AGC outcome is read.
#   - No replacement donor is silently finalized.
#   - No Difference-in-Differences model is run.
#
# Main inputs:
#   TARGET_PAIR_MANIFEST
#       run-py-8b manifest containing treatment/control pairs.
#   TREATMENT_SAMPLE
#       Python treatment sample with the 2024-10 cohort.
#   CANDIDATE_FEATURE_CSV
#       Paper candidate data for the 2024-10 cohort.
#   TREATMENT_EVENTS_CSV / TREATMENT_MONTHLY_CSV
#       Treatment-side event and age data used to engineer paper features.
#   CONTROL_CLONE_ROOT
#       Local cloned control repositories.
#   TREATMENT_NCLOC_CSV / CONTROL_NCLOC_CSV
#       Monthly Python-only NCLOC snapshots for 2024-04 through 2024-09.
#
# Main outputs:
#   webscout_local_control_rematching_candidate_eligibility.csv
#   webscout_local_control_rematching_model_diagnostics.csv
#   webscout_local_control_rematching_per_treatment_ranking.csv
#   webscout_local_control_rematching_common_donor_ranking.csv
#   webscout_local_control_rematching_top_candidate_balance.csv
#   webscout_local_control_rematching_validation.csv
#   webscout_local_control_rematching_summary.json
#   webscout_local_control_rematching_status.txt
#
# Typical usage:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8d-rematch-webscout-control-with-python-ncloc.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/rematch_webscout_control_with_python_ncloc.py}"

TARGET_CONTROL="${TARGET_CONTROL:-HelpingAI/Webscout}"
TARGET_COHORT="${TARGET_COHORT:-2024-10}"

TARGET_PAIR_MANIFEST="${TARGET_PAIR_MANIFEST:-repo_python/run-py-8b/strict/specifications/range100_200/python_snapshot_ncloc/calendar_month/parse_clean/original_positive_sample_fixed/month_ablation_pair_alignment/cliagent_webscout_pair_alignment_target_pair_manifest.csv}"
TREATMENT_SAMPLE="${TREATMENT_SAMPLE:-repo_python/run-py-1f/treatment_python_sample_main_118.csv}"
CANDIDATE_FEATURE_CSV="${CANDIDATE_FEATURE_CSV:-data_baseline_backup/control_repo_candidates_202410.csv}"
TREATMENT_FEATURE_CSV="${TREATMENT_FEATURE_CSV:-}"
TREATMENT_EVENTS_CSV="${TREATMENT_EVENTS_CSV:-data_baseline_backup/repo_events.csv}"
TREATMENT_MONTHLY_CSV="${TREATMENT_MONTHLY_CSV:-data_baseline_backup/ts_repos_monthly.csv}"
ORIGINAL_MATCHING_CSV="${ORIGINAL_MATCHING_CSV:-data_baseline_backup/matching.csv}"
LOCAL_CONTROL_MANIFEST="${LOCAL_CONTROL_MANIFEST:-repo_python/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-/home/user1-system12/project-workspace/ai_code_complexity_study_python/control-repos}"

DEFAULT_TREATMENT_NCLOC_PYONLY="repo_python/run-py-2b/strict/treatment/ts_repos_monthly_scanned_python_only.csv"
DEFAULT_TREATMENT_NCLOC_ALL="repo_python/run-py-2b/strict/treatment/ts_repos_monthly_scanned.csv"
if [[ -n "${TREATMENT_NCLOC_CSV:-}" ]]; then
  TREATMENT_NCLOC_CSV="${TREATMENT_NCLOC_CSV}"
elif [[ -f "${DEFAULT_TREATMENT_NCLOC_PYONLY}" ]]; then
  TREATMENT_NCLOC_CSV="${DEFAULT_TREATMENT_NCLOC_PYONLY}"
else
  TREATMENT_NCLOC_CSV="${DEFAULT_TREATMENT_NCLOC_ALL}"
fi
CONTROL_NCLOC_CSV="${CONTROL_NCLOC_CSV:-repo_python/run-py-2b/strict/control/ts_repos_monthly_scanned.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-8d/strict/specifications/range100_200/python_snapshot_ncloc/202410_local_control_rematching}"
OUTPUT_PREFIX="webscout_local_control_rematching"
STATUS_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}_status.txt"

TOP_K="${TOP_K:-25}"
CHUNKSIZE="${CHUNKSIZE:-100000}"
RANDOM_STATE="${RANDOM_STATE:-20260730}"
MIN_LOCAL_CANDIDATES="${MIN_LOCAL_CANDIDATES:-20}"
MIN_PYTHON_NCLOC_MONTHS="${MIN_PYTHON_NCLOC_MONTHS:-6}"
ALLOW_NCLOC_PARTIAL_WINDOW="${ALLOW_NCLOC_PARTIAL_WINDOW:-0}"
SKIP_FROZEN_TARGET_CHECKS="${SKIP_FROZEN_TARGET_CHECKS:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8d}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8d-rematch-webscout-python-ncloc-${RUN_TS}.log}"
mkdir -p "${LOG_DIR}"

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}"
    exit 1
  fi
}

require_dir() {
  local path="$1"
  local label="$2"
  if [[ ! -d "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}"
    exit 1
  fi
}

optional_arg() {
  local flag="$1"
  local path="$2"
  if [[ -n "${path}" && -f "${path}" ]]; then
    printf '%s\n%s\n' "${flag}" "${path}"
  fi
}

START_EPOCH="$(date +%s)"
STARTED="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-8d: Webscout local-control rematching with Python NCLOC"
  echo "Started:                    ${STARTED}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Target control:             ${TARGET_CONTROL}"
  echo "Target cohort:              ${TARGET_COHORT}"
  echo "Target pair manifest:       ${TARGET_PAIR_MANIFEST}"
  echo "Treatment sample:           ${TREATMENT_SAMPLE}"
  echo "Candidate feature CSV:      ${CANDIDATE_FEATURE_CSV}"
  echo "Treatment feature CSV:      ${TREATMENT_FEATURE_CSV:-<not configured>}"
  echo "Treatment events CSV:       ${TREATMENT_EVENTS_CSV:-<not configured>}"
  echo "Treatment monthly CSV:      ${TREATMENT_MONTHLY_CSV:-<not configured>}"
  echo "Original matching CSV:      ${ORIGINAL_MATCHING_CSV:-<not configured>}"
  echo "Local control manifest:     ${LOCAL_CONTROL_MANIFEST:-<not configured>}"
  echo "Control clone root:         ${CONTROL_CLONE_ROOT}"
  echo "Treatment Python NCLOC:     ${TREATMENT_NCLOC_CSV}"
  echo "Control Python NCLOC:       ${CONTROL_NCLOC_CSV}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Top K:                      ${TOP_K}"
  echo "CSV chunk size:             ${CHUNKSIZE}"
  echo "Random state:               ${RANDOM_STATE}"
  echo "Minimum local candidates:   ${MIN_LOCAL_CANDIDATES}"
  echo "Minimum NCLOC months:       ${MIN_PYTHON_NCLOC_MONTHS}"
  echo "Allow partial NCLOC window: ${ALLOW_NCLOC_PARTIAL_WINDOW}"
  echo "Run self-test:              ${RUN_SELF_TEST}"
  echo "Overwrite output:           ${OVERWRITE_OUTPUT}"
  echo "Post-adoption AGC outcomes: NOT READ"
  echo "DiD execution:              NO"
  echo "Interpretation:             noncausal design-stage rematching sensitivity"
  echo "Log file:                   ${LOG_FILE}"
  echo "================================================================================"

  require_file "${PY_SCRIPT}" "Python script"
  require_file "${TARGET_PAIR_MANIFEST}" "Target pair manifest"
  require_file "${TREATMENT_SAMPLE}" "Treatment sample"
  require_file "${CANDIDATE_FEATURE_CSV}" "Candidate feature CSV"
  require_file "${TREATMENT_NCLOC_CSV}" "Treatment Python NCLOC CSV"
  require_file "${CONTROL_NCLOC_CSV}" "Control Python NCLOC CSV"
  require_dir "${CONTROL_CLONE_ROOT}" "Control clone root"

  if [[ -n "${TREATMENT_FEATURE_CSV}" ]]; then
    require_file "${TREATMENT_FEATURE_CSV}" "Treatment feature CSV"
  fi
  if [[ -n "${TREATMENT_EVENTS_CSV}" ]]; then
    require_file "${TREATMENT_EVENTS_CSV}" "Treatment events CSV"
  fi
  if [[ -n "${TREATMENT_MONTHLY_CSV}" ]]; then
    require_file "${TREATMENT_MONTHLY_CSV}" "Treatment monthly CSV"
  fi
  if [[ -n "${ORIGINAL_MATCHING_CSV}" ]]; then
    require_file "${ORIGINAL_MATCHING_CSV}" "Original matching CSV"
  fi
  if [[ -n "${LOCAL_CONTROL_MANIFEST}" ]]; then
    require_file "${LOCAL_CONTROL_MANIFEST}" "Local control manifest"
  fi

  echo "Python script SHA:          $(sha256_file "${PY_SCRIPT}")"
  echo "Target pair SHA:            $(sha256_file "${TARGET_PAIR_MANIFEST}")"
  echo "Candidate feature SHA:      $(sha256_file "${CANDIDATE_FEATURE_CSV}")"
  echo "Treatment NCLOC SHA:        $(sha256_file "${TREATMENT_NCLOC_CSV}")"
  echo "Control NCLOC SHA:          $(sha256_file "${CONTROL_NCLOC_CSV}")"

  "${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

  if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
  fi

  if [[ -e "${OUTPUT_DIR}" ]]; then
    if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
      rm -rf "${OUTPUT_DIR}"
    else
      echo "ERROR: Output directory already exists. Set OVERWRITE_OUTPUT=1 to replace it: ${OUTPUT_DIR}"
      exit 1
    fi
  fi
  mkdir -p "${OUTPUT_DIR}"

  PY_ARGS=(
    --target-pair-manifest "${TARGET_PAIR_MANIFEST}"
    --treatment-sample "${TREATMENT_SAMPLE}"
    --candidate-feature-csv "${CANDIDATE_FEATURE_CSV}"
    --control-clone-root "${CONTROL_CLONE_ROOT}"
    --treatment-ncloc-csv "${TREATMENT_NCLOC_CSV}"
    --control-ncloc-csv "${CONTROL_NCLOC_CSV}"
    --output-dir "${OUTPUT_DIR}"
    --target-control "${TARGET_CONTROL}"
    --target-cohort "${TARGET_COHORT}"
    --top-k "${TOP_K}"
    --chunksize "${CHUNKSIZE}"
    --random-state "${RANDOM_STATE}"
    --min-local-candidates "${MIN_LOCAL_CANDIDATES}"
    --min-python-ncloc-months "${MIN_PYTHON_NCLOC_MONTHS}"
  )

  if [[ -n "${TREATMENT_FEATURE_CSV}" ]]; then
    PY_ARGS+=(--treatment-feature-csv "${TREATMENT_FEATURE_CSV}")
  fi
  if [[ -n "${TREATMENT_EVENTS_CSV}" ]]; then
    PY_ARGS+=(--treatment-events-csv "${TREATMENT_EVENTS_CSV}")
  fi
  if [[ -n "${TREATMENT_MONTHLY_CSV}" ]]; then
    PY_ARGS+=(--treatment-monthly-csv "${TREATMENT_MONTHLY_CSV}")
  fi
  if [[ -n "${ORIGINAL_MATCHING_CSV}" ]]; then
    PY_ARGS+=(--original-matching-csv "${ORIGINAL_MATCHING_CSV}")
  fi
  if [[ -n "${LOCAL_CONTROL_MANIFEST}" ]]; then
    PY_ARGS+=(--local-control-manifest "${LOCAL_CONTROL_MANIFEST}")
  fi
  if [[ "${ALLOW_NCLOC_PARTIAL_WINDOW}" == "1" ]]; then
    PY_ARGS+=(--allow-ncloc-partial-window)
  fi
  if [[ "${SKIP_FROZEN_TARGET_CHECKS}" == "1" ]]; then
    PY_ARGS+=(--skip-frozen-target-checks)
  fi

  "${PYTHON_BIN}" "${PY_SCRIPT}" "${PY_ARGS[@]}"

  require_file "${STATUS_FILE}" "Status file"
  STATUS_VALUE="$(head -n 1 "${STATUS_FILE}" | tr -d '\r')"
  if [[ "${STATUS_VALUE}" != "PASS" ]]; then
    echo "ERROR: Expected PASS status but found: ${STATUS_VALUE}"
    exit 1
  fi

  EXPECTED_OUTPUTS=(
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_treatments.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_candidate_eligibility.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_model_diagnostics.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_per_treatment_ranking.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_common_donor_ranking.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_top_candidate_balance.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
    "${STATUS_FILE}"
  )
  for expected in "${EXPECTED_OUTPUTS[@]}"; do
    require_file "${expected}" "Expected output"
  done

  echo
  echo "================================================================================"
  echo "run-py-8d PASS"
  echo "Common ranking:            ${OUTPUT_DIR}/${OUTPUT_PREFIX}_common_donor_ranking.csv"
  echo "Per-treatment ranking:     ${OUTPUT_DIR}/${OUTPUT_PREFIX}_per_treatment_ranking.csv"
  echo "Candidate eligibility:     ${OUTPUT_DIR}/${OUTPUT_PREFIX}_candidate_eligibility.csv"
  echo "Model diagnostics:         ${OUTPUT_DIR}/${OUTPUT_PREFIX}_model_diagnostics.csv"
  echo "Balance audit:             ${OUTPUT_DIR}/${OUTPUT_PREFIX}_top_candidate_balance.csv"
  echo "Validation:                ${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
  echo "Summary:                   ${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
  echo "Status:                    ${STATUS_FILE}"
  echo "Next step:                 manually review and freeze one donor before opening post-adoption AGC outcomes"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

EXIT_CODE="${PIPESTATUS[0]}"
END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_FMT '%02d:%02d:%02d' "$((ELAPSED / 3600))" "$(((ELAPSED % 3600) / 60))" "$((ELAPSED % 60))"

echo
echo "================================================================================"
echo "run-py-8d execution summary"
echo "Started:              ${STARTED}"
echo "Completed:            $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Elapsed:              ${ELAPSED_FMT}"
echo "Exit code:            ${EXIT_CODE}"
echo "Output directory:     ${OUTPUT_DIR}"
echo "Log file:             ${LOG_FILE}"
echo "================================================================================"

exit "${EXIT_CODE}"
