#!/usr/bin/env Rscript

# Compare pooled and pair-balanced fixed-positive-sample Borusyak static DiD
# specifications for the Webscout class-method influence diagnosis.
#
# This script performs two related supplementary sensitivity checks:
#   1. In the original pooled fixed sample, jointly ablate HelpingAI/Webscout
#      class-method increments in 2025-04 and 2025-06 while retaining rows.
#   2. Re-estimate baseline and Webscout scenarios on a pair-balanced monthly
#      support sample prepared by the companion Python script. A row enters
#      this sample only when it participates in at least one original matched
#      treatment-control pair observed in the same calendar month.
#
# Important interpretation constraints:
#   - The original paper replication remains the pooled matched-control DiD.
#   - Pair IDs are used to construct the sensitivity sample, not as regressors
#     or direct identifiers in the Borusyak estimator.
#   - The source sample is conditioned on a positive realized outcome.
#   - Every result from this script is noncausal supplementary debugging.

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

max_numeric_difference <- function(left, right, columns) {
  if (nrow(left) != 1 || nrow(right) != 1) {
    return(Inf)
  }
  max(abs(unlist(left[, ..columns]) - unlist(right[, ..columns])))
}

project_root <- normalizePath(
  get_env("PROJECT_ROOT", normalizePath(".", mustWork = TRUE)),
  mustWork = TRUE
)
pooled_panel_path <- resolve_path(
  project_root,
  get_env("POOLED_PANEL_PATH", required = TRUE)
)
pair_panel_path <- resolve_path(
  project_root,
  get_env("PAIR_PANEL_PATH", required = TRUE)
)
pair_validation_path <- resolve_path(
  project_root,
  get_env("PAIR_VALIDATION_PATH", required = TRUE)
)
run7n_checks_path <- resolve_path(
  project_root,
  get_env("RUN7N_CHECKS_PATH", required = TRUE)
)
reference_baseline_path <- resolve_path(
  project_root,
  get_env("REFERENCE_BASELINE_PATH", required = TRUE)
)
reference_run7p_path <- resolve_path(
  project_root,
  get_env("REFERENCE_RUN7P_PATH", required = TRUE)
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
skip_frozen_count_checks <- as_logical_strict(
  get_env("SKIP_FROZEN_COUNT_CHECKS", "0"),
  "SKIP_FROZEN_COUNT_CHECKS"
)

required_paths <- c(
  pooled_panel_path,
  pair_panel_path,
  pair_validation_path,
  run7n_checks_path,
  reference_baseline_path,
  reference_run7p_path,
  helper_path
)
for (path in required_paths) {
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
webscout_repo <- "HelpingAI/Webscout"
webscout_joint_months <- c("2025-04", "2025-06")
expected_webscout_total <- 80
expected_joint_increment <- 48

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

common_required_columns <- c(
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
  baseline_readiness,
  hybrid_readiness,
  "sample_membership_fixed_to_run_py_7h",
  "causal_interpretation_allowed",
  "sample_restriction",
  covariates
)

scenario_definitions <- data.table(
  scenario_order = 1:6,
  scenario = c(
    "pooled_baseline_regular_module_function",
    "pooled_webscout_all_methods",
    "pooled_webscout_without_2025_04_2025_06",
    "pair_balanced_baseline_regular_module_function",
    "pair_balanced_webscout_all_methods",
    "pair_balanced_webscout_without_2025_04_2025_06"
  ),
  sample_name = c(
    "pooled_fixed_positive",
    "pooled_fixed_positive",
    "pooled_fixed_positive",
    "pair_balanced_fixed_positive",
    "pair_balanced_fixed_positive",
    "pair_balanced_fixed_positive"
  ),
  target_repo = c(
    NA_character_,
    webscout_repo,
    webscout_repo,
    NA_character_,
    webscout_repo,
    webscout_repo
  ),
  excluded_months = c(
    "",
    "",
    "2025-04|2025-06",
    "",
    "",
    "2025-04|2025-06"
  ),
  scenario_type = c(
    "baseline",
    "all_methods",
    "joint_month_ablation",
    "baseline",
    "all_methods",
    "joint_month_ablation"
  ),
  pair_balance_applied = c(FALSE, FALSE, FALSE, TRUE, TRUE, TRUE)
)

cat("Project root:", project_root, "\n")
cat("Pooled fixed panel:", pooled_panel_path, "\n")
cat("Pair-balanced panel:", pair_panel_path, "\n")
cat("Pair-panel validation:", pair_validation_path, "\n")
cat("Reference baseline:", reference_baseline_path, "\n")
cat("Reference run-py-7p:", reference_run7p_path, "\n")
cat("Helper file:", helper_path, "\n")
cat("Output directory:", out_dir, "\n")
cat("Webscout joint ablation months: 2025-04 and 2025-06\n")
cat("Pair balance definition: at least one original matched counterpart in the same calendar month\n")
cat("Pair IDs are not passed directly to the estimator.\n")
cat("WARNING: noncausal supplementary selected-sample sensitivity only.\n")

run7n_checks <- fread(run7n_checks_path)
require_columns(run7n_checks, c("check_name", "passed"), "run-py-7n checks")
run7n_checks[, passed_logical := as_logical_strict(passed, "run-py-7n passed")]
if (nrow(run7n_checks[passed_logical == FALSE]) > 0) {
  stop("run-py-7n has failed upstream checks.")
}

pair_checks <- fread(pair_validation_path)
require_columns(pair_checks, c("check_name", "passed"), "Pair-panel checks")
pair_checks[, passed_logical := as_logical_strict(passed, "Pair-panel passed")]
if (nrow(pair_checks[passed_logical == FALSE]) > 0) {
  stop("Pair-balanced panel preparation has failed upstream checks.")
}

prepare_model_sample <- function(panel_raw, sample_name, require_pair_support = FALSE) {
  require_columns(panel_raw, common_required_columns, sample_name)
  if (require_pair_support) {
    require_columns(
      panel_raw,
      c(
        "pair_balanced_support",
        "pair_support_count",
        "pair_id_used_directly_in_estimator",
        "pair_balance_applied_to_sample_construction",
        "pair_balanced_sensitivity_only"
      ),
      sample_name
    )
  }

  if (anyDuplicated(panel_raw[, .(dataset_source, repo_name, time)]) > 0) {
    stop(sample_name, " contains duplicate repository-month keys.")
  }
  if (!all(panel_raw$dataset_source %in% c("control", "treatment"))) {
    stop(sample_name, " contains unexpected dataset_source values.")
  }
  if (any(panel_raw$has_parse_exclusion != 0, na.rm = TRUE)) {
    stop(sample_name, " unexpectedly contains parse-exclusion rows.")
  }
  if (any(as.character(panel_raw$npr_specification) != "range100_200")) {
    stop(sample_name, " contains an unexpected NPR specification.")
  }
  if (any(panel_raw[[baseline_outcome]] <= 0, na.rm = TRUE)) {
    stop(sample_name, " contains a nonpositive baseline outcome.")
  }

  fixed_membership <- as_logical_strict(
    panel_raw$sample_membership_fixed_to_run_py_7h,
    paste0(sample_name, " sample_membership_fixed_to_run_py_7h")
  )
  causal_allowed <- as_logical_strict(
    panel_raw$causal_interpretation_allowed,
    paste0(sample_name, " causal_interpretation_allowed")
  )
  detection_complete <- as_logical_strict(
    panel_raw$npr_detection_complete,
    paste0(sample_name, " npr_detection_complete")
  )
  if (any(!fixed_membership)) {
    stop(sample_name, " is not uniformly fixed to run-py-7h membership.")
  }
  if (any(causal_allowed)) {
    stop(sample_name, " incorrectly permits causal interpretation.")
  }
  if (any(!detection_complete)) {
    stop(sample_name, " has incomplete NPR detection rows.")
  }
  if (any(as.character(panel_raw$sample_restriction) !=
          "original_module_function_outcome > 0")) {
    stop(sample_name, " has an unexpected source-sample restriction.")
  }
  if (any(panel_raw[[baseline_readiness]] != panel_raw[[hybrid_readiness]], na.rm = TRUE)) {
    stop(sample_name, " has mismatched baseline and hybrid readiness.")
  }

  if (require_pair_support) {
    pair_support <- as_logical_strict(
      panel_raw$pair_balanced_support,
      paste0(sample_name, " pair_balanced_support")
    )
    pair_id_direct <- as_logical_strict(
      panel_raw$pair_id_used_directly_in_estimator,
      paste0(sample_name, " pair_id_used_directly_in_estimator")
    )
    pair_applied <- as_logical_strict(
      panel_raw$pair_balance_applied_to_sample_construction,
      paste0(sample_name, " pair_balance_applied_to_sample_construction")
    )
    sensitivity_only <- as_logical_strict(
      panel_raw$pair_balanced_sensitivity_only,
      paste0(sample_name, " pair_balanced_sensitivity_only")
    )
    if (any(!pair_support) || any(panel_raw$pair_support_count <= 0)) {
      stop(sample_name, " contains rows without positive pair support.")
    }
    if (any(pair_id_direct)) {
      stop(sample_name, " incorrectly marks pair IDs for direct estimator use.")
    }
    if (any(!pair_applied) || any(!sensitivity_only)) {
      stop(sample_name, " does not carry the required pair-sensitivity labels.")
    }
  }

  panel_ready <- copy(panel_raw)
  panel_ready <- panel_ready[
    get(baseline_readiness) == 1 & get(hybrid_readiness) == 1
  ]
  ready_rows <- nrow(panel_ready)

  model_required <- c(baseline_outcome, hybrid_outcome, covariates)
  missing_model_rows <- sum(!complete.cases(panel_ready[, ..model_required]))
  if (missing_model_rows > 0) {
    stop(sample_name, " has missing model values: ", missing_model_rows)
  }

  panel_ready[, time_yyyymm := normalize_yyyymm(time)]
  event_yyyymm <- normalize_yyyymm(panel_ready$event)
  event_yyyymm[is.na(event_yyyymm)] <- 0L
  panel_ready[, event_yyyymm := event_yyyymm]

  membership_mismatch <- panel_ready[
    , sum((dataset_source == "treatment") != (event_yyyymm > 0L))
  ]
  if (membership_mismatch > 0) {
    stop(sample_name, " event encoding disagrees with dataset_source.")
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
  panel_ready[, time_str := substr(as.character(time), 1L, 7L)]
  panel_ready[, method_increment :=
    as.numeric(get(hybrid_outcome)) - as.numeric(get(baseline_outcome))]

  if (nrow(panel_ready) == 0) {
    stop(sample_name, " has no rows after readiness and cohort filters.")
  }
  if (anyDuplicated(panel_ready[, .(dataset_source, repo_name, time)]) > 0) {
    stop(sample_name, " model sample has duplicate repository-month keys.")
  }
  if (!all(c("treatment", "control") %in% unique(panel_ready$dataset_source))) {
    stop(sample_name, " model sample lacks treatment or control rows.")
  }

  list(
    data = panel_ready,
    summary = data.table(
      sample_name = sample_name,
      input_rows = nrow(panel_raw),
      readiness_rows = ready_rows,
      model_rows = nrow(panel_ready),
      repositories = uniqueN(panel_ready$repo_name_str),
      treatment_repositories = uniqueN(
        panel_ready[dataset_source == "treatment", repo_name_str]
      ),
      control_repositories = uniqueN(
        panel_ready[dataset_source == "control", repo_name_str]
      ),
      treatment_rows = nrow(panel_ready[dataset_source == "treatment"]),
      control_rows = nrow(panel_ready[dataset_source == "control"]),
      baseline_outcome_total = sum(panel_ready[[baseline_outcome]]),
      webscout_method_increment_total = panel_ready[
        repo_name_str == webscout_repo,
        sum(method_increment)
      ],
      webscout_joint_month_increment = panel_ready[
        repo_name_str == webscout_repo & time_str %in% webscout_joint_months,
        sum(method_increment)
      ],
      time_encoding = time_encoding_used,
      causal_interpretation_allowed = FALSE
    )
  )
}

pooled_raw <- fread(pooled_panel_path)
pair_raw <- fread(pair_panel_path)
pooled_prepared <- prepare_model_sample(
  pooled_raw,
  "pooled_fixed_positive",
  require_pair_support = FALSE
)
pair_prepared <- prepare_model_sample(
  pair_raw,
  "pair_balanced_fixed_positive",
  require_pair_support = TRUE
)

sample_data <- list(
  pooled_fixed_positive = pooled_prepared$data,
  pair_balanced_fixed_positive = pair_prepared$data
)
sample_summary <- rbindlist(
  list(pooled_prepared$summary, pair_prepared$summary),
  fill = TRUE
)

if (!skip_frozen_count_checks) {
  pooled_total <- sample_summary[
    sample_name == "pooled_fixed_positive",
    webscout_method_increment_total
  ]
  pooled_joint <- sample_summary[
    sample_name == "pooled_fixed_positive",
    webscout_joint_month_increment
  ]
  if (!isTRUE(all.equal(as.numeric(pooled_total), expected_webscout_total))) {
    stop("Unexpected pooled Webscout method increment total: ", pooled_total)
  }
  if (!isTRUE(all.equal(as.numeric(pooled_joint), expected_joint_increment))) {
    stop("Unexpected pooled Webscout 2025-04+2025-06 increment: ", pooled_joint)
  }
}

first_stage_formula <- as.formula(
  paste0(
    "~ ",
    paste(covariates, collapse = " + "),
    " | repo_id + time_id"
  )
)

cat("\nSample summary before model estimation:\n")
print(sample_summary)
cat("\nFirst-stage formula:\n")
print(first_stage_formula)

model_errors <- list()
run_scenario <- function(definition) {
  sample_name <- definition$sample_name[[1]]
  data <- copy(sample_data[[sample_name]])
  target_repo <- definition$target_repo[[1]]
  excluded_text <- definition$excluded_months[[1]]
  excluded <- if (identical(excluded_text, "")) {
    character()
  } else {
    strsplit(excluded_text, "|", fixed = TRUE)[[1]]
  }

  data[, scenario_method_increment := 0]
  if (!is.na(target_repo)) {
    data[
      repo_name_str == target_repo,
      scenario_method_increment := method_increment
    ]
    if (length(excluded) > 0) {
      data[
        repo_name_str == target_repo & time_str %in% excluded,
        scenario_method_increment := 0
      ]
    }
  }
  data[, analysis_outcome :=
    as.numeric(get(baseline_outcome)) + scenario_method_increment]

  error_message <- NA_character_
  result <- tryCatch(
    run_borusyak_static(
      data = data,
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
      sample_name = sample_name,
      error = error_message
    )
  }

  extracted <- as.data.table(extract_static_result(result, "analysis_outcome"))
  extracted[, scenario_order := definition$scenario_order[[1]]]
  extracted[, scenario := definition$scenario[[1]]]
  extracted[, sample_name := sample_name]
  extracted[, scenario_type := definition$scenario_type[[1]]]
  extracted[, pair_balance_applied := definition$pair_balance_applied[[1]]]
  extracted[, target_repo := target_repo]
  extracted[, excluded_months := excluded_text]
  extracted[, available_method_bodies := data[
    repo_name_str == webscout_repo,
    sum(method_increment)
  ]]
  extracted[, retained_method_bodies := sum(data$scenario_method_increment)]
  extracted[, ablated_method_bodies :=
    available_method_bodies - retained_method_bodies]
  extracted[, model_rows := nrow(data)]
  extracted[, model_repositories := uniqueN(data$repo_name_str)]
  extracted[, treatment_repositories := uniqueN(
    data[dataset_source == "treatment", repo_name_str]
  )]
  extracted[, control_repositories := uniqueN(
    data[dataset_source == "control", repo_name_str]
  )]
  extracted[, treatment_rows := nrow(data[dataset_source == "treatment"])]
  extracted[, control_rows := nrow(data[dataset_source == "control"])]
  extracted[, outcome_total := sum(data$analysis_outcome)]
  extracted[, p_value_approx := normal_two_sided_p(estimate, std_error)]
  extracted[, ci_includes_zero := conf_low <= 0 & conf_high >= 0]
  extracted[, ci_strictly_positive := conf_low > 0]
  extracted[, causal_interpretation_allowed := FALSE]
  extracted[, pair_id_used_directly_in_estimator := FALSE]
  extracted
}

scenario_results <- lapply(
  seq_len(nrow(scenario_definitions)),
  function(index) run_scenario(scenario_definitions[index])
)
static_results <- rbindlist(scenario_results, fill = TRUE)
setorder(static_results, scenario_order)
errors <- if (length(model_errors) == 0) {
  data.table(
    scenario_order = integer(),
    scenario = character(),
    sample_name = character(),
    error = character()
  )
} else {
  rbindlist(model_errors, fill = TRUE)
}

reference_baseline <- fread(reference_baseline_path)
require_columns(
  reference_baseline,
  c("estimate", "std_error", "conf_low", "conf_high"),
  "run-py-7h reference baseline"
)
reference_baseline <- reference_baseline[1]

reference_run7p <- fread(reference_run7p_path)
require_columns(
  reference_run7p,
  c("model", "added_repo_name", "estimate", "std_error", "conf_low", "conf_high"),
  "run-py-7p static results"
)
reference_webscout <- reference_run7p[
  added_repo_name == webscout_repo |
    model == "baseline_plus_helpingai_webscout"
]
if (nrow(reference_webscout) != 1) {
  stop("Could not identify exactly one Webscout row in run-py-7p reference results.")
}

metric_columns <- c("estimate", "std_error", "conf_low", "conf_high")
pooled_baseline <- static_results[
  scenario == "pooled_baseline_regular_module_function"
]
pooled_webscout_all <- static_results[
  scenario == "pooled_webscout_all_methods"
]
pooled_webscout_joint <- static_results[
  scenario == "pooled_webscout_without_2025_04_2025_06"
]
pair_baseline <- static_results[
  scenario == "pair_balanced_baseline_regular_module_function"
]
pair_webscout_all <- static_results[
  scenario == "pair_balanced_webscout_all_methods"
]
pair_webscout_joint <- static_results[
  scenario == "pair_balanced_webscout_without_2025_04_2025_06"
]

baseline_reference_difference <- max_numeric_difference(
  pooled_baseline,
  reference_baseline,
  metric_columns
)
webscout_reference_difference <- max_numeric_difference(
  pooled_webscout_all,
  reference_webscout,
  metric_columns
)
pair_all_joint_difference <- max_numeric_difference(
  pair_webscout_all,
  pair_webscout_joint,
  metric_columns
)

build_key_comparison <- function(
  comparison_name,
  left_label,
  left_row,
  right_label,
  right_row
) {
  data.table(
    comparison_name = comparison_name,
    left_scenario = left_label,
    right_scenario = right_label,
    left_estimate = left_row$estimate,
    right_estimate = right_row$estimate,
    delta_estimate_right_minus_left = right_row$estimate - left_row$estimate,
    left_std_error = left_row$std_error,
    right_std_error = right_row$std_error,
    delta_std_error_right_minus_left = right_row$std_error - left_row$std_error,
    left_conf_low = left_row$conf_low,
    right_conf_low = right_row$conf_low,
    delta_conf_low_right_minus_left = right_row$conf_low - left_row$conf_low,
    left_conf_high = left_row$conf_high,
    right_conf_high = right_row$conf_high,
    left_ci_includes_zero = left_row$ci_includes_zero,
    right_ci_includes_zero = right_row$ci_includes_zero,
    left_ci_strictly_positive = left_row$ci_strictly_positive,
    right_ci_strictly_positive = right_row$ci_strictly_positive,
    causal_interpretation_allowed = FALSE
  )
}

key_comparisons <- rbindlist(
  list(
    build_key_comparison(
      "pooled_webscout_joint_ablation_recovery",
      pooled_webscout_all$scenario,
      pooled_webscout_all,
      pooled_webscout_joint$scenario,
      pooled_webscout_joint
    ),
    build_key_comparison(
      "pair_balance_change_for_baseline",
      pooled_baseline$scenario,
      pooled_baseline,
      pair_baseline$scenario,
      pair_baseline
    ),
    build_key_comparison(
      "pair_balance_change_for_webscout_all_methods",
      pooled_webscout_all$scenario,
      pooled_webscout_all,
      pair_webscout_all$scenario,
      pair_webscout_all
    ),
    build_key_comparison(
      "pair_balance_change_for_webscout_joint_ablation",
      pooled_webscout_joint$scenario,
      pooled_webscout_joint,
      pair_webscout_joint$scenario,
      pair_webscout_joint
    ),
    build_key_comparison(
      "pair_balanced_all_methods_vs_joint_ablation",
      pair_webscout_all$scenario,
      pair_webscout_all,
      pair_webscout_joint$scenario,
      pair_webscout_joint
    )
  ),
  fill = TRUE
)

sample_summary_for_cast <- copy(sample_summary)
sample_summary_for_cast[, comparison_id := "pooled_vs_pair_balanced"]
sample_comparison <- dcast(
  sample_summary_for_cast,
  comparison_id ~ sample_name,
  value.var = c(
    "input_rows",
    "model_rows",
    "repositories",
    "treatment_repositories",
    "control_repositories",
    "treatment_rows",
    "control_rows",
    "baseline_outcome_total",
    "webscout_method_increment_total",
    "webscout_joint_month_increment"
  )
)
sample_comparison[, `:=`(
  input_row_retention_share =
    input_rows_pair_balanced_fixed_positive / input_rows_pooled_fixed_positive,
  model_row_retention_share =
    model_rows_pair_balanced_fixed_positive / model_rows_pooled_fixed_positive,
  repository_retention_share =
    repositories_pair_balanced_fixed_positive / repositories_pooled_fixed_positive,
  treatment_repository_retention_share =
    treatment_repositories_pair_balanced_fixed_positive /
      treatment_repositories_pooled_fixed_positive,
  control_repository_retention_share =
    control_repositories_pair_balanced_fixed_positive /
      control_repositories_pooled_fixed_positive
)]

validation <- data.table(
  check_name = c(
    "run7n_upstream_checks_all_pass",
    "pair_panel_upstream_checks_all_pass",
    "pooled_input_rows_match_run7n",
    "pair_input_is_smaller_than_pooled_input",
    "pair_model_is_smaller_than_pooled_model",
    "pair_sample_has_treatment_and_control_repositories",
    "pooled_webscout_method_total_matches_expected",
    "pooled_webscout_joint_increment_matches_expected",
    "pair_sample_removes_webscout_joint_month_increment",
    "scenario_count_matches_expected",
    "static_model_error_count",
    "static_results_complete",
    "pooled_baseline_reproduces_run7h",
    "pooled_webscout_all_reproduces_run7p",
    "pair_all_and_joint_ablation_are_identical",
    "sample_rows_identical_within_each_sample",
    "pair_ids_not_used_directly",
    "analysis_labeled_noncausal_sensitivity"
  ),
  value = c(
    nrow(run7n_checks[passed_logical == FALSE]),
    nrow(pair_checks[passed_logical == FALSE]),
    pooled_prepared$summary$input_rows,
    pair_prepared$summary$input_rows,
    pair_prepared$summary$model_rows,
    min(
      pair_prepared$summary$treatment_repositories,
      pair_prepared$summary$control_repositories
    ),
    pooled_prepared$summary$webscout_method_increment_total,
    pooled_prepared$summary$webscout_joint_month_increment,
    pair_prepared$summary$webscout_joint_month_increment,
    nrow(static_results),
    nrow(errors),
    sum(!complete.cases(static_results[, ..metric_columns])),
    baseline_reference_difference,
    webscout_reference_difference,
    pair_all_joint_difference,
    static_results[, uniqueN(model_rows), by = sample_name][, max(V1)],
    sum(static_results$pair_id_used_directly_in_estimator),
    sum(static_results$causal_interpretation_allowed)
  ),
  passed = c(
    TRUE,
    TRUE,
    pooled_prepared$summary$input_rows == 487,
    pair_prepared$summary$input_rows < pooled_prepared$summary$input_rows,
    pair_prepared$summary$model_rows < pooled_prepared$summary$model_rows,
    pair_prepared$summary$treatment_repositories > 0 &
      pair_prepared$summary$control_repositories > 0,
    skip_frozen_count_checks |
      pooled_prepared$summary$webscout_method_increment_total == expected_webscout_total,
    skip_frozen_count_checks |
      pooled_prepared$summary$webscout_joint_month_increment == expected_joint_increment,
    pair_prepared$summary$webscout_joint_month_increment == 0,
    nrow(static_results) == 6,
    nrow(errors) == 0,
    sum(!complete.cases(static_results[, ..metric_columns])) == 0,
    baseline_reference_difference <= repro_tolerance,
    webscout_reference_difference <= repro_tolerance,
    pair_all_joint_difference <= repro_tolerance,
    static_results[, uniqueN(model_rows), by = sample_name][, max(V1)] == 1,
    sum(static_results$pair_id_used_directly_in_estimator) == 0,
    sum(static_results$causal_interpretation_allowed) == 0
  )
)

failed_validation <- validation[passed == FALSE]
if (nrow(failed_validation) > 0) {
  print(failed_validation)
  stop("run-py-8c validation failed.")
}

prefix <- "borusyak_webscout_joint_ablation_pair_balanced_sensitivity"
static_file <- file.path(out_dir, paste0(prefix, "_static_results.csv"))
comparison_file <- file.path(out_dir, paste0(prefix, "_key_comparisons.csv"))
sample_summary_file <- file.path(out_dir, paste0(prefix, "_sample_summary.csv"))
sample_comparison_file <- file.path(out_dir, paste0(prefix, "_sample_comparison.csv"))
scenario_file <- file.path(out_dir, paste0(prefix, "_scenario_definitions.csv"))
validation_file <- file.path(out_dir, paste0(prefix, "_validation.csv"))
errors_file <- file.path(out_dir, paste0(prefix, "_model_errors.csv"))
metadata_file <- file.path(out_dir, paste0(prefix, "_metadata.csv"))
status_file <- file.path(out_dir, paste0(prefix, "_status.txt"))

fwrite(static_results, static_file)
fwrite(key_comparisons, comparison_file)
fwrite(sample_summary, sample_summary_file)
fwrite(sample_comparison, sample_comparison_file)
fwrite(scenario_definitions, scenario_file)
fwrite(validation, validation_file)
fwrite(errors, errors_file)
fwrite(
  data.table(
    metadata_key = c(
      "analysis",
      "source_sample",
      "joint_ablation",
      "pair_balance_definition",
      "pair_id_used_directly_in_estimator",
      "primary_replication_replacement",
      "causal_interpretation_allowed",
      "time_encoding",
      "first_stage_formula"
    ),
    value = c(
      "Webscout joint-month ablation and pair-balanced monthly-support sensitivity",
      "original run-py-7h positive regular-module-function months",
      "set Webscout 2025-04 and 2025-06 method increments to zero; retain rows",
      paste0(
        "retain a repository-month when at least one original matched counterpart ",
        "is present in the same calendar month of the fixed positive sample"
      ),
      "FALSE",
      "FALSE",
      "FALSE",
      pooled_prepared$summary$time_encoding,
      paste(deparse(first_stage_formula), collapse = " ")
    )
  ),
  metadata_file
)
writeLines(
  c(
    "PASS",
    "The pooled sample remains the original-paper-compatible estimator structure.",
    "The pair-balanced sample is supplementary monthly-support sensitivity only.",
    "Pair IDs are used for sample construction and are not passed to the estimator.",
    "The positive-outcome source sample prevents primary causal interpretation."
  ),
  status_file
)

cat("\nStatic results:\n")
print(static_results[, .(
  scenario_order,
  scenario,
  sample_name,
  excluded_months,
  available_method_bodies,
  retained_method_bodies,
  ablated_method_bodies,
  model_rows,
  model_repositories,
  treatment_repositories,
  control_repositories,
  estimate,
  std_error,
  conf_low,
  conf_high,
  p_value_approx,
  ci_includes_zero,
  ci_strictly_positive
)])
cat("\nKey comparisons:\n")
print(key_comparisons)
cat("\nSample comparison:\n")
print(sample_comparison)
cat("\nValidation:\n")
print(validation)
cat("\nrun-py-8c static sensitivity analysis completed successfully.\n")
cat("Output directory:", out_dir, "\n")
