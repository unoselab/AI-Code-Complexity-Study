#!/usr/bin/env Rscript

# Borusyak DiD sensitivity analysis restricted to repository-months with a
# positive AGC-like regular module-function unique-body count.
#
# IMPORTANT:
#   This analysis conditions on the realized outcome. It is a supplementary
#   selected-sample sensitivity analysis, not a replacement for the primary
#   zero-inclusive causal DiD model.
#
# Required environment variables:
#   PROJECT_ROOT   Project root directory.
#   PANEL_PATH     Parse-clean run-py-7e panel CSV.
#   HELPER_FILE    Borusyak helper R file.
#   OUT_DIR        Output directory.
#
# Optional environment variables:
#   NCLOC_SPEC            paper or python_snapshot. Default: python_snapshot
#   TIME_MODE             original_yyyymm or calendar_month. Default: calendar_month
#   MIN_TREATMENT_COHORT  Inclusive YYYYMM lower bound. Default: 202408
#   MAX_TREATMENT_COHORT  Inclusive YYYYMM upper bound. Default: 202503
#   HORIZON_MIN           Dynamic horizon minimum. Default: -6
#   HORIZON_MAX           Dynamic horizon maximum. Default: 6
#   PRETREND_MIN          Pretrend minimum. Default: -6
#   PRETREND_MAX          Pretrend maximum. Default: -2

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
      stage = character(),
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
horizon_min <- as.integer(get_env("HORIZON_MIN", "-6"))
horizon_max <- as.integer(get_env("HORIZON_MAX", "6"))
pretrend_min <- as.integer(get_env("PRETREND_MIN", "-6"))
pretrend_max <- as.integer(get_env("PRETREND_MAX", "-2"))

if (!file.exists(panel_path)) {
  stop("Panel file not found: ", panel_path)
}
if (!file.exists(helper_path)) {
  stop("Helper file not found: ", helper_path)
}
if (!(ncloc_spec %in% c("paper", "python_snapshot"))) {
  stop("NCLOC_SPEC must be paper or python_snapshot. Got: ", ncloc_spec)
}
if (!(time_mode %in% c("original_yyyymm", "calendar_month"))) {
  stop("TIME_MODE must be original_yyyymm or calendar_month. Got: ", time_mode)
}
if (
  any(is.na(c(
    min_treatment_cohort,
    max_treatment_cohort,
    horizon_min,
    horizon_max,
    pretrend_min,
    pretrend_max
  )))
) {
  stop("Cohort, horizon, and pretrend environment variables must be integers.")
}
if (horizon_min > horizon_max) {
  stop("HORIZON_MIN cannot exceed HORIZON_MAX.")
}
if (pretrend_min > pretrend_max) {
  stop("PRETREND_MIN cannot exceed PRETREND_MAX.")
}

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
source(helper_path)

outcome_var <- "npr_agc_regular_module_function_unique_bodies"
occurrence_var <- "has_npr_agc_regular_module_function_unique_body"
zero_var <- "zero_npr_agc_regular_module_function_unique_body_month"

if (identical(ncloc_spec, "paper")) {
  ncloc_column <- "ncloc_paper"
  readiness_column <-
    "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
} else {
  ncloc_column <- "ncloc_python_snapshot"
  readiness_column <-
    "analysis_ready_regular_module_function_agc_unique_body_python_snapshot_ncloc"
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
  "agc_count_unit",
  "agc_outcome_scale",
  outcome_var,
  occurrence_var,
  zero_var,
  readiness_column,
  covariates
)

cat("Project root:", project_root, "\n")
cat("Panel path:", panel_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("NCLOC specification:", ncloc_spec, "\n")
cat("Time mode:", time_mode, "\n")
cat("Sample restriction: outcome > 0\n")
cat(
  "WARNING: This conditions on the realized outcome and is not the primary causal DiD estimand.\n"
)

panel_raw <- fread(panel_path)
require_columns(panel_raw, required_columns, "Input panel")

if (anyDuplicated(panel_raw[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Input panel has duplicate dataset_source/repo_name/time keys.")
}
if (!all(panel_raw$dataset_source %in% c("control", "treatment"))) {
  stop("dataset_source contains unexpected values.")
}
if (any(panel_raw$has_parse_exclusion != 0, na.rm = TRUE)) {
  stop("Parse-clean input unexpectedly contains parse-exclusion rows.")
}
if (any(panel_raw[[outcome_var]] < 0, na.rm = TRUE)) {
  stop("Outcome contains negative values.")
}
if (any(is.na(panel_raw[[outcome_var]]))) {
  stop("Outcome contains missing values.")
}
if (
  any(
    abs(panel_raw[[outcome_var]] - round(panel_raw[[outcome_var]])) > 1e-12,
    na.rm = TRUE
  )
) {
  stop("Outcome contains noninteger values.")
}
if (
  any(
    as.integer(panel_raw[[occurrence_var]]) !=
      as.integer(panel_raw[[outcome_var]] > 0),
    na.rm = TRUE
  )
) {
  stop("Positive-outcome indicator does not match the outcome.")
}
if (
  any(
    as.integer(panel_raw[[zero_var]]) !=
      as.integer(panel_raw[[outcome_var]] == 0),
    na.rm = TRUE
  )
) {
  stop("Zero-outcome indicator does not match the outcome.")
}
if (any(as.character(panel_raw$npr_specification) != "range100_200")) {
  stop("Input contains an unexpected NPR specification.")
}
if (any(as.character(panel_raw$regular_function_scope) != "module_function")) {
  stop("Input contains an unexpected regular-function scope.")
}
if (
  any(
    as.character(panel_raw$agc_count_unit) !=
      "distinct_function_body_sha256_per_repository_month"
  )
) {
  stop("Input contains an unexpected AGC count unit.")
}
if (any(as.character(panel_raw$agc_outcome_scale) != "raw_count")) {
  stop("Input contains an unexpected AGC outcome scale.")
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
  stop(
    "Event encoding disagrees with dataset_source on ",
    membership_mismatch,
    " rows."
  )
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

zero_rows_removed <- panel_ready[get(outcome_var) == 0]
model_data <- panel_ready[get(outcome_var) > 0]

if (nrow(model_data) == 0) {
  stop("No positive-outcome repository-months remain.")
}
if (any(model_data[[outcome_var]] <= 0)) {
  stop("Positive-only model sample still contains a nonpositive outcome.")
}
if (anyDuplicated(model_data[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Positive-only model sample has duplicate repository-month keys.")
}
if (uniqueN(model_data[dataset_source == "treatment", repo_name_str]) == 0) {
  stop("No treated repositories remain after the positive-outcome filter.")
}
if (uniqueN(model_data[dataset_source == "control", repo_name_str]) == 0) {
  stop("No control repositories remain after the positive-outcome filter.")
}

model_data[, repo_id := as.integer(factor(repo_name_str))]
first_stage_formula <- as.formula(
  paste0(
    "~ ",
    paste(covariates, collapse = " + "),
    " | repo_id + time_id"
  )
)

horizon <- seq.int(horizon_min, horizon_max)
pretrends <- seq.int(pretrend_min, pretrend_max)

cat("Input rows:", nrow(panel_raw), "\n")
cat("Rows after readiness/cohort filters:", nrow(panel_ready), "\n")
cat("Zero rows removed:", nrow(zero_rows_removed), "\n")
cat("Positive rows used:", nrow(model_data), "\n")
cat("Repositories used:", uniqueN(model_data$repo_name_str), "\n")
cat(
  "Treatment repositories used:",
  uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
  "\n"
)
cat(
  "Control repositories used:",
  uniqueN(model_data[dataset_source == "control", repo_name_str]),
  "\n"
)
cat("First-stage formula:\n")
print(first_stage_formula)

static_error <- NA_character_
dynamic_error <- NA_character_

static_result <- tryCatch(
  run_borusyak_static(
    data = model_data,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  ),
  error = function(e) {
    static_error <<- conditionMessage(e)
    NULL
  }
)

dynamic_result <- tryCatch(
  run_borusyak_dynamic(
    data = model_data,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    horizon = horizon,
    pretrends = pretrends,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  ),
  error = function(e) {
    dynamic_error <<- conditionMessage(e)
    NULL
  }
)

static_df <- extract_static_result(static_result, outcome_var)
dynamic_df <- extract_dynamic_result(
  dynamic_result,
  outcome = outcome_var,
  outcome_label = "AGC-Like Regular-Function Unique Bodies, Positive Months Only",
  min_horizon = horizon_min,
  max_horizon = horizon_max
)

for (df_name in c("static_df", "dynamic_df")) {
  df <- get(df_name)
  if (nrow(df) > 0) {
    df$sample <- "positive_outcome_months_only"
    df$outcome_unit <- "distinct bodies per positive-outcome repository-month"
    df$causal_interpretation_allowed <- FALSE
    df$selection_note <- paste(
      "Repository-months with zero realized outcome were excluded.",
      "This conditions on the outcome and is supplementary only."
    )
    df$p_value_approx <- normal_two_sided_p(df$estimate, df$std_error)
  }
  assign(df_name, df)
}

sample_summary <- model_data[
  ,
  .(
    rows = .N,
    repositories = uniqueN(repo_name_str),
    total_outcome = sum(get(outcome_var)),
    mean_outcome = mean(get(outcome_var)),
    median_outcome = as.numeric(median(get(outcome_var))),
    maximum_outcome = max(get(outcome_var))
  ),
  by = dataset_source
]

filter_summary <- data.frame(
  metric = c(
    "input_panel_rows",
    "input_panel_repositories",
    "ready_cohort_rows_before_positive_filter",
    "ready_cohort_repositories_before_positive_filter",
    "zero_rows_removed",
    "positive_rows_used",
    "positive_repositories_used",
    "positive_treatment_rows",
    "positive_control_rows",
    "positive_treatment_repositories",
    "positive_control_repositories",
    "total_outcome_preserved"
  ),
  value = c(
    nrow(panel_raw),
    uniqueN(panel_raw$repo_name),
    nrow(panel_ready),
    uniqueN(panel_ready$repo_name_str),
    nrow(zero_rows_removed),
    nrow(model_data),
    uniqueN(model_data$repo_name_str),
    nrow(model_data[dataset_source == "treatment"]),
    nrow(model_data[dataset_source == "control"]),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    sum(model_data[[outcome_var]])
  ),
  stringsAsFactors = FALSE
)

event_time_grid <- CJ(
  dataset_source = c("treatment", "control"),
  event_time = horizon
)
event_time_counts <- rbindlist(list(
  model_data[
    dataset_source == "treatment" &
      !is.na(time_to_event) &
      time_to_event >= horizon_min &
      time_to_event <= horizon_max,
    .(
      positive_rows = .N,
      repositories = uniqueN(repo_name_str),
      total_outcome = sum(get(outcome_var))
    ),
    by = .(dataset_source, event_time = as.integer(time_to_event))
  ],
  data.table(
    dataset_source = "control",
    event_time = horizon,
    positive_rows = NA_integer_,
    repositories = NA_integer_,
    total_outcome = NA_real_
  )
), fill = TRUE)
event_time_counts <- merge(
  event_time_grid,
  event_time_counts,
  by = c("dataset_source", "event_time"),
  all.x = TRUE
)
setorder(event_time_counts, dataset_source, event_time)

rankify_audit <- panel_ready[
  repo_name_str == "DataScienceUIBK/Rankify",
  .(
    dataset_source,
    repo_name = repo_name_str,
    time,
    event,
    time_to_event,
    outcome = get(outcome_var),
    retained_positive_sample = get(outcome_var) > 0,
    removal_reason = fifelse(
      get(outcome_var) == 0,
      "removed_zero_realized_outcome",
      "retained_positive_realized_outcome"
    )
  )
]
setorder(rankify_audit, time)

errors <- rbindlist(list(
  if (!is.na(static_error)) {
    data.table(stage = "static", outcome = outcome_var, error = static_error)
  } else {
    NULL
  },
  if (!is.na(dynamic_error)) {
    data.table(stage = "dynamic", outcome = outcome_var, error = dynamic_error)
  } else {
    NULL
  }
), fill = TRUE)

static_complete <- nrow(static_df) == 1 &&
  all(!is.na(static_df[, c("estimate", "std_error", "conf_low", "conf_high")]))
dynamic_nonempty <- nrow(dynamic_df) > 0
dynamic_has_pre <- dynamic_nonempty && any(dynamic_df$time < 0)
dynamic_has_post <- dynamic_nonempty && any(dynamic_df$time >= 0)

validation <- data.frame(
  check = c(
    "input_has_zero_rows",
    "positive_sample_has_no_zero_rows",
    "positive_sample_treatment_repositories_nonzero",
    "positive_sample_control_repositories_nonzero",
    "rankify_event_month_zero_removed",
    "rankify_month1_zero_removed",
    "static_model_error_count",
    "dynamic_model_error_count",
    "static_result_complete",
    "dynamic_result_nonempty",
    "dynamic_pre_period_present",
    "dynamic_post_period_present",
    "analysis_labeled_noncausal_selected_sample"
  ),
  value = c(
    sum(panel_ready[[outcome_var]] == 0),
    sum(model_data[[outcome_var]] == 0),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    nrow(rankify_audit[time_to_event == 0 & !retained_positive_sample]),
    nrow(rankify_audit[time_to_event == 1 & !retained_positive_sample]),
    as.integer(!is.na(static_error)),
    as.integer(!is.na(dynamic_error)),
    static_complete,
    dynamic_nonempty,
    dynamic_has_pre,
    dynamic_has_post,
    TRUE
  ),
  passed = c(
    sum(panel_ready[[outcome_var]] == 0) > 0,
    sum(model_data[[outcome_var]] == 0) == 0,
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]) > 0,
    uniqueN(model_data[dataset_source == "control", repo_name_str]) > 0,
    nrow(rankify_audit[time_to_event == 0 & !retained_positive_sample]) == 1,
    nrow(rankify_audit[time_to_event == 1 & !retained_positive_sample]) == 1,
    is.na(static_error),
    is.na(dynamic_error),
    static_complete,
    dynamic_nonempty,
    dynamic_has_pre,
    dynamic_has_post,
    TRUE
  ),
  stringsAsFactors = FALSE
)

overall_pass <- all(validation$passed)

metadata <- data.frame(
  key = c(
    "script",
    "panel_path",
    "helper_file",
    "output_directory",
    "outcome",
    "sample_restriction",
    "estimand_label",
    "causal_interpretation_allowed",
    "selection_warning",
    "ncloc_spec",
    "ncloc_column",
    "readiness_column",
    "time_mode",
    "time_encoding",
    "first_stage_formula",
    "horizon",
    "pretrends",
    "treatment_cohort_min",
    "treatment_cohort_max"
  ),
  value = c(
    "proc_r/did_regular_module_function_agc_unique_body_positive_months.R",
    panel_path,
    helper_path,
    out_dir,
    outcome_var,
    "npr_agc_regular_module_function_unique_bodies > 0",
    "conditional intensity among observed positive-outcome repository-months",
    "FALSE",
    paste(
      "The sample is selected using the realized outcome.",
      "Do not interpret this as the total causal effect of Cursor adoption."
    ),
    ncloc_spec,
    ncloc_column,
    readiness_column,
    time_mode,
    time_encoding_used,
    paste(deparse(first_stage_formula), collapse = " "),
    paste0(horizon_min, ":", horizon_max),
    paste0(pretrend_min, ":", pretrend_max),
    min_treatment_cohort,
    max_treatment_cohort
  ),
  stringsAsFactors = FALSE
)

prefix <- "borusyak_regular_module_function_agc_unique_body_positive_months"

fwrite(
  static_df,
  file.path(out_dir, paste0(prefix, "_static_effects.csv"))
)
fwrite(
  dynamic_df,
  file.path(out_dir, paste0(prefix, "_dynamic_effects.csv"))
)
fwrite(
  sample_summary,
  file.path(out_dir, paste0(prefix, "_sample_summary.csv"))
)
fwrite(
  filter_summary,
  file.path(out_dir, paste0(prefix, "_filter_summary.csv"))
)
fwrite(
  event_time_counts,
  file.path(out_dir, paste0(prefix, "_event_time_counts.csv"))
)
fwrite(
  rankify_audit,
  file.path(out_dir, paste0(prefix, "_rankify_audit.csv"))
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
    paste0("input_rows=", nrow(panel_raw)),
    paste0("ready_cohort_rows=", nrow(panel_ready)),
    paste0("zero_rows_removed=", nrow(zero_rows_removed)),
    paste0("positive_rows_used=", nrow(model_data)),
    paste0("repositories_used=", uniqueN(model_data$repo_name_str)),
    paste0(
      "treatment_repositories_used=",
      uniqueN(model_data[dataset_source == "treatment", repo_name_str])
    ),
    paste0(
      "control_repositories_used=",
      uniqueN(model_data[dataset_source == "control", repo_name_str])
    ),
    "causal_interpretation_allowed=FALSE"
  ),
  status_path
)

cat("\nStatic result:\n")
print(static_df)
cat("\nDynamic result:\n")
print(dynamic_df)
cat("\nFilter summary:\n")
print(filter_summary)
cat("\nRankify audit:\n")
print(rankify_audit)
cat("\nValidation:\n")
print(validation)

if (!overall_pass) {
  stop("Positive-outcome-month sensitivity analysis failed validation.")
}

cat("\nPositive-outcome-month sensitivity analysis completed successfully.\n")
