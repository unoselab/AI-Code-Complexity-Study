# PROJECT_ROOT="$(pwd)" \
# PANEL_PATH="repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function.csv" \
# OUT_DIR="repo_python/run-py-5f/strict/full/paper_ncloc/calendar_month" \
# PANEL_LABEL="strict_full_paper_ncloc" \
# NCLOC_SPEC="paper" \
# SAMPLE_TYPE="full" \
# TIME_MODE="calendar_month" \
# HELPER_FILE="proc_r/diff_in_diff_borusyak_helpers.R" \
# Rscript -e "rmarkdown::render(
#   input = 'proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd',
#   output_file = 'DiffInDiffBorusyak_agc_commit_function.html',
#   output_dir = Sys.getenv('OUT_DIR'),
#   knit_root_dir = Sys.getenv('PROJECT_ROOT'),
#   envir = new.env(parent = globalenv()),
#   quiet = FALSE
# )"

# PROJECT_ROOT="$(pwd)" \
# PANEL_PATH="repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function.csv" \
# OUT_DIR="repo_python/run-py-5f/strict/full/python_snapshot_ncloc/calendar_month" \
# PANEL_LABEL="strict_full_python_snapshot_ncloc" \
# NCLOC_SPEC="python_snapshot" \
# SAMPLE_TYPE="full" \
# TIME_MODE="calendar_month" \
# HELPER_FILE="proc_r/diff_in_diff_borusyak_helpers.R" \
# Rscript -e "rmarkdown::render(
#   input = 'proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd',
#   output_file = 'DiffInDiffBorusyak_agc_commit_function.html',
#   output_dir = Sys.getenv('OUT_DIR'),
#   knit_root_dir = Sys.getenv('PROJECT_ROOT'),
#   envir = new.env(parent = globalenv()),
#   quiet = FALSE
# )"

# PROJECT_ROOT="$(pwd)" \
# PANEL_PATH="repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function_ratio_positive.csv" \
# OUT_DIR="repo_python/run-py-5f/strict/ratio/paper_ncloc/calendar_month" \
# PANEL_LABEL="strict_ratio_paper_ncloc" \
# NCLOC_SPEC="paper" \
# SAMPLE_TYPE="ratio" \
# TIME_MODE="calendar_month" \
# HELPER_FILE="proc_r/diff_in_diff_borusyak_helpers.R" \
# Rscript -e "rmarkdown::render(
#   input = 'proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd',
#   output_file = 'DiffInDiffBorusyak_agc_commit_function.html',
#   output_dir = Sys.getenv('OUT_DIR'),
#   knit_root_dir = Sys.getenv('PROJECT_ROOT'),
#   envir = new.env(parent = globalenv()),
#   quiet = FALSE
# )"

PROJECT_ROOT="$(pwd)" \
PANEL_PATH="repo_python/run-py-5e/strict/panel_event_monthly_agc_commit_function_ratio_positive.csv" \
OUT_DIR="repo_python/run-py-5f/strict/ratio/python_snapshot_ncloc/calendar_month" \
PANEL_LABEL="strict_ratio_python_snapshot_ncloc" \
NCLOC_SPEC="python_snapshot" \
SAMPLE_TYPE="ratio" \
TIME_MODE="calendar_month" \
HELPER_FILE="proc_r/diff_in_diff_borusyak_helpers.R" \
Rscript -e "rmarkdown::render(
  input = 'proc_r/DiffInDiffBorusyak_agc_commit_function.Rmd',
  output_file = 'DiffInDiffBorusyak_agc_commit_function.html',
  output_dir = Sys.getenv('OUT_DIR'),
  knit_root_dir = Sys.getenv('PROJECT_ROOT'),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)"
