#!/usr/bin/env Rscript

# run-py-7m: Leave-one-repository-out influence analysis for the static
# Borusyak estimate from run-py-7k.
#
# Function scope:
#   - module_function
#   - method
#
# Sample:
#   - parse-clean repository-months
#   - realized combined AGC unique-body outcome > 0
#
# IMPORTANT:
#   This is a debugging and influence-analysis stage for a selected-sample
#   sensitivity analysis. It must not be interpreted as a primary causal model,
#   and influential repositories must not be removed merely to obtain
#   statistical significance.
#
# Required environment variables:
#   PROJECT_ROOT          Project root directory.
#   PANEL_PATH            run-py-7j positive-outcome parse-clean panel.
#   RUN7J_CHECKS_PATH     run-py-7j QC checks CSV.
#   HELPER_FILE           Borusyak helper R file.
#   REFERENCE_STATIC_PATH run-py-7k static-effects CSV.
#   OUT_DIR               Output directory.
#
# Optional environment variables:
#   NCLOC_SPEC            paper or python_snapshot. Default: python_snapshot
#   TIME_MODE             original_yyyymm or calendar_month. Default: calendar_month
#   MIN_TREATMENT_COHORT  Inclusive YYYYMM lower bound. Default: 202408
#   MAX_TREATMENT_COHORT  Inclusive YYYYMM upper bound. Default: 202503
#   PROGRESS_EVERY        Progress interval. Default: 10
#   TOP_N                 Rows in ranked outputs. Default: 20
#   REPRODUCTION_TOLERANCE Full-model reproduction tolerance. Default: 1e-6

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

safe_numeric <- function(x) {
  suppressWarnings(as.numeric(x))
}

normal_two_sided_p <- function(estimate, std_error) {
  estimate <- safe_numeric(estimate)
  std_error <- safe_numeric(std_error)
  out <- rep(NA_real_, length(estimate))
  valid <- !is.na(estimate) & !is.na(std_error) & std_error > 0
  out[valid] <- 2 * pnorm(
    abs(estimate[valid] / std_error[valid]),
    lower.tail = FALSE
  )
  out
}

as_logical_strict <- function(x, label) {
  normalized <- tolower(trimws(as.character(x)))
  out <- rep(NA, length(normalized))
  out[normalized %in% c("true", "t", "1", "1.0")] <- TRUE
  out[normalized %in% c("false", "f", "0", "0.0")] <- FALSE
  if (any(is.na(out))) {
    stop(label, " contains values that cannot be interpreted as Boolean.")
  }
  out
}

run_static_model <- function(model_data, outcome_var, first_stage_formula) {
  result <- run_borusyak_static(
    data = model_data,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  )

  extracted <- extract_static_result(result, outcome_var)
  if (nrow(extracted) != 1) {
    stop("Static model must return exactly one extracted row. Found: ", nrow(extracted))
  }
  extracted
}

project_root <- normalizePath(
  get_env("PROJECT_ROOT", normalizePath(".", mustWork = TRUE)),
  mustWork = TRUE
)
panel_path <- resolve_path(
  project_root,
  get_env("PANEL_PATH", required = TRUE)
)
run7j_checks_path <- resolve_path(
  project_root,
  get_env("RUN7J_CHECKS_PATH", required = TRUE)
)
helper_path <- resolve_path(
  project_root,
  get_env("HELPER_FILE", required = TRUE)
)
reference_static_path <- resolve_path(
  project_root,
  get_env("REFERENCE_STATIC_PATH", required = TRUE)
)
out_dir <- resolve_path(
  project_root,
  get_env("OUT_DIR", required = TRUE)
)

ncloc_spec <- tolower(get_env("NCLOC_SPEC", "python_snapshot"))
time_mode <- tolower(get_env("TIME_MODE", "calendar_month"))
min_treatment_cohort <- as.integer(get_env("MIN_TREATMENT_COHORT", "202408"))
max_treatment_cohort <- as.integer(get_env("MAX_TREATMENT_COHORT", "202503"))
progress_every <- as.integer(get_env("PROGRESS_EVERY", "10"))
top_n <- as.integer(get_env("TOP_N", "20"))
reproduction_tolerance <- as.numeric(
  get_env("REPRODUCTION_TOLERANCE", "0.000001")
)

for (required_path in c(
  panel_path,
  run7j_checks_path,
  helper_path,
  reference_static_path
)) {
  if (!file.exists(required_path)) {
    stop("Required file not found: ", required_path)
  }
}
if (!(ncloc_spec %in% c("paper", "python_snapshot"))) {
  stop("NCLOC_SPEC must be paper or python_snapshot. Got: ", ncloc_spec)
}
if (!(time_mode %in% c("original_yyyymm", "calendar_month"))) {
  stop("TIME_MODE must be original_yyyymm or calendar_month. Got: ", time_mode)
}
if (is.na(min_treatment_cohort) || is.na(max_treatment_cohort)) {
  stop("Treatment cohort bounds must be integers.")
}
if (is.na(progress_every) || progress_every < 1) {
  stop("PROGRESS_EVERY must be a positive integer.")
}
if (is.na(top_n) || top_n < 1) {
  stop("TOP_N must be a positive integer.")
}
if (is.na(reproduction_tolerance) || reproduction_tolerance < 0) {
  stop("REPRODUCTION_TOLERANCE must be nonnegative.")
}

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
source(helper_path)

outcome_var <-
  "npr_agc_regular_module_function_and_class_method_unique_bodies"
occurrence_var <-
  "has_npr_agc_regular_module_function_and_class_method_unique_body"
zero_var <-
  "zero_npr_agc_regular_module_function_and_class_method_unique_body_month"

if (identical(ncloc_spec, "paper")) {
  ncloc_column <- "ncloc_paper"
  readiness_column <- paste0(
    "analysis_ready_regular_module_function_and_class_method_",
    "agc_unique_body_paper_ncloc"
  )
} else {
  ncloc_column <- "ncloc_python_snapshot"
  readiness_column <- paste0(
    "analysis_ready_regular_module_function_and_class_method_",
    "agc_unique_body_python_snapshot_ncloc"
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
  "regular_function_scope",
  "included_function_kinds",
  "agc_count_unit",
  "agc_outcome_scale",
  "sample_restriction",
  "causal_interpretation_allowed",
  outcome_var,
  occurrence_var,
  zero_var,
  readiness_column,
  covariates
)

cat("Project root:", project_root, "\n")
cat("Panel path:", panel_path, "\n")
cat("run-py-7j checks:", run7j_checks_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Reference static result:", reference_static_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("NCLOC specification:", ncloc_spec, "\n")
cat("Time mode:", time_mode, "\n")
cat("Included function kinds: module_function, method\n")
cat("Sample restriction: outcome > 0\n")
cat("Analysis: static leave-one-repository-out influence debugging\n")
cat(
  "WARNING: This is a supplementary selected-sample influence analysis, not a primary causal estimand.\n"
)

run7j_checks <- fread(run7j_checks_path)
require_columns(run7j_checks, c("check_name", "passed"), "run-py-7j checks")
run7j_checks[, passed_logical := as_logical_strict(passed, "run-py-7j passed")]
upstream_failed_checks <- run7j_checks[passed_logical != TRUE]
if (nrow(upstream_failed_checks) > 0) {
  stop(
    "run-py-7j contains failed QC checks: ",
    paste(upstream_failed_checks$check_name, collapse = ", ")
  )
}

panel_raw <- fread(panel_path)
require_columns(panel_raw, required_columns, "Input panel")

if (anyDuplicated(panel_raw[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Input panel has duplicate dataset_source/repo_name/time keys.")
}
if (!all(panel_raw$dataset_source %in% c("control", "treatment"))) {
  stop("dataset_source contains unexpected values.")
}
if (any(panel_raw$has_parse_exclusion != 0, na.rm = TRUE)) {
  stop("Positive parse-clean input unexpectedly contains parse-exclusion rows.")
}
if (any(is.na(panel_raw[[outcome_var]]))) {
  stop("Outcome contains missing values.")
}
if (any(panel_raw[[outcome_var]] <= 0, na.rm = TRUE)) {
  stop("Positive-outcome input contains a zero or negative outcome.")
}
if (any(as.integer(panel_raw[[occurrence_var]]) != 1L, na.rm = TRUE)) {
  stop("Positive-outcome indicator is not uniformly one.")
}
if (any(as.integer(panel_raw[[zero_var]]) != 0L, na.rm = TRUE)) {
  stop("Zero-outcome indicator is not uniformly zero.")
}
if (any(as.character(panel_raw$npr_specification) != "range100_200")) {
  stop("Input contains an unexpected NPR specification.")
}
if (any(as.character(panel_raw$regular_function_scope) != "module_function+method")) {
  stop("Input contains an unexpected regular-function scope.")
}
if (any(as.character(panel_raw$included_function_kinds) != "module_function;method")) {
  stop("Input contains unexpected included function kinds.")
}
if (any(as.character(panel_raw$agc_outcome_scale) != "raw_count")) {
  stop("Input contains an unexpected AGC outcome scale.")
}
if (any(as.character(panel_raw$sample_restriction) != "outcome > 0")) {
  stop("Input contains an unexpected sample restriction.")
}
causal_allowed <- as_logical_strict(
  panel_raw$causal_interpretation_allowed,
  "causal_interpretation_allowed"
)
if (any(causal_allowed)) {
  stop("Selected-sample input incorrectly permits causal interpretation.")
}

detection_complete <- panel_raw$npr_detection_complete %in%
  c(TRUE, 1L, 1.0, "True", "TRUE", "true", "1", "1.0")
if (any(!detection_complete)) {
  stop("npr_detection_complete is not uniformly true.")
}

panel_ready <- copy(panel_raw)
panel_ready <- panel_ready[get(readiness_column) == 1]

model_required <- c(outcome_var, covariates)
missing_model_rows <- sum(!complete.cases(panel_ready[, ..model_required]))
if (missing_model_rows > 0) {
  stop(
    "Analysis-ready rows contain missing outcome or covariate values: ",
    missing_model_rows
  )
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

panel_ready_before_cohort <- copy(panel_ready)
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

model_data <- copy(panel_ready)
if (nrow(model_data) == 0) {
  stop("No positive-outcome repository-months remain for modeling.")
}
if (any(model_data[[outcome_var]] <= 0)) {
  stop("Model sample contains a nonpositive outcome.")
}
if (uniqueN(model_data[dataset_source == "treatment", repo_name_str]) == 0) {
  stop("No treated repositories remain in the model sample.")
}
if (uniqueN(model_data[dataset_source == "control", repo_name_str]) == 0) {
  stop("No control repositories remain in the model sample.")
}

model_data[, repo_id := as.integer(factor(repo_name_str))]
first_stage_formula <- as.formula(
  paste0(
    "~ ",
    paste(covariates, collapse = " + "),
    " | repo_id + time_id"
  )
)

cat("Input positive parse-clean rows:", nrow(panel_raw), "\n")
cat("Rows excluded by readiness:", nrow(panel_raw) - nrow(panel_ready_before_cohort), "\n")
cat("Rows excluded by cohort filter:", nrow(panel_ready_before_cohort) - nrow(panel_ready), "\n")
cat("Model rows:", nrow(model_data), "\n")
cat("Model repositories:", uniqueN(model_data$repo_name_str), "\n")
cat(
  "Treatment repositories:",
  uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
  "\n"
)
cat(
  "Control repositories:",
  uniqueN(model_data[dataset_source == "control", repo_name_str]),
  "\n"
)
cat("First-stage formula:\n")
print(first_stage_formula)

full_row <- run_static_model(
  model_data = model_data,
  outcome_var = outcome_var,
  first_stage_formula = first_stage_formula
)

full_estimate <- safe_numeric(full_row$estimate[1])
full_std_error <- safe_numeric(full_row$std_error[1])
full_conf_low <- safe_numeric(full_row$conf_low[1])
full_conf_high <- safe_numeric(full_row$conf_high[1])
full_p_value_approx <- normal_two_sided_p(full_estimate, full_std_error)

cat("Full-model static estimate:", full_estimate, "\n")
cat("Full-model standard error:", full_std_error, "\n")
cat("Full-model 95% CI:", full_conf_low, "to", full_conf_high, "\n")
cat("Full-model approximate two-sided p-value:", full_p_value_approx, "\n")

reference_static <- fread(reference_static_path)
require_columns(
  reference_static,
  c("estimate", "std_error", "conf_low", "conf_high"),
  "Reference static results"
)
if (nrow(reference_static) != 1) {
  stop("Reference static file must contain exactly one row. Found: ", nrow(reference_static))
}

reference_estimate <- safe_numeric(reference_static$estimate[1])
reference_std_error <- safe_numeric(reference_static$std_error[1])
reference_conf_low <- safe_numeric(reference_static$conf_low[1])
reference_conf_high <- safe_numeric(reference_static$conf_high[1])
reference_max_abs_difference <- max(abs(c(
  full_estimate - reference_estimate,
  full_std_error - reference_std_error,
  full_conf_low - reference_conf_low,
  full_conf_high - reference_conf_high
)))

if (is.na(reference_max_abs_difference) ||
    reference_max_abs_difference > reproduction_tolerance) {
  stop(
    "Full-model reproduction differs from run-py-7k reference by ",
    reference_max_abs_difference,
    ", exceeding tolerance ",
    reproduction_tolerance,
    "."
  )
}
cat(
  "Full-model reproduction against run-py-7k: PASS; max abs difference = ",
  reference_max_abs_difference,
  "\n",
  sep = ""
)

repo_profile <- model_data[, .(
  dataset_source = unique(dataset_source)[1],
  rows_removed = .N,
  total_outcome_removed = sum(get(outcome_var), na.rm = TRUE),
  mean_outcome_removed = mean(get(outcome_var), na.rm = TRUE),
  median_outcome_removed = as.numeric(median(get(outcome_var), na.rm = TRUE)),
  maximum_monthly_outcome_removed = max(get(outcome_var), na.rm = TRUE),
  untreated_rows_removed = sum(
    dataset_source == "control" |
      (dataset_source == "treatment" & time_to_event < 0),
    na.rm = TRUE
  ),
  treated_post_rows_removed = sum(
    dataset_source == "treatment" & time_to_event >= 0,
    na.rm = TRUE
  ),
  pre_treatment_outcome_removed = sum(
    fifelse(
      dataset_source == "treatment" & time_to_event < 0,
      get(outcome_var),
      0
    ),
    na.rm = TRUE
  ),
  post_treatment_outcome_removed = sum(
    fifelse(
      dataset_source == "treatment" & time_to_event >= 0,
      get(outcome_var),
      0
    ),
    na.rm = TRUE
  ),
  event_month_outcome_removed = sum(
    fifelse(
      dataset_source == "treatment" & time_to_event == 0,
      get(outcome_var),
      0
    ),
    na.rm = TRUE
  ),
  month1_outcome_removed = sum(
    fifelse(
      dataset_source == "treatment" & time_to_event == 1,
      get(outcome_var),
      0
    ),
    na.rm = TRUE
  )
), by = .(removed_repo_name = repo_name_str)]

repo_names <- sort(unique(model_data$repo_name_str))
loo_rows <- vector("list", length(repo_names))

for (i in seq_along(repo_names)) {
  removed_repo <- repo_names[i]
  removed_profile <- repo_profile[removed_repo_name == removed_repo]

  loo_data <- copy(model_data[repo_name_str != removed_repo])
  loo_data[, repo_id := as.integer(factor(repo_name_str))]

  model_error <- NA_character_
  loo_row <- tryCatch(
    run_static_model(
      model_data = loo_data,
      outcome_var = outcome_var,
      first_stage_formula = first_stage_formula
    ),
    error = function(e) {
      model_error <<- conditionMessage(e)
      NULL
    }
  )

  if (is.null(loo_row)) {
    loo_estimate <- NA_real_
    loo_std_error <- NA_real_
    loo_conf_low <- NA_real_
    loo_conf_high <- NA_real_
  } else {
    loo_estimate <- safe_numeric(loo_row$estimate[1])
    loo_std_error <- safe_numeric(loo_row$std_error[1])
    loo_conf_low <- safe_numeric(loo_row$conf_low[1])
    loo_conf_high <- safe_numeric(loo_row$conf_high[1])
  }

  loo_p_value_approx <- normal_two_sided_p(loo_estimate, loo_std_error)
  delta_estimate <- loo_estimate - full_estimate
  std_error_reduction <- full_std_error - loo_std_error
  lower_bound_estimate_component <- delta_estimate
  lower_bound_se_component <- 1.96 * std_error_reduction
  lower_bound_increase <- loo_conf_low - full_conf_low
  lower_bound_decomposition_error <- lower_bound_increase -
    lower_bound_estimate_component - lower_bound_se_component

  influence_channel <- if (is.na(lower_bound_increase)) {
    "model_error"
  } else if (lower_bound_increase <= 0) {
    "lower_bound_decrease"
  } else if (lower_bound_estimate_component > 0 && lower_bound_se_component > 0) {
    "estimate_and_se"
  } else if (lower_bound_estimate_component > 0) {
    "estimate_increase_offset_by_se"
  } else if (lower_bound_se_component > 0) {
    "se_reduction_offset_by_estimate"
  } else {
    "other"
  }

  loo_rows[[i]] <- data.frame(
    removed_repo_name = removed_repo,
    dataset_source = as.character(removed_profile$dataset_source[1]),
    rows_removed = as.integer(removed_profile$rows_removed[1]),
    total_outcome_removed = as.numeric(removed_profile$total_outcome_removed[1]),
    mean_outcome_removed = as.numeric(removed_profile$mean_outcome_removed[1]),
    median_outcome_removed = as.numeric(removed_profile$median_outcome_removed[1]),
    maximum_monthly_outcome_removed = as.numeric(
      removed_profile$maximum_monthly_outcome_removed[1]
    ),
    untreated_rows_removed = as.integer(removed_profile$untreated_rows_removed[1]),
    treated_post_rows_removed = as.integer(removed_profile$treated_post_rows_removed[1]),
    pre_treatment_outcome_removed = as.numeric(
      removed_profile$pre_treatment_outcome_removed[1]
    ),
    post_treatment_outcome_removed = as.numeric(
      removed_profile$post_treatment_outcome_removed[1]
    ),
    event_month_outcome_removed = as.numeric(
      removed_profile$event_month_outcome_removed[1]
    ),
    month1_outcome_removed = as.numeric(
      removed_profile$month1_outcome_removed[1]
    ),
    full_estimate = full_estimate,
    full_std_error = full_std_error,
    full_conf_low = full_conf_low,
    full_conf_high = full_conf_high,
    full_p_value_approx = full_p_value_approx,
    loo_estimate = loo_estimate,
    loo_std_error = loo_std_error,
    loo_conf_low = loo_conf_low,
    loo_conf_high = loo_conf_high,
    loo_p_value_approx = loo_p_value_approx,
    delta_estimate = delta_estimate,
    abs_delta_estimate = abs(delta_estimate),
    delta_std_error = loo_std_error - full_std_error,
    std_error_reduction = std_error_reduction,
    delta_conf_low = lower_bound_increase,
    delta_conf_high = loo_conf_high - full_conf_high,
    lower_bound_increase = lower_bound_increase,
    lower_bound_estimate_component = lower_bound_estimate_component,
    lower_bound_se_component = lower_bound_se_component,
    lower_bound_decomposition_error = lower_bound_decomposition_error,
    loo_significant_positive_95 = !is.na(loo_conf_low) && loo_conf_low > 0,
    loo_significant_negative_95 = !is.na(loo_conf_high) && loo_conf_high < 0,
    significance_flip_to_positive_95 =
      full_conf_low <= 0 && !is.na(loo_conf_low) && loo_conf_low > 0,
    effect_sign_flip =
      !is.na(loo_estimate) && sign(loo_estimate) != sign(full_estimate),
    influence_channel = influence_channel,
    model_error = model_error,
    stringsAsFactors = FALSE
  )

  if (i %% progress_every == 0 || i == length(repo_names)) {
    cat(
      "Progress:",
      i,
      "/",
      length(repo_names),
      "repositories; latest=",
      removed_repo,
      "; loo_conf_low=",
      loo_conf_low,
      "\n",
      sep = ""
    )
  }
}

loo <- rbindlist(loo_rows, fill = TRUE)
loo[, rank_lower_bound_increase := frank(
  -lower_bound_increase,
  ties.method = "min",
  na.last = "keep"
)]
loo[, rank_lower_bound_decrease := frank(
  lower_bound_increase,
  ties.method = "min",
  na.last = "keep"
)]
loo[, rank_std_error_reduction := frank(
  -std_error_reduction,
  ties.method = "min",
  na.last = "keep"
)]
loo[, rank_abs_estimate_change := frank(
  -abs_delta_estimate,
  ties.method = "min",
  na.last = "keep"
)]
setorder(loo, rank_lower_bound_increase, removed_repo_name)

full_model <- data.frame(
  outcome = outcome_var,
  term = "treat",
  estimate = full_estimate,
  std_error = full_std_error,
  conf_low = full_conf_low,
  conf_high = full_conf_high,
  p_value_approx = full_p_value_approx,
  model_rows = nrow(model_data),
  model_repositories = uniqueN(model_data$repo_name_str),
  treatment_repositories = uniqueN(
    model_data[dataset_source == "treatment", repo_name_str]
  ),
  control_repositories = uniqueN(
    model_data[dataset_source == "control", repo_name_str]
  ),
  function_scope = "module_function+method",
  sample = "positive_outcome_months_only",
  causal_interpretation_allowed = FALSE,
  stringsAsFactors = FALSE
)

model_error_count <- sum(!is.na(loo$model_error))
significance_flip_count <- sum(
  loo$significance_flip_to_positive_95 %in% TRUE,
  na.rm = TRUE
)
max_decomposition_error <- max(
  abs(loo$lower_bound_decomposition_error),
  na.rm = TRUE
)
if (!is.finite(max_decomposition_error)) {
  max_decomposition_error <- NA_real_
}

validation <- data.frame(
  check = c(
    "run7j_upstream_checks_all_pass",
    "input_sample_has_no_zero_rows",
    "analysis_labeled_noncausal_selected_sample",
    "full_model_reference_available",
    "full_model_reference_max_abs_difference",
    "full_model_reproduction_within_tolerance",
    "loo_expected_repositories",
    "loo_result_rows",
    "loo_duplicate_removed_repositories",
    "loo_model_error_count",
    "loo_results_complete",
    "lower_bound_decomposition_max_abs_error",
    "lower_bound_decomposition_within_tolerance",
    "significance_flip_to_positive_count"
  ),
  value = c(
    nrow(upstream_failed_checks),
    sum(panel_raw[[outcome_var]] <= 0, na.rm = TRUE),
    sum(causal_allowed),
    1,
    reference_max_abs_difference,
    reference_max_abs_difference <= reproduction_tolerance,
    length(repo_names),
    nrow(loo),
    anyDuplicated(loo$removed_repo_name),
    model_error_count,
    sum(!complete.cases(loo[, .(
      loo_estimate,
      loo_std_error,
      loo_conf_low,
      loo_conf_high
    )])),
    max_decomposition_error,
    !is.na(max_decomposition_error) &&
      max_decomposition_error <= max(reproduction_tolerance, 1e-8),
    significance_flip_count
  ),
  passed = c(
    nrow(upstream_failed_checks) == 0,
    sum(panel_raw[[outcome_var]] <= 0, na.rm = TRUE) == 0,
    sum(causal_allowed) == 0,
    TRUE,
    reference_max_abs_difference <= reproduction_tolerance,
    reference_max_abs_difference <= reproduction_tolerance,
    length(repo_names) > 0,
    nrow(loo) == length(repo_names),
    anyDuplicated(loo$removed_repo_name) == 0,
    model_error_count == 0,
    sum(!complete.cases(loo[, .(
      loo_estimate,
      loo_std_error,
      loo_conf_low,
      loo_conf_high
    )])) == 0,
    !is.na(max_decomposition_error),
    !is.na(max_decomposition_error) &&
      max_decomposition_error <= max(reproduction_tolerance, 1e-8),
    TRUE
  ),
  stringsAsFactors = FALSE
)

metadata <- data.frame(
  key = c(
    "analysis_stage",
    "analysis_type",
    "function_scope",
    "included_function_kinds",
    "sample_restriction",
    "causal_interpretation_allowed",
    "outcome",
    "ncloc_specification",
    "time_mode",
    "time_encoding_used",
    "min_treatment_cohort",
    "max_treatment_cohort",
    "first_stage_formula",
    "model_rows",
    "model_repositories",
    "treatment_repositories",
    "control_repositories",
    "loo_model_fits",
    "reproduction_tolerance"
  ),
  value = c(
    "run-py-7m",
    "static_leave_one_repository_out_influence",
    "module_function+method",
    "module_function;method",
    "outcome > 0",
    "FALSE",
    outcome_var,
    ncloc_spec,
    time_mode,
    time_encoding_used,
    min_treatment_cohort,
    max_treatment_cohort,
    paste(deparse(first_stage_formula), collapse = " "),
    nrow(model_data),
    uniqueN(model_data$repo_name_str),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    length(repo_names) + 1L,
    reproduction_tolerance
  ),
  stringsAsFactors = FALSE
)

prefix <- paste0(
  "borusyak_regfun_classmethod_agc_uniquebody_positive_months_",
  "static_leave_one_repository_out"
)

fwrite(full_model, file.path(out_dir, paste0(prefix, "_full_model.csv")))
fwrite(loo, file.path(out_dir, paste0(prefix, "_all_repositories.csv")))
fwrite(
  head(loo[order(-lower_bound_increase, -abs_delta_estimate)], top_n),
  file.path(out_dir, paste0(prefix, "_top_lower_bound_increase.csv"))
)
fwrite(
  head(loo[order(lower_bound_increase, -abs_delta_estimate)], top_n),
  file.path(out_dir, paste0(prefix, "_top_lower_bound_decrease.csv"))
)
fwrite(
  head(loo[order(-std_error_reduction, -abs_delta_estimate)], top_n),
  file.path(out_dir, paste0(prefix, "_top_std_error_reduction.csv"))
)
fwrite(
  head(loo[order(-abs_delta_estimate)], top_n),
  file.path(out_dir, paste0(prefix, "_top_absolute_estimate_change.csv"))
)
fwrite(
  loo[significance_flip_to_positive_95 %in% TRUE][
    order(-lower_bound_increase, -abs_delta_estimate)
  ],
  file.path(out_dir, paste0(prefix, "_significance_flips.csv"))
)
fwrite(
  loo[!is.na(model_error)],
  file.path(out_dir, paste0(prefix, "_model_errors.csv"))
)
fwrite(validation, file.path(out_dir, paste0(prefix, "_validation.csv")))
fwrite(metadata, file.path(out_dir, paste0(prefix, "_metadata.csv")))

status_path <- file.path(out_dir, paste0(prefix, "_status.txt"))
writeLines(c(
  "status=PASS",
  "analysis_stage=run-py-7m",
  "analysis_type=static_leave_one_repository_out_influence",
  "included_function_kinds=module_function;method",
  "sample_restriction=outcome > 0",
  "causal_interpretation_allowed=FALSE",
  paste0("full_estimate=", full_estimate),
  paste0("full_std_error=", full_std_error),
  paste0("full_conf_low=", full_conf_low),
  paste0("full_conf_high=", full_conf_high),
  paste0("loo_repositories=", nrow(loo)),
  paste0("loo_model_errors=", model_error_count),
  paste0("significance_flips=", significance_flip_count)
), status_path)

cat("\nFull model:\n")
print(full_model)
cat("\nTop repositories increasing the lower confidence bound when removed:\n")
print(
  head(
    loo[order(-lower_bound_increase), .(
      removed_repo_name,
      dataset_source,
      loo_estimate,
      loo_std_error,
      loo_conf_low,
      lower_bound_increase,
      lower_bound_estimate_component,
      lower_bound_se_component,
      influence_channel
    )],
    top_n
  )
)
cat("\nValidation:\n")
print(validation)

if (nrow(loo) != length(repo_names)) {
  stop("LOO output row count does not match the expected repository count.")
}
if (anyDuplicated(loo$removed_repo_name) > 0) {
  stop("LOO output contains duplicate removed repositories.")
}
if (model_error_count > 0) {
  stop("One or more leave-one-repository-out models failed.")
}
if (any(validation$passed != TRUE)) {
  stop(
    "Validation failed: ",
    paste(validation$check[validation$passed != TRUE], collapse = ", ")
  )
}

cat("\nStatic leave-one-repository-out influence analysis completed successfully.\n")
