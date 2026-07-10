#!/usr/bin/env bash
set -euo pipefail

Rscript -e "rmarkdown::render('proc_r/DiffInDiffBorusyak.Rmd')"

