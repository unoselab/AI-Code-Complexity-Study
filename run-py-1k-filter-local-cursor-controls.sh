#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1k: Filter controls with local Cursor evidence
# ============================================================
#
# Purpose:
#   Remove clone-usable control repositories that contain local Cursor
#   evidence within the analysis window and recompute final matched
#   control-pair coverage.
#
# Input:
#   repo_python/control_clone_usable_repos_main.csv
#   repo_python/matched_control_pairs_main_clone_usable.csv
#   repo_python/control_did/ai_adoption_dates.csv
#   repo_python/control_did/ts_repos_monthly.csv
#   repo_python/control_did/ts_contributors_monthly.csv
#
# Outputs:
#   repo_python/control_local_cursor_evidence_in_window.csv
#   repo_python/control_local_cursor_evidence_post_window.csv
#   repo_python/control_clone_usable_repos_main_final_clean.csv
#   repo_python/matched_control_pairs_main_final_clean.csv
#   repo_python/matched_control_pairs_main_local_cursor_dropped.csv
#   repo_python/control_pair_coverage_main_final_clean.csv
#   repo_python/treatment_lost_all_controls_main_final_clean.csv
#   repo_python/control_local_cursor_filter_summary_main.csv
#   repo_python/matched_control_pairs_main_final_clean_1to3_only.csv
#   repo_python/control_pair_coverage_main_final_clean_1to3_only.csv
#   repo_python/control_did/ts_repos_monthly_final_clean.csv
#   repo_python/control_did/ts_contributors_monthly_final_clean.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1k_filter_local_cursor_controls_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/filter_controls_by_local_cursor_evidence.py}"

ANALYSIS_END="${ANALYSIS_END:-2025-08}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
CONTROL_OUTPUT_DIR="${CONTROL_OUTPUT_DIR:-${OUTPUT_DIR}/control_did}"

CONTROL_FILE="${CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main.csv}"
PAIR_FILE="${PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_clone_usable.csv}"
ADOPTION_FILE="${ADOPTION_FILE:-${CONTROL_OUTPUT_DIR}/ai_adoption_dates.csv}"

CONTROL_TS_REPOS_FILE="${CONTROL_TS_REPOS_FILE:-${CONTROL_OUTPUT_DIR}/ts_repos_monthly.csv}"
CONTROL_TS_CONTRIBUTORS_FILE="${CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_OUTPUT_DIR}/ts_contributors_monthly.csv}"

IN_WINDOW_EVIDENCE_FILE="${IN_WINDOW_EVIDENCE_FILE:-${OUTPUT_DIR}/control_local_cursor_evidence_in_window.csv}"
POST_WINDOW_EVIDENCE_FILE="${POST_WINDOW_EVIDENCE_FILE:-${OUTPUT_DIR}/control_local_cursor_evidence_post_window.csv}"

FINAL_CONTROL_FILE="${FINAL_CONTROL_FILE:-${OUTPUT_DIR}/control_clone_usable_repos_main_final_clean.csv}"
FINAL_PAIR_FILE="${FINAL_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean.csv}"
DROPPED_PAIR_FILE="${DROPPED_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_local_cursor_dropped.csv}"
COVERAGE_FILE="${COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_final_clean.csv}"
ZERO_CONTROL_TREATMENT_FILE="${ZERO_CONTROL_TREATMENT_FILE:-${OUTPUT_DIR}/treatment_lost_all_controls_main_final_clean.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/control_local_cursor_filter_summary_main.csv}"

STRICT_1TO3_PAIR_FILE="${STRICT_1TO3_PAIR_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean_1to3_only.csv}"
STRICT_1TO3_COVERAGE_FILE="${STRICT_1TO3_COVERAGE_FILE:-${OUTPUT_DIR}/control_pair_coverage_main_final_clean_1to3_only.csv}"

FINAL_CONTROL_TS_REPOS_FILE="${FINAL_CONTROL_TS_REPOS_FILE:-${CONTROL_OUTPUT_DIR}/ts_repos_monthly_final_clean.csv}"
FINAL_CONTROL_TS_CONTRIBUTORS_FILE="${FINAL_CONTROL_TS_CONTRIBUTORS_FILE:-${CONTROL_OUTPUT_DIR}/ts_contributors_monthly_final_clean.csv}"

FAIL_IF_ZERO_CONTROL="${FAIL_IF_ZERO_CONTROL:-true}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}" "${CONTROL_OUTPUT_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1k: filter controls with local Cursor evidence" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                     ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Analysis end:                      ${ANALYSIS_END}" | tee -a "${LOG_FILE}"
echo "Control file:                      ${CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Pair file:                         ${PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Adoption file:                     ${ADOPTION_FILE}" | tee -a "${LOG_FILE}"
echo "Control repo time-series file:     ${CONTROL_TS_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Control contributor time-series:   ${CONTROL_TS_CONTRIBUTORS_FILE}" | tee -a "${LOG_FILE}"
echo "Final control file:                ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file:                   ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file:               ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pair file:              ${STRICT_1TO3_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 coverage file:          ${STRICT_1TO3_COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Final control repo time-series:    ${FINAL_CONTROL_TS_REPOS_FILE}" | tee -a "${LOG_FILE}"
echo "Final control contributor series:  ${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file:                      ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Fail if zero control:              ${FAIL_IF_ZERO_CONTROL}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${CONTROL_FILE}" \
  "${PAIR_FILE}" \
  "${ADOPTION_FILE}" \
  "${CONTROL_TS_REPOS_FILE}" \
  "${CONTROL_TS_CONTRIBUTORS_FILE}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

CMD=(
  python "${PY_SCRIPT}"
  --analysis-end "${ANALYSIS_END}"
  --control-file "${CONTROL_FILE}"
  --pair-file "${PAIR_FILE}"
  --adoption-file "${ADOPTION_FILE}"
  --control-ts-repos-file "${CONTROL_TS_REPOS_FILE}"
  --control-ts-contributors-file "${CONTROL_TS_CONTRIBUTORS_FILE}"
  --in-window-evidence-file "${IN_WINDOW_EVIDENCE_FILE}"
  --post-window-evidence-file "${POST_WINDOW_EVIDENCE_FILE}"
  --final-control-file "${FINAL_CONTROL_FILE}"
  --final-pair-file "${FINAL_PAIR_FILE}"
  --dropped-pair-file "${DROPPED_PAIR_FILE}"
  --coverage-file "${COVERAGE_FILE}"
  --zero-control-treatment-file "${ZERO_CONTROL_TREATMENT_FILE}"
  --summary-file "${SUMMARY_FILE}"
  --strict-1to3-pair-file "${STRICT_1TO3_PAIR_FILE}"
  --strict-1to3-coverage-file "${STRICT_1TO3_COVERAGE_FILE}"
  --final-control-ts-repos-file "${FINAL_CONTROL_TS_REPOS_FILE}"
  --final-control-ts-contributors-file "${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}"
)

if [[ "${FAIL_IF_ZERO_CONTROL}" == "true" ]]; then
  CMD+=(--fail-if-zero-control)
fi

echo "** Running local Cursor evidence filter" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${IN_WINDOW_EVIDENCE_FILE}" \
  "${POST_WINDOW_EVIDENCE_FILE}" \
  "${FINAL_CONTROL_FILE}" \
  "${FINAL_PAIR_FILE}" \
  "${DROPPED_PAIR_FILE}" \
  "${COVERAGE_FILE}" \
  "${ZERO_CONTROL_TREATMENT_FILE}" \
  "${SUMMARY_FILE}" \
  "${STRICT_1TO3_PAIR_FILE}" \
  "${STRICT_1TO3_COVERAGE_FILE}" \
  "${FINAL_CONTROL_TS_REPOS_FILE}" \
  "${FINAL_CONTROL_TS_CONTRIBUTORS_FILE}"
do
  if [[ -f "${f}" ]]; then
    echo "Command: wc -l ${f}" | tee -a "${LOG_FILE}"
    wc -l "${f}" | tee -a "${LOG_FILE}"
  else
    echo "MISSING: ${f}" | tee -a "${LOG_FILE}"
  fi
done

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1k completed successfully." | tee -a "${LOG_FILE}"
echo "Final control file: ${FINAL_CONTROL_FILE}" | tee -a "${LOG_FILE}"
echo "Final pair file: ${FINAL_PAIR_FILE}" | tee -a "${LOG_FILE}"
echo "Final coverage file: ${COVERAGE_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
# This wrapper is adapted from the logic of run8d2-filter-local-cursor-controls.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
