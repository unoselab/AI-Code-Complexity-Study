#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2e: Prepare Python quality DiD input
# ============================================================
# Purpose:
#   Convert merged Python SonarQube panels into quality DiD inputs.
#   Optionally create a paper-schema diagnostic output without calling
#   compare/run-py-2b15-create-paper-structure-panel.sh.
#
# Input:
#   repo_python/run-py-2c/<variant>/panel_event_matched_<variant>_with_sonarqube.csv
#
# Main output for the strict paper-overlap run:
#   repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv
#
# Main output for flexible or non-paper runs:
#   repo_python/run-py-2e/<variant>/
#     panel_event_matched_<variant>_with_sonarqube_quality_did_input_complete.csv
#
# Extra outputs:
#   repo_python/tmp/run-py-2e/<variant>/quality_did_input_qc.csv
#   repo_python/tmp/run-py-2e/<variant>/paper_audit/
#
# Temporary outputs:
#   Full inputs, missing-row outputs, manifest, and combined QC files are
#   created under a timestamped work directory and removed after success.
#
# Paper-comparable strict run:
#   PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE
# 
# Usage for Python only
# OUTPUT_SUFFIX=python_only PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE
#
# Important:
#   The paper-schema output preserves regenerated Python SonarQube metrics.
#   Selected unavailable covariates are filled from the frozen paper panel
#   only on exact repo-month matches.
# ============================================================

SCRIPT_NAME="$(basename "$0")"
if [[ "${SCRIPT_NAME}" =~ ^(run-py-[^-]+)- ]]; then
  RUN_PREFIX="${BASH_REMATCH[1]}"
else
  echo "ERROR: unable to extract run prefix from script name: ${SCRIPT_NAME}" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Usage:
  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh [options]

Options:
  --convert-paper-same-column TRUE|FALSE
  --keep-overlap-paper-same-column TRUE|FALSE
  --paper-panel-file PATH
  --paper-audit-dir PATH
  --fill-from-paper-columns CSV_LIST
  --metric-compare-columns CSV_LIST
  --top-print INTEGER
  --help
EOF
}

normalize_bool() {
  local value
  value="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
  case "${value}" in
    TRUE|FALSE)
      printf '%s' "${value}"
      ;;
    *)
      echo "ERROR: expected TRUE or FALSE, got: $1" >&2
      exit 1
      ;;
  esac
}

require_option_value() {
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "${option_value}" ]]; then
    echo "ERROR: ${option_name} requires a value." >&2
    exit 1
  fi
}

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"
OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-repo_python}"
PANEL_INPUT_DIR="${PANEL_INPUT_DIR:-${OUTPUT_BASE_DIR}/run-py-2c}"
MAIN_OUTPUT_DIR="${MAIN_OUTPUT_DIR:-${OUTPUT_BASE_DIR}/${RUN_PREFIX}}"
TMP_DIR="${TMP_DIR:-${OUTPUT_BASE_DIR}/tmp/${RUN_PREFIX}}"

CONVERT_PAPER_SAME_COLUMN="${CONVERT_PAPER_SAME_COLUMN:-FALSE}"
KEEP_OVERLAP_PAPER_SAME_COLUMN="${KEEP_OVERLAP_PAPER_SAME_COLUMN:-FALSE}"
PAPER_PANEL_FILE="${PAPER_PANEL_FILE:-data/panel_event_monthly.csv}"
PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR:-${TMP_DIR}}"
FILL_FROM_PAPER_COLUMNS="${FILL_FROM_PAPER_COLUMNS:-stars,issues,issue_comments,age,num_dependencies_total,num_vulnerable_dependencies,average_technical_lag,other_agents,high_confidence}"
METRIC_COMPARE_COLUMNS="${METRIC_COMPARE_COLUMNS:-ncloc,bugs,vulnerabilities,code_smells,duplicated_lines_density,comment_lines_density,cognitive_complexity,technical_debt}"
TOP_PRINT="${TOP_PRINT:-20}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --convert-paper-same-column)
      require_option_value "$1" "${2:-}"
      CONVERT_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --keep-overlap-paper-same-column)
      require_option_value "$1" "${2:-}"
      KEEP_OVERLAP_PAPER_SAME_COLUMN="$2"
      shift 2
      ;;
    --paper-panel-file)
      require_option_value "$1" "${2:-}"
      PAPER_PANEL_FILE="$2"
      shift 2
      ;;
    --paper-audit-dir)
      require_option_value "$1" "${2:-}"
      PAPER_AUDIT_DIR="$2"
      shift 2
      ;;
    --fill-from-paper-columns)
      require_option_value "$1" "${2:-}"
      FILL_FROM_PAPER_COLUMNS="$2"
      shift 2
      ;;
    --metric-compare-columns)
      require_option_value "$1" "${2:-}"
      METRIC_COMPARE_COLUMNS="$2"
      shift 2
      ;;
    --top-print)
      require_option_value "$1" "${2:-}"
      TOP_PRINT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

CONVERT_PAPER_SAME_COLUMN="$(normalize_bool "${CONVERT_PAPER_SAME_COLUMN}")"
KEEP_OVERLAP_PAPER_SAME_COLUMN="$(normalize_bool "${KEEP_OVERLAP_PAPER_SAME_COLUMN}")"

if [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" && "${CONVERT_PAPER_SAME_COLUMN}" != "TRUE" ]]; then
  echo "ERROR: --keep-overlap-paper-same-column TRUE requires --convert-paper-same-column TRUE."
  exit 1
fi

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

if [[ -n "${OUTPUT_SUFFIX}" && ! "${OUTPUT_SUFFIX}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERROR: OUTPUT_SUFFIX must contain only letters, numbers, and underscores. Got: ${OUTPUT_SUFFIX}"
  exit 1
fi

FILE_SUFFIX=""
if [[ -n "${OUTPUT_SUFFIX}" ]]; then
  FILE_SUFFIX="_${OUTPUT_SUFFIX}"
fi

WORK_ROOT="${WORK_ROOT:-${TMP_DIR}/work_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}}"


if ! [[ "${TOP_PRINT}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --top-print must be a non-negative integer. Got: ${TOP_PRINT}"
  exit 1
fi

if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && ! -f "${PAPER_PANEL_FILE}" ]]; then
  echo "ERROR: paper panel file not found: ${PAPER_PANEL_FILE}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_PREFIX}_prepare_quality_did_input_${PANEL_VARIANT}${FILE_SUFFIX}_${RUN_TS}.log}"
MANIFEST_FILE="${WORK_ROOT}/quality_did_input_manifest_${PANEL_VARIANT}${FILE_SUFFIX}.csv"
COMBINED_QC_LONG="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}${FILE_SUFFIX}_long.csv"
COMBINED_QC_WIDE="${WORK_ROOT}/quality_did_input_qc_${PANEL_VARIANT}${FILE_SUFFIX}_wide.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${PANEL_INPUT_DIR}/strict/panel_event_matched_strict_with_sonarqube${FILE_SUFFIX}.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${PANEL_INPUT_DIR}/flexible/panel_event_matched_flexible_with_sonarqube${FILE_SUFFIX}.csv")
fi

mkdir -p "${LOG_DIR}" "${MAIN_OUTPUT_DIR}" "${TMP_DIR}" "${WORK_ROOT}"

{
  echo "============================================================"
  echo "${RUN_PREFIX}: prepare Python quality DiD input"
  echo "Started:                           $(date)"
  echo "Script name:                       ${SCRIPT_NAME}"
  echo "Run prefix:                        ${RUN_PREFIX}"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Output suffix:                     ${OUTPUT_SUFFIX:-<none>}"
  echo "Python script:                     ${PY_SCRIPT}"
  echo "Panel input dir:                   ${PANEL_INPUT_DIR}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Paper panel file:                  ${PAPER_PANEL_FILE}"
  echo "Paper audit root:                   ${PAPER_AUDIT_DIR}"
  echo "Fill from paper columns:           ${FILL_FROM_PAPER_COLUMNS}"
  echo "Metric compare columns:            ${METRIC_COMPARE_COLUMNS}"
  echo "Top print:                         ${TOP_PRINT}"
  echo "Temporary manifest:                ${MANIFEST_FILE}"
  echo "Temporary combined QC long:        ${COMBINED_QC_LONG}"
  echo "Temporary combined QC wide:        ${COMBINED_QC_WIDE}"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  echo "panel,input,output,complete_output,qc_output,missing_output,paper_same_column_output,paper_key_summary,paper_unmatched_output" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input merged SonarQube panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control SonarQube scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      echo "  3. PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh"
      exit 1
    fi

    PANEL_MAIN_DIR="${MAIN_OUTPUT_DIR}/${PANEL_LABEL}"
    PANEL_TMP_DIR="${TMP_DIR}/${PANEL_LABEL}${FILE_SUFFIX}"
    PANEL_WORK_DIR="${WORK_ROOT}/${PANEL_LABEL}"
    CURRENT_PAPER_AUDIT_DIR="${PAPER_AUDIT_DIR}/${PANEL_LABEL}${FILE_SUFFIX}/paper_audit"

    mkdir -p "${PANEL_MAIN_DIR}" "${PANEL_TMP_DIR}" "${PANEL_WORK_DIR}" "${CURRENT_PAPER_AUDIT_DIR}"

    OUTPUT_FILE="${PANEL_WORK_DIR}/quality_did_input_full.csv"
    MISSING_OUTPUT_FILE="${PANEL_WORK_DIR}/missing_core_quality.csv"
    QC_OUTPUT_FILE="${PANEL_TMP_DIR}/quality_did_input_qc.csv"

    if [[ "${PANEL_LABEL}" == "strict" && "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      COMPLETE_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_matched_strict_with_sonarqube${FILE_SUFFIX}_quality_did_input_complete.csv"
    else
      COMPLETE_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_matched_${PANEL_LABEL}_with_sonarqube${FILE_SUFFIX}_quality_did_input_complete.csv"
    fi

    PAPER_SAME_COLUMN_OUTPUT_FILE=""
    PAPER_KEY_SUMMARY_FILE=""
    PAPER_UNMATCHED_OUTPUT_FILE=""

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      if [[ "${PANEL_LABEL}" == "strict" && "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_MAIN_DIR}/panel_event_monthly_quality_py${FILE_SUFFIX}.csv"
      elif [[ "${KEEP_OVERLAP_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}${FILE_SUFFIX}.csv"
      else
        PAPER_SAME_COLUMN_OUTPUT_FILE="${PANEL_TMP_DIR}/panel_event_monthly_quality_py_${PANEL_LABEL}${FILE_SUFFIX}_with_unmatched.csv"
      fi
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      PAPER_KEY_SUMMARY_FILE="${PAPER_AUDIT_BASE}_key_match_summary.csv"
      PAPER_UNMATCHED_OUTPUT_FILE="${PAPER_AUDIT_BASE}_unmatched_repo_months.csv"
    fi

    echo
    echo "============================================================"
    echo "Preparing quality DiD input for panel: ${PANEL_LABEL}"
    echo "Input:                         ${INPUT_FILE}"
    echo "Output:                        ${OUTPUT_FILE}"
    echo "Complete output:               ${COMPLETE_OUTPUT_FILE}"
    echo "QC output:                     ${QC_OUTPUT_FILE}"
    echo "Missing output:                ${MISSING_OUTPUT_FILE}"
    echo "Paper same-column output:      ${PAPER_SAME_COLUMN_OUTPUT_FILE:-<disabled>}"
    echo "Paper audit directory:         ${CURRENT_PAPER_AUDIT_DIR}"
    echo "Paper overlap-only:            ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
    echo "============================================================"

    PY_ARGS=(
      --panel-label "${PANEL_LABEL}"
      --input "${INPUT_FILE}"
      --output "${OUTPUT_FILE}"
      --complete-output "${COMPLETE_OUTPUT_FILE}"
      --qc-output "${QC_OUTPUT_FILE}"
      --missing-output "${MISSING_OUTPUT_FILE}"
      --convert-paper-same-column "${CONVERT_PAPER_SAME_COLUMN}"
      --keep-overlap-paper-same-column "${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
      --paper-panel-file "${PAPER_PANEL_FILE}"
      --paper-audit-dir "${CURRENT_PAPER_AUDIT_DIR}"
      --fill-from-paper-columns "${FILL_FROM_PAPER_COLUMNS}"
      --metric-compare-columns "${METRIC_COMPARE_COLUMNS}"
      --top-print "${TOP_PRINT}"
    )

    if [[ -n "${PAPER_SAME_COLUMN_OUTPUT_FILE}" ]]; then
      PY_ARGS+=(--paper-same-column-output "${PAPER_SAME_COLUMN_OUTPUT_FILE}")
    fi

    python "${PY_SCRIPT}" "${PY_ARGS[@]}"

    for expected_file in \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}"; do
      if [[ ! -f "${expected_file}" ]]; then
        echo "ERROR: missing expected output: ${expected_file}"
        exit 1
      fi
    done

    if [[ "${CONVERT_PAPER_SAME_COLUMN}" == "TRUE" ]]; then
      PAPER_OUTPUT_STEM="$(basename "${PAPER_SAME_COLUMN_OUTPUT_FILE%.csv}")"
      PAPER_AUDIT_BASE="${CURRENT_PAPER_AUDIT_DIR}/${PAPER_OUTPUT_STEM}"
      for expected_file in \
        "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
        "${PAPER_AUDIT_BASE}_column_sources.csv" \
        "${PAPER_AUDIT_BASE}_key_match_summary.csv" \
        "${PAPER_AUDIT_BASE}_metric_comparison.csv" \
        "${PAPER_AUDIT_BASE}_unmatched_repo_months.csv" \
        "${PAPER_AUDIT_BASE}_notes.md"; do
        if [[ ! -f "${expected_file}" ]]; then
          echo "ERROR: missing expected paper-schema output: ${expected_file}"
          exit 1
        fi
      done

      echo "Paper-schema key match summary:"
      cat "${PAPER_KEY_SUMMARY_FILE}"
      rm -f "${PAPER_AUDIT_BASE}_notes.md"
    fi

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}" \
      "${PAPER_SAME_COLUMN_OUTPUT_FILE}" \
      "${PAPER_KEY_SUMMARY_FILE}" \
      "${PAPER_UNMATCHED_OUTPUT_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined quality DiD input QC"
  echo "------------------------------------------------------------"

  python - <<PY
from pathlib import Path
import pandas as pd

manifest_path = Path("${MANIFEST_FILE}")
combined_long_path = Path("${COMBINED_QC_LONG}")
combined_wide_path = Path("${COMBINED_QC_WIDE}")

manifest = pd.read_csv(manifest_path).fillna("")

qc_frames = []
wide_rows = []

def read_csv_if_possible(path_value):
    if not path_value:
        return pd.DataFrame()
    path = Path(path_value)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    qc = read_csv_if_possible(row["qc_output"])
    if not qc.empty:
        qc.insert(0, "panel", panel)
        qc_frames.append(qc)

    output_df = read_csv_if_possible(row["output"])
    complete_df = read_csv_if_possible(row["complete_output"])
    missing_df = read_csv_if_possible(row["missing_output"])
    paper_df = read_csv_if_possible(row["paper_same_column_output"])
    paper_key_summary = read_csv_if_possible(row["paper_key_summary"])

    wide_row = {
        "panel": panel,
        "output_file": row["output"],
        "complete_output_file": row["complete_output"],
        "missing_output_file": row["missing_output"],
        "paper_same_column_output_file": row["paper_same_column_output"],
        "output_rows": len(output_df),
        "complete_rows": len(complete_df),
        "missing_core_quality_rows": len(missing_df),
        "paper_same_column_output_rows": len(paper_df) if row["paper_same_column_output"] else None,
        "output_repos": output_df["repo_name"].nunique() if "repo_name" in output_df.columns else None,
        "complete_repos": complete_df["repo_name"].nunique() if "repo_name" in complete_df.columns else None,
        "paper_same_column_repos": paper_df["repo_name"].nunique() if "repo_name" in paper_df.columns else None,
    }

    if not paper_key_summary.empty:
        summary = paper_key_summary.iloc[0]
        wide_row.update({
            "paper_repo_month_rows_matched": summary.get("repo_month_rows_matched_to_paper"),
            "paper_repo_month_rows_unmatched": summary.get("repo_month_rows_not_matched_to_paper"),
            "keep_overlap_paper_same_column": summary.get("keep_overlap_paper_same_column"),
            "paper_duplicate_repo_month_rows": summary.get("paper_duplicate_repo_month_rows"),
        })
    else:
        wide_row.update({
            "paper_repo_month_rows_matched": None,
            "paper_repo_month_rows_unmatched": None,
            "keep_overlap_paper_same_column": None,
            "paper_duplicate_repo_month_rows": None,
        })

    wide_rows.append(wide_row)

combined_long = pd.concat(qc_frames, ignore_index=True) if qc_frames else pd.DataFrame()
combined_wide = pd.DataFrame(wide_rows)

combined_long_path.parent.mkdir(parents=True, exist_ok=True)
combined_wide_path.parent.mkdir(parents=True, exist_ok=True)

combined_long.to_csv(combined_long_path, index=False)
combined_wide.to_csv(combined_wide_path, index=False)

print("Saved combined QC long:", combined_long_path)
print("Saved combined QC wide:", combined_wide_path)
print()
print("Combined QC wide:")
print(combined_wide.to_string(index=False))
PY

  rm -rf "${WORK_ROOT}"

  echo
  echo "============================================================"
  echo "${RUN_PREFIX} completed successfully."
  echo "Completed:                         $(date)"
  echo "Panel variant:                     ${PANEL_VARIANT}"
  echo "Output suffix:                     ${OUTPUT_SUFFIX:-<none>}"
  echo "Convert paper same column:         ${CONVERT_PAPER_SAME_COLUMN}"
  echo "Keep overlap paper same column:    ${KEEP_OVERLAP_PAPER_SAME_COLUMN}"
  echo "Main output dir:                   ${MAIN_OUTPUT_DIR}"
  echo "Extra output dir:                  ${TMP_DIR}"
  echo "Temporary work files:              removed"
  echo "Log file:                          ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

# This wrapper reuses the logic of the previous run-py-2e and run-py-2b15
# workflows without directly calling either existing wrapper.
