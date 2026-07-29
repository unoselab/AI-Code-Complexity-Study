#!/usr/bin/env Rscript

# Run fixed-sample static Borusyak DiD month-ablation diagnostics for the two
# influential control repositories identified by run-py-7p and run-py-8a.
#
# The original run-py-7h positive-month sample remains fixed. A month ablation
# sets only the selected repository-month class-method increment to zero; it
# does not remove the repository-month row, repository, or baseline regular
# module-function outcome.
#
# Scenarios:
#   - baseline regular module functions only
#   - cli-agent with all selected class methods
#   - cli-agent excluding 2025-06
#   - cli-agent excluding 2025-07
#   - cli-agent excluding both 2025-06 and 2025-07
#   - Webscout with all selected class methods
#   - Webscout excluding 2025-06
#   - Webscout excluding 2025-04
#   - Webscout excluding 2025-01
#   - Webscout excluding 2025-01, 2025-04, and 2025-06
#
# IMPORTANT:
#   This is supplementary fixed-sample debugging. It is not a primary causal
#   estimand and does not justify removing repositories or months.

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
  out[valid] <- 2 * pnorm(abs(estimate[valid] / std_error[valid]), lower.tail = FALSE)
  out
}

static_complete <- function(df) {
  required <- c("estimate", "std_error", "conf_low", "conf_high")
  nrow(df) == 1 &&
    all(required %in% names(df)) &&
    all(!is.na(as.data.frame(df)[, required, drop = FALSE]))
}

month_string <- function(x) {
  value <- trimws(as.character(x))
  value <- substr(value, 1L, 7L)
  if (!grepl("^[0-9]{4}-[0-9]{2}$", value)) {
    stop("Invalid YYYY-MM value: ", x)
  }
  value
}

project_root <- normalizePath(
  get_env("PROJECT_ROOT", normalizePath(".", mustWork = TRUE)),
  mustWork = TRUE
)
panel_path <- resolve_path(project_root, get_env("PANEL_PATH", required = TRUE))
run7n_checks_path <- resolve_path(
  project_root,
  get_env("RUN7N_CHECKS_PATH", required = TRUE)
)
reference_static_path <- resolve_path(
  project_root,
  get_env("REFERENCE_STATIC_PATH", required = TRUE)
)
helper_path <- resolve_path(project_root, get_env("HELPER_FILE", required = TRUE))
out_dir <- resolve_path(project_root, get_env("OUT_DIR", required = TRUE))

ncloc_spec <- tolower(get_env("NCLOC_SPEC", "python_snapshot"))
time_mode <- tolower(get_env("TIME_MODE", "calendar_month"))
min_treatment_cohort <- as.integer(get_env("MIN_TREATMENT_COHORT", "202408"))
max_treatment_cohort <- as.integer(get_env("MAX_TREATMENT_COHORT", "202503"))
repro_tolerance <- as.numeric(get_env("REPRO_TOLERANCE", "0.000001"))
skip_frozen_count_checks <- as_logical_strict(
  get_env("SKIP_FROZEN_COUNT_CHECKS", "0"),
  "SKIP_FROZEN_COUNT_CHECKS"
)

for (path in c(panel_path, run7n_checks_path, reference_static_path, helper_path)) {
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
method_added_column <- "selected_repo_method_agc_unique_bodies"
overlap_column <- "selected_repo_module_method_agc_unique_body_overlap"

cli_repo <- "pieces-app/cli-agent"
web_repo <- "HelpingAI/Webscout"

expected_repo_totals <- c(
  "pieces-app/cli-agent" = 60,
  "HelpingAI/Webscout" = 80
)
expected_month_increments <- c(
  "pieces-app/cli-agent|2025-06" = 24,
  "pieces-app/cli-agent|2025-07" = 22,
  "HelpingAI/Webscout|2025-01" = 10,
  "HelpingAI/Webscout|2025-04" = 18,
  "HelpingAI/Webscout|2025-06" = 30
)

scenario_definitions <- data.table(
  scenario_order = 1:10,
  scenario = c(
    "baseline_regular_module_function",
    "cliagent_all_methods",
    "cliagent_without_2025_06",
    "cliagent_without_2025_07",
    "cliagent_without_2025_06_2025_07",
    "webscout_all_methods",
    "webscout_without_2025_06",
    "webscout_without_2025_04",
    "webscout_without_2025_01",
    "webscout_without_2025_01_2025_04_2025_06"
  ),
  target_repo = c(
    NA_character_,
    cli_repo,
    cli_repo,
    cli_repo,
    cli_repo,
    web_repo,
    web_repo,
    web_repo,
    web_repo,
    web_repo
  ),
  excluded_months = c(
    "",
    "",
    "2025-06",
    "2025-07",
    "2025-06|2025-07",
    "",
    "2025-06",
    "2025-04",
    "2025-01",
    "2025-01|2025-04|2025-06"
  ),
  scenario_type = c(
    "baseline",
    "all_methods",
    "single_month_ablation",
    "single_month_ablation",
    "multi_month_ablation",
    "all_methods",
    "single_month_ablation",
    "single_month_ablation",
    "single_month_ablation",
    "multi_month_ablation"
  )
)

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
cat("Reference static result:", reference_static_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("Sample membership: fixed to original module-function outcome > 0\n")
cat("Month ablation changes method increments only; rows remain fixed.\n")
cat("WARNING: supplementary debugging only; causal primary use is NO.\n")

checks_upstream <- fread(run7n_checks_path)
require_columns(checks_upstream, c("check_name", "passed"), "run-py-7n checks")
checks_upstream[, passed_logical := as_logical_strict(passed, "run-py-7n passed")]
if (nrow(checks_upstream[passed_logical == FALSE]) > 0) {
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
detection_complete <- as_logical_strict(
  panel_raw$npr_detection_complete,
  "npr_detection_complete"
)
if (any(!fixed_membership)) {
  stop("Input membership is not uniformly fixed to run-py-7h.")
}
if (any(causal_allowed)) {
  stop("Input incorrectly permits causal interpretation.")
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
    (event_yyyymm >= min_treatment_cohort & event_yyyymm <= max_treatment_cohort)
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
panel_ready[, repo_name_str := as.character(repo_name)]
panel_ready[, repo_id := as.integer(factor(repo_name_str))]
panel_ready[, method_increment := get(hybrid_outcome) - get(baseline_outcome)]
panel_ready[, time_str := substr(as.character(time), 1L, 7L)]
model_data <- copy(panel_ready)

if (nrow(model_data) == 0) {
  stop("No repository-months remain for modeling.")
}
if (anyDuplicated(model_data[, .(dataset_source, repo_name, time)]) > 0) {
  stop("Model sample has duplicate repository-month keys.")
}

for (repo in c(cli_repo, web_repo)) {
  if (nrow(model_data[repo_name_str == repo]) == 0) {
    stop("Target repository is missing from model sample: ", repo)
  }
  if (!all(model_data[repo_name_str == repo, dataset_source] == "control")) {
    stop("Target repository is not uniformly control: ", repo)
  }
}

if (!skip_frozen_count_checks) {
  for (repo in names(expected_repo_totals)) {
    actual <- model_data[repo_name_str == repo, sum(method_increment)]
    if (!isTRUE(all.equal(as.numeric(actual), as.numeric(expected_repo_totals[[repo]])))) {
      stop("Unexpected total method increment for ", repo, ": ", actual)
    }
  }
  for (key in names(expected_month_increments)) {
    parts <- strsplit(key, "|", fixed = TRUE)[[1]]
    repo <- parts[[1]]
    month <- parts[[2]]
    actual <- model_data[
      repo_name_str == repo & time_str == month,
      sum(method_increment)
    ]
    if (!isTRUE(all.equal(as.numeric(actual), as.numeric(expected_month_increments[[key]])))) {
      stop("Unexpected method increment for ", repo, " ", month, ": ", actual)
    }
  }
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
cat("Planned static models:", nrow(scenario_definitions), "\n")
cat("First-stage formula:\n")
print(first_stage_formula)

model_errors <- list()
run_static_scenario <- function(definition) {
  target_repo <- definition$target_repo[[1]]
  excluded_text <- definition$excluded_months[[1]]
  excluded <- if (identical(excluded_text, "")) {
    character()
  } else {
    strsplit(excluded_text, "|", fixed = TRUE)[[1]]
  }

  analysis_data <- copy(model_data)
  analysis_data[, scenario_method_increment := 0]

  if (!is.na(target_repo)) {
    analysis_data[
      repo_name_str == target_repo,
      scenario_method_increment := method_increment
    ]
    if (length(excluded) > 0) {
      analysis_data[
        repo_name_str == target_repo & time_str %in% excluded,
        scenario_method_increment := 0
      ]
    }
  }

  analysis_data[, analysis_outcome :=
    as.numeric(get(baseline_outcome)) + scenario_method_increment]

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
      scenario_order = definition$scenario_order[[1]],
      scenario = definition$scenario[[1]],
      error = error_message
    )
  }

  extracted <- extract_static_result(result, "analysis_outcome")
  extracted$scenario_order <- definition$scenario_order[[1]]
  extracted$scenario <- definition$scenario[[1]]
  extracted$scenario_type <- definition$scenario_type[[1]]
  extracted$target_repo <- target_repo
  extracted$excluded_months <- excluded_text
  extracted$method_bodies_available <- if (is.na(target_repo)) {
    0
  } else {
    model_data[repo_name_str == target_repo, sum(method_increment)]
  }
  extracted$method_bodies_ablated <- if (is.na(target_repo) || length(excluded) == 0) {
    0
  } else {
    model_data[
      repo_name_str == target_repo & time_str %in% excluded,
      sum(method_increment)
    ]
  }
  extracted$method_bodies_retained <-
    extracted$method_bodies_available - extracted$method_bodies_ablated
  extracted$model_rows <- nrow(analysis_data)
  extracted$model_repositories <- uniqueN(analysis_data$repo_name_str)
  extracted$sample <- "original_regfun_positive_months_fixed"
  extracted$causal_interpretation_allowed <- FALSE
  extracted$repository_or_month_removal_justified <- FALSE
  extracted$p_value_approx <- normal_two_sided_p(
    extracted$estimate,
    extracted$std_error
  )
  extracted
}

result_list <- lapply(
  seq_len(nrow(scenario_definitions)),
  function(index) run_static_scenario(scenario_definitions[index])
)
static_results <- rbindlist(result_list, fill = TRUE)
setorder(static_results, scenario_order)

errors <- if (length(model_errors) == 0) {
  data.table(
    scenario_order = integer(),
    scenario = character(),
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

baseline_static <- static_results[scenario == "baseline_regular_module_function"]
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

all_method_lookup <- static_results[
  scenario %in% c("cliagent_all_methods", "webscout_all_methods"),
  .(
    target_repo,
    all_method_estimate = estimate,
    all_method_std_error = std_error,
    all_method_conf_low = conf_low,
    all_method_conf_high = conf_high,
    all_method_p_value_approx = p_value_approx
  )
]

comparison <- merge(
  copy(static_results),
  all_method_lookup,
  by = "target_repo",
  all.x = TRUE,
  sort = FALSE
)
setorder(comparison, scenario_order)
comparison[, baseline_estimate := baseline_static$estimate]
comparison[, baseline_std_error := baseline_static$std_error]
comparison[, baseline_conf_low := baseline_static$conf_low]
comparison[, baseline_conf_high := baseline_static$conf_high]
comparison[, delta_estimate_from_baseline := estimate - baseline_estimate]
comparison[, delta_std_error_from_baseline := std_error - baseline_std_error]
comparison[, delta_conf_low_from_baseline := conf_low - baseline_conf_low]
comparison[, ci_includes_zero := conf_low <= 0 & conf_high >= 0]
comparison[, ci_strictly_positive := conf_low > 0]
comparison[, ci_strictly_negative := conf_high < 0]
comparison[, restores_positive_ci_after_ablation :=
  scenario_type %in% c("single_month_ablation", "multi_month_ablation") &
    ci_strictly_positive]
comparison[, estimate_recovery_from_all_methods := estimate - all_method_estimate]
comparison[, std_error_reduction_from_all_methods := all_method_std_error - std_error]
comparison[, lower_bound_recovery_from_all_methods := conf_low - all_method_conf_low]
comparison[, lower_bound_recovery_estimate_component :=
  estimate - all_method_estimate]
comparison[, lower_bound_recovery_se_component :=
  1.96 * (all_method_std_error - std_error)]
comparison[, lower_bound_recovery_decomposition_error :=
  lower_bound_recovery_from_all_methods -
    lower_bound_recovery_estimate_component -
    lower_bound_recovery_se_component]
comparison[, lower_bound_recovery_per_ablated_body := fifelse(
  method_bodies_ablated > 0,
  lower_bound_recovery_from_all_methods / method_bodies_ablated,
  NA_real_
)]
comparison[, ablation_channel := fifelse(
  scenario_type == "baseline",
  "baseline",
  fifelse(
    scenario_type == "all_methods",
    "all_methods_reference",
    fifelse(
      estimate_recovery_from_all_methods > 0 &
        std_error_reduction_from_all_methods > 0,
      "estimate_and_se_recovery",
      fifelse(
        estimate_recovery_from_all_methods > 0,
        "estimate_recovery_offset_by_se",
        fifelse(
          std_error_reduction_from_all_methods > 0,
          "se_recovery_offset_by_estimate",
          "no_lower_bound_recovery"
        )
      )
    )
  )
)]

ranking <- comparison[
  scenario_type %in% c("single_month_ablation", "multi_month_ablation")
]
setorder(
  ranking,
  -lower_bound_recovery_from_all_methods,
  -lower_bound_recovery_per_ablated_body
)
ranking[, impact_rank_lower_bound_recovery := seq_len(.N)]

scenario_month_audit <- rbindlist(
  lapply(seq_len(nrow(scenario_definitions)), function(index) {
    definition <- scenario_definitions[index]
    target_repo <- definition$target_repo[[1]]
    excluded_text <- definition$excluded_months[[1]]
    if (is.na(target_repo)) {
      return(data.table(
        scenario_order = definition$scenario_order,
        scenario = definition$scenario,
        target_repo = NA_character_,
        month = NA_character_,
        baseline_outcome = sum(model_data[[baseline_outcome]]),
        method_increment_available = 0,
        method_increment_retained = 0,
        method_increment_ablated = 0
      ))
    }
    excluded <- if (identical(excluded_text, "")) character() else
      strsplit(excluded_text, "|", fixed = TRUE)[[1]]
    subset <- model_data[repo_name_str == target_repo]
    subset[, .(
      scenario_order = definition$scenario_order,
      scenario = definition$scenario,
      target_repo = target_repo,
      month = time_str,
      baseline_outcome = get(baseline_outcome),
      method_increment_available = method_increment,
      method_increment_retained = fifelse(
        time_str %in% excluded,
        0,
        method_increment
      ),
      method_increment_ablated = fifelse(
        time_str %in% excluded,
        method_increment,
        0
      )
    )]
  })
)

validation <- data.table(
  check_name = c(
    "run7n_upstream_checks_all_pass",
    "input_rows_match_expected_fixed_sample",
    "input_repositories_match_expected",
    "input_baseline_outcome_strictly_positive",
    "input_membership_fixed_to_run7h",
    "model_rows_match_expected",
    "model_treatment_repositories_match_expected",
    "model_control_repositories_match_expected",
    "target_controls_present",
    "scenario_count_match_expected",
    "static_model_error_count",
    "static_results_complete",
    "baseline_reproduces_run7h_within_tolerance",
    "lower_bound_recovery_decomposition_within_tolerance",
    "sample_rows_identical_across_scenarios",
    "analysis_labeled_noncausal_debugging"
  ),
  value = c(
    nrow(checks_upstream[passed_logical == FALSE]),
    nrow(panel_raw),
    uniqueN(panel_raw$repo_name),
    sum(panel_raw[[baseline_outcome]] <= 0, na.rm = TRUE),
    sum(!fixed_membership),
    nrow(model_data),
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]),
    uniqueN(model_data[dataset_source == "control", repo_name_str]),
    sum(c(cli_repo, web_repo) %in% unique(model_data$repo_name_str)),
    nrow(static_results),
    nrow(errors),
    sum(!complete.cases(static_results[, .(estimate, std_error, conf_low, conf_high)])),
    baseline_reference_difference,
    max(abs(comparison$lower_bound_recovery_decomposition_error), na.rm = TRUE),
    uniqueN(static_results$model_rows),
    sum(static_results$causal_interpretation_allowed)
  ),
  passed = c(
    TRUE,
    nrow(panel_raw) == 487,
    uniqueN(panel_raw$repo_name) == 132,
    sum(panel_raw[[baseline_outcome]] <= 0, na.rm = TRUE) == 0,
    sum(!fixed_membership) == 0,
    nrow(model_data) == 486,
    uniqueN(model_data[dataset_source == "treatment", repo_name_str]) == 75,
    uniqueN(model_data[dataset_source == "control", repo_name_str]) == 57,
    sum(c(cli_repo, web_repo) %in% unique(model_data$repo_name_str)) == 2,
    nrow(static_results) == 10,
    nrow(errors) == 0,
    sum(!complete.cases(static_results[, .(estimate, std_error, conf_low, conf_high)])) == 0,
    baseline_reference_difference <= repro_tolerance,
    max(abs(comparison$lower_bound_recovery_decomposition_error), na.rm = TRUE) <= repro_tolerance,
    uniqueN(static_results$model_rows) == 1,
    sum(static_results$causal_interpretation_allowed) == 0
  )
)

failed_validation <- validation[passed == FALSE]
if (nrow(failed_validation) > 0) {
  print(failed_validation)
  stop("Month-ablation validation failed.")
}

prefix <- "cliagent_webscout_classmethod_month_ablation_fixed_sample"
static_file <- file.path(out_dir, paste0(prefix, "_static_results.csv"))
comparison_file <- file.path(out_dir, paste0(prefix, "_comparison.csv"))
ranking_file <- file.path(out_dir, paste0(prefix, "_root_cause_ranking.csv"))
scenario_file <- file.path(out_dir, paste0(prefix, "_scenario_definitions.csv"))
month_audit_file <- file.path(out_dir, paste0(prefix, "_scenario_month_audit.csv"))
validation_file <- file.path(out_dir, paste0(prefix, "_validation.csv"))
errors_file <- file.path(out_dir, paste0(prefix, "_model_errors.csv"))
metadata_file <- file.path(out_dir, paste0(prefix, "_metadata.csv"))
status_file <- file.path(out_dir, paste0(prefix, "_status.txt"))

fwrite(static_results, static_file)
fwrite(comparison, comparison_file)
fwrite(ranking, ranking_file)
fwrite(scenario_definitions, scenario_file)
fwrite(scenario_month_audit, month_audit_file)
fwrite(validation, validation_file)
fwrite(errors, errors_file)
fwrite(
  data.table(
    metadata_key = c(
      "analysis",
      "sample",
      "method_ablation_unit",
      "pair_id_used_directly_in_estimator",
      "causal_interpretation_allowed",
      "repository_or_month_removal_justified",
      "time_encoding",
      "first_stage_formula"
    ),
    value = c(
      "fixed-sample control class-method spike-month ablation",
      "original run-py-7h positive regular-function months",
      "repository-month method increment set to zero; row retained",
      "FALSE",
      "FALSE",
      "FALSE",
      time_encoding_used,
      paste(deparse(first_stage_formula), collapse = " ")
    )
  ),
  metadata_file
)
writeLines(
  c(
    "PASS",
    "Month ablation changes method increments only; sample rows are retained.",
    "Pair alignment is audited separately and pair IDs are not passed to the static estimator.",
    "This is supplementary debugging and does not justify repository or month removal."
  ),
  status_file
)

cat("\nStatic month-ablation results:\n")
print(static_results[, .(
  scenario_order,
  scenario,
  target_repo,
  excluded_months,
  method_bodies_ablated,
  estimate,
  std_error,
  conf_low,
  conf_high,
  p_value_approx
)])
cat("\nRoot-cause ranking by lower-bound recovery from all-method scenario:\n")
print(ranking[, .(
  impact_rank_lower_bound_recovery,
  scenario,
  target_repo,
  excluded_months,
  method_bodies_ablated,
  estimate,
  std_error,
  conf_low,
  conf_high,
  lower_bound_recovery_from_all_methods,
  lower_bound_recovery_per_ablated_body,
  restores_positive_ci_after_ablation,
  ablation_channel
)])
cat("\nValidation:\n")
print(validation)
cat("\nFixed-sample month-ablation analysis completed successfully.\n")
cat("Output directory:", out_dir, "\n")
