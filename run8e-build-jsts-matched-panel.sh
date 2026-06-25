#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run8e: Build final matched JS/TS DiD event panel
# ============================================================
# This wrapper reuses proc_scripts/prepare_panel_event_v2.py.
#
# Inputs:
#   1. Treatment metadata with event_month.
#   2. Final clean treatment-control matched pairs.
#   3. Treatment repository monthly git-history time series.
#   4. Final clean control repository monthly git-history time series.
#
# Outputs:
#   1. Unbalanced final matched DiD panel.
#   2. Balanced/window-completed final matched DiD panel.
#
# Notes:
#   - Controls remain never-treated units with event=NA.
#   - PSM pairs are retained as provenance, not as pseudo-event assignments.
#   - The balanced panel zero-fills missing repo-months inside the analysis window.
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run8e_build_jsts_matched_panel_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_panel_event_v2.py}"

TREATMENT_META="${TREATMENT_META:-tmp_jsts_test/data/jsts_treatment_sample_main_398.csv}"
PAIRS_FILE="${PAIRS_FILE:-tmp_jsts_test/data/jsts_matched_control_pairs_main_398_final_clean.csv}"
TREATMENT_TS="${TREATMENT_TS:-tmp_jsts_test/data/jsts_did_test/ts_repos_monthly.csv}"
CONTROL_TS="${CONTROL_TS:-tmp_jsts_test/data/jsts_did_control/ts_repos_monthly_final_clean.csv}"

OUTPUT_FILE="${OUTPUT_FILE:-tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean.csv}"
BALANCED_OUTPUT_FILE="${BALANCED_OUTPUT_FILE:-tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv}"

mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_FILE}")" "$(dirname "${BALANCED_OUTPUT_FILE}")"

echo "============================================================" | tee "${LOG_FILE}"
echo "run8e: build final matched JS/TS DiD event panel" | tee -a "${LOG_FILE}"
echo "Timestamp:              ${RUN_TS}" | tee -a "${LOG_FILE}"
echo "Python script:          ${PY_SCRIPT}" | tee -a "${LOG_FILE}"
echo "Treatment metadata:     ${TREATMENT_META}" | tee -a "${LOG_FILE}"
echo "Pairs file:             ${PAIRS_FILE}" | tee -a "${LOG_FILE}"
echo "Treatment time series:  ${TREATMENT_TS}" | tee -a "${LOG_FILE}"
echo "Control time series:    ${CONTROL_TS}" | tee -a "${LOG_FILE}"
echo "Output file:            ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Balanced output file:   ${BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Log file:               ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

for f in "${PY_SCRIPT}" "${TREATMENT_META}" "${PAIRS_FILE}" "${TREATMENT_TS}" "${CONTROL_TS}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: required file not found: ${f}" | tee -a "${LOG_FILE}"
    exit 1
  fi
done

echo "** Checking input schemas" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

files = {
    "treatment_meta": Path("${TREATMENT_META}"),
    "pairs": Path("${PAIRS_FILE}"),
    "treatment_ts": Path("${TREATMENT_TS}"),
    "control_ts": Path("${CONTROL_TS}"),
}

for name, path in files.items():
    df = pd.read_csv(path, nrows=5)
    print(f"{name}: {path}")
    print("  columns:", list(df.columns))
    print()

# Required columns for prepare_panel_event_v2.py
meta_cols = set(pd.read_csv(files["treatment_meta"], nrows=0).columns)
pair_cols = set(pd.read_csv(files["pairs"], nrows=0).columns)
treat_ts_cols = set(pd.read_csv(files["treatment_ts"], nrows=0).columns)
control_ts_cols = set(pd.read_csv(files["control_ts"], nrows=0).columns)

required_meta = {"repo_name", "event_month"}
required_pairs = {"treatment_repo", "control_repo"}
required_ts = {"repo_name", "month"}

missing = []
if not required_meta.issubset(meta_cols):
    missing.append(("treatment_meta", sorted(required_meta - meta_cols)))
if not required_pairs.issubset(pair_cols):
    missing.append(("pairs", sorted(required_pairs - pair_cols)))
if not required_ts.issubset(treat_ts_cols):
    missing.append(("treatment_ts", sorted(required_ts - treat_ts_cols)))
if not required_ts.issubset(control_ts_cols):
    missing.append(("control_ts", sorted(required_ts - control_ts_cols)))

if missing:
    for name, cols in missing:
        print(f"ERROR: {name} missing columns: {cols}")
    raise SystemExit(1)

print("Schema check passed.")
PY

echo | tee -a "${LOG_FILE}"
echo "** Running panel builder" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

CMD=(
  python "${PY_SCRIPT}"
  --treatment-meta "${TREATMENT_META}"
  --pairs "${PAIRS_FILE}"
  --treatment-ts "${TREATMENT_TS}"
  --control-ts "${CONTROL_TS}"
  --output "${OUTPUT_FILE}"
  --balanced-output "${BALANCED_OUTPUT_FILE}"
)

echo "${CMD[*]}" | tee -a "${LOG_FILE}"
echo | tee -a "${LOG_FILE}"

"${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"

echo | tee -a "${LOG_FILE}"
echo "** Output summary" | tee -a "${LOG_FILE}"
echo "------------------------------------------------------------" | tee -a "${LOG_FILE}"

python - <<PY 2>&1 | tee -a "${LOG_FILE}"
import pandas as pd
from pathlib import Path

for label, path_text in [
    ("unbalanced", "${OUTPUT_FILE}"),
    ("balanced", "${BALANCED_OUTPUT_FILE}"),
]:
    path = Path(path_text)
    if not path.exists():
        print(f"MISSING: {label}: {path}")
        continue

    df = pd.read_csv(path)
    print(f"{label}: {path}")
    print("  rows:", len(df))
    print("  repos:", df["repo_name"].nunique())
    if "ever_treated" in df.columns:
        print("  treated repos:", df.loc[df["ever_treated"] == 1, "repo_name"].nunique())
        print("  control repos:", df.loc[df["ever_treated"] == 0, "repo_name"].nunique())
    if "dataset_source" in df.columns:
        print("  dataset_source counts:")
        print(df["dataset_source"].value_counts(dropna=False).to_string())
    print()
PY

echo | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
echo "run8e completed successfully." | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "Output file: ${OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "Balanced output file: ${BALANCED_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
echo "============================================================" | tee -a "${LOG_FILE}"
