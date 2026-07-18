# cp DiffInDiffBorusyak_AGC_ChangedBlock_ActivityCheck-v1.Rmd \
#   proc_r/DiffInDiffBorusyak_AGC_ChangedBlock_ActivityCheck.Rmd

mkdir -p repo_python/run-py-4c/strict/activity-check

Rscript -e 'rmarkdown::render(
  input="proc_r/DiffInDiffBorusyak_AGC_ChangedBlock_ActivityCheck.Rmd",
  params=list(
    panel_file="repo_python/run-py-4a/strict/panel_event_monthly_agc_changed_block_py.csv",
    output_dir="repo_python/run-py-4c/strict/activity-check",
    apply_original_event_filter=TRUE
  ),
  output_file="DiffInDiffBorusyak_AGC_ChangedBlock_ActivityCheck.html",
  output_dir="repo_python/run-py-4c/strict/activity-check",
  knit_root_dir=getwd(),
  envir=new.env(parent=globalenv())
)'
