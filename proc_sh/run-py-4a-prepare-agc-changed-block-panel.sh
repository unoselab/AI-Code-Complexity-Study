#!/usr/bin/env bash
# Prepare repository-month AGC outcomes for newly added or modified blocks.
#
# Inputs:
#   - Monthly Python snapshot manifest and snapshot files from run-py-3a.
#   - Validated AGC DiD panel from run-py-3b.
#   - PASS input-check summary created by check_agc_changed_block_inputs.py.
#   - Existing treatment/control block predictions from the AGC detector.
#   - Treatment/control Git clones containing the historical commits.
#
# Outputs:
#   - Final strict panel with changed-block AGC outcomes.
#   - Repository-month changed-block outcome table.
#   - Block-level change classifications.
#   - QC summary, checks, pair diagnostics, and mismatch/error files.
# 
# Usage: 
#   bash run-py-4a-prepare-agc-changed-block-panel.sh
#
# Run this wrapper from a Python environment that provides pandas and
# tree_sitter. The wrapper does not activate or modify a Conda environment.

set -euo pipefail

PANEL_VARIANT="${PANEL_VARIANT:-strict}"
PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/prepare_agc_changed_block_panel.py}"

MANIFEST="${MANIFEST:-repo_python/run-py-3a/${PANEL_VARIANT}/repo_month_snapshot_manifest.csv}"
BASE_PANEL="${BASE_PANEL:-repo_python/run-py-3b/${PANEL_VARIANT}/panel_event_monthly_agc_py.csv}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-repo_python/run-py-3a/${PANEL_VARIANT}/python_snapshots}"

DETECTOR_PROFILE="${DETECTOR_PROFILE:-codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast}"
DETECTOR_ROOT="${DETECTOR_ROOT:-../python_snapshots_detect/${DETECTOR_PROFILE}/${PANEL_VARIANT}}"
INPUT_CHECK_SUMMARY="${INPUT_CHECK_SUMMARY:-repo_python/tmp/run-py-4a-input-check/${PANEL_VARIANT}/agc_changed_block_input_check_summary.json}"

TREE_SITTER_LIB="${TREE_SITTER_LIB:-../../ai_detector/src/code-analyzer-tree-sitter/build/my-languages.so}"
AST_HELPER_DIR="${AST_HELPER_DIR:-../../ai_detector/src/code-analyzer-tree-sitter}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-4a/${PANEL_VARIANT}}"
QC_DIR="${QC_DIR:-repo_python/tmp/run-py-4a/${PANEL_VARIANT}}"
LOG_DIR="${LOG_DIR:-logs}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-py-4a_prepare_agc_changed_block_panel_${PANEL_VARIANT}_${TIMESTAMP}.log"
START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "$path" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
        exit 1
    fi
}

require_dir() {
    local path="$1"
    local label="$2"
    if [[ ! -d "$path" ]]; then
        echo "ERROR: Missing ${label}: ${path}" >&2
        exit 1
    fi
}

require_file "$PYTHON_SCRIPT" "Python script"
require_file "$MANIFEST" "snapshot manifest"
require_file "$BASE_PANEL" "base AGC DiD panel"
require_file "$INPUT_CHECK_SUMMARY" "changed-block input-check summary"
require_file "$TREE_SITTER_LIB" "tree-sitter library"
require_file "${DETECTOR_ROOT}/block_predictions_treatment.csv" "treatment block predictions"
require_file "${DETECTOR_ROOT}/block_predictions_control.csv" "control block predictions"
require_dir "$SNAPSHOT_ROOT" "snapshot root"
require_dir "$AST_HELPER_DIR" "AST helper directory"
require_dir "$TREATMENT_CLONE_DIR" "treatment clone directory"
require_dir "$CONTROL_CLONE_DIR" "control clone directory"

mkdir -p "$OUTPUT_DIR" "$QC_DIR" "$LOG_DIR"

cat <<EOF
============================================================
run-py-4a: prepare AGC changed-block repository-month panel
Started:                  ${START_TEXT}
Panel variant:            ${PANEL_VARIANT}
Conda environment:        ${CONDA_DEFAULT_ENV:-<none>}
Python:                   ${PYTHON_BIN}
Python script:            ${PYTHON_SCRIPT}
Snapshot manifest:        ${MANIFEST}
Base panel:               ${BASE_PANEL}
Snapshot root:            ${SNAPSHOT_ROOT}
Detector root:            ${DETECTOR_ROOT}
Input-check summary:      ${INPUT_CHECK_SUMMARY}
Treatment clones:         ${TREATMENT_CLONE_DIR}
Control clones:           ${CONTROL_CLONE_DIR}
Output directory:         ${OUTPUT_DIR}
QC directory:             ${QC_DIR}
Log file:                 ${LOG_FILE}
============================================================
EOF

"$PYTHON_BIN" "$PYTHON_SCRIPT" \
    --manifest "$MANIFEST" \
    --base-panel "$BASE_PANEL" \
    --snapshot-root "$SNAPSHOT_ROOT" \
    --detector-root "$DETECTOR_ROOT" \
    --input-check-summary "$INPUT_CHECK_SUMMARY" \
    --tree-sitter-lib "$TREE_SITTER_LIB" \
    --ast-helper-dir "$AST_HELPER_DIR" \
    --treatment-clone-dir "$TREATMENT_CLONE_DIR" \
    --control-clone-dir "$CONTROL_CLONE_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --qc-dir "$QC_DIR" \
    2>&1 | tee "$LOG_FILE"

REQUIRED_OUTPUTS=(
    "${OUTPUT_DIR}/panel_event_monthly_agc_changed_block_py.csv"
    "${OUTPUT_DIR}/repo_month_agc_changed_block_outcomes_py.csv"
    "${OUTPUT_DIR}/changed_block_classifications_py.csv"
    "${QC_DIR}/agc_changed_block_prepare_summary.json"
    "${QC_DIR}/agc_changed_block_prepare_checks.csv"
    "${QC_DIR}/agc_changed_block_pair_qc.csv"
    "${QC_DIR}/agc_changed_block_prediction_mismatches.csv"
    "${QC_DIR}/agc_changed_block_errors.csv"
)

for output_path in "${REQUIRED_OUTPUTS[@]}"; do
    require_file "$output_path" "required output"
done

END_EPOCH="$(date +%s)"
ELAPSED_SECONDS="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_TEXT '%02d:%02d:%02d' \
    "$((ELAPSED_SECONDS / 3600))" \
    "$(((ELAPSED_SECONDS % 3600) / 60))" \
    "$((ELAPSED_SECONDS % 60))"

cat <<EOF

============================================================
run-py-4a completed successfully.
Completed:                $(date)
Elapsed:                  ${ELAPSED_TEXT}
Output panel:             ${OUTPUT_DIR}/panel_event_monthly_agc_changed_block_py.csv
Outcome table:            ${OUTPUT_DIR}/repo_month_agc_changed_block_outcomes_py.csv
Block classifications:    ${OUTPUT_DIR}/changed_block_classifications_py.csv
Validation summary:       ${QC_DIR}/agc_changed_block_prepare_summary.json
Log file:                 ${LOG_FILE}
============================================================
EOF
