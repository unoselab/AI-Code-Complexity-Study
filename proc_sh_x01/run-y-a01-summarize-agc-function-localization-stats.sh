#!/usr/bin/env bash

set -euo pipefail

PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/summarize_agc_function_localization_stats-v1.py}"

python "${PY_SCRIPT}" \
  --a05-code-manifest ../../detect_code_gpt/output/snapshot_npr/run-x-a05/python_code_unit_manifest.csv \
  --a11-results-root ../../detect_code_gpt/output/snapshot_npr/run-x-a11/results \
  --a13-reuse-file ../../detect_code_gpt/output/snapshot_npr/run-x-a13/python_cfun_reuse_from_a11.csv \
  --a14-results-root ../../detect_code_gpt/output/snapshot_npr/run-x-a14/results \
  --ml-i06-summary repo_x01/run-x-i06/summary.json

