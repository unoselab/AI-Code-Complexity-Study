#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run9h: Borusyak DiD for JS/TS development velocity outcomes
# ============================================================
# Outcomes:
#   - commits
#   - lines_added
#
# Panels:
#   - main_unbalanced
#   - main_balanced
#   - strict_1to3_unbalanced
#   - strict_1to3_balanced
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run9h_did_velocity_borusyak_${RUN_TS}.log}"

RMD="${RMD:-proc_r/DiffInDiffBorusyak_velocity_v2.Rmd}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/velocity_did_borusyak}"
SUMMARY_DIR="${SUMMARY_DIR:-${OUT_ROOT}/summary}"

MAIN_UNBALANCED_PANEL="${MAIN_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean.csv}"
MAIN_BALANCED_PANEL="${MAIN_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_balanced.csv}"
STRICT_UNBALANCED_PANEL="${STRICT_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only.csv}"
STRICT_BALANCED_PANEL="${STRICT_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced.csv}"

mkdir -p "${LOG_DIR}" "${OUT_ROOT}" "${SUMMARY_DIR}"

render_one_panel() {
  local label="$1"
  local panel="$2"
  local out_dir="${OUT_ROOT}/${label}"

  echo
  echo "============================================================"
  echo "Rendering velocity Borusyak panel: ${label}"
  echo "Panel:      ${panel}"
  echo "Output dir: ${out_dir}"
  echo "============================================================"

  if [[ ! -f "${panel}" ]]; then
    echo "ERROR: panel file not found: ${panel}"
    exit 1
  fi

  mkdir -p "${out_dir}"

  PANEL_LABEL="${label}" \
  PANEL_PATH="${panel}" \
  OUT_DIR="${out_dir}" \
  RMD_PATH="${RMD}" \
  Rscript - <<'RS'
rmd <- Sys.getenv("RMD_PATH")
panel_label <- Sys.getenv("PANEL_LABEL")
panel_path <- Sys.getenv("PANEL_PATH")
out_dir <- Sys.getenv("OUT_DIR")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = paste0("borusyak_velocity_", panel_label, ".html"),
  output_dir = out_dir,
  params = list(
    panel_label = panel_label,
    panel_path = panel_path,
    out_dir = out_dir
  ),
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS
}

{
  echo "============================================================"
  echo "run9h: JS/TS development velocity Borusyak DiD"
  echo "Started:        $(date)"
  echo "Rmd:            ${RMD}"
  echo "DID dir:        ${DID_DIR}"
  echo "Output root:    ${OUT_ROOT}"
  echo "Summary dir:    ${SUMMARY_DIR}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD}"
    exit 1
  fi

  render_one_panel "main_unbalanced" "${MAIN_UNBALANCED_PANEL}"
  render_one_panel "main_balanced" "${MAIN_BALANCED_PANEL}"
  render_one_panel "strict_1to3_unbalanced" "${STRICT_UNBALANCED_PANEL}"
  render_one_panel "strict_1to3_balanced" "${STRICT_BALANCED_PANEL}"

  echo
  echo "** Building combined velocity summaries"
  echo "------------------------------------------------------------"

  python - <<PY
import pandas as pd
from pathlib import Path
import math

out_root = Path("${OUT_ROOT}")
summary_dir = Path("${SUMMARY_DIR}")
summary_dir.mkdir(parents=True, exist_ok=True)

labels = [
    "main_unbalanced",
    "main_balanced",
    "strict_1to3_unbalanced",
    "strict_1to3_balanced",
]

def read_if_exists(label, filename):
    path = out_root / label / filename
    if not path.exists():
        print("MISSING:", path)
        return None
    df = pd.read_csv(path)
    if "panel" not in df.columns:
        df["panel"] = label
    return df

combined_specs = [
    ("borusyak_velocity_static_effects.csv", "borusyak_velocity_static_effects_all.csv"),
    ("borusyak_velocity_dynamic_effects.csv", "borusyak_velocity_dynamic_effects_all.csv"),
    ("borusyak_velocity_input_summary.csv", "borusyak_velocity_input_summary_all.csv"),
    ("borusyak_velocity_panel_checks.csv", "borusyak_velocity_panel_checks_all.csv"),
]

for src_name, out_name in combined_specs:
    parts = []
    for label in labels:
        df = read_if_exists(label, src_name)
        if df is not None:
            parts.append(df)
    if parts:
        combined = pd.concat(parts, ignore_index=True)
        out = out_root / out_name
        combined.to_csv(out, index=False)
        print("Saved:", out)

static_path = out_root / "borusyak_velocity_static_effects_all.csv"
if static_path.exists():
    static = pd.read_csv(static_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in static.columns:
            static[f"{col}_pct"] = static[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(x) - 1.0) * 100.0
            )

    paper_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "estimate",
        "estimate_pct",
        "conf_low",
        "conf_low_pct",
        "conf_high",
        "conf_high_pct",
        "std_error",
        "p_value",
        "note",
    ]
    paper_cols = [c for c in paper_cols if c in static.columns]

    paper = static[paper_cols].copy()
    out = summary_dir / "borusyak_velocity_static_effects_paper_ready.csv"
    paper.to_csv(out, index=False)
    print("Saved:", out)

    wide = paper.pivot_table(
        index=["panel"],
        columns=["outcome"],
        values=["estimate_pct", "conf_low_pct", "conf_high_pct"],
        aggfunc="first"
    )
    wide.columns = ["_".join([str(x) for x in col if str(x) != ""]) for col in wide.columns]
    wide = wide.reset_index()
    out = summary_dir / "borusyak_velocity_static_effects_wide.csv"
    wide.to_csv(out, index=False)
    print("Saved:", out)

dynamic_path = out_root / "borusyak_velocity_dynamic_effects_all.csv"
if dynamic_path.exists():
    dynamic = pd.read_csv(dynamic_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in dynamic.columns:
            dynamic[f"{col}_pct"] = dynamic[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(x) - 1.0) * 100.0
            )

    out = summary_dir / "borusyak_velocity_dynamic_effects_percent.csv"
    dynamic.to_csv(out, index=False)
    print("Saved:", out)

    plot_cols = [
        "panel",
        "outcome",
        "outcome_label",
        "time",
        "estimate",
        "conf_low",
        "conf_high",
        "estimate_pct",
        "conf_low_pct",
        "conf_high_pct",
        "significant",
    ]
    plot_cols = [c for c in plot_cols if c in dynamic.columns]
    out = summary_dir / "borusyak_velocity_dynamic_effects_plot_ready.csv"
    dynamic[plot_cols].to_csv(out, index=False)
    print("Saved:", out)

notes = summary_dir / "borusyak_velocity_summary_notes.txt"
notes.write_text(
    "Velocity Borusyak DiD completed for main_unbalanced, main_balanced, "
    "strict_1to3_unbalanced, and strict_1to3_balanced panels. "
    "Outcomes are log_commits and log_lines_added. "
    "Static effects summarize average post-adoption treatment effects. "
    "Dynamic effects use event-time horizons -6 to 6 with pretrend horizons -6 to -2.\\n"
)
print("Saved:", notes)
PY

  echo
  echo "============================================================"
  echo "run9h completed successfully."
  echo "Completed:       $(date)"
  echo "Output root:     ${OUT_ROOT}"
  echo "Summary dir:     ${SUMMARY_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
