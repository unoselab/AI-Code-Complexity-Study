#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1l: Build and summarize final matched Python DiD panels
# ============================================================
#
# Purpose:
#   1. Build flexible and strict matched Python DiD panels.
#   2. Build window-driven versions of both panels.
#   3. Summarize the panels and compare them with paper counts.
#
# Reused Python scripts:
#   proc_scripts/prepare_panel_event_v2.py
#   proc_scripts/summarize_matched_panels.py
#
# Main outputs:
#   repo_python/run-py-1l/panel_event_matched_flexible.csv
#   repo_python/run-py-1l/panel_event_matched_flexible_window_driven.csv
#   repo_python/run-py-1l/panel_event_matched_strict.csv
#   repo_python/run-py-1l/panel_event_matched_strict_window_driven.csv
#
# Extra QC outputs:
#   repo_python/tmp/run-py-1l/qc/panel_qc_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_by_source.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_paper_comparison.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_attrition_summary.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_dropped_by_strict.csv
#   repo_python/tmp/run-py-1l/qc/panel_qc_notes.md
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are kept as provenance, not as pseudo-event assignments.
#   - Normalized time-series inputs are removed after the run by default.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_build_and_summarize_matched_panels_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"
SUMMARY_SCRIPT="${SUMMARY_SCRIPT:-proc_scripts/summarize_matched_panels.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"
QC_TMP_DIR="${QC_TMP_DIR:-${TMP_DIR}/qc}"
DID_DIR="${DID_DIR:-${MAIN_OUTPUT_DIR}}"
NORMALIZED_DIR="${NORMALIZED_DIR:-${TMP_DIR}/normalized_inputs_${RUN_TS}}"
KEEP_NORMALIZED_INPUTS="${KEEP_NORMALIZED_INPUTS:-false}"

resolve_single_input() {
  local pattern="$1"
  local label="$2"
  local matches=()

  mapfile -t matches < <(compgen -G "${pattern}" | sort)

  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one ${label} matching: ${pattern}" >&2
    if [[ "${#matches[@]}" -gt 0 ]]; then
      printf '  %s\n' "${matches[@]}" >&2
    fi
    exit 1
  fi

  printf '%s\n' "${matches[0]}"
}

TREATMENT_META_PATTERN="${OUTPUT_BASE_DIR}/run-py-1f/treatment_python_sample_main_[0-9]*.csv"
TREATMENT_MISSING_MATCHING_PATTERN="${OUTPUT_BASE_DIR}/tmp/run-py-1g/python_treatment_missing_matching_main_[0-9]*.csv"

TREATMENT_META="${TREATMENT_META:-$(resolve_single_input "${TREATMENT_META_PATTERN}" "treatment metadata file")}"
TREATMENT_MISSING_MATCHING="${TREATMENT_MISSING_MATCHING:-$(resolve_single_input "${TREATMENT_MISSING_MATCHING_PATTERN}" "missing-matching file")}"

MAIN_PAIRS_FILE="${MAIN_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean.csv}"
STRICT_PAIRS_FILE="${STRICT_PAIRS_FILE:-${OUTPUT_BASE_DIR}/run-py-1k/python_matched_control_pairs_main_final_clean_1to3_only.csv}"

TREATMENT_TS_RAW="${TREATMENT_TS_RAW:-${OUTPUT_BASE_DIR}/treatment_python_did/ts_repos_monthly.csv}"
CONTROL_TS_RAW="${CONTROL_TS_RAW:-${OUTPUT_BASE_DIR}/run-py-1k/ts_repos_monthly_final_clean.csv}"

TREATMENT_TS="${TREATMENT_TS:-${NORMALIZED_DIR}/treatment_ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-${NORMALIZED_DIR}/control_ts_repos_monthly.csv}"

MAIN_OUTPUT_FILE="${MAIN_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
MAIN_BALANCED_OUTPUT_FILE="${MAIN_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_OUTPUT_FILE="${STRICT_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
STRICT_BALANCED_OUTPUT_FILE="${STRICT_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

OUTPUT_SUMMARY="${OUTPUT_SUMMARY:-${QC_TMP_DIR}/panel_qc_summary.csv}"
OUTPUT_BY_SOURCE="${OUTPUT_BY_SOURCE:-${QC_TMP_DIR}/panel_qc_by_source.csv}"
OUTPUT_PAPER_COMPARISON="${OUTPUT_PAPER_COMPARISON:-${QC_TMP_DIR}/panel_qc_paper_comparison.csv}"
OUTPUT_ATTRITION="${OUTPUT_ATTRITION:-${QC_TMP_DIR}/panel_qc_attrition_summary.csv}"
OUTPUT_DROPPED_BY_STRICT="${OUTPUT_DROPPED_BY_STRICT:-${QC_TMP_DIR}/panel_qc_dropped_by_strict.csv}"
OUTPUT_NOTES="${OUTPUT_NOTES:-${QC_TMP_DIR}/panel_qc_notes.md}"

FINAL_COVERAGE="${FINAL_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean.csv}"
STRICT_COVERAGE="${STRICT_COVERAGE:-${OUTPUT_BASE_DIR}/tmp/run-py-1k/python_control_pair_coverage_main_final_clean_1to3_only.csv}"
FINAL_CONTROLS="${FINAL_CONTROLS:-${OUTPUT_BASE_DIR}/run-py-1k/python_control_clone_usable_repos_main_final_clean.csv}"

PAPER_TREATMENT_REPOS="${PAPER_TREATMENT_REPOS:-121}"
PAPER_CONTROL_REPOS="${PAPER_CONTROL_REPOS:-127}"
PAPER_TOTAL_OBSERVATIONS="${PAPER_TOTAL_OBSERVATIONS:-2461}"
PAPER_POST_TREATMENT_OBSERVATIONS="${PAPER_POST_TREATMENT_OBSERVATIONS:-582}"

cleanup_normalized_inputs() {
  if [[ "${KEEP_NORMALIZED_INPUTS}" != "true" ]]; then
    rm -rf "${NORMALIZED_DIR}"
  fi
}
trap cleanup_normalized_inputs EXIT

mkdir -p "${LOG_DIR}" "${DID_DIR}" "${QC_TMP_DIR}" "${NORMALIZED_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "${RUN_PREFIX}: build and summarize final matched Python DiD panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                         ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Script name:                       ${SCRIPT_NAME}" | tee -a "${LOG_FILE}"
echo "Run prefix:                        ${RUN_PREFIX}" | tee -a "${LOG_FILE}"
echo "Panel script:                      ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Summary script:                    ${SUMMARY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Main output dir:                   ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Extra QC dir:                      ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:                ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Treatment missing matching:        ${TREATMENT_MISSING_MATCHING}" | tee -a "${LOG_FILE}"
echo "Main pairs file:                   ${MAIN_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pairs file:             ${STRICT_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series raw:         ${TREATMENT_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Control time series raw:           ${CONTROL_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Flexible panel:                    ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:                      ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC output dir:                     ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "QC summary:                        ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison:                  ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:                          ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Keep normalized inputs:            ${KEEP_NORMALIZED_INPUTS}" | tee -a "${LOG_FILE}"
echo "Log file:                          ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${SUMMARY_SCRIPT}" \
  "${TREATMENT_META}" \
  "${TREATMENT_MISSING_MATCHING}" \
  "${MAIN_PAIRS_FILE}" \
  "${STRICT_PAIRS_FILE}" \
  "${TREATMENT_TS_RAW}" \
  "${CONTROL_TS_RAW}" \
  "${FINAL_COVERAGE}" \
  "${STRICT_COVERAGE}" \
  "${FINAL_CONTROLS}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Step 0: Compile Python scripts" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"
python -m py_compile "${PY_SCRIPT}" "${SUMMARY_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 1: Normalize time-series input columns" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

def normalize_ts(src_text, dst_text, label):
    src = Path(src_text)
    dst = Path(dst_text)
    df = pd.read_csv(src)

    if "repo_name" not in df.columns:
        raise SystemExit(f"ERROR: {label} is missing repo_name column: {src}")

    # prepare_panel_event_v2.py expects a month column in the JS/TS wrapper.
    # Some analyzer versions write time instead of month, so create month safely.
    if "month" not in df.columns:
        if "time" in df.columns:
            df["month"] = df["time"].astype(str).str[:7]
        else:
            raise SystemExit(
                f"ERROR: {label} must contain either month or time column. "
                f"Columns: {list(df.columns)}"
            )

    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["month"] = df["month"].astype(str).str.strip().str[:7]

    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False)

    print(f"{label}:")
    print(f"  input:  {src}")
    print(f"  output: {dst}")
    print(f"  rows:   {len(df)}")
    print(f"  repos:  {df['repo_name'].nunique()}")
    print(f"  month range: {df['month'].min()} to {df['month'].max()}")
    print(f"  columns: {list(df.columns)}")
    print()

normalize_ts("${TREATMENT_TS_RAW}", "${TREATMENT_TS}", "treatment_ts")
normalize_ts("${CONTROL_TS_RAW}", "${CONTROL_TS}", "control_ts")
PY

echo | tee -a "${LOG_FILE}"
echo "** Step 2: Check input schemas" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

files = {
    "treatment_meta": Path("${TREATMENT_META}"),
    "main_pairs": Path("${MAIN_PAIRS_FILE}"),
    "strict_pairs": Path("${STRICT_PAIRS_FILE}"),
    "treatment_ts": Path("${TREATMENT_TS}"),
    "control_ts": Path("${CONTROL_TS}"),
}

required = {
    "treatment_meta": {"repo_name", "event_month"},
    "main_pairs": {"treatment_repo", "control_repo"},
    "strict_pairs": {"treatment_repo", "control_repo"},
    "treatment_ts": {"repo_name", "month"},
    "control_ts": {"repo_name", "month"},
}

for name, path in files.items():
    cols = set(pd.read_csv(path, nrows=0).columns)
    missing = required[name] - cols
    print(f"{name}: {path}")
    print("  required:", sorted(required[name]))
    print("  columns:", sorted(cols))
    if missing:
        raise SystemExit(f"ERROR: {name} missing columns: {sorted(missing)}")
    print("  status: OK")
    print()

print("Schema check passed.")
PY

run_panel_builder() {
  local label="$1"
  local pairs_file="$2"
  local output_file="$3"
  local balanced_output_file="$4"

  echo | tee -a "${LOG_FILE}"
  echo "** Step 3: Build ${label} panel" | tee -a "${LOG_FILE}"
  echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

  CMD=(
    python "${PY_SCRIPT}"
    --treatment-meta "${TREATMENT_META}"
    --pairs "${pairs_file}"
    --treatment-ts "${TREATMENT_TS}"
    --control-ts "${CONTROL_TS}"
    --output "${output_file}"
    --balanced-output "${balanced_output_file}"
  )

  echo "${CMD[*]}" | tee -a "${LOG_FILE}"
  echo | tee -a "${LOG_FILE}"

  "${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"
}

run_panel_builder \
  "main final-clean" \
  "${MAIN_PAIRS_FILE}" \
  "${MAIN_OUTPUT_FILE}" \
  "${MAIN_BALANCED_OUTPUT_FILE}"

run_panel_builder \
  "strict 1:3 final-clean" \
  "${STRICT_PAIRS_FILE}" \
  "${STRICT_OUTPUT_FILE}" \
  "${STRICT_BALANCED_OUTPUT_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 4: Summarize matched panels" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

SUMMARY_CMD=(
  python "${SUMMARY_SCRIPT}"
  --flexible-panel "${MAIN_OUTPUT_FILE}"
  --strict-panel "${STRICT_OUTPUT_FILE}"
  --flexible-window-driven-panel "${MAIN_BALANCED_OUTPUT_FILE}"
  --strict-window-driven-panel "${STRICT_BALANCED_OUTPUT_FILE}"
  --output-summary "${OUTPUT_SUMMARY}"
  --output-by-source "${OUTPUT_BY_SOURCE}"
  --output-paper-comparison "${OUTPUT_PAPER_COMPARISON}"
  --output-attrition "${OUTPUT_ATTRITION}"
  --output-dropped-by-strict "${OUTPUT_DROPPED_BY_STRICT}"
  --output-notes "${OUTPUT_NOTES}"
  --treatment-sample "${TREATMENT_META}"
  --treatment-missing-matching "${TREATMENT_MISSING_MATCHING}"
  --final-coverage "${FINAL_COVERAGE}"
  --strict-coverage "${STRICT_COVERAGE}"
  --final-controls "${FINAL_CONTROLS}"
  --paper-treatment-repos "${PAPER_TREATMENT_REPOS}"
  --paper-control-repos "${PAPER_CONTROL_REPOS}"
  --paper-total-observations "${PAPER_TOTAL_OBSERVATIONS}"
  --paper-post-treatment-observations "${PAPER_POST_TREATMENT_OBSERVATIONS}"
)

echo "${SUMMARY_CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"
"${SUMMARY_CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Step 5: Output file check" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

for f in \
  "${MAIN_OUTPUT_FILE}" \
  "${MAIN_BALANCED_OUTPUT_FILE}" \
  "${STRICT_OUTPUT_FILE}" \
  "${STRICT_BALANCED_OUTPUT_FILE}" \
  "${OUTPUT_SUMMARY}" \
  "${OUTPUT_PAPER_COMPARISON}" \
  "${OUTPUT_NOTES}" \
  "${OUTPUT_BY_SOURCE}" \
  "${OUTPUT_ATTRITION}" \
  "${OUTPUT_DROPPED_BY_STRICT}"
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
echo "${RUN_PREFIX} completed successfully." | tee -a "${LOG_FILE}"
echo "Flexible panel:   ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict panel:     ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "QC summary:       ${OUTPUT_SUMMARY}" | tee -a "${LOG_FILE}"
echo "Paper comparison: ${OUTPUT_PAPER_COMPARISON}" | tee -a "${LOG_FILE}"
echo "QC notes:         ${OUTPUT_NOTES}" | tee -a "${LOG_FILE}"
echo "Main output dir:  ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "QC output dir:    ${QC_TMP_DIR}" | tee -a "${LOG_FILE}"
echo "Log file:         ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e-build-jsts-matched-panel.sh,
# and run8e2-summarize-jsts-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.