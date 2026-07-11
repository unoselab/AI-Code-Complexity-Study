#!/usr/bin/env bash
set -euo pipefail

# Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd')"
Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd', params = list(panel_file = '../repo_python/run-py-2e/strict/panel_event_monthly_quality_py.csv'))"
