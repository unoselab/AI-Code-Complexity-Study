#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1a: Count Python Cursor-adopting treatment repositories
# ============================================================
# This wrapper is the Python version of run7a-count-repo.sh.
#
# Goal:
#   Prepare the first Python treatment-repository input file for
#   reproducing the paper's language-specific Appendix result.
#
# Main purpose:
#   1. Read the paper baseline panel and repository metadata.
#   2. Count treatment repositories by primary language.
#   3. Extract Python treatment repositories.
#   4. Save the full Python treatment sample for the unbalanced-panel pipeline.
#   5. Also save a balanced-window >= K subset for diagnostics/robustness only.
#
# Why main sample is primary:
#   The paper uses an unbalanced panel. Therefore, the full Python
#   treatment sample should be used as the primary sample. The bw6
#   output is stricter and should be used only as a diagnostic or
#   robustness sample.
#
# Paper-replication logic:
#   - Primary language: Python
#   - Dataset source: treatment
#   - Main sample: all Python treatment repos found in the baseline panel
#   - Diagnostic sample: Python treatment repos with balanced_window >= 6
#
# Required input files:
#   DATA_DIR/panel_event_monthly.csv
#     - Monthly panel file from the paper-replication dataset.
#     - Used to identify treatment repositories and event-window coverage.
#
#   DATA_DIR/repos.csv
#     - Repository metadata file.
#     - Used to attach repo_primary_language and other repo-level metadata.
#
# Output files:
#   repo_python/treatment_python_repos.csv
#     - Primary Python treatment repository file.
#     - This should be used for the unbalanced-panel Python replication.
#
#   repo_python/treatment_python_repos_bw6.csv
#     - Diagnostic/robustness Python treatment repository file.
#     - Includes only repos with balanced_window >= MIN_BALANCED_WINDOW.
#     - Do not use this as the primary paper-replication sample.
#
# Typical usage:
#   bash run-py-1a-count-repo.sh
#
# Optional override examples:
#   MIN_BALANCED_WINDOW=5 bash run-py-1a-count-repo.sh
#
#   OUTPUT_DIR=repo_python_test \
#   bash run-py-1a-count-repo.sh
# ============================================================

# ------------------------------------------------------------
# Input dataset location
# ------------------------------------------------------------
# DATA_DIR should contain:
#   - panel_event_monthly.csv
#   - repos.csv
#
# In this project, data_baseline_backup is safer than data because it
# preserves the original baseline files used for replication.
DATA_DIR="${DATA_DIR:-data_baseline_backup}"

# We are extracting Cursor-adopting repositories, so dataset_source
# should be treatment.
DATASET_SOURCE="${DATASET_SOURCE:-treatment}"

# Human-readable group name printed by count_repo_lang.py.
GROUP_NAME="${GROUP_NAME:-Python}"

# ------------------------------------------------------------
# Output file locations
# ------------------------------------------------------------
# All Python-specific repository selection outputs are stored here.
OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"

# Primary output:
#   Full Python treatment sample.
#   Use this file for the main unbalanced-panel replication pipeline.
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos.csv}"

# Diagnostic output:
#   Python treatment sample restricted by balanced_window >= K.
#   Use this only for diagnostics or robustness checks.
WINDOW_OUTPUT_FILE="${WINDOW_OUTPUT_FILE:-${OUTPUT_DIR}/treatment_python_repos_bw6.csv}"

# ------------------------------------------------------------
# Event-window diagnostic setting
# ------------------------------------------------------------
# balanced_window is the minimum of available pre-event and post-event
# monthly observations. A value of 6 means the repo has at least 6 months
# before and 6 months after the event month in the panel.
#
# This should not define the primary sample because the paper uses an
# unbalanced panel.
MIN_BALANCED_WINDOW="${MIN_BALANCED_WINDOW:-6}"

# Number of rows printed by the Python script for quick inspection.
TOP_PRINT="${TOP_PRINT:-30}"

mkdir -p "${OUTPUT_DIR}"

echo "============================================================"
echo "run-py-1a: count Python Cursor-adopting treatment repositories"
echo "Data dir:                    ${DATA_DIR}"
echo "Dataset source:              ${DATASET_SOURCE}"
echo "Group name:                  ${GROUP_NAME}"
echo "Output dir:                  ${OUTPUT_DIR}"
echo "Primary output file:         ${OUTPUT_FILE}"
echo "BW${MIN_BALANCED_WINDOW} diagnostic output: ${WINDOW_OUTPUT_FILE}"
echo "Min balanced window:         ${MIN_BALANCED_WINDOW}"
echo "Top print:                   ${TOP_PRINT}"
echo "============================================================"
echo

# ------------------------------------------------------------
# Run language filtering and event-window summarization
# ------------------------------------------------------------
# count_repo_lang.py will:
#   1. Read DATA_DIR/panel_event_monthly.csv.
#   2. Extract unique treatment repositories.
#   3. Join repository metadata from DATA_DIR/repos.csv.
#   4. Filter repositories whose repo_primary_language is Python.
#   5. Save the full Python treatment file.
#   6. Save the balanced-window diagnostic subset.
python proc_scripts/count_repo_lang.py \
  --data-dir "${DATA_DIR}" \
  --dataset-source "${DATASET_SOURCE}" \
  --language Python \
  --group-name "${GROUP_NAME}" \
  --output-file "${OUTPUT_FILE}" \
  --window-output-file "${WINDOW_OUTPUT_FILE}" \
  --min-balanced-window "${MIN_BALANCED_WINDOW}" \
  --top-print "${TOP_PRINT}"

echo
echo "============================================================"
echo "run-py-1a output check"
echo "============================================================"

# ------------------------------------------------------------
# Check primary Python treatment file
# ------------------------------------------------------------
# wc -l includes the CSV header. Therefore:
#   actual repo rows = wc -l output - 1
echo
echo "===== Main Python treatment file ====="
echo "File: ${OUTPUT_FILE}"
echo "Command: wc -l ${OUTPUT_FILE}"
wc -l "${OUTPUT_FILE}"
echo
echo "Command: head ${OUTPUT_FILE}"
head "${OUTPUT_FILE}"

# ------------------------------------------------------------
# Check balanced-window diagnostic file
# ------------------------------------------------------------
# This file is useful to understand how many Python repos have enough
# symmetric pre/post observations, but it should not replace the main
# unbalanced-panel sample.
echo
echo "===== Balanced-window diagnostic Python file ====="
echo "File: ${WINDOW_OUTPUT_FILE}"
echo "Command: wc -l ${WINDOW_OUTPUT_FILE}"
wc -l "${WINDOW_OUTPUT_FILE}"
echo
echo "Command: head ${WINDOW_OUTPUT_FILE}"
head "${WINDOW_OUTPUT_FILE}"

echo
echo "============================================================"
echo "run-py-1a completed successfully."
echo "Primary file for Python unbalanced-panel pipeline:"
echo "  ${OUTPUT_FILE}"
echo "Diagnostic bw${MIN_BALANCED_WINDOW} file:"
echo "  ${WINDOW_OUTPUT_FILE}"
echo "============================================================"
