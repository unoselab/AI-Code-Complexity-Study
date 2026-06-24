#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8a_extract_jsts_control_repos_${RUN_TS}.log}"

TREATMENT_SAMPLE_FILE="${TREATMENT_SAMPLE_FILE:-tmp_jsts_test/data/jsts_treatment_sample_main_398.csv}"
MATCHING_FILE="${MATCHING_FILE:-data_baseline_backup/matching.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_jsts_test/data}"

PAIR_OUTPUT_FILE="${PAIR_OUTPUT_FILE:-${OUTPUT_DIR}/jsts_matched_control_pairs_main_398.csv}"
CONTROL_CLONE_FILE="${CONTROL_CLONE_FILE:-${OUTPUT_DIR}/jsts_control_repos_to_clone_main_398.csv}"
MISSING_MATCH_FILE="${MISSING_MATCH_FILE:-${OUTPUT_DIR}/jsts_treatment_missing_matching_main_398.csv}"
SUMMARY_FILE="${SUMMARY_FILE:-${OUTPUT_DIR}/jsts_control_extract_summary_main_398.csv}"

TOP_PRINT="${TOP_PRINT:-30}"

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

echo "run8a: extract matched JS/TS control repositories" | tee "${LOG_FILE}"
echo "Timestamp: ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Treatment sample: ${TREATMENT_SAMPLE_FILE}" | tee -a "${LOG_FILE}"
echo "Matching file: ${MATCHING_FILE}" | tee -a "${LOG_FILE}"
echo "Output dir: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

set +e
python proc_scripts/extract-jsts-control-repos.py \
  --treatment-sample-file "${TREATMENT_SAMPLE_FILE}" \
  --matching-file "${MATCHING_FILE}" \
  --pair-output-file "${PAIR_OUTPUT_FILE}" \
  --control-clone-file "${CONTROL_CLONE_FILE}" \
  --missing-match-file "${MISSING_MATCH_FILE}" \
  --summary-file "${SUMMARY_FILE}" \
  --top-print "${TOP_PRINT}" \
  2>&1 | tee -a "${LOG_FILE}"
run_status=${PIPESTATUS[0]}
set -e

echo | tee -a "${LOG_FILE}"
echo "run8a finished with exit code: ${run_status}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Pair output file: ${PAIR_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Control clone file: ${CONTROL_CLONE_FILE}" | tee -a "${LOG_FILE}"
echo "Missing match file: ${MISSING_MATCH_FILE}" | tee -a "${LOG_FILE}"
echo "Summary file: ${SUMMARY_FILE}" | tee -a "${LOG_FILE}"

exit "${run_status}"
