#!/usr/bin/env bash
set -euo pipefail

# Run regular module-function NPR token-range diagnostics.
#
# Inputs:
#   - Frozen run-py-7a NPR event and body classifications
#   - Strict matched repository-month panel
#   - Treatment adoption metadata
#   - Strict 1:3 treatment-control pair manifest
#
# Outputs:
#   repo_python/run-py-7d/strict/specifications/range100_200/
#   regular_module_function_token_ranges/

python proc_scripts/analyze_regular_module_function_npr_token_ranges.py \
  --treatment-meta repo_python/run-py-1f/treatment_python_sample_main_118.csv \
  --matched-pairs repo_python/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv \
  --overwrite-output
