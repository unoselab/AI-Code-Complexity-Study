#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run9c: Merge JS/TS SonarQube metrics into matched DiD panels
# ============================================================
# This script reuses proc_scripts/merge_sonarqube_panel_v2.py.
#
# It merges treatment/control SonarQube metrics into:
#   1. main final-clean balanced panel
#   2. main final-clean unbalanced panel
#   3. strict 1:3 balanced panel
#   4. strict 1:3 unbalanced panel
#
# It also adds additional QC flags:
#   - sonarqube_ncloc_zero
#   - sonarqube_all_raw_metrics_missing
#   - sonarqube_static_warnings_missing
#   - sonarqube_duplicate_density_missing
#   - sonarqube_cognitive_complexity_missing
#   - sonarqube_quality_outcomes_complete
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run9c_merge_sonarqube_panel_${RUN_TS}.log}"

PY_SCRIPT="${PY_SCRIPT:-proc_scripts/merge_sonarqube_panel_v2.py}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
SONAR_ROOT="${SONAR_ROOT:-tmp_jsts_test/data/jsts_sonarqube_main}"

TREATMENT_METRICS="${TREATMENT_METRICS:-${SONAR_ROOT}/treatment/data/ts_repos_monthly_scanned.csv}"
CONTROL_METRICS="${CONTROL_METRICS:-${SONAR_ROOT}/control/data/ts_repos_monthly_scanned.csv}"

MAIN_BALANCED_PANEL="${MAIN_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_balanced.csv}"
MAIN_UNBALANCED_PANEL="${MAIN_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean.csv}"

STRICT_BALANCED_PANEL="${STRICT_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced.csv}"
STRICT_UNBALANCED_PANEL="${STRICT_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only.csv}"

MAIN_BALANCED_OUTPUT="${MAIN_BALANCED_OUTPUT:-${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube.csv}"
MAIN_UNBALANCED_OUTPUT="${MAIN_UNBALANCED_OUTPUT:-${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube.csv}"

STRICT_BALANCED_OUTPUT="${STRICT_BALANCED_OUTPUT:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube.csv}"
STRICT_UNBALANCED_OUTPUT="${STRICT_UNBALANCED_OUTPUT:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube.csv}"

MAIN_BALANCED_QC="${MAIN_BALANCED_QC:-${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube_qc.csv}"
MAIN_UNBALANCED_QC="${MAIN_UNBALANCED_QC:-${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube_qc.csv}"

STRICT_BALANCED_QC="${STRICT_BALANCED_QC:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube_qc.csv}"
STRICT_UNBALANCED_QC="${STRICT_UNBALANCED_QC:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube_qc.csv}"

MERGE_SUMMARY="${MERGE_SUMMARY:-${DID_DIR}/sonarqube_panel_merge_summary.csv}"

mkdir -p "${LOG_DIR}" "${DID_DIR}"

merge_one_panel() {
  local label="$1"
  local panel="$2"
  local output="$3"
  local qc_output="$4"

  echo
  echo "============================================================"
  echo "Merging panel: ${label}"
  echo "Panel:         ${panel}"
  echo "Output:        ${output}"
  echo "QC output:     ${qc_output}"
  echo "============================================================"

  if [[ ! -f "${panel}" ]]; then
    echo "ERROR: panel file not found: ${panel}"
    exit 1
  fi

  python "${PY_SCRIPT}" \
    --panel "${panel}" \
    --treatment-metrics "${TREATMENT_METRICS}" \
    --control-metrics "${CONTROL_METRICS}" \
    --output "${output}" \
    --qc-output "${qc_output}"

  echo
  echo "** Adding run9c QC flags for ${label}"
  echo "------------------------------------------------------------"

  python - <<PY
import pandas as pd
from pathlib import Path

output = Path("${output}")
qc_output = Path("${qc_output}")
label = "${label}"

df = pd.read_csv(output)

raw_metric_cols = [
    "ncloc_raw",
    "bugs_raw",
    "vulnerabilities_raw",
    "code_smells_raw",
    "duplicated_lines_density_raw",
    "comment_lines_density_raw",
    "cognitive_complexity_raw",
    "technical_debt_raw",
]

required = {"repo_name", "time", "dataset_source"} | set(raw_metric_cols)
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns in merged output: {sorted(missing)}")

df["sonarqube_all_raw_metrics_missing"] = df[raw_metric_cols].isna().all(axis=1).astype(int)
df["sonarqube_ncloc_zero"] = (
    df["ncloc_raw"].notna() & (df["ncloc_raw"] == 0)
).astype(int)

df["sonarqube_static_warnings_missing"] = (
    df[["bugs_raw", "vulnerabilities_raw", "code_smells_raw"]].isna().any(axis=1)
).astype(int)

df["sonarqube_duplicate_density_missing"] = df["duplicated_lines_density_raw"].isna().astype(int)
df["sonarqube_cognitive_complexity_missing"] = df["cognitive_complexity_raw"].isna().astype(int)

df["sonarqube_quality_outcomes_complete"] = (
    (df["sonarqube_static_warnings_missing"] == 0)
    & (df["sonarqube_duplicate_density_missing"] == 0)
    & (df["sonarqube_cognitive_complexity_missing"] == 0)
).astype(int)

df.to_csv(output, index=False)

qc = pd.read_csv(qc_output)

new_checks = pd.DataFrame([
    {"check": "run9c_panel_label", "value": label},
    {"check": "run9c_rows", "value": len(df)},
    {"check": "run9c_treatment_rows", "value": int((df["dataset_source"] == "treatment").sum())},
    {"check": "run9c_control_rows", "value": int((df["dataset_source"] == "control").sum())},
    {"check": "run9c_sonarqube_all_raw_metrics_missing_rows", "value": int(df["sonarqube_all_raw_metrics_missing"].sum())},
    {"check": "run9c_sonarqube_ncloc_zero_rows", "value": int(df["sonarqube_ncloc_zero"].sum())},
    {"check": "run9c_static_warnings_missing_rows", "value": int(df["sonarqube_static_warnings_missing"].sum())},
    {"check": "run9c_duplicate_density_missing_rows", "value": int(df["sonarqube_duplicate_density_missing"].sum())},
    {"check": "run9c_cognitive_complexity_missing_rows", "value": int(df["sonarqube_cognitive_complexity_missing"].sum())},
    {"check": "run9c_quality_outcomes_complete_rows", "value": int(df["sonarqube_quality_outcomes_complete"].sum())},
])

qc = qc[~qc["check"].isin(new_checks["check"])]
qc = pd.concat([qc, new_checks], ignore_index=True)
qc.to_csv(qc_output, index=False)

print("Updated output:", output)
print("Updated QC:", qc_output)
print()
print(new_checks.to_string(index=False))
PY
}

{
  echo "============================================================"
  echo "run9c: merge JS/TS SonarQube metrics into DiD panels"
  echo "Started:            $(date)"
  echo "Python script:      ${PY_SCRIPT}"
  echo "DID dir:            ${DID_DIR}"
  echo "Sonar root:         ${SONAR_ROOT}"
  echo "Treatment metrics:  ${TREATMENT_METRICS}"
  echo "Control metrics:    ${CONTROL_METRICS}"
  echo "Merge summary:      ${MERGE_SUMMARY}"
  echo "Log file:           ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    echo "Place merge_sonarqube_panel_v2.py under proc_scripts/ first."
    exit 1
  fi

  if [[ ! -f "${TREATMENT_METRICS}" ]]; then
    echo "ERROR: treatment metrics file not found: ${TREATMENT_METRICS}"
    exit 1
  fi

  if [[ ! -f "${CONTROL_METRICS}" ]]; then
    echo "ERROR: control metrics file not found: ${CONTROL_METRICS}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  merge_one_panel \
    "main_balanced" \
    "${MAIN_BALANCED_PANEL}" \
    "${MAIN_BALANCED_OUTPUT}" \
    "${MAIN_BALANCED_QC}"

  merge_one_panel \
    "main_unbalanced" \
    "${MAIN_UNBALANCED_PANEL}" \
    "${MAIN_UNBALANCED_OUTPUT}" \
    "${MAIN_UNBALANCED_QC}"

  merge_one_panel \
    "strict_1to3_balanced" \
    "${STRICT_BALANCED_PANEL}" \
    "${STRICT_BALANCED_OUTPUT}" \
    "${STRICT_BALANCED_QC}"

  merge_one_panel \
    "strict_1to3_unbalanced" \
    "${STRICT_UNBALANCED_PANEL}" \
    "${STRICT_UNBALANCED_OUTPUT}" \
    "${STRICT_UNBALANCED_QC}"

  echo
  echo "** Building combined merge summary"
  echo "------------------------------------------------------------"

  python - <<PY
import pandas as pd
from pathlib import Path

outputs = {
    "main_balanced": Path("${MAIN_BALANCED_OUTPUT}"),
    "main_unbalanced": Path("${MAIN_UNBALANCED_OUTPUT}"),
    "strict_1to3_balanced": Path("${STRICT_BALANCED_OUTPUT}"),
    "strict_1to3_unbalanced": Path("${STRICT_UNBALANCED_OUTPUT}"),
}

metric_cols = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
    "static_analysis_warnings",
]

rows = []

for label, path in outputs.items():
    if not path.exists():
        raise SystemExit(f"Missing merged output: {path}")

    df = pd.read_csv(path)

    row = {
        "panel": label,
        "file": str(path),
        "rows": len(df),
        "repos": df["repo_name"].nunique(),
        "treatment_rows": int((df["dataset_source"] == "treatment").sum()),
        "control_rows": int((df["dataset_source"] == "control").sum()),
        "treatment_repos": df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique(),
        "control_repos": df.loc[df["dataset_source"] == "control", "repo_name"].nunique(),
        "months_min": df["time"].min(),
        "months_max": df["time"].max(),
        "raw_metric_missing_rows": int(df["sonarqube_any_raw_metric_missing"].sum()) if "sonarqube_any_raw_metric_missing" in df.columns else None,
        "all_raw_metrics_missing_rows": int(df["sonarqube_all_raw_metrics_missing"].sum()),
        "ncloc_zero_rows": int(df["sonarqube_ncloc_zero"].sum()),
        "quality_outcomes_complete_rows": int(df["sonarqube_quality_outcomes_complete"].sum()),
    }

    for col in metric_cols:
        if col in df.columns:
            row[f"{col}_nonmissing"] = int(df[col].notna().sum())

    rows.append(row)

summary = pd.DataFrame(rows)
out = Path("${MERGE_SUMMARY}")
out.parent.mkdir(parents=True, exist_ok=True)
summary.to_csv(out, index=False)

print(summary.to_string(index=False))
print()
print("Saved:", out)
PY

  echo
  echo "============================================================"
  echo "run9c completed successfully."
  echo "Completed:      $(date)"
  echo "Merge summary:  ${MERGE_SUMMARY}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
