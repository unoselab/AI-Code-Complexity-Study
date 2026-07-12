#!/usr/bin/env bash
set -euo pipefail

# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd')"
# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd', params = list(panel_file = '../repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv'))"

OUTPUT_SUFFIX="${OUTPUT_SUFFIX:-python_only}"
PANEL_FILE="${PANEL_FILE:-../repo_python/run-py-2e/strict/panel_event_monthly_quality_py_${OUTPUT_SUFFIX}.csv}"
HTML_OUTPUT="${HTML_OUTPUT:-DiffInDiffBorusyak_${OUTPUT_SUFFIX}.html}"
BORUSYAK_PDF="${BORUSYAK_PDF:-../proc_r/dynamic_effects_borusyak_${OUTPUT_SUFFIX}.pdf}"
PYTHON_GROUP_PDF="${PYTHON_GROUP_PDF:-../proc_r/dynamic_effects_python_group_${OUTPUT_SUFFIX}.pdf}"

Rscript - "${PANEL_FILE}" "${HTML_OUTPUT}" "${BORUSYAK_PDF}" "${PYTHON_GROUP_PDF}" <<'RS'
args <- commandArgs(trailingOnly = TRUE)
rmarkdown::render(
  input = "proc_r/DiffInDiffBorusyak.Rmd",
  output_file = args[[2]],
  output_dir = "proc_r",
  params = list(
    panel_file = args[[1]],
    borusyak_pdf_file = args[[3]],
    python_group_pdf_file = args[[4]]
  )
)
RS
