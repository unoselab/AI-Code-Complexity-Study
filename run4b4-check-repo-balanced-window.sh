#!/usr/bin/env bash
set -euo pipefail

INPUT_FILE="${INPUT_FILE:-tmp_typescript_test/data/ai_adopt_repo_typescript_candidates.csv}"
OUTPUT_FILE="${OUTPUT_FILE:-tmp_typescript_test/data/ai_adopt_repo_typescript_candidates_bw6.csv}"
MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"
LANGUAGE="${LANGUAGE:-TypeScript}"
TOP_PRINT="${TOP_PRINT:-50}"

python proc_scripts/check_repo_balanced_window.py \
  --input-file "${INPUT_FILE}" \
  --output-file "${OUTPUT_FILE}" \
  --min-balanced-window "${MIN_BALANCED_WINDOW}" \
  --language "${LANGUAGE}" \
  --top-print "${TOP_PRINT}"
