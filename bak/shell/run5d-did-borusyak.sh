export PROJECT_ROOT="$(pwd)"

Rscript -e "rmarkdown::render(
  'proc_r/DiffInDiffBorusyak_v2.Rmd',
  output_dir = 'tmp_adoption_test/data/python_did_test/activity_did_smoke_borusyak_v2',
  envir = new.env()
)"