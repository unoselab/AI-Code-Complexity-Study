#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-data_baseline_backup}"
DATASET_SOURCE="${DATASET_SOURCE:-treatment}"
GROUP_NAME="${GROUP_NAME:-JavaScript_TypeScript}"

OUTPUT_FILE="${OUTPUT_FILE:-tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv}"
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-tmp_jsts_test/data/original_paper_treatment_jsts_repos_bw6.csv}"

MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"
TOP_PRINT="${TOP_PRINT:-30}"

python proc_scripts/count_repo_lang.py \
  --data-dir "${DATA_DIR}" \
  --dataset-source "${DATASET_SOURCE}" \
  --languages TypeScript JavaScript \
  --group-name "${GROUP_NAME}" \
  --output-file "${OUTPUT_FILE}" \
  --window-output-file "${WINDOW_OUTPUT_FILE}" \
  --min-balanced-window "${MIN_BALANCED_WINDOW}" \
  --top-print "${TOP_PRINT}"
