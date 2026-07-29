#!/usr/bin/env Rscript

# Compare the original regular-module-function static Borusyak DiD result
# against five one-repository-at-a-time hybrid outcomes on the exact same
# fixed sample.
#
# Models:
#   1. Baseline regular module functions only.
#   2. Baseline plus class-method AGC unique bodies for Rankify only.
#   3. Baseline plus class-method AGC unique bodies for cli-agent only.
#   4. Baseline plus class-method AGC unique bodies for Webscout only.
#   5. Baseline plus class-method AGC unique bodies for flock only.
#   6. Baseline plus class-method AGC unique bodies for sentry only.
#
# Sample membership remains fixed to the original run-py-7h positive-month
# sample prepared by run-py-7n. Method-only positive months are not added.
# This isolates the effect of appending one repository's class methods from
# both sample-membership changes and additions from the other repositories.
#
# IMPORTANT:
#   This is supplementary influence debugging, not a primary causal estimand.
#   The results must not be used to justify repository removal.

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

static_complete <- function(df) {
  required <- c("estimate", "std_error", "conf_low", "conf_high")
  nrow(df) == 1 &&
    all(required %in% names(df)) &&
    all(!is.na(as.data.frame(df)[, required, drop = FALSE]))
}

safe_repo_label <- function(repo_name) {
  label <- gsub("[^A-Za-z0-9]+", "_", repo_name)
  label <- gsub("^_+|_+$", "", label)
  tolower(label)
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

target_repository_string <- get_env(
  "TARGET_REPOSITORIES",
  paste(
    c(
      "DataScienceUIBK/Rankify",
      "pieces-app/cli-agent",
      "HelpingAI/Webscout",
      "whiteducksoftware/flock",
      "getsentry/sentry"
    ),
    collapse = "|"
  )
)
target_repositories <- trimws(
  strsplit(target_repository_string, "|", fixed = TRUE)[[1]]
)
target_repositories <- target_repositories[target_repositories != ""]
if (length(target_repositories) == 0) {
  stop("TARGET_REPOSITORIES must contain at least one repository.")
}
if (anyDuplicated(target_repositories) > 0) {
  stop("TARGET_REPOSITORIES contains duplicates.")
}

expected_added_bodies <- c(
  "DataScienceUIBK/Rankify" = 59,
  "pieces-app/cli-agent" = 60,
  "HelpingAI/Webscout" = 80,
  "whiteducksoftware/flock" = 82,
  "getsentry/sentry" = 544
)

ncloc_spec <- tolower(get_env("NCLOC_SPEC", "python_snapshot"))
time_mode <- tolower(get_env("TIME_MODE", "calendar_month"))
min_treatment_cohort <- as.integer(get_env("MIN_TREATMENT_COHORT", "202408"))
max_treatment_cohort <- as.integer(get_env("MAX_TREATMENT_COHORT", "202503"))
repro_tolerance <- as.numeric(get_env("REPRO_TOLERANCE", "0.000001"))
skip_frozen_count_checks <- as_logical_strict(
  get_env("SKIP_FROZEN_COUNT_CHECKS", "0"),
  "SKIP_FROZEN_COUNT_CHECKS"
)

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
cat("One-repository-at-a-time class-method additions:\n")
for (repo_name in target_repositories) {
  cat("  -", repo_name, "\n")
}
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
panel_ready[, method_increment := get(hybrid_outcome) - get(baseline_outcome)]
model_data <- copy(panel_ready)

if (nrow(model_data) == 0) {
  stop("No repository-months remain for modeling.")
}
if (anyDuplicated(model_data[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Model sample has duplicate repository-month keys.")
}

selected_repositories_in_input <- unique(
  panel_raw[selected_logical == TRUE, as.character(repo_name)]
)
missing_targets <- setdiff(target_repositories, selected_repositories_in_input)
extra_targets <- setdiff(selected_repositories_in_input, target_repositories)
if (length(missing_targets) > 0) {
  stop("Target repositories missing from selected input: ", paste(missing_targets, collapse = ", "))
}
if (length(extra_targets) > 0) {
  stop("Input contains unexpected selected repositories: ", paste(extra_targets, collapse = ", "))
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
cat("Selected-repository method increment total:", sum(model_data$method_increment), "\n")
cat("Planned static models:", 1L + length(target_repositories), "\n")
cat("First-stage formula:\n")
print(first_stage_formula)

model_errors <- list()
run_static_model <- function(
  outcome_values,
  model_order,
  model_label,
  added_repo_name = NA_character_
) {
  analysis_data <- copy(model_data)
  analysis_data[, analysis_outcome := as.numeric(outcome_values)]

  error_message <- NA_character_
  result <- tryCatch(
    run_borusyak_static(
      data = analysis_data,
      outcome_var = "analysis_outcome",
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
      model_order = model_order,
      model = model_label,
      added_repo_name = added_repo_name,
      error = error_message
    )
  }

  extracted <- extract_static_result(result, "analysis_outcome")
  if (nrow(extracted) > 0) {
    extracted$model_order <- model_order
    extracted$model <- model_label
    extracted$added_repo_name <- added_repo_name
    extracted$added_repo_dataset_source <- if (is.na(added_repo_name)) {
      NA_character_
    } else {
      model_data[repo_name_str == added_repo_name, first(dataset_source)]
    }
    extracted$added_repo_model_rows <- if (is.na(added_repo_name)) {
      0L
    } else {
      model_data[repo_name_str == added_repo_name, .N]
    }
    extracted$added_method_bodies <- if (is.na(added_repo_name)) {
      0
    } else {
      model_data[repo_name_str == added_repo_name, sum(method_increment)]
    }
    extracted$added_method_bodies_pre <- if (is.na(added_repo_name)) {
      0
    } else {
      model_data[
        repo_name_str == added_repo_name &
          !is.na(time_to_event) & time_to_event < 0,
        sum(method_increment)
      ]
    }
    extracted$added_method_bodies_event_post <- if (is.na(added_repo_name)) {
      0
    } else {
      model_data[
        repo_name_str == added_repo_name &
          !is.na(time_to_event) & time_to_event >= 0,
        sum(method_increment)
      ]
    }
    extracted$sample <- "original_regfun_positive_months_fixed"
    extracted$causal_interpretation_allowed <- FALSE
    extracted$p_value_approx <- normal_two_sided_p(
      extracted$estimate,
      extracted$std_error
    )
  }
  extracted
}

result_list <- list()
result_list[[1L]] <- run_static_model(
  outcome_values = model_data[[baseline_outcome]],
  model_order = 1L,
  model_label = "baseline_regular_module_function",
  added_repo_name = NA_character_
)

for (index in seq_along(target_repositories)) {
  target_repo <- target_repositories[[index]]
  one_repo_outcome <- model_data[[baseline_outcome]] + ifelse(
    model_data$repo_name_str == target_repo,
    model_data$method_increment,
    0
  )
  result_list[[index + 1L]] <- run_static_model(
    outcome_values = one_repo_outcome,
    model_order = index + 1L,
    model_label = paste0("baseline_plus_", safe_repo_label(target_repo)),
    added_repo_name = target_repo
  )
}

static_results <- rbindlist(result_list, fill = TRUE)
setorder(static_results, model_order)

errors <- if (length(model_errors) == 0) {
  data.table(
    model_order = integer(),
    model = character(),
    added_repo_name = character(),
    error = character()
  )
} else {
  rbindlist(model_errors, fill = TRUE)
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

baseline_static <- static_results[model_order == 1L]
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

comparison <- copy(static_results)
comparison[, baseline_estimate := baseline_static$estimate]
comparison[, baseline_std_error := baseline_static$std_error]
comparison[, baseline_conf_low := baseline_static$conf_low]
comparison[, baseline_conf_high := baseline_static$conf_high]
comparison[, delta_estimate := estimate - baseline_estimate]
comparison[, delta_std_error := std_error - baseline_std_error]
comparison[, delta_conf_low := conf_low - baseline_conf_low]
comparison[, delta_conf_high := conf_high - baseline_conf_high]
comparison[, estimate_drop := baseline_estimate - estimate]
comparison[, std_error_increase := std_error - baseline_std_error]
comparison[, lower_bound_drop := baseline_conf_low - conf_low]
comparison[, lower_bound_drop_estimate_component := baseline_estimate - estimate]
comparison[, lower_bound_drop_se_component := 1.96 * (std_error - baseline_std_error)]
comparison[, lower_bound_decomposition_error :=
  lower_bound_drop -
    lower_bound_drop_estimate_component -
    lower_bound_drop_se_component]
comparison[, ci_includes_zero := conf_low <= 0 & conf_high >= 0]
comparison[, ci_strictly_positive := conf_low > 0]
comparison[, ci_strictly_negative := conf_high < 0]
comparison[, changes_positive_baseline_ci_to_include_zero :=
  model_order > 1L & baseline_conf_low > 0 & ci_includes_zero]
comparison[, confidence_interval_verdict := fifelse(
  ci_strictly_positive,
  "95CI_EXCLUDES_ZERO_POSITIVE",
  fifelse(
    ci_strictly_negative,
    "95CI_EXCLUDES_ZERO_NEGATIVE",
    "95CI_INCLUDES_ZERO"
  )
)]
comparison[, influence_channel := fifelse(
  estimate_drop > 0 & std_error_increase > 0,
  "estimate_drop_and_se_increase",
  fifelse(
    estimate_drop > 0 & std_error_increase <= 0,
    "estimate_drop_offset_by_se_decrease",
    fifelse(
      estimate_drop <= 0 & std_error_increase > 0,
      "se_increase_offset_by_estimate_increase",
      "estimate_and_se_do_not_worsen"
    )
  )
)]
comparison[model_order > 1L, impact_rank_lower_bound_drop :=
  frank(-lower_bound_drop, ties.method = "min")]
comparison[model_order > 1L, impact_rank_absolute_estimate_change :=
  frank(-abs(delta_estimate), ties.method = "min")]

root_cause_ranking <- comparison[model_order > 1L]
setorder(root_cause_ranking, -lower_bound_drop, model_order)

repo_summary <- model_data[
  repo_name_str %in% target_repositories,
  .(
    dataset_source = first(dataset_source),
    model_rows = .N,
    pre_event_rows = sum(!is.na(time_to_event) & time_to_event < 0),
    event_and_post_rows = sum(!is.na(time_to_event) & time_to_event >= 0),
    baseline_outcome_total = sum(get(baseline_outcome)),
    method_increment_total = sum(method_increment),
    method_increment_pre = sum(
      method_increment[!is.na(time_to_event) & time_to_event < 0]
    ),
    method_increment_event_post = sum(
      method_increment[!is.na(time_to_event) & time_to_event >= 0]
    ),
    one_repo_outcome_total = sum(get(baseline_outcome) + method_increment),
    maximum_baseline_outcome = max(get(baseline_outcome)),
    maximum_method_increment = max(method_increment),
    maximum_one_repo_outcome = max(get(baseline_outcome) + method_increment)
  ),
  by = repo_name_str
]
setnames(repo_summary, "repo_name_str", "repo_name")
repo_summary[, requested_order := match(repo_name, target_repositories)]
setorder(repo_summary, requested_order)

repo_month_audit <- model_data[
  repo_name_str %in% target_repositories,
  .(
    requested_order = match(repo_name_str, target_repositories),
    dataset_source,
    repo_name = repo_name_str,
    time,
    event,
    time_to_event,
    baseline_outcome = get(baseline_outcome),
    method_increment,
    one_repo_outcome = get(baseline_outcome) + method_increment,
    ncloc = get(ncloc_column)
  )
]
setorder(repo_month_audit, requested_order, time)

observed_additions <- setNames(
  repo_summary$method_increment_total,
  repo_summary$repo_name
)
frozen_counts_match <- TRUE
if (!skip_frozen_count_checks) {
  expected_for_targets <- expected_added_bodies[target_repositories]
  if (any(is.na(expected_for_targets))) {
    stop("Frozen expected additions are missing for one or more target repositories.")
  }
  frozen_counts_match <- all(
    as.numeric(observed_additions[target_repositories]) ==
      as.numeric(expected_for_targets)
  )
}

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
    "target_repositories",
    "planned_models",
    "completed_models",
    "baseline_outcome_total",
    "all_target_method_increment_total"
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
    length(target_repositories),
    1L + length(target_repositories),
    nrow(static_results),
    sum(model_data[[baseline_outcome]]),
    sum(model_data$method_increment)
  ),
  stringsAsFactors = FALSE
)

validation <- data.frame(
  check = c(
    "run7n_upstream_checks_all_pass",
    "input_rows_match_expected_fixed_sample",
    "input_repositories_match_expected",
    "input_baseline_outcome_strictly_positive",
    "input_membership_fixed_to_run7h",
    "input_labeled_noncausal",
    "baseline_hybrid_readiness_identical",
    "model_rows_match_expected",
    "model_treatment_repositories_match_expected",
    "model_control_repositories_match_expected",
    "target_repository_count_match_expected",
    "target_repositories_all_present",
    "target_repository_additions_match_frozen_counts",
    "static_model_error_count",
    "static_result_rows_match_expected",
    "static_results_complete",
    "baseline_reproduces_run7h_within_tolerance",
    "lower_bound_decomposition_within_tolerance",
    "comparison_rows_match_expected",
    "root_cause_ranking_rows_match_expected"
  ),
  value = c(
    nrow(upstream_failed),
    nrow(panel_raw),
    uniqueN(panel_raw$repo_name),
    sum(panel_raw[[baseline_outcome]] <= 0),
    sum(!fixed_membership),
    sum(causal_allowed),
    sum(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE),
    nrow(model_data),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    length(target_repositories),
    length(setdiff(target_repositories, model_data$repo_name_str)),
    as.integer(frozen_counts_match),
    nrow(errors),
    nrow(static_results),
    sum(!complete.cases(static_results[, .(estimate, std_error, conf_low, conf_high)])),
    baseline_reference_difference,
    max(abs(comparison$lower_bound_decomposition_error), na.rm = TRUE),
    nrow(comparison),
    nrow(root_cause_ranking)
  ),
  passed = c(
    nrow(upstream_failed) == 0,
    nrow(panel_raw) == 487,
    uniqueN(panel_raw$repo_name) == 132,
    sum(panel_raw[[baseline_outcome]] <= 0) == 0,
    sum(!fixed_membership) == 0,
    sum(causal_allowed) == 0,
    sum(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE) == 0,
    nrow(model_data) == 486,
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]) == 75,
    uniqueN(model_data[dataset_source == "control", repo_name_str]) == 57,
    length(target_repositories) == 5,
    length(setdiff(target_repositories, model_data$repo_name_str)) == 0,
    frozen_counts_match,
    nrow(errors) == 0,
    nrow(static_results) == 1L + length(target_repositories),
    sum(!complete.cases(static_results[, .(estimate, std_error, conf_low, conf_high)])) == 0,
    baseline_reference_difference <= repro_tolerance,
    max(abs(comparison$lower_bound_decomposition_error), na.rm = TRUE) <= repro_tolerance,
    nrow(comparison) == 1L + length(target_repositories),
    nrow(root_cause_ranking) == length(target_repositories)
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
    "one_repository_at_a_time_rule",
    "target_repositories",
    "sample_membership_rule",
    "causal_interpretation_allowed",
    "ncloc_spec",
    "ncloc_column",
    "time_mode",
    "time_encoding",
    "first_stage_formula",
    "treatment_cohort_min",
    "treatment_cohort_max",
    "reproduction_tolerance",
    "skip_frozen_count_checks"
  ),
  value = c(
    "proc_r/did_regfun_each_selected_classmethod_agc_uniquebody_fixed_sample.R",
    panel_path,
    run7n_checks_path,
    reference_static_path,
    helper_path,
    out_dir,
    baseline_outcome,
    "baseline + method increment for exactly one target repository",
    paste(target_repositories, collapse = "|"),
    "original_module_function_outcome > 0",
    "FALSE",
    ncloc_spec,
    ncloc_column,
    time_mode,
    time_encoding_used,
    paste(deparse(first_stage_formula), collapse = " "),
    min_treatment_cohort,
    max_treatment_cohort,
    repro_tolerance,
    skip_frozen_count_checks
  ),
  stringsAsFactors = FALSE
)

prefix <- "borusyak_regfun_each_selected_classmethod_agc_uniquebody_fixed_sample"

fwrite(
  static_results,
  file.path(out_dir, paste0(prefix, "_static_results.csv"))
)
fwrite(
  comparison,
  file.path(out_dir, paste0(prefix, "_comparison_to_baseline.csv"))
)
fwrite(
  root_cause_ranking,
  file.path(out_dir, paste0(prefix, "_root_cause_ranking.csv"))
)
fwrite(
  repo_summary,
  file.path(out_dir, paste0(prefix, "_target_repo_summary.csv"))
)
fwrite(
  repo_month_audit,
  file.path(out_dir, paste0(prefix, "_target_repo_month_audit.csv"))
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
fwrite(
  errors,
  file.path(out_dir, paste0(prefix, "_model_errors.csv"))
)

status_path <- file.path(out_dir, paste0(prefix, "_status.txt"))
zero_transition_count <- comparison[
  changes_positive_baseline_ci_to_include_zero == TRUE,
  .N
]
writeLines(
  c(
    paste0("status=", if (overall_pass) "PASS" else "FAIL"),
    paste0("model_rows=", nrow(model_data)),
    paste0("model_repositories=", uniqueN(model_data$repo_name_str)),
    paste0("target_repositories=", length(target_repositories)),
    paste0("completed_static_models=", nrow(static_results)),
    paste0("baseline_reference_max_abs_difference=", format(baseline_reference_difference, scientific = TRUE)),
    paste0("models_changing_positive_baseline_ci_to_include_zero=", zero_transition_count),
    "sample_membership_fixed_to_run_py_7h=TRUE",
    "one_repository_at_a_time=TRUE",
    "causal_interpretation_allowed=FALSE"
  ),
  status_path
)

cat("\nStatic results:\n")
print(static_results[, .(
  model_order,
  model,
  added_repo_name,
  added_repo_dataset_source,
  added_method_bodies,
  estimate,
  std_error,
  conf_low,
  conf_high,
  p_value_approx
)])
cat("\nComparison to baseline:\n")
print(comparison[, .(
  model_order,
  added_repo_name,
  estimate,
  std_error,
  conf_low,
  conf_high,
  delta_estimate,
  delta_std_error,
  lower_bound_drop,
  changes_positive_baseline_ci_to_include_zero,
  influence_channel
)])
cat("\nRoot-cause ranking by lower-bound drop:\n")
print(root_cause_ranking[, .(
  impact_rank_lower_bound_drop,
  added_repo_name,
  added_repo_dataset_source,
  added_method_bodies,
  estimate,
  std_error,
  conf_low,
  conf_high,
  lower_bound_drop,
  lower_bound_drop_estimate_component,
  lower_bound_drop_se_component,
  changes_positive_baseline_ci_to_include_zero
)])
cat("\nValidation:\n")
print(validation)

if (!overall_pass) {
  stop("One-repository-at-a-time fixed-sample DiD comparison failed validation.")
}

cat("\nOne-repository-at-a-time fixed-sample DiD comparison completed successfully.\n")
