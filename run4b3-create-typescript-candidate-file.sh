#!/usr/bin/env bash
set -euo pipefail

INPUT_FILE="${INPUT_FILE:-tmp_typescript_test/data/top_typescript_clone_candidates_all_eligible.csv}"
OUTPUT_FILE="${OUTPUT_FILE:-tmp_typescript_test/data/ai_adopt_repo_typescript_candidates.csv}"
LANGUAGE="${LANGUAGE:-TypeScript}"

python proc_scripts/create-lang-candidate-file.py \
  --input-file "${INPUT_FILE}" \
  --output-file "${OUTPUT_FILE}" \
  --language "${LANGUAGE}" \
  --top-print 50
