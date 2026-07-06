#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-1l: Build final matched Python DiD event panels
# ============================================================
#
# Purpose:
#   Build final matched DiD panels for the Python experiment.
#
# Reused Python script:
#   proc_scripts/prepare_panel_event_v2.py
#
# Inputs:
#   1. Treatment metadata with event_month:
#        repo_python/treatment_sample_main.csv
#
#   2. Final clean treatment-control matched pairs:
#        repo_python/matched_control_pairs_main_final_clean.csv
#
#   3. Strict 1:3 final clean treatment-control matched pairs:
#        repo_python/matched_control_pairs_main_final_clean_1to3_only.csv
#
#   4. Treatment monthly git-history time series:
#        repo_python/treatment_python_did/ts_repos_monthly.csv
#
#   5. Final clean control monthly git-history time series:
#        repo_python/control_did/ts_repos_monthly_final_clean.csv
#
# Outputs:
#   Main final-clean panels:
#        repo_python/did_final/panel_event_matched_flexible.csv
#        repo_python/did_final/panel_event_matched_flexible_window_driven.csv
#
#   Strict 1:3 final-clean panels:
#        repo_python/did_final/panel_event_matched_strict.csv
#        repo_python/did_final/panel_event_matched_strict_window_driven.csv
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are kept as provenance, not as pseudo-event assignments.
#   - The balanced panel is window-completed by the panel builder.
#   - This wrapper normalizes time-series columns if the analyzer writes
#     "time" instead of "month".
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-1l_build_matched_panel_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_python}"
DID_DIR="${DID_DIR:-${OUTPUT_DIR}/did_final}"
NORMALIZED_DIR="${NORMALIZED_DIR:-${DID_DIR}/_normalized_inputs_${RUN_TS}}"

TREATMENT_META="${TREATMENT_META:-${OUTPUT_DIR}/treatment_sample_main.csv}"

MAIN_PAIRS_FILE="${MAIN_PAIRS_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean.csv}"
STRICT_PAIRS_FILE="${STRICT_PAIRS_FILE:-${OUTPUT_DIR}/matched_control_pairs_main_final_clean_1to3_only.csv}"

TREATMENT_TS_RAW="${TREATMENT_TS_RAW:-${OUTPUT_DIR}/treatment_python_did/ts_repos_monthly.csv}"
CONTROL_TS_RAW="${CONTROL_TS_RAW:-${OUTPUT_DIR}/control_did/ts_repos_monthly_final_clean.csv}"

TREATMENT_TS="${TREATMENT_TS:-${NORMALIZED_DIR}/treatment_ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-${NORMALIZED_DIR}/control_ts_repos_monthly.csv}"

MAIN_OUTPUT_FILE="${MAIN_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible.csv}"
MAIN_BALANCED_OUTPUT_FILE="${MAIN_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"

STRICT_OUTPUT_FILE="${STRICT_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict.csv}"
STRICT_BALANCED_OUTPUT_FILE="${STRICT_BALANCED_OUTPUT_FILE:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

mkdir -p "${LOG_DIR}" "${DID_DIR}" "${NORMALIZED_DIR}"

echo "============================================================" | tee "${LOG_FILE}"
echo "run-py-1l: build final matched Python DiD event panels" | tee -a "${LOG_FILE}"
echo "Timestamp:                    ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:                ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:           ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Main pairs file:              ${MAIN_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Strict 1:3 pairs file:        ${STRICT_PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series raw:    ${TREATMENT_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Control time series raw:      ${CONTROL_TS_RAW}" | tee -a "${LOG_FILE}"
echo "Treatment time series norm:   ${TREATMENT_TS}" | tee -a "${LOG_FILE}"
echo "Control time series norm:     ${CONTROL_TS}" | tee -a "${LOG_FILE}"
echo "DID output dir:               ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Main output:                  ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Main balanced output:         ${MAIN_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict output:                ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict balanced output:       ${STRICT_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:                     ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in \
  "${PY_SCRIPT}" \
  "${TREATMENT_META}" \
  "${MAIN_PAIRS_FILE}" \
  "${STRICT_PAIRS_FILE}" \
  "${TREATMENT_TS_RAW}" \
  "${CONTROL_TS_RAW}"
do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Step 0: Normalize time-series input columns" | tee -a "${LOG_FILE}"
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

echo "** Step 1: Check input schemas" | tee -a "${LOG_FILE}"
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
  echo "** Step 2: Build ${label} panel" | tee -a "${LOG_FILE}"
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
echo "** Output summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

outputs = [
    ("main_unbalanced", Path("${MAIN_OUTPUT_FILE}")),
    ("main_balanced", Path("${MAIN_BALANCED_OUTPUT_FILE}")),
    ("strict_1to3_unbalanced", Path("${STRICT_OUTPUT_FILE}")),
    ("strict_1to3_balanced", Path("${STRICT_BALANCED_OUTPUT_FILE}")),
]

for label, path in outputs:
    if not path.exists():
        print(f"MISSING: {label}: {path}")
        continue

    df = pd.read_csv(path)

    print(f"{label}: {path}")
    print("  rows:", len(df))
    print("  repos:", df["repo_name"].nunique() if "repo_name" in df.columns else "(missing repo_name)")

    if "ever_treated" in df.columns:
        print("  treated repos:", df.loc[df["ever_treated"].eq(1), "repo_name"].nunique())
        print("  control repos:", df.loc[df["ever_treated"].eq(0), "repo_name"].nunique())

    if "dataset_source" in df.columns:
        print("  dataset_source counts:")
        print(df["dataset_source"].value_counts(dropna=False).to_string())

    if "time" in df.columns:
        print("  time range:", df["time"].min(), "to", df["time"].max())
    elif "month" in df.columns:
        print("  month range:", df["month"].min(), "to", df["month"].max())

    print()
PY

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run-py-1l completed successfully." | tee -a "${LOG_FILE}"
echo "DID output dir: ${DID_DIR}" | tee -a "${LOG_FILE}"
echo "Main output: ${MAIN_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Main balanced output: ${MAIN_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict output: ${STRICT_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Strict balanced output: ${STRICT_BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run8e-build-jsts-matched-panel.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
