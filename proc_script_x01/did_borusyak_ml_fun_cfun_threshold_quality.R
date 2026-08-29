#!/usr/bin/env Rscript

# ================================================================
# run-x-i09 v1: Borusyak DiD across frozen combined-ML thresholds
# ================================================================
#
# Purpose:
#   Estimate Cursor-adoption effects on unresolved SonarQube issue burden
#   localized to Python files whose token-weighted combined regular-function +
#   class-method ML AGC share exceeds each threshold frozen by run-x-i07-v2 and
#   materialized into the run-x-i08 quality-burden panel.
#
# Input contract:
#   - run-x-i08 has already applied the corrected 21-point strict ML threshold
#     grid and aggregated selected-file SonarQube issue stock to repo-months.
#   - 21 thresholds: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90.
#   - Two samples: full_sample and exclude_scope_mismatch_repos.
#   - Mapping: all_ml_files.
#   - Primary threshold: combined weighted ML AGC share > 0.50.
#   - Threshold selection is outcome-blind; I09 never re-selects files.
#
# Estimation:
#   - didimputation::did_imputation.
#   - Repository-clustered standard errors.
#   - Adjusted and FE-only burden specifications.
#   - Eight log1p selected-file SonarQube issue-stock outcomes.
#   - Static ATT over all post-adoption observations.
#   - Dynamic effects at event 0:+6 and placebo/pretrend terms -6:-2.
#   - Event -1 is the omitted reference period.
#
# Treatment timing:
#   - Reconstructed only from event_index and time_index.
#   - Legacy post_event/time_to_event fields are not used to define treatment.
#
# Provenance gate:
#   - I08 status must be PASS.
#   - I08 hard QC failures must be zero.
#   - I08 must report zero I07-v2 threshold-reproduction mismatches.
#   - The 42 sample-threshold aggregate rows must reconcile to I08 global audit.
#
# This program is standalone. It reuses the validated H07/I05 statistical
# structure but does not call any prior experiment script or shell wrapper.
# ================================================================

options(stringsAsFactors = FALSE, warn = 1)

abortf <- function(fmt, ...) {
  stop(sprintf(fmt, ...), call. = FALSE)
}

log_message <- function(level, fmt, ...) {
  message(sprintf("%s [%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)))
}

parse_cli_args <- function(args) {
  out <- list()
  i <- 1L
  while (i <= length(args)) {
    token <- args[[i]]
    if (!startsWith(token, "--")) abortf("Unexpected positional argument: %s", token)
    key <- gsub("-", "_", sub("^--", "", token), fixed = TRUE)
    if (i == length(args) || startsWith(args[[i + 1L]], "--")) {
      out[[key]] <- TRUE
      i <- i + 1L
    } else {
      out[[key]] <- args[[i + 1L]]
      i <- i + 2L
    }
  }
  out
}

require_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(as.character(value))) {
    abortf("Missing required argument: --%s", gsub("_", "-", name, fixed = TRUE))
  }
  as.character(value)
}

as_integer_arg <- function(args, name, default = NULL) {
  value <- args[[name]]
  if (is.null(value)) {
    if (is.null(default)) abortf("Missing integer argument: --%s", gsub("_", "-", name, fixed = TRUE))
    return(as.integer(default))
  }
  result <- suppressWarnings(as.integer(value))
  if (is.na(result)) abortf("Argument --%s must be an integer: %s", gsub("_", "-", name, fixed = TRUE), value)
  result
}

as_numeric_arg <- function(args, name, default = NULL) {
  value <- args[[name]]
  if (is.null(value)) {
    if (is.null(default)) abortf("Missing numeric argument: --%s", gsub("_", "-", name, fixed = TRUE))
    return(as.numeric(default))
  }
  result <- suppressWarnings(as.numeric(value))
  if (!is.finite(result)) abortf("Argument --%s must be finite numeric: %s", gsub("_", "-", name, fixed = TRUE), value)
  result
}

as_logical_arg <- function(args, name, default = FALSE) {
  value <- args[[name]]
  if (is.null(value)) return(isTRUE(default))
  text <- tolower(trimws(as.character(value)))
  if (text %in% c("1", "true", "yes", "y", "on")) return(TRUE)
  if (text %in% c("0", "false", "no", "n", "off")) return(FALSE)
  abortf("Argument --%s must be boolean-like: %s", gsub("_", "-", name, fixed = TRUE), value)
}

safe_package_version <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) return(NA_character_)
  as.character(utils::packageVersion(package))
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing) > 0L) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

sha256_file <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  command <- Sys.which("sha256sum")
  if (!nzchar(command)) return(NA_character_)
  output <- suppressWarnings(system2(command, path, stdout = TRUE, stderr = TRUE))
  if (length(output) == 0L) return(NA_character_)
  strsplit(output[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

capture_evaluation <- function(expr) {
  warnings <- character()
  started <- proc.time()[[3L]]
  value <- tryCatch(
    withCallingHandlers(
      expr,
      warning = function(w) {
        warnings <<- c(warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) structure(list(message = conditionMessage(e)), class = "captured_error")
  )
  elapsed <- proc.time()[[3L]] - started
  list(value = value, warnings = unique(warnings), elapsed = elapsed, error = inherits(value, "captured_error"))
}

bool_to_int <- function(x) {
  if (is.logical(x)) return(as.integer(replace(x, is.na(x), FALSE)))
  text <- tolower(trimws(as.character(x)))
  result <- rep(NA_integer_, length(text))
  result[text %in% c("1", "true", "t", "yes", "y")] <- 1L
  result[text %in% c("0", "false", "f", "no", "n", "", "na", "nan", "none")] <- 0L
  numeric_value <- suppressWarnings(as.numeric(text))
  replace_idx <- is.na(result) & !is.na(numeric_value)
  result[replace_idx] <- as.integer(numeric_value[replace_idx] != 0)
  result[is.na(result)] <- 0L
  result
}

validate_columns <- function(data, required, label = "Input") {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
}

extract_effect_table <- function(result, outcome_name, confidence_level) {
  table <- data.table::as.data.table(result)
  validate_columns(table, c("term", "estimate", "std.error", "conf.low", "conf.high"), "did_imputation result")
  alpha <- 1 - confidence_level
  critical_value <- stats::qnorm(1 - alpha / 2)
  table[, outcome := outcome_name]
  table[, conf.low := estimate - critical_value * std.error]
  table[, conf.high := estimate + critical_value * std.error]
  table[, p_value := ifelse(is.finite(std.error) & std.error > 0,
                            2 * stats::pnorm(-abs(estimate / std.error)), NA_real_)]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table
}

fit_first_stage_diagnostic <- function(data, outcome, first_stage_formula_text) {
  untreated <- data[absorbing_treated == 0L]
  formula <- stats::as.formula(sprintf("%s %s", outcome, first_stage_formula_text))
  captured <- capture_evaluation(
    fixest::feols(
      formula,
      data = untreated,
      se = "standard",
      warn = FALSE,
      notes = FALSE,
      fixef.rm = "none"
    )
  )
  if (captured$error) return(captured)
  predictions <- capture_evaluation(stats::predict(captured$value, newdata = data))
  if (predictions$error) return(predictions)
  captured$predictions <- predictions$value
  captured$warnings <- unique(c(captured$warnings, predictions$warnings))
  captured$elapsed <- captured$elapsed + predictions$elapsed
  captured
}

run_did_model <- function(data, outcome, first_stage_formula, horizon = NULL, pretrends = NULL) {
  capture_evaluation(
    didimputation::did_imputation(
      data = data,
      yname = outcome,
      gname = "event_index",
      tname = "time_index",
      idname = "repo_id",
      first_stage = first_stage_formula,
      horizon = horizon,
      pretrends = pretrends,
      cluster_var = "repo_id"
    )
  )
}

make_model_specs <- function() {
  outcomes <- c(
    "log1p_selected_issue_total",
    "log1p_selected_issue_code_smell",
    "log1p_selected_issue_bug",
    "log1p_selected_issue_vulnerability",
    "log1p_selected_issue_high_severity",
    "log1p_selected_issue_maintainability_impact",
    "log1p_selected_issue_reliability_impact",
    "log1p_selected_issue_security_impact"
  )
  list(
    adjusted_burden = list(
      label = "Adjusted burden",
      outcomes = outcomes,
      first_stage = ~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index,
      first_stage_text = "~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index",
      model_fields = c("log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues")
    ),
    fe_only_burden = list(
      label = "FE-only burden",
      outcomes = outcomes,
      first_stage = ~ 1 | repo_id + time_index,
      first_stage_text = "~ 1 | repo_id + time_index",
      model_fields = character()
    )
  )
}

outcome_labels <- c(
  log1p_selected_issue_total = "Combined procedure-ML-selected total unresolved issue stock",
  log1p_selected_issue_code_smell = "Combined procedure-ML-selected code-smell issue stock",
  log1p_selected_issue_bug = "Combined procedure-ML-selected bug issue stock",
  log1p_selected_issue_vulnerability = "Combined procedure-ML-selected vulnerability issue stock",
  log1p_selected_issue_high_severity = "Combined procedure-ML-selected high-severity issue stock",
  log1p_selected_issue_maintainability_impact = "Combined procedure-ML-selected maintainability-impact issue stock",
  log1p_selected_issue_reliability_impact = "Combined procedure-ML-selected reliability-impact issue stock",
  log1p_selected_issue_security_impact = "Combined procedure-ML-selected security-impact issue stock"
)

outcome_roles <- c(
  log1p_selected_issue_total = "primary_burden",
  log1p_selected_issue_code_smell = "type_robustness",
  log1p_selected_issue_bug = "type_robustness",
  log1p_selected_issue_vulnerability = "type_robustness",
  log1p_selected_issue_high_severity = "severity_robustness",
  log1p_selected_issue_maintainability_impact = "impact_robustness",
  log1p_selected_issue_reliability_impact = "impact_robustness",
  log1p_selected_issue_security_impact = "impact_robustness"
)

# Resolve one named scalar outside data.table j expressions. This avoids
# non-standard-evaluation collisions when an input table already contains a
# column named `outcome` with multiple rows (as dynamic event-study tables do).
lookup_named_scalar <- function(mapping, key, mapping_name) {
  if (length(key) != 1L || is.na(key) || !nzchar(as.character(key))) {
    abortf("%s lookup requires exactly one non-missing key.", mapping_name)
  }
  key <- as.character(key)
  if (!(key %in% names(mapping))) {
    abortf("Unknown key for %s: %s", mapping_name, key)
  }
  unname(mapping[[key]])
}

raw_log_pairs <- list(
  selected_issue_total = "log1p_selected_issue_total",
  selected_issue_code_smell = "log1p_selected_issue_code_smell",
  selected_issue_bug = "log1p_selected_issue_bug",
  selected_issue_vulnerability = "log1p_selected_issue_vulnerability",
  selected_issue_high_severity = "log1p_selected_issue_high_severity",
  selected_issue_maintainability_impact = "log1p_selected_issue_maintainability_impact",
  selected_issue_reliability_impact = "log1p_selected_issue_reliability_impact",
  selected_issue_security_impact = "log1p_selected_issue_security_impact"
)

expected_thresholds <- seq(0.10, 0.90, by = 0.04)
expected_threshold_ids <- sprintf("ml_t%02d", as.integer(round(expected_thresholds * 100)))
primary_threshold <- 0.50
primary_threshold_id <- "ml_t50"
expected_samples <- c("full_sample", "exclude_scope_mismatch_repos")
expected_mapping <- "all_ml_files"
expected_ml_metric <- "file_ml_fun_cfun_agc_share_space_by_token_weighted"
expected_operator <- ">"

run_self_test <- function() {
  stopifnot(length(expected_thresholds) == 21L)
  stopifnot(length(unique(expected_threshold_ids)) == 21L)
  stopifnot(abs(expected_thresholds[[11L]] - primary_threshold) < 1e-12)
  stopifnot(expected_threshold_ids[[11L]] == primary_threshold_id)
  stopifnot(length(make_model_specs()) == 2L)
  stopifnot(length(make_model_specs()$adjusted_burden$outcomes) == 8L)
  stopifnot(2L * 21L * 2L * 8L == 672L)
  stopifnot(672L * 12L == 8064L)
  test_outcome <- "log1p_selected_issue_total"
  stopifnot(identical(
    lookup_named_scalar(outcome_labels, test_outcome, "outcome_labels"),
    "Combined procedure-ML-selected total unresolved issue stock"
  ))
  stopifnot(identical(
    lookup_named_scalar(outcome_roles, test_outcome, "outcome_roles"),
    "primary_burden"
  ))
  cat("did_borusyak_ml_fun_cfun_threshold_quality self-test: PASS\n")
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
if (isTRUE(args$self_test)) {
  run_self_test()
  quit(save = "no", status = 0L)
}

input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
input_summary_file <- normalizePath(require_arg(args, "input_summary_file"), mustWork = TRUE)
input_checks_file <- normalizePath(require_arg(args, "input_checks_file"), mustWork = TRUE)
input_sample_summary_file <- normalizePath(require_arg(args, "input_sample_summary_file"), mustWork = TRUE)
input_global_audit_file <- normalizePath(require_arg(args, "input_global_audit_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)

plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_long_rows <- as_integer_arg(args, "expected_long_rows", 81249L)
expected_threshold_count <- as_integer_arg(args, "expected_thresholds", 21L)
expected_sample_count <- as_integer_arg(args, "expected_sample_specs", 2L)
sparse_min_dynamic_positive_repos <- as_integer_arg(args, "sparse_min_dynamic_positive_repos", 10L)
sparse_min_within_variation_repos <- as_integer_arg(args, "sparse_min_within_variation_repos", 20L)

if (plot_min_event != -6L || plot_max_event != 6L) abortf("I09 v1 requires dynamic window -6:6.")
if (pretrend_min != -6L || pretrend_max != -2L) abortf("I09 v1 requires pretrend window -6:-2.")
if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")
if (expected_threshold_count != 21L || expected_sample_count != 2L) abortf("I09 v1 requires 21 thresholds and 2 sample specifications.")

required_packages <- c("data.table", "didimputation", "fixest")
check_packages(required_packages)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  static = file.path(output_dir, "quality_ml_fun_cfun_threshold_static_effects.csv"),
  dynamic = file.path(output_dir, "quality_ml_fun_cfun_threshold_dynamic_effects.csv"),
  pretrend_checks = file.path(output_dir, "quality_ml_fun_cfun_threshold_pretrend_checks.csv"),
  pretrend_summary = file.path(output_dir, "quality_ml_fun_cfun_threshold_pretrend_summary.csv"),
  diagnostics = file.path(output_dir, "quality_ml_fun_cfun_threshold_model_diagnostics.csv"),
  failures = file.path(output_dir, "quality_ml_fun_cfun_threshold_model_failures.csv"),
  threshold_support = file.path(output_dir, "quality_ml_fun_cfun_threshold_support.csv"),
  event_support = file.path(output_dir, "quality_ml_fun_cfun_threshold_event_support.csv"),
  support_policy = file.path(output_dir, "quality_ml_fun_cfun_support_policy.csv"),
  primary_threshold_static = file.path(output_dir, "quality_ml_fun_cfun_primary_threshold_static.csv"),
  primary_total_static = file.path(output_dir, "quality_ml_fun_cfun_primary_total_static.csv"),
  primary_total_dynamic = file.path(output_dir, "quality_ml_fun_cfun_primary_total_dynamic.csv"),
  total_threshold_static = file.path(output_dir, "quality_ml_fun_cfun_total_threshold_static.csv"),
  total_threshold_dynamic = file.path(output_dir, "quality_ml_fun_cfun_total_threshold_dynamic.csv"),
  qc = file.path(output_dir, "quality_ml_fun_cfun_threshold_qc.csv"),
  summary = file.path(output_dir, "quality_ml_fun_cfun_threshold_summary.csv"),
  metadata = file.path(output_dir, "quality_ml_fun_cfun_threshold_run_metadata.csv")
)

run_started <- Sys.time()
log_message("INFO", "Reading I08 combined-ML threshold-input long panel: %s", input_file)
panel_all <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
input_summary <- data.table::fread(input_summary_file, na.strings = c("", "NA", "NaN"))
input_checks <- data.table::fread(input_checks_file, na.strings = c("", "NA", "NaN"))
input_sample_summary <- data.table::fread(input_sample_summary_file, na.strings = c("", "NA", "NaN"))
input_global_audit <- data.table::fread(input_global_audit_file, na.strings = c("", "NA", "NaN"))

# Validate I08 provenance artifacts before fitting any model.
validate_columns(input_summary, c("metric", "value"), "I08 threshold-input summary")
summary_map <- setNames(as.character(input_summary$value), as.character(input_summary$metric))
required_summary_metrics <- c(
  "script_version", "status", "ml_metric", "quality_semantics", "mapping_spec",
  "thresholds", "sample_specs", "full_sample_repo_month_rows",
  "scope_sensitivity_repo_month_rows", "long_panel_rows", "primary_threshold",
  "primary_full_selected_file_rows", "primary_full_selected_unique_files",
  "primary_full_selected_issue_total", "eligible_expanded_file_rows",
  "eligible_unique_historical_files", "scope_sensitivity_repositories",
  "i07_threshold_reproduction_mismatches", "density_computed", "hard_qc_failures"
)
if (!all(required_summary_metrics %in% names(summary_map))) abortf("I08 threshold-input summary is missing required metrics.")
if (summary_map[["script_version"]] != "run-x-i08-v1") abortf("I08 summary must report script_version=run-x-i08-v1; observed %s", summary_map[["script_version"]])
if (summary_map[["status"]] != "PASS") abortf("I08 threshold-input summary status is not PASS.")
if (summary_map[["ml_metric"]] != expected_ml_metric) abortf("I08 threshold-input ML metric mismatch.")
if (summary_map[["quality_semantics"]] != "unresolved_sonarqube_issue_stock_at_historical_snapshot") abortf("I08 threshold-input quality semantics mismatch.")
if (summary_map[["mapping_spec"]] != expected_mapping) abortf("I08 threshold-input mapping mismatch.")
expected_summary_numeric <- c(
  thresholds = 21, sample_specs = 2, full_sample_repo_month_rows = 1954,
  scope_sensitivity_repo_month_rows = 1915, long_panel_rows = expected_long_rows,
  primary_threshold = primary_threshold, primary_full_selected_file_rows = 64153,
  primary_full_selected_unique_files = 62319, primary_full_selected_issue_total = 35765,
  eligible_expanded_file_rows = 359466, eligible_unique_historical_files = 347562,
  scope_sensitivity_repositories = 2, i07_threshold_reproduction_mismatches = 0,
  density_computed = 0, hard_qc_failures = 0
)
for (name in names(expected_summary_numeric)) {
  observed <- suppressWarnings(as.numeric(summary_map[[name]]))
  if (!is.finite(observed) || abs(observed - expected_summary_numeric[[name]]) > 1e-9) {
    abortf("I08 threshold-input summary mismatch for %s: expected %s, observed %s", name, expected_summary_numeric[[name]], summary_map[[name]])
  }
}

validate_columns(input_checks, c("check_name", "severity", "passed"), "I08 threshold-input checks")
input_checks[, passed_numeric := suppressWarnings(as.integer(passed))]
if (nrow(input_checks) == 0L || anyNA(input_checks$passed_numeric) || any(input_checks$passed_numeric != 1L)) {
  abortf("I08 threshold-input checks contain non-passing rows.")
}

validate_columns(input_sample_summary, c(
  "repo_month_rows", "repositories", "control_repositories", "treatment_repositories",
  "control_rows", "treatment_pre_rows", "treatment_post_rows",
  "dynamic_event_0_to_6_rows", "sample_spec", "excluded_repository_count"
), "I08 threshold-input sample summary")
input_sample_summary[, untreated_first_stage_rows := as.integer(control_rows) + as.integer(treatment_pre_rows)]
expected_sample_support <- data.table::data.table(
  sample_spec = expected_samples,
  repo_month_rows = c(1954L, 1915L), repositories = c(167L, 165L),
  control_repositories = c(104L, 103L), treatment_repositories = c(63L, 62L),
  control_rows = c(1040L, 1020L), treatment_pre_rows = c(551L, 537L),
  untreated_first_stage_rows = c(1591L, 1557L), treatment_post_rows = c(363L, 358L),
  dynamic_event_0_to_6_rows = c(343L, 338L), excluded_repository_count = c(0L, 2L)
)
for (i in seq_len(nrow(expected_sample_support))) {
  expected_row <- expected_sample_support[i]
  observed_row <- input_sample_summary[sample_spec == expected_row$sample_spec]
  if (nrow(observed_row) != 1L) abortf("I08 sample summary must contain one row for %s.", expected_row$sample_spec)
  for (field in setdiff(names(expected_sample_support), "sample_spec")) {
    if (as.integer(observed_row[[field]]) != as.integer(expected_row[[field]])) {
      abortf("I08 sample-summary mismatch for %s/%s.", expected_row$sample_spec, field)
    }
  }
}

model_specs <- make_model_specs()
all_outcomes <- model_specs$adjusted_burden$outcomes
raw_issue_columns <- names(raw_log_pairs)
required_columns <- unique(c(
  "repo_id", "repo_name", "treatment_group", "time_index", "event_index", "time_to_event",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  "sample_spec", "mapping_spec", "threshold_spec_id", "threshold", "threshold_role",
  "ml_metric", "ml_operator", "primary_threshold", "primary_analysis",
  "quality_scope", "quality_count_semantics", "density_computed",
  "eligible_ml_file_count", "selected_file_count", raw_issue_columns, all_outcomes
))
validate_columns(panel_all, required_columns, "I08 threshold-input long panel")

if (nrow(panel_all) != expected_long_rows) abortf("I08 threshold-input long-panel row mismatch: expected %d, observed %d", expected_long_rows, nrow(panel_all))
if (data.table::uniqueN(panel_all$sample_spec) != 2L) abortf("I08 threshold-input long panel must contain two sample specifications.")
if (!setequal(unique(panel_all$sample_spec), expected_samples)) abortf("Unexpected I08 threshold-input sample specifications.")
if (any(panel_all$mapping_spec != expected_mapping)) abortf("I08 threshold-input mapping_spec mismatch.")
if (any(panel_all$ml_metric != expected_ml_metric)) abortf("I08 threshold-input ml_metric mismatch.")
if (any(panel_all$ml_operator != expected_operator)) abortf("I08 threshold-input ml_operator mismatch.")
if (any(panel_all$quality_scope != "canonical_i06_python_files_with_finite_combined_ml")) abortf("I08 threshold-input quality_scope mismatch.")
if (any(panel_all$quality_count_semantics != "unresolved_sonarqube_issue_stock_at_historical_snapshot")) abortf("I08 threshold-input quality_count_semantics mismatch.")

numeric_columns <- unique(c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event", "threshold",
  "primary_threshold", "primary_analysis", "density_computed", "eligible_ml_file_count", "selected_file_count",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  raw_issue_columns, all_outcomes
))
for (column in numeric_columns) panel_all[, (column) := suppressWarnings(as.numeric(get(column)))]
if (anyNA(panel_all$repo_id) || anyNA(panel_all$time_index) || anyNA(panel_all$event_index)) abortf("Core timing identifiers contain missing values.")
panel_all[, repo_id := as.integer(repo_id)]
panel_all[, treatment_group := as.integer(treatment_group)]
panel_all[, time_index := as.integer(time_index)]
panel_all[, event_index := as.integer(event_index)]

if (any(panel_all$density_computed != 0)) abortf("I08 threshold-input density_computed must remain zero.")
if (any(abs(panel_all$primary_threshold - primary_threshold) > 1e-12)) abortf("I08 row-level primary threshold mismatch.")
expected_primary_analysis <- as.integer(panel_all$sample_spec == "full_sample" & panel_all$threshold_spec_id == primary_threshold_id)
if (any(panel_all$primary_analysis != expected_primary_analysis)) abortf("I08 row-level primary_analysis flag mismatch.")

# Validate exact threshold IDs, values, roles, and nested panel keys.
threshold_map <- unique(panel_all[, .(threshold_spec_id, threshold, threshold_role)])
data.table::setorder(threshold_map, threshold)
if (nrow(threshold_map) != 21L) abortf("Expected 21 unique threshold specifications, observed %d.", nrow(threshold_map))
if (!identical(as.character(threshold_map$threshold_spec_id), expected_threshold_ids)) abortf("I08 threshold-input threshold IDs do not match the 21-point ML grid.")
if (any(abs(threshold_map$threshold - expected_thresholds) > 1e-12)) abortf("I08 threshold-input threshold values do not match the expected 0.10:0.90 grid.")
expected_roles <- ifelse(expected_threshold_ids == primary_threshold_id, "primary", "sensitivity_grid")
if (!identical(as.character(threshold_map$threshold_role), expected_roles)) abortf("I08 threshold-input threshold roles are inconsistent with the primary 0.50 threshold.")

key_duplicates <- panel_all[, .N, by = .(sample_spec, threshold_spec_id, repo_id, time_index)][N > 1L]
if (nrow(key_duplicates) > 0L) abortf("Found %d duplicate sample-threshold-repo-time keys.", nrow(key_duplicates))

for (column in c("eligible_ml_file_count", "selected_file_count", raw_issue_columns)) {
  if (anyNA(panel_all[[column]]) || any(!is.finite(panel_all[[column]])) || any(panel_all[[column]] < 0)) {
    abortf("I08 threshold-input column %s contains missing, non-finite, or negative values.", column)
  }
}
for (raw_name in names(raw_log_pairs)) {
  log_name <- raw_log_pairs[[raw_name]]
  observed <- panel_all[[log_name]]
  expected <- log1p(panel_all[[raw_name]])
  if (anyNA(observed) || any(!is.finite(observed)) || max(abs(observed - expected)) > 1e-10) {
    abortf("I08 threshold-input log1p mismatch for %s <- %s.", log_name, raw_name)
  }
}

model_fields <- unique(c(all_outcomes, model_specs$adjusted_burden$model_fields))
if (any(!stats::complete.cases(panel_all[, ..model_fields]))) abortf("I08 threshold-input long panel has missing model fields.")
if (any(!vapply(panel_all[, ..model_fields], function(x) all(is.finite(x)), logical(1)))) abortf("I08 threshold-input long panel has non-finite model fields.")

# Check nested strict-threshold construction using totals from the I08 threshold-input long panel.
monotonic_failures <- character()
for (sample_name in expected_samples) {
  aggregate <- panel_all[sample_spec == sample_name, lapply(.SD, sum),
                         by = .(threshold_spec_id, threshold),
                         .SDcols = c("selected_file_count", raw_issue_columns)]
  data.table::setorder(aggregate, threshold)
  for (column in c("selected_file_count", raw_issue_columns)) {
    if (any(diff(aggregate[[column]]) > 1e-8)) monotonic_failures <- c(monotonic_failures, sprintf("%s/%s", sample_name, column))
  }
}
if (length(monotonic_failures) > 0L) abortf("Threshold nesting monotonicity failed: %s", paste(monotonic_failures, collapse = ", "))

# Reconcile I08 threshold-input global audit to the panel for selected-file and total-issue counts.
validate_columns(input_global_audit, c(
  "sample_spec", "mapping_spec", "threshold_spec_id", "threshold", "threshold_role",
  "repo_month_rows", "repositories", "selected_file_rows", "selected_issue_total",
  "repositories_with_within_quality_variation"
), "I08 threshold-input global audit")
if (nrow(input_global_audit) != 42L) abortf("I08 threshold-input global audit must contain 42 rows.")
audit_recalc <- panel_all[, .(
  repo_month_rows = .N,
  repositories = data.table::uniqueN(repo_id),
  selected_file_rows = sum(selected_file_count),
  selected_issue_total = sum(selected_issue_total),
  repositories_with_within_quality_variation = sum(vapply(split(selected_issue_total, repo_id), function(x) data.table::uniqueN(x) > 1L, logical(1)))
), by = .(sample_spec, mapping_spec, threshold_spec_id, threshold, threshold_role)]
audit_check <- merge(
  input_global_audit[, .(sample_spec, mapping_spec, threshold_spec_id, threshold,
                       audit_repo_month_rows = repo_month_rows,
                       audit_repositories = repositories,
                       audit_selected_file_rows = selected_file_rows,
                       audit_selected_issue_total = selected_issue_total,
                       audit_within_variation = repositories_with_within_quality_variation)],
  audit_recalc,
  by = c("sample_spec", "mapping_spec", "threshold_spec_id", "threshold"), all = TRUE
)
if (nrow(audit_check) != 42L || anyNA(audit_check$repo_month_rows)) abortf("I08 threshold-input global audit keys do not reconcile to the long panel.")
if (any(abs(audit_check$audit_repo_month_rows - audit_check$repo_month_rows) > 0) ||
    any(abs(audit_check$audit_repositories - audit_check$repositories) > 0) ||
    any(abs(audit_check$audit_selected_file_rows - audit_check$selected_file_rows) > 1e-8) ||
    any(abs(audit_check$audit_selected_issue_total - audit_check$selected_issue_total) > 1e-8) ||
    any(abs(audit_check$audit_within_variation - audit_check$repositories_with_within_quality_variation) > 0)) {
  abortf("I08 threshold-input global audit values do not reconcile to the long panel.")
}

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)
support_event_values <- seq.int(plot_min_event, plot_max_event)

support_policy <- data.table::data.table(
  policy = "sparse_support_flag",
  definition = sprintf("min dynamic positive repositories < %d OR repositories with within-outcome variation < %d",
                       sparse_min_dynamic_positive_repos, sparse_min_within_variation_repos),
  min_dynamic_positive_repositories = sparse_min_dynamic_positive_repos,
  min_within_variation_repositories = sparse_min_within_variation_repos,
  thresholds_omitted = 0L
)
write_csv(support_policy, paths$support_policy)

# Threshold-level and event-level support is computed once, before estimation.
threshold_support_rows <- list()
event_support_rows <- list()
for (sample_name in expected_samples) {
  for (i in seq_along(expected_threshold_ids)) {
    threshold_id <- expected_threshold_ids[[i]]
    threshold_value <- expected_thresholds[[i]]
    threshold_data <- panel_all[sample_spec == sample_name & threshold_spec_id == threshold_id]
    threshold_data[, event_time_normalized := data.table::fifelse(
      treatment_group == 1L, time_index - event_index, NA_integer_
    )]
    positive_by_event <- threshold_data[
      treatment_group == 1L & event_time_normalized %in% support_event_values,
      .(
        treatment_rows = .N,
        treatment_repositories = data.table::uniqueN(repo_id),
        positive_issue_rows = sum(selected_issue_total > 0),
        positive_issue_repositories = data.table::uniqueN(repo_id[selected_issue_total > 0])
      ),
      by = .(event_time = as.integer(event_time_normalized))
    ]
    support_grid <- merge(data.table::data.table(event_time = support_event_values), positive_by_event, by = "event_time", all.x = TRUE)
    for (column in c("treatment_rows", "treatment_repositories", "positive_issue_rows", "positive_issue_repositories")) {
      support_grid[is.na(get(column)), (column) := 0L]
    }
    support_grid[, `:=`(
      sample_spec = sample_name,
      mapping_spec = expected_mapping,
      threshold_id = threshold_id,
      threshold = threshold_value,
      threshold_role = ifelse(threshold_id == primary_threshold_id, "primary", "sensitivity_grid"),
      grid_order = i - 1L,
      delta_from_primary = threshold_value - primary_threshold,
      comparison_operator = expected_operator,
      ml_metric = expected_ml_metric,
      period_type = data.table::fcase(
        event_time %in% pretrend_values, "placebo_pretrend",
        event_time == -1L, "reference",
        event_time >= 0L, "post_treatment",
        default = "other"
      )
    )]
    event_support_rows[[length(event_support_rows) + 1L]] <- support_grid

    within_variation <- threshold_data[, .(varies = data.table::uniqueN(selected_issue_total) > 1L), by = repo_id][, sum(varies)]
    min_dynamic_positive <- min(support_grid[event_time %in% post_values, positive_issue_repositories])
    zero_share <- mean(threshold_data$selected_issue_total == 0)
    post_rows <- threshold_data[treatment_group == 1L & time_index >= event_index]
    post_zero_share <- if (nrow(post_rows) > 0L) mean(post_rows$selected_issue_total == 0) else NA_real_
    sparse_reasons <- character()
    if (min_dynamic_positive < sparse_min_dynamic_positive_repos) {
      sparse_reasons <- c(sparse_reasons, sprintf("min_dynamic_positive_repositories=%d<%d", min_dynamic_positive, sparse_min_dynamic_positive_repos))
    }
    if (within_variation < sparse_min_within_variation_repos) {
      sparse_reasons <- c(sparse_reasons, sprintf("repositories_within_variation=%d<%d", within_variation, sparse_min_within_variation_repos))
    }
    threshold_support_rows[[length(threshold_support_rows) + 1L]] <- data.table::data.table(
      sample_spec = sample_name,
      mapping_spec = expected_mapping,
      threshold_id = threshold_id,
      threshold = threshold_value,
      threshold_role = ifelse(threshold_id == primary_threshold_id, "primary", "sensitivity_grid"),
      grid_order = i - 1L,
      delta_from_primary = threshold_value - primary_threshold,
      comparison_operator = expected_operator,
      ml_metric = expected_ml_metric,
      repo_month_rows = nrow(threshold_data),
      repositories = data.table::uniqueN(threshold_data$repo_id),
      treatment_repositories = data.table::uniqueN(threshold_data[treatment_group == 1L, repo_id]),
      control_repositories = data.table::uniqueN(threshold_data[treatment_group == 0L, repo_id]),
      selected_file_rows = sum(threshold_data$selected_file_count),
      selected_issue_total = sum(threshold_data$selected_issue_total),
      repo_months_with_positive_issue_burden = sum(threshold_data$selected_issue_total > 0),
      repositories_with_within_outcome_variation = within_variation,
      min_dynamic_positive_repositories = min_dynamic_positive,
      zero_outcome_share = zero_share,
      post_zero_outcome_share = post_zero_share,
      sparse_support_flag = as.integer(length(sparse_reasons) > 0L),
      sparse_support_reason = paste(sparse_reasons, collapse = " | ")
    )
  }
}
threshold_support <- data.table::rbindlist(threshold_support_rows, fill = TRUE)
event_support <- data.table::rbindlist(event_support_rows, fill = TRUE)
data.table::setorder(threshold_support, sample_spec, threshold)
data.table::setorder(event_support, sample_spec, threshold, event_time)
write_csv(threshold_support, paths$threshold_support)
write_csv(event_support, paths$event_support)

static_tables <- list()
dynamic_tables <- list()
pretrend_tables <- list()
diagnostics <- list()
failures <- list()

add_diagnostic <- function(meta, spec_name, outcome, model_type, status, elapsed, warnings = character(), error_message = "", result_terms = NA_integer_, extra = "") {
  spec <- model_specs[[spec_name]]
  diagnostics[[length(diagnostics) + 1L]] <<- data.table::data.table(
    sample_spec = meta$sample_spec,
    threshold_id = meta$threshold_id,
    threshold = meta$threshold,
    threshold_role = meta$threshold_role,
    grid_order = meta$grid_order,
    model_spec = spec_name,
    model_spec_label = spec$label,
    outcome = outcome,
    outcome_label = lookup_named_scalar(outcome_labels, outcome, "outcome_labels"),
    outcome_role = lookup_named_scalar(outcome_roles, outcome, "outcome_roles"),
    model_type = model_type,
    status = status,
    runtime_seconds = as.numeric(elapsed),
    warning_count = length(warnings),
    warning_messages = paste(warnings, collapse = " | "),
    error_message = error_message,
    input_rows = meta$input_rows,
    untreated_rows = meta$untreated_rows,
    treated_rows = meta$treated_rows,
    result_terms = as.integer(result_terms),
    extra = extra
  )
}

add_failure <- function(meta, spec_name, outcome, stage, message) {
  failures[[length(failures) + 1L]] <<- data.table::data.table(
    sample_spec = meta$sample_spec,
    threshold_id = meta$threshold_id,
    threshold = meta$threshold,
    model_spec = spec_name,
    outcome = outcome,
    stage = stage,
    error_message = message
  )
}

attach_meta <- function(table, meta, spec_name, outcome, term_type = NULL) {
  spec <- model_specs[[spec_name]]

  # Resolve these scalars before entering data.table's j expression. The table
  # itself contains an `outcome` column, so using outcome_labels[[outcome]]
  # inside `:=` would bind to that column for multi-row dynamic results.
  outcome_key <- as.character(outcome)
  outcome_label_value <- lookup_named_scalar(outcome_labels, outcome_key, "outcome_labels")
  outcome_role_value <- lookup_named_scalar(outcome_roles, outcome_key, "outcome_roles")
  term_type_value <- term_type

  support_row <- threshold_support[sample_spec == meta$sample_spec & threshold_id == meta$threshold_id]

  # Assign outcome metadata with data.table::set outside j so column names in
  # the result table can never shadow the scalar function arguments.
  data.table::set(table, j = "outcome_label", value = rep(outcome_label_value, nrow(table)))
  data.table::set(table, j = "outcome_role", value = rep(outcome_role_value, nrow(table)))
  if (!is.null(term_type_value)) {
    data.table::set(table, j = "term_type", value = rep(term_type_value, nrow(table)))
  }

  table[, `:=`(
    sample_spec = meta$sample_spec,
    mapping_spec = expected_mapping,
    threshold_id = meta$threshold_id,
    threshold_role = meta$threshold_role,
    grid_order = meta$grid_order,
    delta_from_primary = meta$threshold - primary_threshold,
    threshold = meta$threshold,
    comparison_operator = expected_operator,
    ml_metric = expected_ml_metric,
    primary_threshold = primary_threshold,
    is_primary_threshold = as.integer(meta$threshold_id == primary_threshold_id),
    primary_analysis = as.integer(meta$sample_spec == "full_sample" && meta$threshold_id == primary_threshold_id),
    analysis_role = ifelse(meta$sample_spec == "full_sample" && meta$threshold_id == primary_threshold_id, "primary", "threshold_sensitivity"),
    model_spec = spec_name,
    model_spec_label = spec$label,
    first_stage_formula = spec$first_stage_text,
    sparse_support_flag = as.integer(support_row$sparse_support_flag),
    sparse_support_reason = as.character(support_row$sparse_support_reason),
    post_rows_with_positive_issue_burden = sum(meta$data[treatment_group == 1L & absorbing_treated == 1L, selected_issue_total > 0]),
    post_repositories_with_positive_issue_burden = data.table::uniqueN(meta$data[treatment_group == 1L & absorbing_treated == 1L & selected_issue_total > 0, repo_id]),
    dynamic_rows_with_positive_issue_burden = sum(meta$data[treatment_group == 1L & event_time_normalized %in% post_values, selected_issue_total > 0]),
    dynamic_repositories_with_positive_issue_burden = data.table::uniqueN(meta$data[treatment_group == 1L & event_time_normalized %in% post_values & selected_issue_total > 0, repo_id]),
    repositories_with_within_outcome_variation = as.integer(support_row$repositories_with_within_outcome_variation),
    min_dynamic_positive_repositories = as.integer(support_row$min_dynamic_positive_repositories),
    zero_outcome_share = as.numeric(support_row$zero_outcome_share),
    post_zero_outcome_share = as.numeric(support_row$post_zero_outcome_share),
    percent_interpretation = "100*(exp(beta)-1) on the corresponding log1p outcome scale"
  )]
  table
}

for (sample_name in expected_samples) {
  for (i in seq_along(expected_threshold_ids)) {
    threshold_id <- expected_threshold_ids[[i]]
    threshold_value <- expected_thresholds[[i]]
    threshold_role <- ifelse(threshold_id == primary_threshold_id, "primary", "sensitivity_grid")
    panel <- data.table::copy(panel_all[sample_spec == sample_name & threshold_spec_id == threshold_id])

    panel[, event_time_normalized := data.table::fifelse(
      treatment_group == 1L, time_index - event_index, NA_integer_
    )]
    panel[, absorbing_treated := as.integer(
      treatment_group == 1L & event_index > 0L & time_index >= event_index
    )]

    control_event_errors <- panel[treatment_group == 0L & event_index != 0L]
    treatment_event_errors <- panel[treatment_group == 1L & event_index <= 0L]
    timing_errors <- panel[treatment_group == 1L & (is.na(time_to_event) | as.integer(time_to_event) != event_time_normalized)]
    if (nrow(control_event_errors) > 0L || nrow(treatment_event_errors) > 0L || nrow(timing_errors) > 0L) {
      abortf("Treatment timing validation failed for %s/%s.", sample_name, threshold_id)
    }

    input_rows <- nrow(panel)
    untreated_rows <- nrow(panel[absorbing_treated == 0L])
    treated_rows <- nrow(panel[absorbing_treated == 1L])
    treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
    control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])

    expected_sample_row <- expected_sample_support[sample_spec == sample_name]
    if (input_rows != expected_sample_row$repo_month_rows ||
        untreated_rows != expected_sample_row$untreated_first_stage_rows ||
        treated_rows != expected_sample_row$treatment_post_rows ||
        treatment_repos != expected_sample_row$treatment_repositories ||
        control_repos != expected_sample_row$control_repositories) {
      abortf("Panel support mismatch for %s/%s.", sample_name, threshold_id)
    }

    meta <- list(
      sample_spec = sample_name,
      threshold_id = threshold_id,
      threshold = threshold_value,
      threshold_role = threshold_role,
      grid_order = i - 1L,
      input_rows = input_rows,
      untreated_rows = untreated_rows,
      treated_rows = treated_rows,
      data = panel
    )

    log_message("INFO", "Starting sample=%s threshold=%s (%.2f; role=%s)", sample_name, threshold_id, threshold_value, threshold_role)

    for (spec_name in names(model_specs)) {
      spec <- model_specs[[spec_name]]
      for (outcome in spec$outcomes) {
        first_stage_capture <- fit_first_stage_diagnostic(panel, outcome, spec$first_stage_text)
        if (first_stage_capture$error) {
          error_text <- first_stage_capture$value$message
          add_diagnostic(meta, spec_name, outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text)
          add_failure(meta, spec_name, outcome, "first_stage", error_text)
          next
        }
        prediction_na_treated <- sum(is.na(first_stage_capture$predictions[panel$absorbing_treated == 1L]))
        if (prediction_na_treated > 0L) {
          error_text <- sprintf("First-stage predictions missing for %d treated rows.", prediction_na_treated)
          add_diagnostic(meta, spec_name, outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text)
          add_failure(meta, spec_name, outcome, "first_stage", error_text)
          next
        }
        add_diagnostic(meta, spec_name, outcome, "first_stage", "success", first_stage_capture$elapsed,
                       first_stage_capture$warnings, result_terms = length(stats::coef(first_stage_capture$value)),
                       extra = sprintf("nobs=%d", stats::nobs(first_stage_capture$value)))

        static_capture <- run_did_model(panel, outcome, spec$first_stage, horizon = NULL, pretrends = NULL)
        if (static_capture$error) {
          error_text <- static_capture$value$message
          add_diagnostic(meta, spec_name, outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
          add_failure(meta, spec_name, outcome, "static", error_text)
          next
        }
        static_table <- extract_effect_table(static_capture$value, outcome, confidence_level)[term == "treat"]
        if (nrow(static_table) != 1L) {
          error_text <- sprintf("Expected one static treat term, observed %d.", nrow(static_table))
          add_diagnostic(meta, spec_name, outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text, nrow(static_table))
          add_failure(meta, spec_name, outcome, "static", error_text)
          next
        }
        static_table <- attach_meta(static_table, meta, spec_name, outcome, "static_att")
        static_table[, `:=`(
          treated_observations = treated_rows,
          first_stage_observations = untreated_rows,
          treatment_repositories = treatment_repos,
          control_repositories = control_repos,
          model_status = "success",
          warning_count = length(static_capture$warnings),
          warning_messages = paste(static_capture$warnings, collapse = " | "),
          error_message = ""
        )]
        static_tables[[length(static_tables) + 1L]] <- static_table
        add_diagnostic(meta, spec_name, outcome, "static", "success", static_capture$elapsed, static_capture$warnings, result_terms = 1L)

        dynamic_capture <- run_did_model(panel, outcome, spec$first_stage, horizon = dynamic_horizon_values, pretrends = pretrend_values)
        if (dynamic_capture$error) {
          error_text <- dynamic_capture$value$message
          add_diagnostic(meta, spec_name, outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
          add_failure(meta, spec_name, outcome, "dynamic", error_text)
          next
        }
        dynamic_table <- extract_effect_table(dynamic_capture$value, outcome, confidence_level)
        dynamic_table[, event_time := suppressWarnings(as.integer(as.character(term)))]
        dynamic_table <- dynamic_table[!is.na(event_time)]
        dynamic_table[, term_type := data.table::fcase(
          event_time %in% pretrend_values, "placebo_pretrend",
          event_time >= 0L, "post_treatment",
          default = "other"
        )]
        expected_dynamic_terms <- length(pretrend_values) + length(post_values)
        if (nrow(dynamic_table) != expected_dynamic_terms || !setequal(dynamic_table$event_time, c(pretrend_values, post_values))) {
          error_text <- sprintf("Expected %d dynamic/placebo terms over -6:-2 and 0:6; observed %d.", expected_dynamic_terms, nrow(dynamic_table))
          add_diagnostic(meta, spec_name, outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text, nrow(dynamic_table))
          add_failure(meta, spec_name, outcome, "dynamic", error_text)
          next
        }
        support_for_merge <- event_support[sample_spec == sample_name & threshold_id == meta$threshold_id,
                                           .(event_time, support_rows = treatment_rows, support_repositories = treatment_repositories)]
        dynamic_table <- merge(dynamic_table, support_for_merge, by = "event_time", all.x = TRUE, sort = FALSE)
        dynamic_table <- attach_meta(dynamic_table, meta, spec_name, outcome)
        dynamic_table[, `:=`(
          ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0,
          term_present = TRUE,
          model_status = "success",
          warning_count = length(dynamic_capture$warnings),
          warning_messages = paste(dynamic_capture$warnings, collapse = " | "),
          error_message = ""
        )]
        data.table::setorder(dynamic_table, event_time)
        dynamic_tables[[length(dynamic_tables) + 1L]] <- dynamic_table
        pretrend_tables[[length(pretrend_tables) + 1L]] <- dynamic_table[term_type == "placebo_pretrend"]
        add_diagnostic(meta, spec_name, outcome, "dynamic", "success", dynamic_capture$elapsed, dynamic_capture$warnings,
                       result_terms = nrow(dynamic_table),
                       extra = "horizon=-6:6; pretrends=-6:-2; reference=-1 omitted")
      }
    }
  }
}

failures_dt <- if (length(failures) == 0L) {
  data.table::data.table(sample_spec = character(), threshold_id = character(), threshold = numeric(),
                         model_spec = character(), outcome = character(), stage = character(), error_message = character())
} else {
  data.table::rbindlist(failures, fill = TRUE)
}
write_csv(failures_dt, paths$failures)
if (nrow(failures_dt) > 0L) abortf("One or more I09 models failed; inspect %s", paths$failures)

static_all <- data.table::rbindlist(static_tables, fill = TRUE, use.names = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, fill = TRUE, use.names = TRUE)
pretrend_all <- data.table::rbindlist(pretrend_tables, fill = TRUE, use.names = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostics, fill = TRUE, use.names = TRUE)

pretrend_summary <- pretrend_all[, .(
  pretrend_terms = .N,
  periods_excluding_zero = sum(!ci_includes_zero, na.rm = TRUE),
  significant_periods = sum(!is.na(p_value) & p_value < (1 - confidence_level)),
  all_cis_include_zero = all(ci_includes_zero),
  minimum_p_value = if (all(is.na(p_value))) NA_real_ else min(p_value, na.rm = TRUE),
  minimum_p_event = if (all(is.na(p_value))) NA_integer_ else event_time[which.min(p_value)][1L]
), by = .(sample_spec, mapping_spec, threshold_id, threshold_role, grid_order, delta_from_primary,
         threshold, comparison_operator, ml_metric, primary_threshold, is_primary_threshold,
         primary_analysis, analysis_role, model_spec, model_spec_label, first_stage_formula,
         outcome, outcome_label, outcome_role, sparse_support_flag, sparse_support_reason)]

data.table::setorder(static_all, sample_spec, threshold, model_spec, outcome)
data.table::setorder(dynamic_all, sample_spec, threshold, model_spec, outcome, event_time)
data.table::setorder(pretrend_all, sample_spec, threshold, model_spec, outcome, event_time)
data.table::setorder(pretrend_summary, sample_spec, threshold, model_spec, outcome)
data.table::setorder(diagnostics_all, sample_spec, threshold, model_spec, outcome, model_type)

write_csv(static_all, paths$static)
write_csv(dynamic_all, paths$dynamic)
write_csv(pretrend_all, paths$pretrend_checks)
write_csv(pretrend_summary, paths$pretrend_summary)
write_csv(diagnostics_all, paths$diagnostics)

primary_threshold_static <- static_all[threshold_id == primary_threshold_id]
primary_total_static <- primary_threshold_static[outcome == "log1p_selected_issue_total"]
primary_total_dynamic <- dynamic_all[threshold_id == primary_threshold_id & outcome == "log1p_selected_issue_total"]
total_threshold_static <- static_all[outcome == "log1p_selected_issue_total"]
total_threshold_dynamic <- dynamic_all[outcome == "log1p_selected_issue_total"]

write_csv(primary_threshold_static, paths$primary_threshold_static)
write_csv(primary_total_static, paths$primary_total_static)
write_csv(primary_total_dynamic, paths$primary_total_dynamic)
write_csv(total_threshold_static, paths$total_threshold_static)
write_csv(total_threshold_dynamic, paths$total_threshold_dynamic)

# No prior combined-ML effect estimate exists to reproduce.
# The pre-estimation provenance gate is the frozen I08/I07-v2 measurement contract above.

expected_model_jobs <- 2L * 21L * 2L * 8L
expected_dynamic_terms <- length(pretrend_values) + length(post_values)
expected_counts <- c(
  static_effect_rows = expected_model_jobs,
  dynamic_effect_rows = expected_model_jobs * expected_dynamic_terms,
  pretrend_check_rows = expected_model_jobs * length(pretrend_values),
  pretrend_summary_rows = expected_model_jobs,
  primary_threshold_static_rows = 2L * 2L * 8L,
  primary_total_static_rows = 2L * 2L,
  primary_total_dynamic_rows = 2L * 2L * expected_dynamic_terms,
  total_threshold_static_rows = 2L * 21L * 2L,
  total_threshold_dynamic_rows = 2L * 21L * 2L * expected_dynamic_terms,
  threshold_support_rows = 2L * 21L,
  event_support_rows = 2L * 21L * length(support_event_values),
  model_failure_rows = 0L
)
observed_counts <- c(
  static_effect_rows = nrow(static_all),
  dynamic_effect_rows = nrow(dynamic_all),
  pretrend_check_rows = nrow(pretrend_all),
  pretrend_summary_rows = nrow(pretrend_summary),
  primary_threshold_static_rows = nrow(primary_threshold_static),
  primary_total_static_rows = nrow(primary_total_static),
  primary_total_dynamic_rows = nrow(primary_total_dynamic),
  total_threshold_static_rows = nrow(total_threshold_static),
  total_threshold_dynamic_rows = nrow(total_threshold_dynamic),
  threshold_support_rows = nrow(threshold_support),
  event_support_rows = nrow(event_support),
  model_failure_rows = nrow(failures_dt)
)

primary_warning_count <- diagnostics_all[sample_spec == "full_sample" & threshold_id == primary_threshold_id, sum(warning_count)]
qc <- data.table::data.table(
  check = c(
    "input_long_rows", "threshold_count", "sample_spec_count", "duplicate_long_panel_keys",
    "input_checks_nonpass", "input_global_audit_rows", "threshold_nesting_failures",
    names(expected_counts), "primary_model_warning_count"
  ),
  observed = c(
    nrow(panel_all), nrow(threshold_map), data.table::uniqueN(panel_all$sample_spec), nrow(key_duplicates),
    sum(input_checks$passed_numeric != 1L), nrow(input_global_audit), length(monotonic_failures),
    unname(observed_counts), primary_warning_count
  ),
  expected = c(
    expected_long_rows, 21L, 2L, 0L,
    0L, 42L, 0L,
    unname(expected_counts), 0L
  )
)
qc[, status := ifelse(as.numeric(observed) == as.numeric(expected), "pass", "fail")]
qc[, detail := c(
  "I08 authoritative combined-ML long-panel row count.",
  "ML threshold grid count.",
  "Full and scope-sensitivity samples.",
  "sample+threshold+repo+time must be unique.",
  "All I08 threshold-input hard checks must pass.",
  "21 thresholds x 2 samples.",
  "Strict threshold nesting must be monotone.",
  rep("Strict I09 output row-count contract.", length(expected_counts)),
  "Primary I09 model path must be warning-free."
)]
write_csv(qc, paths$qc)
failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) abortf("I09 hard QC failed: %s", paste(failed_qc$check, collapse = ", "))

summary <- data.table::data.table(
  metric = c(
    "script_version", "status", "ml_metric", "comparison_operator", "primary_threshold",
    "thresholds", "sample_specs", "model_specs", "burden_outcomes", "model_jobs",
    "static_effect_rows", "dynamic_effect_rows", "pretrend_check_rows",
    "primary_total_static_rows", "primary_total_dynamic_rows",
    "total_threshold_static_rows", "total_threshold_dynamic_rows",
    "sparse_support_threshold_sample_rows", "model_failures", "model_warnings",
    "primary_model_warnings", "density_computed", "hard_qc_failures"
  ),
  value = as.character(c(
    paste0("run-x-i09-", implementation_version), ifelse(nrow(failed_qc) == 0L, "PASS", "FAIL"),
    expected_ml_metric, expected_operator, primary_threshold,
    21L, 2L, 2L, 8L, expected_model_jobs,
    nrow(static_all), nrow(dynamic_all), nrow(pretrend_all),
    nrow(primary_total_static), nrow(primary_total_dynamic),
    nrow(total_threshold_static), nrow(total_threshold_dynamic),
    sum(threshold_support$sparse_support_flag), nrow(failures_dt), sum(diagnostics_all$warning_count),
    primary_warning_count, 0L, nrow(failed_qc)
  ))
)
write_csv(summary, paths$summary)

metadata <- data.table::data.table(
  section = c(
    rep("run", 10), rep("software", 4), rep("definition", 13), rep("input_sha256", 5)
  ),
  metric = c(
    "implementation_version", "started", "finished", "input_file", "input_summary_file", "input_checks_file",
    "input_sample_summary_file", "input_global_audit_file", "script_path", "script_sha256",
    "R", "data.table", "didimputation", "fixest",
    "ml_metric", "comparison_operator", "primary_threshold", "threshold_grid", "samples", "mapping_spec",
    "cluster_variable", "dynamic_window", "pretrend_window", "reference_event", "confidence_level",
    "density_computed", "threshold_selection_policy",
    "input_long_panel", "input_summary", "input_checks", "input_sample_summary", "input_global_audit"
  ),
  value = c(
    implementation_version, format(run_started, "%Y-%m-%d %H:%M:%S %Z"), format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
    input_file, input_summary_file, input_checks_file, input_sample_summary_file, input_global_audit_file,
    script_path, ifelse(is.na(script_path), NA_character_, sha256_file(script_path)),
    R.version.string, safe_package_version("data.table"), safe_package_version("didimputation"), safe_package_version("fixest"),
    expected_ml_metric, expected_operator, as.character(primary_threshold), paste(sprintf("%.2f", expected_thresholds), collapse = ","),
    paste(expected_samples, collapse = "|"), expected_mapping, "repo_id", "-6:6", "-6:-2", "-1",
    as.character(confidence_level), "0",
    "I07-v2 thresholds are frozen before quality analysis; I09 never chooses thresholds using downstream significance.",
    sha256_file(input_file), sha256_file(input_summary_file), sha256_file(input_checks_file),
    sha256_file(input_sample_summary_file), sha256_file(input_global_audit_file)
  )
)
write_csv(metadata, paths$metadata)

log_message(
  "INFO",
  "Completed run-x-i09 %s: status=%s; jobs=%d; static=%d; dynamic=%d; sparse threshold-sample rows=%d; warnings=%d; hard QC failures=%d",
  implementation_version, ifelse(nrow(failed_qc) == 0L, "PASS", "FAIL"), expected_model_jobs,
  nrow(static_all), nrow(dynamic_all), sum(threshold_support$sparse_support_flag),
  sum(diagnostics_all$warning_count), nrow(failed_qc)
)
