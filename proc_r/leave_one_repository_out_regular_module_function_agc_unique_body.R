#!/usr/bin/env Rscript

# Leave-one-repository-out influence analysis for the month-1 dynamic
# Borusyak DiD estimate of AGC-like regular module-function unique bodies.
#
# This script reproduces the model sample and first-stage specification used by
# DiffInDiffBorusyak_regular_module_function_agc_unique_body.Rmd, estimates the
# full dynamic model, then removes one repository at a time and re-estimates the
# same dynamic model. The primary diagnostic is how each omission changes the
# event-month 1 estimate, standard error, and 95% confidence-interval lower
# bound.
#
# Required environment variables:
#   PROJECT_ROOT               Project root directory.
#   PANEL_PATH                 Parse-clean run-py-7e panel CSV.
#   HELPER_FILE                Borusyak helper R file.
#   OUT_DIR                    Output directory.
#
# Optional environment variables:
#   REFERENCE_DYNAMIC_PATH     Existing run-py-7f dynamic-effects CSV used to
#                              verify exact reproduction of the full model.
#   NCLOC_SPEC                 paper or python_snapshot. Default: python_snapshot
#   TIME_MODE                  original_yyyymm or calendar_month. Default:
#                              calendar_month
#   TARGET_EVENT_MONTH         Dynamic event month to diagnose. Default: 1
#   MIN_TREATMENT_COHORT       Inclusive YYYYMM lower bound. Default: 202408
#   MAX_TREATMENT_COHORT       Inclusive YYYYMM upper bound. Default: 202503
#   PROGRESS_EVERY             Print progress every N repositories. Default: 10
#   TOP_N                      Rows written to each focused top-influence table.
#                              Default: 20
#   REPRODUCTION_TOLERANCE     Full-model comparison tolerance. Default: 1e-6

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
  if (is.na(estimate) || is.na(std_error) || std_error <= 0) {
    return(NA_real_)
  }
  2 * pnorm(abs(estimate / std_error), lower.tail = FALSE)
}

extract_target_row <- function(result, outcome_var, target_event_month) {
  dynamic_df <- extract_dynamic_result(
    result,
    outcome = outcome_var,
    outcome_label = outcome_var,
    min_horizon = target_event_month,
    max_horizon = target_event_month
  )

  dynamic_df <- dynamic_df[dynamic_df$time == target_event_month, , drop = FALSE]
  if (nrow(dynamic_df) != 1) {
    stop(
      "Expected exactly one dynamic result for event month ",
      target_event_month,
      "; found ",
      nrow(dynamic_df)
    )
  }

  dynamic_df[1, , drop = FALSE]
}

prepare_model_data <- function(
    panel_raw,
    ncloc_spec,
    time_mode,
    min_treatment_cohort,
    max_treatment_cohort) {
  outcome_var <- "npr_agc_regular_module_function_unique_bodies"

  if (identical(ncloc_spec, "paper")) {
    ncloc_column <- "ncloc_paper"
    readiness_column <-
      "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
  } else if (identical(ncloc_spec, "python_snapshot")) {
    ncloc_column <- "ncloc_python_snapshot"
    readiness_column <-
      "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc"
  } else {
    stop("NCLOC_SPEC must be paper or python_snapshot. Got: ", ncloc_spec)
  }

  if (!(time_mode %in% c("original_yyyymm", "calendar_month"))) {
    stop(
      "TIME_MODE must be original_yyyymm or calendar_month. Got: ",
      time_mode
    )
  }

  covariates <- c(
    "log1p_age",
    ncloc_column,
    "log1p_contributors",
    "log1p_stars",
    "log1p_issues"
  )

  required <- c(
    "dataset_source",
    "repo_name",
    "time",
    "event",
    "time_to_event",
    outcome_var,
    "has_parse_exclusion",
    readiness_column,
    covariates
  )
  require_columns(panel_raw, required, "Input panel")

  if (anyDuplicated(panel_raw[, .(dataset_source, repo_name, time)]) > 0) {
    stop("Input panel has duplicate dataset_source/repo_name/time keys.")
  }
  if (!all(panel_raw$dataset_source %in% c("control", "treatment"))) {
    stop("dataset_source contains unexpected values.")
  }
  if (any(panel_raw$has_parse_exclusion != 0, na.rm = TRUE)) {
    stop("Parse-clean input unexpectedly contains parse-exclusion rows.")
  }

  panel_data <- copy(panel_raw)
  panel_data <- panel_data[get(readiness_column) == 1]

  model_required <- c(outcome_var, covariates)
  if (sum(!complete.cases(panel_data[, ..model_required])) > 0) {
    stop("Analysis-ready rows contain missing outcome or covariate values.")
  }

  panel_data[, time_yyyymm := normalize_yyyymm(time)]
  event_yyyymm_raw <- normalize_yyyymm(panel_data$event)
  event_yyyymm_raw[is.na(event_yyyymm_raw)] <- 0L
  panel_data[, event_yyyymm := event_yyyymm_raw]

  membership_mismatch <- panel_data[
    ,
    sum((dataset_source == "treatment") != (event_yyyymm > 0L))
  ]
  if (membership_mismatch > 0) {
    stop(
      "Event encoding disagrees with dataset_source on ",
      membership_mismatch,
      " rows."
    )
  }

  panel_data <- panel_data[
    event_yyyymm == 0L |
      (event_yyyymm >= min_treatment_cohort &
         event_yyyymm <= max_treatment_cohort)
  ]

  panel_data[, repo_name_str := as.character(repo_name)]

  if (identical(time_mode, "original_yyyymm")) {
    panel_data[, time_id := time_yyyymm]
    panel_data[, event_id := event_yyyymm]
    time_encoding_used <- "numeric_YYYYMM_original_notebook_compatible"
  } else {
    panel_data[, time_id := yyyymm_to_month_id(time_yyyymm)]
    panel_data[, event_id := fifelse(
      event_yyyymm == 0L,
      0L,
      yyyymm_to_month_id(event_yyyymm)
    )]
    time_encoding_used <- "sequential_calendar_month_id"
  }

  panel_data <- panel_data[!is.na(time_id)]
  panel_data <- panel_data[event_id == 0L | !is.na(event_id)]
  panel_data[, treated := as.integer(event_id > 0L)]
  panel_data[, repo_id := as.integer(factor(repo_name_str))]

  first_stage_rhs <- paste(covariates, collapse = " + ")
  first_stage_formula <- as.formula(
    paste0("~ ", first_stage_rhs, " | repo_id + time_id")
  )

  list(
    data = panel_data,
    outcome_var = outcome_var,
    ncloc_column = ncloc_column,
    readiness_column = readiness_column,
    covariates = covariates,
    first_stage_formula = first_stage_formula,
    time_encoding_used = time_encoding_used
  )
}

run_dynamic_model <- function(
    model_data,
    outcome_var,
    first_stage_formula,
    target_event_month) {
  result <- run_borusyak_dynamic(
    data = model_data,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    horizon = -6:6,
    pretrends = -6:-2,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  )

  extract_target_row(result, outcome_var, target_event_month)
}

project_root <- normalizePath(
  get_env("PROJECT_ROOT", normalizePath(".", mustWork = TRUE)),
  mustWork = TRUE
)
panel_path <- resolve_path(
  project_root,
  get_env("PANEL_PATH", required = TRUE)
)
helper_path <- resolve_path(
  project_root,
  get_env("HELPER_FILE", required = TRUE)
)
out_dir <- resolve_path(
  project_root,
  get_env("OUT_DIR", required = TRUE)
)
reference_dynamic_path <- resolve_path(
  project_root,
  get_env("REFERENCE_DYNAMIC_PATH", "")
)

ncloc_spec <- tolower(get_env("NCLOC_SPEC", "python_snapshot"))
time_mode <- tolower(get_env("TIME_MODE", "calendar_month"))
target_event_month <- as.integer(get_env("TARGET_EVENT_MONTH", "1"))
min_treatment_cohort <- as.integer(get_env("MIN_TREATMENT_COHORT", "202408"))
max_treatment_cohort <- as.integer(get_env("MAX_TREATMENT_COHORT", "202503"))
progress_every <- as.integer(get_env("PROGRESS_EVERY", "10"))
top_n <- as.integer(get_env("TOP_N", "20"))
reproduction_tolerance <- as.numeric(
  get_env("REPRODUCTION_TOLERANCE", "0.000001")
)

if (!file.exists(panel_path)) {
  stop("Panel file not found: ", panel_path)
}
if (!file.exists(helper_path)) {
  stop("Helper file not found: ", helper_path)
}
if (is.na(target_event_month)) {
  stop("TARGET_EVENT_MONTH must be an integer.")
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

cat("Project root:", project_root, "\n")
cat("Panel path:", panel_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("NCLOC specification:", ncloc_spec, "\n")
cat("Time mode:", time_mode, "\n")
cat("Target event month:", target_event_month, "\n")
cat(
  "Treatment cohort range:",
  min_treatment_cohort,
  "through",
  max_treatment_cohort,
  "\n"
)

panel_raw <- fread(panel_path)
prepared <- prepare_model_data(
  panel_raw = panel_raw,
  ncloc_spec = ncloc_spec,
  time_mode = time_mode,
  min_treatment_cohort = min_treatment_cohort,
  max_treatment_cohort = max_treatment_cohort
)

model_data <- prepared$data
outcome_var <- prepared$outcome_var
first_stage_formula <- prepared$first_stage_formula

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

full_row <- run_dynamic_model(
  model_data = model_data,
  outcome_var = outcome_var,
  first_stage_formula = first_stage_formula,
  target_event_month = target_event_month
)

full_estimate <- safe_numeric(full_row$estimate[1])
full_std_error <- safe_numeric(full_row$std_error[1])
full_conf_low <- safe_numeric(full_row$conf_low[1])
full_conf_high <- safe_numeric(full_row$conf_high[1])
full_p_value_approx <- normal_two_sided_p(full_estimate, full_std_error)

cat("Full-model month", target_event_month, "estimate:", full_estimate, "\n")
cat("Full-model standard error:", full_std_error, "\n")
cat("Full-model 95% CI:", full_conf_low, "to", full_conf_high, "\n")
cat("Full-model approximate two-sided p-value:", full_p_value_approx, "\n")

reference_available <- FALSE
reference_estimate <- NA_real_
reference_std_error <- NA_real_
reference_conf_low <- NA_real_
reference_conf_high <- NA_real_
reference_max_abs_difference <- NA_real_

if (!identical(reference_dynamic_path, "") && file.exists(reference_dynamic_path)) {
  reference_dynamic <- fread(reference_dynamic_path)
  require_columns(
    reference_dynamic,
    c("time", "estimate", "std_error", "conf_low", "conf_high"),
    "Reference dynamic results"
  )
  reference_row <- reference_dynamic[time == target_event_month]
  if (nrow(reference_row) != 1) {
    stop(
      "Reference dynamic file must contain exactly one row for event month ",
      target_event_month,
      ". Found: ",
      nrow(reference_row)
    )
  }

  reference_available <- TRUE
  reference_estimate <- safe_numeric(reference_row$estimate[1])
  reference_std_error <- safe_numeric(reference_row$std_error[1])
  reference_conf_low <- safe_numeric(reference_row$conf_low[1])
  reference_conf_high <- safe_numeric(reference_row$conf_high[1])
  reference_max_abs_difference <- max(abs(c(
    full_estimate - reference_estimate,
    full_std_error - reference_std_error,
    full_conf_low - reference_conf_low,
    full_conf_high - reference_conf_high
  )))

  if (is.na(reference_max_abs_difference) ||
      reference_max_abs_difference > reproduction_tolerance) {
    stop(
      "Full-model reproduction differs from run-py-7f reference by ",
      reference_max_abs_difference,
      ", exceeding tolerance ",
      reproduction_tolerance,
      "."
    )
  }

  cat(
    "Full-model reproduction against run-py-7f: PASS; max abs difference =",
    reference_max_abs_difference,
    "\n"
  )
} else {
  cat(
    "Reference dynamic file not provided or not found; ",
    "full-model cross-file reproduction check skipped.\n",
    sep = ""
  )
}

repo_profile <- model_data[, .(
  dataset_source = unique(dataset_source)[1],
  rows_removed = .N,
  total_outcome_removed = sum(get(outcome_var), na.rm = TRUE),
  positive_outcome_months_removed = sum(get(outcome_var) > 0, na.rm = TRUE),
  zero_outcome_months_removed = sum(get(outcome_var) == 0, na.rm = TRUE),
  maximum_monthly_outcome_removed = max(get(outcome_var), na.rm = TRUE),
  target_month_rows_removed = sum(
    dataset_source == "treatment" & time_to_event == target_event_month,
    na.rm = TRUE
  ),
  target_month_outcome_removed = sum(
    fifelse(
      dataset_source == "treatment" & time_to_event == target_event_month,
      get(outcome_var),
      0
    ),
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
    run_dynamic_model(
      model_data = loo_data,
      outcome_var = outcome_var,
      first_stage_formula = first_stage_formula,
      target_event_month = target_event_month
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
  loo_significant_positive <- !is.na(loo_conf_low) && loo_conf_low > 0
  loo_significant_negative <- !is.na(loo_conf_high) && loo_conf_high < 0

  loo_rows[[i]] <- data.frame(
    removed_repo_name = removed_repo,
    dataset_source = as.character(removed_profile$dataset_source[1]),
    rows_removed = as.integer(removed_profile$rows_removed[1]),
    total_outcome_removed = as.numeric(
      removed_profile$total_outcome_removed[1]
    ),
    positive_outcome_months_removed = as.integer(
      removed_profile$positive_outcome_months_removed[1]
    ),
    zero_outcome_months_removed = as.integer(
      removed_profile$zero_outcome_months_removed[1]
    ),
    maximum_monthly_outcome_removed = as.numeric(
      removed_profile$maximum_monthly_outcome_removed[1]
    ),
    target_month_rows_removed = as.integer(
      removed_profile$target_month_rows_removed[1]
    ),
    target_month_outcome_removed = as.numeric(
      removed_profile$target_month_outcome_removed[1]
    ),
    pre_treatment_outcome_removed = as.numeric(
      removed_profile$pre_treatment_outcome_removed[1]
    ),
    post_treatment_outcome_removed = as.numeric(
      removed_profile$post_treatment_outcome_removed[1]
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
    delta_estimate = loo_estimate - full_estimate,
    abs_delta_estimate = abs(loo_estimate - full_estimate),
    delta_std_error = loo_std_error - full_std_error,
    std_error_reduction = full_std_error - loo_std_error,
    delta_conf_low = loo_conf_low - full_conf_low,
    delta_conf_high = loo_conf_high - full_conf_high,
    lower_bound_increase = loo_conf_low - full_conf_low,
    upper_bound_increase = loo_conf_high - full_conf_high,
    loo_significant_positive_95 = loo_significant_positive,
    loo_significant_negative_95 = loo_significant_negative,
    significance_flip_to_positive_95 =
      full_conf_low <= 0 && loo_significant_positive,
    estimate_direction_flip =
      !is.na(loo_estimate) && sign(loo_estimate) != sign(full_estimate),
    model_error = model_error,
    stringsAsFactors = FALSE
  )

  if (i %% progress_every == 0 || i == length(repo_names)) {
    cat(
      sprintf(
        "Progress: %d/%d repositories; latest=%s; conf_low=%.6f\n",
        i,
        length(repo_names),
        removed_repo,
        loo_conf_low
      )
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
loo[, rank_abs_estimate_change := frank(
  -abs_delta_estimate,
  ties.method = "min",
  na.last = "keep"
)]
loo[, rank_std_error_reduction := frank(
  -std_error_reduction,
  ties.method = "min",
  na.last = "keep"
)]

loo[, influence_interpretation := fifelse(
  !is.na(model_error),
  "model_error",
  fifelse(
    significance_flip_to_positive_95,
    "removal_makes_month1_significant_positive",
    fifelse(
      lower_bound_increase > 0,
      "removal_moves_lower_bound_up",
      fifelse(
        lower_bound_increase < 0,
        "removal_moves_lower_bound_down",
        "no_lower_bound_change"
      )
    )
  )
)]

setorder(loo, rank_lower_bound_increase, removed_repo_name)

full_model <- data.frame(
  target_event_month = target_event_month,
  estimate = full_estimate,
  std_error = full_std_error,
  conf_low = full_conf_low,
  conf_high = full_conf_high,
  p_value_approx = full_p_value_approx,
  significant_positive_95 = full_conf_low > 0,
  model_rows = nrow(model_data),
  model_repositories = uniqueN(model_data$repo_name_str),
  treatment_repositories = uniqueN(
    model_data[dataset_source == "treatment", repo_name_str]
  ),
  control_repositories = uniqueN(
    model_data[dataset_source == "control", repo_name_str]
  ),
  total_outcome = sum(model_data[[outcome_var]], na.rm = TRUE),
  ncloc_spec = ncloc_spec,
  ncloc_column = prepared$ncloc_column,
  readiness_column = prepared$readiness_column,
  time_mode = time_mode,
  time_encoding = prepared$time_encoding_used,
  first_stage_formula = paste(deparse(first_stage_formula), collapse = " "),
  treatment_cohort_min = min_treatment_cohort,
  treatment_cohort_max = max_treatment_cohort,
  reference_dynamic_path = reference_dynamic_path,
  reference_available = reference_available,
  reference_estimate = reference_estimate,
  reference_std_error = reference_std_error,
  reference_conf_low = reference_conf_low,
  reference_conf_high = reference_conf_high,
  reference_max_abs_difference = reference_max_abs_difference,
  stringsAsFactors = FALSE
)

model_error_count <- sum(!is.na(loo$model_error))
significance_flip_count <- sum(
  loo$significance_flip_to_positive_95 %in% TRUE,
  na.rm = TRUE
)

validation <- data.frame(
  check = c(
    "input_panel_rows",
    "model_rows",
    "model_repositories",
    "treatment_repositories",
    "control_repositories",
    "loo_expected_repositories",
    "loo_result_rows",
    "loo_duplicate_removed_repositories",
    "loo_model_error_count",
    "full_model_reference_available",
    "full_model_reference_max_abs_difference",
    "full_model_reproduction_within_tolerance",
    "significance_flip_to_positive_count"
  ),
  value = c(
    nrow(panel_raw),
    nrow(model_data),
    uniqueN(model_data$repo_name_str),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    length(repo_names),
    nrow(loo),
    anyDuplicated(loo$removed_repo_name),
    model_error_count,
    reference_available,
    reference_max_abs_difference,
    if (reference_available) {
      reference_max_abs_difference <= reproduction_tolerance
    } else {
      NA
    },
    significance_flip_count
  ),
  stringsAsFactors = FALSE
)

metadata <- data.frame(
  key = c(
    "script",
    "panel_path",
    "helper_file",
    "output_directory",
    "outcome",
    "target_event_month",
    "ncloc_spec",
    "time_mode",
    "time_encoding",
    "first_stage_formula",
    "horizon",
    "pretrends",
    "leave_one_out_unit",
    "influence_primary_metric",
    "interpretation"
  ),
  value = c(
    "proc_r/leave_one_repository_out_regular_module_function_agc_unique_body.R",
    panel_path,
    helper_path,
    out_dir,
    outcome_var,
    target_event_month,
    ncloc_spec,
    time_mode,
    prepared$time_encoding_used,
    paste(deparse(first_stage_formula), collapse = " "),
    "-6:6",
    "-6:-2",
    "repository",
    "change in month-1 95% confidence-interval lower bound",
    paste(
      "A repository with a positive lower_bound_increase makes the original",
      "month-1 lower bound more negative or less positive when included.",
      "A significance_flip_to_positive_95 row identifies an omission under",
      "which the month-1 95% confidence interval becomes strictly positive."
    )
  ),
  stringsAsFactors = FALSE
)

prefix <- paste0(
  "borusyak_regular_module_function_agc_unique_body_month",
  target_event_month,
  "_leave_one_repository_out"
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
  loo[significance_flip_to_positive_95 %in% TRUE][
    order(-lower_bound_increase, -abs_delta_estimate)
  ],
  file.path(out_dir, paste0(prefix, "_significance_flips.csv"))
)
fwrite(
  head(loo[order(-abs_delta_estimate)], top_n),
  file.path(out_dir, paste0(prefix, "_top_absolute_estimate_change.csv"))
)
fwrite(validation, file.path(out_dir, paste0(prefix, "_validation.csv")))
fwrite(metadata, file.path(out_dir, paste0(prefix, "_metadata.csv")))

cat("\nTop repositories whose removal raises the month-1 lower bound:\n")
print(
  head(
    loo[
      order(-lower_bound_increase, -abs_delta_estimate),
      .(
        removed_repo_name,
        dataset_source,
        target_month_outcome_removed,
        loo_estimate,
        loo_std_error,
        loo_conf_low,
        lower_bound_increase,
        significance_flip_to_positive_95
      )
    ],
    top_n
  )
)

cat("\nTop repositories whose removal lowers the month-1 lower bound:\n")
print(
  head(
    loo[
      order(lower_bound_increase, -abs_delta_estimate),
      .(
        removed_repo_name,
        dataset_source,
        target_month_outcome_removed,
        loo_estimate,
        loo_std_error,
        loo_conf_low,
        lower_bound_increase,
        significance_flip_to_positive_95
      )
    ],
    top_n
  )
)

cat("\nValidation summary:\n")
print(validation)

if (nrow(loo) != length(repo_names)) {
  stop("LOO result row count does not match the model repository count.")
}
if (anyDuplicated(loo$removed_repo_name) > 0) {
  stop("LOO output contains duplicate removed repository names.")
}
if (model_error_count > 0) {
  stop("One or more LOO models failed. Count: ", model_error_count)
}

cat("\nLeave-one-repository-out influence analysis completed successfully.\n")
