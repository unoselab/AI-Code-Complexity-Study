#!/usr/bin/env Rscript

# Compare two Borusyak static DiD outcomes on the exact same fixed sample:
#   1. Original AGC-like regular module-function unique-body count.
#   2. The original count plus synchronous class-method counts for five
#      selected repositories identified by run-py-7m influence debugging.
#
# The input was prepared by run-py-7n. Sample membership is fixed by the
# original module-function outcome > 0 rule. Method-only positive months are
# intentionally not added. This isolates the outcome-value change from a
# sample-membership change.
#
# IMPORTANT:
#   This is supplementary selected-sample influence debugging. It is not a
#   primary causal estimand and must not be used to justify repository removal.
#
# Required environment variables:
#   PROJECT_ROOT           Project root directory.
#   PANEL_PATH             run-py-7n fixed-sample panel CSV.
#   RUN7N_CHECKS_PATH      run-py-7n QC checks CSV.
#   REFERENCE_STATIC_PATH  run-py-7h regular-only static result CSV.
#   HELPER_FILE            Borusyak helper R file.
#   OUT_DIR                Output directory.
#
# Optional environment variables:
#   NCLOC_SPEC             paper or python_snapshot. Default: python_snapshot
#   TIME_MODE              original_yyyymm or calendar_month. Default: calendar_month
#   MIN_TREATMENT_COHORT   Inclusive YYYYMM lower bound. Default: 202408
#   MAX_TREATMENT_COHORT   Inclusive YYYYMM upper bound. Default: 202503
#   REPRO_TOLERANCE        Baseline reproduction tolerance. Default: 1e-6

suppressPackageStartupMessages({
  library(data.table)
  library(didimputation)
})

get_env <- function(name, default = "", required = FALSE) {
  value <- Sys.getenv(name, unset = default)
  if (required && identical(value, "")) {
    stop("Required environment variable is missing: ", name)
  }
  value
}

resolve_path <- function(project_root, value) {
  if (identical(value, "")) {
    return("")
  }
  if (grepl("^/", value)) {
    return(normalizePath(value, mustWork = FALSE))
  }
  normalizePath(file.path(project_root, value), mustWork = FALSE)
}

normalize_yyyymm <- function(x) {
  x <- as.character(x)
  x[x %in% c("", "NA", "NaN", "NULL", "None")] <- NA_character_
  x <- gsub("-", "", x)
  suppressWarnings(as.integer(x))
}

yyyymm_to_month_id <- function(x) {
  x <- as.integer(x)
  year <- x %/% 100L
  month <- x %% 100L
  out <- year * 12L + month
  out[is.na(x) | month < 1L | month > 12L] <- NA_integer_
  out
}

require_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0) {
    stop(label, " missing required columns: ", paste(missing, collapse = ", "))
  }
}

as_logical_strict <- function(x, label) {
  normalized <- tolower(trimws(as.character(x)))
  out <- rep(NA, length(normalized))
  out[normalized %in% c("true", "t", "1", "1.0")] <- TRUE
  out[normalized %in% c("false", "f", "0", "0.0")] <- FALSE
  if (any(is.na(out))) {
    stop(label, " contains values that cannot be interpreted as logical.")
  }
  out
}

normal_two_sided_p <- function(estimate, std_error) {
  estimate <- suppressWarnings(as.numeric(estimate))
  std_error <- suppressWarnings(as.numeric(std_error))
  out <- rep(NA_real_, length(estimate))
  valid <- !is.na(estimate) & !is.na(std_error) & std_error > 0
  out[valid] <- 2 * pnorm(
    abs(estimate[valid] / std_error[valid]),
    lower.tail = FALSE
  )
  out
}

write_empty_error_table <- function(path) {
  fwrite(
    data.frame(
      model = character(),
      outcome = character(),
      error = character(),
      stringsAsFactors = FALSE
    ),
    path
  )
}

project_root <- normalizePath(
  get_env("PROJECT_ROOT", normalizePath(".", mustWork = TRUE)),
  mustWork = TRUE
)
panel_path <- resolve_path(
  project_root,
  get_env("PANEL_PATH", required = TRUE)
)
run7n_checks_path <- resolve_path(
  project_root,
  get_env("RUN7N_CHECKS_PATH", required = TRUE)
)
reference_static_path <- resolve_path(
  project_root,
  get_env("REFERENCE_STATIC_PATH", required = TRUE)
)
helper_path <- resolve_path(
  project_root,
  get_env("HELPER_FILE", required = TRUE)
)
out_dir <- resolve_path(
  project_root,
  get_env("OUT_DIR", required = TRUE)
)

ncloc_spec <- tolower(get_env("NCLOC_SPEC", "python_snapshot"))
time_mode <- tolower(get_env("TIME_MODE", "calendar_month"))
min_treatment_cohort <- as.integer(get_env("MIN_TREATMENT_COHORT", "202408"))
max_treatment_cohort <- as.integer(get_env("MAX_TREATMENT_COHORT", "202503"))
repro_tolerance <- as.numeric(get_env("REPRO_TOLERANCE", "0.000001"))

for (path in c(
  panel_path,
  run7n_checks_path,
  reference_static_path,
  helper_path
)) {
  if (!file.exists(path)) {
    stop("Required file not found: ", path)
  }
}
if (!(ncloc_spec %in% c("paper", "python_snapshot"))) {
  stop("NCLOC_SPEC must be paper or python_snapshot. Got: ", ncloc_spec)
}
if (!(time_mode %in% c("original_yyyymm", "calendar_month"))) {
  stop("TIME_MODE must be original_yyyymm or calendar_month. Got: ", time_mode)
}
if (any(is.na(c(min_treatment_cohort, max_treatment_cohort, repro_tolerance)))) {
  stop("Cohort bounds and reproduction tolerance must be numeric.")
}
if (repro_tolerance <= 0) {
  stop("REPRO_TOLERANCE must be positive.")
}

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
source(helper_path)

baseline_outcome <- "npr_agc_regular_module_function_unique_bodies"
hybrid_outcome <- "npr_agc_regfun_selected_classmethod_unique_bodies"
selected_flag <- "selected_classmethod_repository"
method_added_column <- "selected_repo_method_agc_unique_bodies"
overlap_column <- "selected_repo_module_method_agc_unique_body_overlap"

if (identical(ncloc_spec, "paper")) {
  ncloc_column <- "ncloc_paper"
  baseline_readiness <-
    "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
  hybrid_readiness <-
    "analysis_ready_regfun_selected_classmethod_agc_uniquebody_paper_ncloc"
} else {
  ncloc_column <- "ncloc_python_snapshot"
  baseline_readiness <-
    "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc"
  hybrid_readiness <- paste0(
    "analysis_ready_regfun_selected_classmethod_agc_uniquebody_",
    "python_snapshot_ncloc"
  )
}

covariates <- c(
  "log1p_age",
  ncloc_column,
  "log1p_contributors",
  "log1p_stars",
  "log1p_issues"
)

required_columns <- c(
  "dataset_source",
  "repo_name",
  "time",
  "event",
  "time_to_event",
  "has_parse_exclusion",
  "npr_detection_complete",
  "npr_specification",
  baseline_outcome,
  hybrid_outcome,
  selected_flag,
  method_added_column,
  overlap_column,
  baseline_readiness,
  hybrid_readiness,
  "sample_membership_fixed_to_run_py_7h",
  "causal_interpretation_allowed",
  "sample_restriction",
  covariates
)

cat("Project root:", project_root, "\n")
cat("Panel path:", panel_path, "\n")
cat("run-py-7n checks:", run7n_checks_path, "\n")
cat("Reference regular-only static result:", reference_static_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("NCLOC specification:", ncloc_spec, "\n")
cat("Time mode:", time_mode, "\n")
cat("Sample membership: fixed to original module-function outcome > 0\n")
cat("Appended methods: selected repositories only\n")
cat("WARNING: This is supplementary influence debugging, not a primary causal estimand.\n")

checks_upstream <- fread(run7n_checks_path)
require_columns(
  checks_upstream,
  c("check_name", "passed"),
  "run-py-7n checks"
)
checks_upstream[, passed_logical := as_logical_strict(passed, "run-py-7n passed")]
upstream_failed <- checks_upstream[passed_logical == FALSE]
if (nrow(upstream_failed) > 0) {
  stop("run-py-7n has failed upstream checks.")
}

panel_raw <- fread(panel_path)
require_columns(panel_raw, required_columns, "Input panel")

if (anyDuplicated(panel_raw[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Input panel has duplicate repository-month keys.")
}
if (!all(panel_raw$dataset_source %in% c("control", "treatment"))) {
  stop("dataset_source contains unexpected values.")
}
if (any(panel_raw$has_parse_exclusion != 0, na.rm = TRUE)) {
  stop("Parse-clean input unexpectedly contains parse-exclusion rows.")
}
if (any(as.character(panel_raw$npr_specification) != "range100_200")) {
  stop("Input contains an unexpected NPR specification.")
}
if (any(panel_raw[[baseline_outcome]] <= 0, na.rm = TRUE)) {
  stop("Fixed sample contains a nonpositive baseline outcome.")
}
if (any(panel_raw[[hybrid_outcome]] <= 0, na.rm = TRUE)) {
  stop("Fixed sample contains a nonpositive hybrid outcome.")
}
if (any(panel_raw[[hybrid_outcome]] < panel_raw[[baseline_outcome]], na.rm = TRUE)) {
  stop("Hybrid outcome is smaller than the baseline outcome.")
}
if (any(panel_raw[[method_added_column]] < 0, na.rm = TRUE)) {
  stop("Selected method count contains negative values.")
}
if (any(panel_raw[[overlap_column]] < 0, na.rm = TRUE)) {
  stop("Selected overlap count contains negative values.")
}

fixed_membership <- as_logical_strict(
  panel_raw$sample_membership_fixed_to_run_py_7h,
  "sample_membership_fixed_to_run_py_7h"
)
causal_allowed <- as_logical_strict(
  panel_raw$causal_interpretation_allowed,
  "causal_interpretation_allowed"
)
selected_logical <- as_logical_strict(
  panel_raw[[selected_flag]],
  selected_flag
)
detection_complete <- as_logical_strict(
  panel_raw$npr_detection_complete,
  "npr_detection_complete"
)

if (any(!fixed_membership)) {
  stop("Input is not uniformly fixed to the run-py-7h sample membership.")
}
if (any(causal_allowed)) {
  stop("Selected-sample input incorrectly permits causal interpretation.")
}
if (any(!detection_complete)) {
  stop("npr_detection_complete is not uniformly true.")
}
if (any(as.character(panel_raw$sample_restriction) !=
        "original_module_function_outcome > 0")) {
  stop("Input contains an unexpected sample restriction.")
}
if (any(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE)) {
  stop("Baseline and hybrid readiness indicators differ.")
}

panel_raw[, selected_logical := selected_logical]
panel_ready <- copy(panel_raw)
panel_ready <- panel_ready[
  get(baseline_readiness) == 1 & get(hybrid_readiness) == 1
]
panel_ready_before_cohort <- copy(panel_ready)

model_required <- c(baseline_outcome, hybrid_outcome, covariates)
missing_model_rows <- sum(!complete.cases(panel_ready[, ..model_required]))
if (missing_model_rows > 0) {
  stop("Analysis-ready rows contain missing outcome or covariate values: ", missing_model_rows)
}

panel_ready[, time_yyyymm := normalize_yyyymm(time)]
event_yyyymm <- normalize_yyyymm(panel_ready$event)
event_yyyymm[is.na(event_yyyymm)] <- 0L
panel_ready[, event_yyyymm := event_yyyymm]

membership_mismatch <- panel_ready[
  ,
  sum((dataset_source == "treatment") != (event_yyyymm > 0L))
]
if (membership_mismatch > 0) {
  stop("Event encoding disagrees with dataset_source on ", membership_mismatch, " rows.")
}

panel_ready <- panel_ready[
  event_yyyymm == 0L |
    (event_yyyymm >= min_treatment_cohort &
       event_yyyymm <= max_treatment_cohort)
]

if (identical(time_mode, "original_yyyymm")) {
  panel_ready[, time_id := time_yyyymm]
  panel_ready[, event_id := event_yyyymm]
  time_encoding_used <- "numeric_YYYYMM_original_notebook_compatible"
} else {
  panel_ready[, time_id := yyyymm_to_month_id(time_yyyymm)]
  panel_ready[, event_id := fifelse(
    event_yyyymm == 0L,
    0L,
    yyyymm_to_month_id(event_yyyymm)
  )]
  time_encoding_used <- "sequential_calendar_month_id"
}

panel_ready <- panel_ready[!is.na(time_id)]
panel_ready <- panel_ready[event_id == 0L | !is.na(event_id)]
panel_ready[, treated := as.integer(event_id > 0L)]
panel_ready[, repo_name_str := as.character(repo_name)]
panel_ready[, repo_id := as.integer(factor(repo_name_str))]
model_data <- copy(panel_ready)

if (nrow(model_data) == 0) {
  stop("No repository-months remain for modeling.")
}
if (anyDuplicated(model_data[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Model sample has duplicate repository-month keys.")
}

first_stage_formula <- as.formula(
  paste0(
    "~ ",
    paste(covariates, collapse = " + "),
    " | repo_id + time_id"
  )
)

cat("Input fixed-sample rows:", nrow(panel_raw), "\n")
cat("Rows excluded by readiness:", nrow(panel_raw) - nrow(panel_ready_before_cohort), "\n")
cat("Rows excluded by cohort/time filters:", nrow(panel_ready_before_cohort) - nrow(model_data), "\n")
cat("Model rows:", nrow(model_data), "\n")
cat("Model repositories:", uniqueN(model_data$repo_name_str), "\n")
cat("Treatment repositories:", uniqueN(model_data[dataset_source == "treatment", repo_name_str]), "\n")
cat("Control repositories:", uniqueN(model_data[dataset_source == "control", repo_name_str]), "\n")
cat("Baseline outcome total:", sum(model_data[[baseline_outcome]]), "\n")
cat("Hybrid outcome total:", sum(model_data[[hybrid_outcome]]), "\n")
cat("Net method bodies appended:", sum(model_data[[hybrid_outcome]] - model_data[[baseline_outcome]]), "\n")
cat("First-stage formula:\n")
print(first_stage_formula)

model_errors <- list()
run_static_model <- function(outcome_name, model_label) {
  error_message <- NA_character_
  result <- tryCatch(
    run_borusyak_static(
      data = model_data,
      outcome_var = outcome_name,
      first_stage_formula = first_stage_formula,
      idname = "repo_id",
      tname = "time_id",
      gname = "event_id"
    ),
    error = function(e) {
      error_message <<- conditionMessage(e)
      NULL
    }
  )
  if (!is.na(error_message)) {
    model_errors[[length(model_errors) + 1L]] <<- data.table(
      model = model_label,
      outcome = outcome_name,
      error = error_message
    )
  }
  extracted <- extract_static_result(result, outcome_name)
  if (nrow(extracted) > 0) {
    extracted$model <- model_label
    extracted$sample <- "original_regfun_positive_months_fixed"
    extracted$causal_interpretation_allowed <- FALSE
    extracted$p_value_approx <- normal_two_sided_p(
      extracted$estimate,
      extracted$std_error
    )
  }
  extracted
}

baseline_static <- run_static_model(baseline_outcome, "regular_module_function_baseline")
hybrid_static <- run_static_model(hybrid_outcome, "selected_classmethod_hybrid")

static_complete <- function(df) {
  nrow(df) == 1 &&
    all(!is.na(df[, c("estimate", "std_error", "conf_low", "conf_high")]))
}

reference_static <- fread(reference_static_path)
require_columns(
  reference_static,
  c("estimate", "std_error", "conf_low", "conf_high"),
  "run-py-7h reference static result"
)
if (nrow(reference_static) != 1) {
  stop("run-py-7h reference static result must contain exactly one row.")
}

baseline_reference_difference <- if (static_complete(baseline_static)) {
  max(abs(c(
    baseline_static$estimate - reference_static$estimate,
    baseline_static$std_error - reference_static$std_error,
    baseline_static$conf_low - reference_static$conf_low,
    baseline_static$conf_high - reference_static$conf_high
  )))
} else {
  Inf
}

if (baseline_reference_difference > repro_tolerance) {
  stop(
    "Baseline model does not reproduce run-py-7h within tolerance. Max difference: ",
    format(baseline_reference_difference, scientific = TRUE)
  )
}

comparison <- data.frame(
  baseline_estimate = baseline_static$estimate,
  baseline_std_error = baseline_static$std_error,
  baseline_conf_low = baseline_static$conf_low,
  baseline_conf_high = baseline_static$conf_high,
  baseline_p_value_approx = baseline_static$p_value_approx,
  hybrid_estimate = hybrid_static$estimate,
  hybrid_std_error = hybrid_static$std_error,
  hybrid_conf_low = hybrid_static$conf_low,
  hybrid_conf_high = hybrid_static$conf_high,
  hybrid_p_value_approx = hybrid_static$p_value_approx,
  delta_estimate = hybrid_static$estimate - baseline_static$estimate,
  delta_std_error = hybrid_static$std_error - baseline_static$std_error,
  delta_conf_low = hybrid_static$conf_low - baseline_static$conf_low,
  delta_conf_high = hybrid_static$conf_high - baseline_static$conf_high,
  hybrid_ci_includes_zero = (
    hybrid_static$conf_low <= 0 & hybrid_static$conf_high >= 0
  ),
  hybrid_ci_strictly_positive = hybrid_static$conf_low > 0,
  hybrid_ci_strictly_negative = hybrid_static$conf_high < 0,
  selected_repository_count = uniqueN(
    model_data[selected_logical == TRUE, repo_name_str]
  ),
  model_rows = nrow(model_data),
  model_repositories = uniqueN(model_data$repo_name_str),
  stringsAsFactors = FALSE
)
comparison$confidence_interval_verdict <- ifelse(
  comparison$hybrid_ci_strictly_positive,
  "HYBRID_95CI_EXCLUDES_ZERO_POSITIVE",
  ifelse(
    comparison$hybrid_ci_strictly_negative,
    "HYBRID_95CI_EXCLUDES_ZERO_NEGATIVE",
    "HYBRID_95CI_INCLUDES_ZERO"
  )
)

selected_repo_summary <- model_data[
  selected_logical == TRUE,
  .(
    dataset_source = first(dataset_source),
    model_rows = .N,
    pre_event_rows = sum(!is.na(time_to_event) & time_to_event < 0),
    event_and_post_rows = sum(!is.na(time_to_event) & time_to_event >= 0),
    baseline_outcome_total = sum(get(baseline_outcome)),
    selected_method_bodies_total = sum(get(method_added_column)),
    selected_overlap_total = sum(get(overlap_column)),
    net_appended_bodies = sum(get(hybrid_outcome) - get(baseline_outcome)),
    hybrid_outcome_total = sum(get(hybrid_outcome)),
    maximum_baseline_outcome = max(get(baseline_outcome)),
    maximum_hybrid_outcome = max(get(hybrid_outcome))
  ),
  by = repo_name_str
]
setnames(selected_repo_summary, "repo_name_str", "repo_name")
setorder(selected_repo_summary, -net_appended_bodies, repo_name)

filter_summary <- data.frame(
  metric = c(
    "input_fixed_sample_rows",
    "input_repositories",
    "readiness_rows_excluded",
    "cohort_or_time_rows_excluded",
    "model_rows",
    "model_repositories",
    "treatment_repositories",
    "control_repositories",
    "selected_repositories_in_model",
    "baseline_outcome_total",
    "hybrid_outcome_total",
    "net_appended_bodies"
  ),
  value = c(
    nrow(panel_raw),
    uniqueN(panel_raw$repo_name),
    nrow(panel_raw) - nrow(panel_ready_before_cohort),
    nrow(panel_ready_before_cohort) - nrow(model_data),
    nrow(model_data),
    uniqueN(model_data$repo_name_str),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    uniqueN(model_data[selected_logical == TRUE, repo_name_str]),
    sum(model_data[[baseline_outcome]]),
    sum(model_data[[hybrid_outcome]]),
    sum(model_data[[hybrid_outcome]] - model_data[[baseline_outcome]])
  ),
  stringsAsFactors = FALSE
)

errors <- if (length(model_errors) == 0) {
  data.table(model = character(), outcome = character(), error = character())
} else {
  rbindlist(model_errors, fill = TRUE)
}

validation <- data.frame(
  check = c(
    "run7n_upstream_checks_all_pass",
    "input_rows_match_expected_fixed_sample",
    "input_repositories_match_expected",
    "input_baseline_outcome_strictly_positive",
    "input_hybrid_outcome_strictly_positive",
    "input_membership_fixed_to_run7h",
    "input_labeled_noncausal",
    "baseline_hybrid_readiness_identical",
    "model_rows_match_expected",
    "model_treatment_repositories_match_expected",
    "model_control_repositories_match_expected",
    "selected_repositories_match_expected",
    "net_appended_bodies_match_expected",
    "baseline_model_error_count",
    "hybrid_model_error_count",
    "baseline_static_result_complete",
    "hybrid_static_result_complete",
    "baseline_reproduces_run7h_within_tolerance",
    "comparison_verdict_available"
  ),
  value = c(
    nrow(upstream_failed),
    nrow(panel_raw),
    uniqueN(panel_raw$repo_name),
    sum(panel_raw[[baseline_outcome]] <= 0),
    sum(panel_raw[[hybrid_outcome]] <= 0),
    sum(!fixed_membership),
    sum(causal_allowed),
    sum(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE),
    nrow(model_data),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    uniqueN(model_data[selected_logical == TRUE, repo_name_str]),
    sum(model_data[[hybrid_outcome]] - model_data[[baseline_outcome]]),
    nrow(errors[model == "regular_module_function_baseline"]),
    nrow(errors[model == "selected_classmethod_hybrid"]),
    static_complete(baseline_static),
    static_complete(hybrid_static),
    baseline_reference_difference,
    nrow(comparison) == 1 && comparison$confidence_interval_verdict != ""
  ),
  passed = c(
    nrow(upstream_failed) == 0,
    nrow(panel_raw) == 487,
    uniqueN(panel_raw$repo_name) == 132,
    sum(panel_raw[[baseline_outcome]] <= 0) == 0,
    sum(panel_raw[[hybrid_outcome]] <= 0) == 0,
    sum(!fixed_membership) == 0,
    sum(causal_allowed) == 0,
    sum(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE) == 0,
    nrow(model_data) == 486,
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]) == 75,
    uniqueN(model_data[dataset_source == "control", repo_name_str]) == 57,
    uniqueN(model_data[selected_logical == TRUE, repo_name_str]) == 5,
    sum(model_data[[hybrid_outcome]] - model_data[[baseline_outcome]]) == 825,
    nrow(errors[model == "regular_module_function_baseline"]) == 0,
    nrow(errors[model == "selected_classmethod_hybrid"]) == 0,
    static_complete(baseline_static),
    static_complete(hybrid_static),
    baseline_reference_difference <= repro_tolerance,
    nrow(comparison) == 1 && comparison$confidence_interval_verdict != ""
  ),
  stringsAsFactors = FALSE
)

overall_pass <- all(validation$passed)

metadata <- data.frame(
  key = c(
    "script",
    "panel_path",
    "run7n_checks_path",
    "reference_static_path",
    "helper_file",
    "output_directory",
    "baseline_outcome",
    "hybrid_outcome",
    "sample_membership_rule",
    "selected_repository_count",
    "causal_interpretation_allowed",
    "ncloc_spec",
    "ncloc_column",
    "time_mode",
    "time_encoding",
    "first_stage_formula",
    "treatment_cohort_min",
    "treatment_cohort_max",
    "reproduction_tolerance"
  ),
  value = c(
    "proc_r/did_regfun_selected_classmethod_agc_uniquebody_fixed_sample.R",
    panel_path,
    run7n_checks_path,
    reference_static_path,
    helper_path,
    out_dir,
    baseline_outcome,
    hybrid_outcome,
    "original_module_function_outcome > 0",
    uniqueN(model_data[selected_logical == TRUE, repo_name_str]),
    "FALSE",
    ncloc_spec,
    ncloc_column,
    time_mode,
    time_encoding_used,
    paste(deparse(first_stage_formula), collapse = " "),
    min_treatment_cohort,
    max_treatment_cohort,
    repro_tolerance
  ),
  stringsAsFactors = FALSE
)

prefix <- "borusyak_regfun_selected_classmethod_agc_uniquebody_fixed_sample"

fwrite(
  baseline_static,
  file.path(out_dir, paste0(prefix, "_baseline_static_effects.csv"))
)
fwrite(
  hybrid_static,
  file.path(out_dir, paste0(prefix, "_hybrid_static_effects.csv"))
)
fwrite(
  comparison,
  file.path(out_dir, paste0(prefix, "_static_comparison.csv"))
)
fwrite(
  selected_repo_summary,
  file.path(out_dir, paste0(prefix, "_selected_repo_summary.csv"))
)
fwrite(
  filter_summary,
  file.path(out_dir, paste0(prefix, "_filter_summary.csv"))
)
fwrite(
  validation,
  file.path(out_dir, paste0(prefix, "_validation.csv"))
)
fwrite(
  metadata,
  file.path(out_dir, paste0(prefix, "_metadata.csv"))
)

error_path <- file.path(out_dir, paste0(prefix, "_model_errors.csv"))
if (nrow(errors) == 0) {
  write_empty_error_table(error_path)
} else {
  fwrite(errors, error_path)
}

status_path <- file.path(out_dir, paste0(prefix, "_status.txt"))
writeLines(
  c(
    paste0("status=", if (overall_pass) "PASS" else "FAIL"),
    paste0("model_rows=", nrow(model_data)),
    paste0("model_repositories=", uniqueN(model_data$repo_name_str)),
    paste0("selected_repositories=", uniqueN(model_data[selected_logical == TRUE, repo_name_str])),
    paste0("net_appended_bodies=", sum(model_data[[hybrid_outcome]] - model_data[[baseline_outcome]])),
    paste0("baseline_reference_max_abs_difference=", format(baseline_reference_difference, scientific = TRUE)),
    paste0("hybrid_conf_low=", comparison$hybrid_conf_low),
    paste0("hybrid_conf_high=", comparison$hybrid_conf_high),
    paste0("hybrid_ci_includes_zero=", toupper(as.character(comparison$hybrid_ci_includes_zero))),
    paste0("confidence_interval_verdict=", comparison$confidence_interval_verdict),
    "sample_membership_fixed_to_run_py_7h=TRUE",
    "causal_interpretation_allowed=FALSE"
  ),
  status_path
)

cat("\nBaseline static result:\n")
print(baseline_static)
cat("\nHybrid static result:\n")
print(hybrid_static)
cat("\nStatic comparison:\n")
print(comparison)
cat("\nSelected repository summary:\n")
print(selected_repo_summary)
cat("\nValidation:\n")
print(validation)

if (!overall_pass) {
  stop("Fixed-sample selected-classmethod DiD comparison failed validation.")
}

cat("\nFixed-sample selected-classmethod DiD comparison completed successfully.\n")
