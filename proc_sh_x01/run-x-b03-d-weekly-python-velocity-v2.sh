#!/usr/bin/env bash
# 
# Run:
# bash proc_sh_x01/run-x-b03-d-weekly-python-velocity-v2.sh
# 

set -euo pipefail

RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PYTHON_BIN="${PYTHON_BIN:-python}"

WEEKLY_PANEL="${WEEKLY_PANEL:-run-x-b03-d/panels/velocity_did_panel_python_added_lines_weekly_chicago.csv}"
MONTHLY_TREATMENT="${MONTHLY_TREATMENT:-ts_repos_monthly.csv}"
MONTHLY_CONTROL="${MONTHLY_CONTROL:-ts_repos_control_monthly.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-run-x-b03-d-v2/weekly_did}"
R_SCRIPT="${R_SCRIPT:-did_borusyak_velocity_python_added_lines_weekly-v2.R}"
PLOT_SCRIPT="${PLOT_SCRIPT:-plot_did_velocity_python_weekly-v2.py}"
PLOT_PREFIX="${PLOT_PREFIX:-fig_did_velocity_python_weekly-v2}"

mkdir -p "${OUTPUT_DIR}"

"${RSCRIPT_BIN}" "${R_SCRIPT}" \
  --weekly-panel "${WEEKLY_PANEL}" \
  --monthly-treatment "${MONTHLY_TREATMENT}" \
  --monthly-control "${MONTHLY_CONTROL}" \
  --output-dir "${OUTPUT_DIR}" \
  --calendar-key chicago \
  --strict-expected-counts true \
  --expected-treatment-repos 63 \
  --expected-control-repos 104

# "${PYTHON_BIN}" "${PLOT_SCRIPT}" \
#   "${OUTPUT_DIR}/velocity_python_added_lines_weekly_v2_dynamic_effects.csv" \
#   --output-prefix "${PLOT_PREFIX}"

# printf 'Weekly dynamic CSV: %s\n' "${OUTPUT_DIR}/velocity_python_added_lines_weekly_v2_dynamic_effects.csv"
# printf 'Weekly figure PDF: %s\n' "${PLOT_PREFIX}.pdf"
# printf 'Weekly figure PNG: %s\n' "${PLOT_PREFIX}.png"
