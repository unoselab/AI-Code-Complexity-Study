#!/usr/bin/env bash
# ==============================================================================
# run-py-8d: restore pre-adoption Python NCLOC and rematch Webscout controls
# ==============================================================================
#
# Purpose:
#   Preserve the original paper propensity score and use directly restored
#   Python-only NCLOC to distinguish exact-score control ties for the six
#   treatments that originally used HelpingAI/Webscout as control rank 3.
#
# Design:
#   1. Read the six frozen treatment/control pairs.
#   2. Read original propensity scores at paper matched period 202409.
#   3. Find the last Git commit at or before 2024-09-30 23:59:59 UTC.
#   4. Read that immutable snapshot with git archive without changing HEAD.
#   5. Count direct Python token/AST NCLOC.
#   6. Rank exact-score local controls by Python NCLOC distance.
#
# Important safeguards:
#   - Missing history is never converted to zero.
#   - Zero is used only when complete Git history proves that the repository
#     had no commit before the cutoff.
#   - Existing SonarQube Python-only NCLOC is validation data only.
#   - No 2025-04 or 2025-06 AGC outcome is read.
#   - No Difference-in-Differences model is run.
#
# This wrapper reuses the execution, validation, logging, and output-checking
# logic of the earlier run-py-8d wrapper, but it is independent and does not
# call that wrapper.
#
# Typical execution:
#   RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8d-rematch-webscout-control-with-python-ncloc.sh
#
# Small repository smoke test:
#   MAX_CONTROLS=10 RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh/run-py-8d-rematch-webscout-control-with-python-ncloc.sh
# ============================================================================== 

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/rematch_webscout_control_with_python_ncloc.py}"

TARGET_CONTROL="${TARGET_CONTROL:-HelpingAI/Webscout}"
TARGET_ADOPTION_COHORT="${TARGET_ADOPTION_COHORT:-2024-10}"
PAPER_MATCHED_PERIOD="${PAPER_MATCHED_PERIOD:-202409}"
CUTOFF_UTC="${CUTOFF_UTC:-2024-09-30T23:59:59+00:00}"
PROPENSITY_CALIPER="${PROPENSITY_CALIPER:-1e-12}"

TARGET_PAIR_MANIFEST="${TARGET_PAIR_MANIFEST:-repo_python/run-py-8b/strict/specifications/range100_200/python_snapshot_ncloc/calendar_month/parse_clean/original_positive_sample_fixed/month_ablation_pair_alignment/cliagent_webscout_pair_alignment_target_pair_manifest.csv}"
TREATMENT_SAMPLE="${TREATMENT_SAMPLE:-repo_python/run-py-1f/treatment_python_sample_main_118.csv}"
ORIGINAL_MATCHING_CSV="${ORIGINAL_MATCHING_CSV:-data_baseline_backup/matching.csv}"
CANDIDATE_FEATURE_CSV="${CANDIDATE_FEATURE_CSV:-data_baseline_backup/control_repo_candidates_202410.csv}"
LOCAL_CONTROL_MANIFEST="${LOCAL_CONTROL_MANIFEST:-repo_python/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv}"

TREATMENT_CLONE_ROOT="${TREATMENT_CLONE_ROOT:-../treatment-repos}"
CONTROL_CLONE_ROOT="${CONTROL_CLONE_ROOT:-../control-repos}"

TREATMENT_SONAR_NCLOC_CSV="${TREATMENT_SONAR_NCLOC_CSV:-repo_python/run-py-2b/strict/treatment/ts_repos_monthly_scanned_python_only.csv}"
CONTROL_SONAR_NCLOC_CSV="${CONTROL_SONAR_NCLOC_CSV:-repo_python/run-py-2b/strict/control/ts_repos_monthly_scanned_python_only.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-8d/strict/specifications/range100_200/python_snapshot_ncloc/202410_local_control_rematching}"
OUTPUT_PREFIX="webscout_local_control_rematching"
STATUS_FILE="${OUTPUT_DIR}/${OUTPUT_PREFIX}_status.txt"

TOP_K="${TOP_K:-25}"
WORKERS="${WORKERS:-4}"
CHUNKSIZE="${CHUNKSIZE:-250000}"
MAX_CONTROLS="${MAX_CONTROLS:-0}"
MAX_PYTHON_FILE_BYTES="${MAX_PYTHON_FILE_BYTES:-5000000}"
EXCLUDED_DIRS="${EXCLUDED_DIRS:-.git,__pycache__,.venv,venv,env,node_modules,dist,build,.tox,.mypy_cache,.pytest_cache,coverage,.next,.nuxt}"
SKIP_FROZEN_TARGET_CHECKS="${SKIP_FROZEN_TARGET_CHECKS:-0}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs/run-py-8d}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-8d-rematch-webscout-python-ncloc-${RUN_TS}.log}"
mkdir -p "${LOG_DIR}"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: ${label} not found: ${path}"
    exit 1
  fi
}

require_optional_file() {
  local path="$1"
  local label="$2"
  if [[ -n "${path}" && ! -f "${path}" ]]; then
    echo "WARNING: ${label} not found; optional audit will be skipped: ${path}"
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

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

print_optional_sha() {
  local path="$1"
  local label="$2"
  if [[ -f "${path}" ]]; then
    echo "${label}: $(sha256_file "${path}")"
  else
    echo "${label}: <not available>"
  fi
}

append_optional_path_arg() {
  local flag="$1"
  local path="$2"
  if [[ -n "${path}" && -f "${path}" ]]; then
    PY_ARGS+=("${flag}" "${path}")
  fi
}

START_EPOCH="$(date +%s)"
STARTED="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  echo "================================================================================"
  echo "run-py-8d: restore Python NCLOC and rematch Webscout controls"
  echo "Started:                    ${STARTED}"
  echo "Project root:               ${PROJECT_ROOT}"
  echo "Python:                     $(command -v "${PYTHON_BIN}")"
  echo "Python version:             $("${PYTHON_BIN}" --version 2>&1)"
  echo "Python script:              ${PY_SCRIPT}"
  echo "Target control:             ${TARGET_CONTROL}"
  echo "Target adoption cohort:     ${TARGET_ADOPTION_COHORT}"
  echo "Paper matched period:       ${PAPER_MATCHED_PERIOD}"
  echo "Cutoff UTC:                 ${CUTOFF_UTC}"
  echo "Propensity caliper:         ${PROPENSITY_CALIPER}"
  echo "Target pair manifest:       ${TARGET_PAIR_MANIFEST}"
  echo "Treatment sample:           ${TREATMENT_SAMPLE}"
  echo "Original matching CSV:      ${ORIGINAL_MATCHING_CSV}"
  echo "Candidate feature CSV:      ${CANDIDATE_FEATURE_CSV}"
  echo "Local control manifest:     ${LOCAL_CONTROL_MANIFEST}"
  echo "Treatment clone root:       ${TREATMENT_CLONE_ROOT}"
  echo "Control clone root:         ${CONTROL_CLONE_ROOT}"
  echo "Treatment Sonar validation:${TREATMENT_SONAR_NCLOC_CSV}"
  echo "Control Sonar validation:  ${CONTROL_SONAR_NCLOC_CSV}"
  echo "Output directory:           ${OUTPUT_DIR}"
  echo "Top K:                      ${TOP_K}"
  echo "Workers:                    ${WORKERS}"
  echo "CSV chunk size:             ${CHUNKSIZE}"
  echo "Maximum controls:           ${MAX_CONTROLS}"
  echo "Maximum Python file bytes: ${MAX_PYTHON_FILE_BYTES}"
  echo "Excluded directories:       ${EXCLUDED_DIRS}"
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
  require_file "${ORIGINAL_MATCHING_CSV}" "Original matching CSV"
  require_dir "${TREATMENT_CLONE_ROOT}" "Treatment clone root"
  require_dir "${CONTROL_CLONE_ROOT}" "Control clone root"
  require_optional_file "${CANDIDATE_FEATURE_CSV}" "Candidate feature CSV"
  require_optional_file "${LOCAL_CONTROL_MANIFEST}" "Local control manifest"
  require_optional_file "${TREATMENT_SONAR_NCLOC_CSV}" "Treatment Sonar validation CSV"
  require_optional_file "${CONTROL_SONAR_NCLOC_CSV}" "Control Sonar validation CSV"

  echo "Python script SHA:          $(sha256_file "${PY_SCRIPT}")"
  echo "Target pair SHA:            $(sha256_file "${TARGET_PAIR_MANIFEST}")"
  echo "Treatment sample SHA:       $(sha256_file "${TREATMENT_SAMPLE}")"
  echo "Original matching SHA:      $(sha256_file "${ORIGINAL_MATCHING_CSV}")"
  print_optional_sha "${CANDIDATE_FEATURE_CSV}" "Candidate feature SHA      "
  print_optional_sha "${LOCAL_CONTROL_MANIFEST}" "Local control manifest SHA "
  print_optional_sha "${TREATMENT_SONAR_NCLOC_CSV}" "Treatment Sonar SHA        "
  print_optional_sha "${CONTROL_SONAR_NCLOC_CSV}" "Control Sonar SHA          "
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
  mkdir -p "${OUTPUT_DIR}"

  PY_ARGS=(
    --target-pair-manifest "${TARGET_PAIR_MANIFEST}"
    --treatment-sample "${TREATMENT_SAMPLE}"
    --original-matching-csv "${ORIGINAL_MATCHING_CSV}"
    --treatment-clone-root "${TREATMENT_CLONE_ROOT}"
    --control-clone-root "${CONTROL_CLONE_ROOT}"
    --output-dir "${OUTPUT_DIR}"
    --target-control "${TARGET_CONTROL}"
    --target-adoption-cohort "${TARGET_ADOPTION_COHORT}"
    --paper-matched-period "${PAPER_MATCHED_PERIOD}"
    --cutoff-utc "${CUTOFF_UTC}"
    --propensity-caliper "${PROPENSITY_CALIPER}"
    --top-k "${TOP_K}"
    --workers "${WORKERS}"
    --chunksize "${CHUNKSIZE}"
    --max-controls "${MAX_CONTROLS}"
    --max-python-file-bytes "${MAX_PYTHON_FILE_BYTES}"
    --excluded-dirs "${EXCLUDED_DIRS}"
  )

  append_optional_path_arg --candidate-feature-csv "${CANDIDATE_FEATURE_CSV}"
  append_optional_path_arg --local-control-manifest "${LOCAL_CONTROL_MANIFEST}"
  append_optional_path_arg --treatment-sonar-ncloc-csv "${TREATMENT_SONAR_NCLOC_CSV}"
  append_optional_path_arg --control-sonar-ncloc-csv "${CONTROL_SONAR_NCLOC_CSV}"

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
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_matching_profile.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_python_ncloc_snapshot_restoration.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_python_ncloc_file_measurements.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_python_ncloc_measurements.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_candidate_eligibility.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_per_treatment_ranking.csv"
    "${OUTPUT_DIR}/${OUTPUT_PREFIX}_common_donor_ranking.csv"
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
  echo "Snapshot restoration:      ${OUTPUT_DIR}/${OUTPUT_PREFIX}_python_ncloc_snapshot_restoration.csv"
  echo "Target NCLOC measurements: ${OUTPUT_DIR}/${OUTPUT_PREFIX}_target_python_ncloc_measurements.csv"
  echo "Candidate eligibility:     ${OUTPUT_DIR}/${OUTPUT_PREFIX}_candidate_eligibility.csv"
  echo "Per-treatment ranking:     ${OUTPUT_DIR}/${OUTPUT_PREFIX}_per_treatment_ranking.csv"
  echo "Common donor ranking:      ${OUTPUT_DIR}/${OUTPUT_PREFIX}_common_donor_ranking.csv"
  echo "Validation:                ${OUTPUT_DIR}/${OUTPUT_PREFIX}_validation.csv"
  echo "Summary:                   ${OUTPUT_DIR}/${OUTPUT_PREFIX}_summary.json"
  echo "Status:                    ${STATUS_FILE}"
  echo "Next step:                 review and freeze one donor before opening 2025-04/06 AGC outcomes"
  echo "================================================================================"
} 2>&1 | tee "${LOG_FILE}"

EXIT_CODE="${PIPESTATUS[0]}"
END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_FMT '%02d:%02d:%02d' \
  "$((ELAPSED / 3600))" \
  "$(((ELAPSED % 3600) / 60))" \
  "$((ELAPSED % 60))"

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
