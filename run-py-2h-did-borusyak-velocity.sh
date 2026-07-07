#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2h: Borusyak DiD for Python development velocity outcomes
# ============================================================
#
# Purpose:
#   Run Borusyak imputation DiD for Python development velocity
#   outcomes using the final matched Python panels.
#
# Outcomes handled inside the Rmd:
#   - commits
#   - lines_added
#
# Current Python panel naming convention:
#   flexible
#     - Sample-coverage panel.
#     - Keeps treatments with 2 or 3 final controls.
#     - Primary analysis candidate.
#
#   strict
#     - 1:3 matching-rule panel.
#     - Keeps only treatments with exactly 3 final controls.
#     - Primary robustness / matching-rule panel.
#
#   flexible_window_driven
#     - Diagnostic window-completed version of flexible.
#
#   strict_window_driven
#     - Diagnostic window-completed version of strict.
#
# Default run:
#   PANEL_VARIANTS="flexible strict"
#
# Optional diagnostic run:
#   PANEL_VARIANTS="flexible strict flexible_window_driven strict_window_driven"
#
# Inputs:
#   repo_python/did_final/panel_event_matched_flexible.csv
#   repo_python/did_final/panel_event_matched_strict.csv
#   repo_python/did_final/panel_event_matched_flexible_window_driven.csv
#   repo_python/did_final/panel_event_matched_strict_window_driven.csv
#
# Outputs:
#   repo_python/did_final/velocity_did_borusyak/<variant>/borusyak_velocity_<variant>.html
#   repo_python/did_final/velocity_did_borusyak/borusyak_velocity_static_effects_all.csv
#   repo_python/did_final/velocity_did_borusyak/borusyak_velocity_dynamic_effects_all.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_static_effects_paper_ready.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_static_effects_wide.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_dynamic_effects_percent.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_dynamic_effects_plot_ready.csv
#   repo_python/did_final/velocity_did_borusyak/summary/borusyak_velocity_summary_notes.txt
#
# Usage:
#   bash run-py-2h-did-borusyak-velocity.sh
#
#   PANEL_VARIANTS="flexible strict flexible_window_driven strict_window_driven" \
#   bash run-py-2h-did-borusyak-velocity.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2h_did_borusyak_velocity_${RUN_TS}.log}"

RMD="${RMD:-proc_r/DiffInDiffBorusyak_velocity_python_v2.Rmd}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/velocity_did_borusyak}"
SUMMARY_DIR="${SUMMARY_DIR:-${OUT_ROOT}/summary}"

PANEL_VARIANTS="${PANEL_VARIANTS:-flexible strict}"

FLEXIBLE_PANEL="${FLEXIBLE_PANEL:-${DID_DIR}/panel_event_matched_flexible.csv}"
STRICT_PANEL="${STRICT_PANEL:-${DID_DIR}/panel_event_matched_strict.csv}"
FLEXIBLE_WINDOW_DRIVEN_PANEL="${FLEXIBLE_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_flexible_window_driven.csv}"
STRICT_WINDOW_DRIVEN_PANEL="${STRICT_WINDOW_DRIVEN_PANEL:-${DID_DIR}/panel_event_matched_strict_window_driven.csv}"

mkdir -p "${LOG_DIR}" "${OUT_ROOT}" "${SUMMARY_DIR}"

resolve_panel_path() {
  local label="$1"

  case "${label}" in
    flexible)
      echo "${FLEXIBLE_PANEL}"
      ;;
    strict)
      echo "${STRICT_PANEL}"
      ;;
    flexible_window_driven)
      echo "${FLEXIBLE_WINDOW_DRIVEN_PANEL}"
      ;;
    strict_window_driven)
      echo "${STRICT_WINDOW_DRIVEN_PANEL}"
      ;;
    *)
      echo "ERROR: unsupported panel variant: ${label}" >&2
      echo "Supported variants: flexible strict flexible_window_driven strict_window_driven" >&2
      exit 1
      ;;
  esac
}

render_one_panel() {
  local label="$1"
  local panel="$2"
  local out_dir="${OUT_ROOT}/${label}"

  echo
  echo "============================================================"
  echo "Rendering Python velocity Borusyak panel: ${label}"
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
  echo "run-py-2h: Python development velocity Borusyak DiD"
  echo "Started:        $(date)"
  echo "Rmd:            ${RMD}"
  echo "DID dir:        ${DID_DIR}"
  echo "Output root:    ${OUT_ROOT}"
  echo "Summary dir:    ${SUMMARY_DIR}"
  echo "Panel variants: ${PANEL_VARIANTS}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD}"
    echo "Create it first from proc_r/DiffInDiffBorusyak_velocity_v2.Rmd."
    exit 1
  fi

  for label in ${PANEL_VARIANTS}; do
    panel_path="$(resolve_panel_path "${label}")"
    render_one_panel "${label}" "${panel_path}"
  done

  echo
  echo "** Building combined Python velocity summaries"
  echo "------------------------------------------------------------"

  python - "${OUT_ROOT}" "${SUMMARY_DIR}" "${PANEL_VARIANTS}" <<'PY'
import math
import sys
from pathlib import Path

import pandas as pd

out_root = Path(sys.argv[1])
summary_dir = Path(sys.argv[2])
labels = sys.argv[3].split()

summary_dir.mkdir(parents=True, exist_ok=True)

def read_if_exists(label: str, filename: str) -> pd.DataFrame | None:
    path = out_root / label / filename
    if not path.exists():
        print(f"MISSING: {path}")
        return None

    df = pd.read_csv(path)

    if "panel" not in df.columns:
        df.insert(0, "panel", label)
    else:
        df["panel"] = df["panel"].fillna(label)
        df.loc[df["panel"].astype(str).str.strip().eq(""), "panel"] = label

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
        print(f"Saved: {out}")
    else:
        print(f"WARNING: no input files found for {src_name}")

static_path = out_root / "borusyak_velocity_static_effects_all.csv"
if static_path.exists():
    static = pd.read_csv(static_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in static.columns:
            static[f"{col}_pct"] = static[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(float(x)) - 1.0) * 100.0
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
    print(f"Saved: {out}")

    if {"panel", "outcome", "estimate_pct"}.issubset(paper.columns):
        wide = paper.pivot_table(
            index=["panel"],
            columns=["outcome"],
            values=["estimate_pct", "conf_low_pct", "conf_high_pct"],
            aggfunc="first",
        )
        wide.columns = ["_".join([str(x) for x in col if str(x) != ""]) for col in wide.columns]
        wide = wide.reset_index()
        out = summary_dir / "borusyak_velocity_static_effects_wide.csv"
        wide.to_csv(out, index=False)
        print(f"Saved: {out}")

dynamic_path = out_root / "borusyak_velocity_dynamic_effects_all.csv"
if dynamic_path.exists():
    dynamic = pd.read_csv(dynamic_path)

    for col in ["estimate", "conf_low", "conf_high"]:
        if col in dynamic.columns:
            dynamic[f"{col}_pct"] = dynamic[col].apply(
                lambda x: None if pd.isna(x) else (math.exp(float(x)) - 1.0) * 100.0
            )

    out = summary_dir / "borusyak_velocity_dynamic_effects_percent.csv"
    dynamic.to_csv(out, index=False)
    print(f"Saved: {out}")

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
    print(f"Saved: {out}")

notes = summary_dir / "borusyak_velocity_summary_notes.txt"
notes.write_text(
    "Python velocity Borusyak DiD completed for panel variants: "
    + ", ".join(labels)
    + ". Outcomes are log_commits and log_lines_added. "
    + "Static effects summarize average post-adoption treatment effects. "
    + "Dynamic effects use event-time horizons -6 to 6 with pretrend horizons -6 to -2. "
    + "Primary Python panels are flexible and strict; window-driven panels are diagnostic if included.\\n",
    encoding="utf-8",
)
print(f"Saved: {notes}")
PY

  echo
  echo "============================================================"
  echo "run-py-2h completed successfully."
  echo "Completed:       $(date)"
  echo "Output root:     ${OUT_ROOT}"
  echo "Summary dir:     ${SUMMARY_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
#
# Reused logic:
#   This wrapper is adapted from run9h-did-velocity-borusyak.sh.
#   It does not call the old JS/TS shell wrapper.
