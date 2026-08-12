#!/usr/bin/env Rscript

# ============================================================
# run-x-d04 v1: Borusyak DiD across frozen FUN-NPR thresholds
# ============================================================
#
# Purpose:
#   Estimate Cursor-adoption effects on unresolved SonarQube issue burden
#   concentrated in Python files whose contemporaneous FUN-NPR exceeds each
#   threshold frozen by run-x-d01 and aggregated by run-x-d03.
#
# Primary interpretation:
#   The outcome is the log1p unresolved SonarQube issue stock among Python files
#   exceeding a specified FUN-NPR threshold at the corresponding historical
#   repository-month snapshot. It is not a calibrated file-level defect rate
#   and does not prove that selected files were AI-generated.
#
# Input:
#   repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz
#
# Frozen analysis dimensions:
#   - 22 FUN-NPR threshold specifications (21 grid + 1 legacy anchor).
#   - 2 sample specifications:
#       full_sample
#       exclude_scope_mismatch_repos
#   - 2 first-stage specifications:
#       adjusted_burden
#       fe_only_burden
#   - 8 selected-file SonarQube burden outcomes.
#
# Estimation design reused from validated run-x-b07 logic:
#   - Borusyak et al. did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic post-treatment effects event 0 through +6.
#   - Package-native placebo terms event -6 through -2.
#   - Event -1 omitted as the reference period.
#
# Treatment timing:
#   - Reconstructed only from event_index and time_index.
#   - Legacy cursor/is_treatment/post_event fields are audit-only.
#
# Density:
#   Not estimated here. ncloc_py_sonarqube in adjusted_burden is a whole-
#   snapshot repository-size covariate, not a selected-file density denominator.
#
# Sparse upper thresholds:
#   All frozen thresholds remain in the analysis. Sparse-support diagnostics are
#   descriptive only and never remove a threshold or model from estimation.
# ============================================================

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
  if (is.na(result)) abortf("Argument --%s must be numeric: %s", gsub("_", "-", name, fixed = TRUE), value)
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

ensure_parent_dir <- function(path) {
  directory <- dirname(path)
  if (!dir.exists(directory)) dir.create(directory, recursive = TRUE, showWarnings = FALSE)
}

write_csv <- function(data, path) {
  ensure_parent_dir(path)
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
  index <- is.na(result) & !is.na(numeric_value)
  result[index] <- as.integer(numeric_value[index] != 0)
  result[is.na(result)] <- 0L
  result
}

validate_columns <- function(data, required) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("Input is missing required columns: %s", paste(missing, collapse = ", "))
}

strict_count_check <- function(actual, expected, label, strict) {
  if (is.na(expected) || expected < 0L) return(invisible(TRUE))
  if (!identical(as.integer(actual), as.integer(expected))) {
    text <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, actual)
    if (strict) abortf("%s", text) else log_message("WARNING", "%s", text)
  }
  invisible(TRUE)
}

make_summary_row <- function(section, metric, value, note = "") {
  data.table::data.table(section = section, metric = metric, value = as.character(value), note = note)
}

lookup_metric <- function(summary_data, metric_name) {
  row <- summary_data[summary_data$metric == metric_name]
  if (nrow(row) != 1L) abortf("Expected exactly one summary row for metric=%s; observed %d", metric_name, nrow(row))
  as.character(row$value[[1L]])
}

extract_effect_table <- function(result, confidence_level) {
  table <- data.table::as.data.table(result)
  required <- c("term", "estimate", "std.error", "conf.low", "conf.high")
  validate_columns(table, required)
  alpha <- 1 - confidence_level
  critical_value <- stats::qnorm(1 - alpha / 2)
  table[, conf.low := estimate - critical_value * std.error]
  table[, conf.high := estimate + critical_value * std.error]
  table[, p_value := ifelse(
    is.finite(std.error) & std.error > 0,
    2 * stats::pnorm(-abs(estimate / std.error)),
    NA_real_
  )]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table
}

fit_first_stage_diagnostic <- function(data, outcome, first_stage_formula_text) {
  untreated <- data[absorbing_treated_recomputed == 0L]
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
  list(
    adjusted_burden = list(
      label = "Adjusted burden",
      first_stage = ~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index,
      first_stage_text = "~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index",
      model_fields = c("log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues")
    ),
    fe_only_burden = list(
      label = "FE-only burden",
      first_stage = ~ 1 | repo_id + time_index,
      first_stage_text = "~ 1 | repo_id + time_index",
      model_fields = character()
    )
  )
}

outcome_labels <- c(
  log1p_selected_issue_total = "Selected high-FUN-NPR total issue stock",
  log1p_selected_issue_code_smell = "Selected high-FUN-NPR code-smell stock",
  log1p_selected_issue_bug = "Selected high-FUN-NPR bug stock",
  log1p_selected_issue_vulnerability = "Selected high-FUN-NPR vulnerability stock",
  log1p_selected_issue_high_severity = "Selected high-FUN-NPR BLOCKER+CRITICAL stock",
  log1p_selected_issue_maintainability_impact = "Selected high-FUN-NPR maintainability-impact stock",
  log1p_selected_issue_reliability_impact = "Selected high-FUN-NPR reliability-impact stock",
  log1p_selected_issue_security_impact = "Selected high-FUN-NPR security-impact stock"
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

raw_outcome_map <- c(
  log1p_selected_issue_total = "selected_issue_total",
  log1p_selected_issue_code_smell = "selected_issue_code_smell",
  log1p_selected_issue_bug = "selected_issue_bug",
  log1p_selected_issue_vulnerability = "selected_issue_vulnerability",
  log1p_selected_issue_high_severity = "selected_issue_high_severity",
  log1p_selected_issue_maintainability_impact = "selected_issue_maintainability_impact",
  log1p_selected_issue_reliability_impact = "selected_issue_reliability_impact",
  log1p_selected_issue_security_impact = "selected_issue_security_impact"
)

make_static_placeholder <- function(job, model_status, error_message = "", warning_count = 0L, warning_messages = "") {
  data.table::data.table(
    sample_spec = job$sample_spec,
    threshold_id = job$threshold_id,
    threshold_role = job$threshold_role,
    grid_order = job$grid_order,
    delta_from_primary = job$delta_from_primary,
    threshold = job$threshold,
    comparison_operator = job$comparison_operator,
    model_spec = job$model_spec,
    model_spec_label = job$model_spec_label,
    first_stage_formula = job$first_stage_formula,
    outcome = job$outcome,
    outcome_label = job$outcome_label,
    outcome_role = job$outcome_role,
    term = "treat",
    term_type = "static_att",
    estimate = NA_real_,
    std.error = NA_real_,
    conf.low = NA_real_,
    conf.high = NA_real_,
    p_value = NA_real_,
    exp_coefficient_change_pct = NA_real_,
    exp_ci_low_pct = NA_real_,
    exp_ci_high_pct = NA_real_,
    model_status = model_status,
    error_message = error_message,
    warning_count = as.integer(warning_count),
    warning_messages = warning_messages
  )
}

make_dynamic_template <- function(job, expected_terms, model_status, error_message = "", warning_count = 0L, warning_messages = "") {
  data.table::data.table(
    sample_spec = job$sample_spec,
    threshold_id = job$threshold_id,
    threshold_role = job$threshold_role,
    grid_order = job$grid_order,
    delta_from_primary = job$delta_from_primary,
    threshold = job$threshold,
    comparison_operator = job$comparison_operator,
    model_spec = job$model_spec,
    model_spec_label = job$model_spec_label,
    first_stage_formula = job$first_stage_formula,
    outcome = job$outcome,
    outcome_label = job$outcome_label,
    outcome_role = job$outcome_role,
    event_time = as.integer(expected_terms),
    term = as.character(expected_terms),
    term_type = ifelse(expected_terms < 0L, "placebo_pretrend", "post_treatment"),
    estimate = NA_real_,
    std.error = NA_real_,
    conf.low = NA_real_,
    conf.high = NA_real_,
    p_value = NA_real_,
    exp_coefficient_change_pct = NA_real_,
    exp_ci_low_pct = NA_real_,
    exp_ci_high_pct = NA_real_,
    ci_includes_zero = NA,
    term_present = FALSE,
    model_status = model_status,
    error_message = error_message,
    warning_count = as.integer(warning_count),
    warning_messages = warning_messages
  )
}

compute_threshold_support <- function(data, post_values, sparse_min_dynamic_positive_repos, sparse_min_within_variation_repos) {
  primary_raw <- "selected_issue_total"
  primary_log <- "log1p_selected_issue_total"
  post <- data[absorbing_treated_recomputed == 1L]
  dynamic <- data[
    absorbing_treated_recomputed == 1L &
      event_time_recomputed >= min(post_values) &
      event_time_recomputed <= max(post_values)
  ]

  within <- data[, .(
    distinct_outcome_values = data.table::uniqueN(get(primary_log))
  ), by = .(repo_id, treatment_group)]
  within_vary <- within[distinct_outcome_values > 1L]

  event_positive <- data[
    treatment_group == 1L & event_time_recomputed %in% post_values,
    .(positive_repositories = data.table::uniqueN(repo_id[get(primary_raw) > 0])),
    by = event_time_recomputed
  ]
  full_events <- data.table::data.table(event_time_recomputed = as.integer(post_values))
  event_positive <- merge(full_events, event_positive, by = "event_time_recomputed", all.x = TRUE)
  event_positive[is.na(positive_repositories), positive_repositories := 0L]
  min_dynamic_positive_repositories <- min(event_positive$positive_repositories)

  repositories_with_within_variation <- data.table::uniqueN(within_vary$repo_id)
  sparse_flag <- (
    min_dynamic_positive_repositories < sparse_min_dynamic_positive_repos ||
      repositories_with_within_variation < sparse_min_within_variation_repos
  )
  sparse_reasons <- character()
  if (min_dynamic_positive_repositories < sparse_min_dynamic_positive_repos) {
    sparse_reasons <- c(sparse_reasons, sprintf(
      "min_dynamic_positive_repositories=%d<%d",
      min_dynamic_positive_repositories, sparse_min_dynamic_positive_repos
    ))
  }
  if (repositories_with_within_variation < sparse_min_within_variation_repos) {
    sparse_reasons <- c(sparse_reasons, sprintf(
      "repositories_with_within_variation=%d<%d",
      repositories_with_within_variation, sparse_min_within_variation_repos
    ))
  }

  data.table::data.table(
    repo_month_rows = nrow(data),
    repositories = data.table::uniqueN(data$repo_id),
    treatment_repositories = data.table::uniqueN(data[treatment_group == 1L, repo_id]),
    control_repositories = data.table::uniqueN(data[treatment_group == 0L, repo_id]),
    untreated_first_stage_rows = nrow(data[absorbing_treated_recomputed == 0L]),
    treated_post_rows = nrow(post),
    dynamic_event_0_to_6_rows = nrow(dynamic),
    eligible_fun_file_rows = sum(data$eligible_fun_file_count),
    selected_file_rows = sum(data$selected_file_count),
    selected_issue_total = sum(data$selected_issue_total),
    repo_months_with_selected_files = sum(data$selected_file_count > 0),
    repo_months_with_positive_issue_burden = sum(data$selected_issue_total > 0),
    zero_outcome_share = mean(data$selected_issue_total == 0),
    post_rows_with_selected_files = sum(post$selected_file_count > 0),
    post_rows_with_positive_issue_burden = sum(post$selected_issue_total > 0),
    post_zero_outcome_share = if (nrow(post) > 0L) mean(post$selected_issue_total == 0) else NA_real_,
    post_repositories_with_selected_files = data.table::uniqueN(post[selected_file_count > 0, repo_id]),
    post_repositories_with_positive_issue_burden = data.table::uniqueN(post[selected_issue_total > 0, repo_id]),
    dynamic_rows_with_selected_files = sum(dynamic$selected_file_count > 0),
    dynamic_rows_with_positive_issue_burden = sum(dynamic$selected_issue_total > 0),
    dynamic_repositories_with_selected_files = data.table::uniqueN(dynamic[selected_file_count > 0, repo_id]),
    dynamic_repositories_with_positive_issue_burden = data.table::uniqueN(dynamic[selected_issue_total > 0, repo_id]),
    repositories_with_within_outcome_variation = repositories_with_within_variation,
    treatment_repositories_with_within_outcome_variation = data.table::uniqueN(within_vary[treatment_group == 1L, repo_id]),
    control_repositories_with_within_outcome_variation = data.table::uniqueN(within_vary[treatment_group == 0L, repo_id]),
    min_dynamic_positive_repositories = min_dynamic_positive_repositories,
    sparse_support_flag = as.integer(sparse_flag),
    sparse_support_reason = paste(sparse_reasons, collapse = " | ")
  )
}

compute_event_support <- function(data, event_values) {
  rows <- list()
  for (event_value in event_values) {
    part <- data[treatment_group == 1L & event_time_recomputed == event_value]
    rows[[length(rows) + 1L]] <- data.table::data.table(
      event_time = as.integer(event_value),
      treatment_rows = nrow(part),
      treatment_repositories = data.table::uniqueN(part$repo_id),
      rows_with_selected_files = sum(part$selected_file_count > 0),
      repositories_with_selected_files = data.table::uniqueN(part[selected_file_count > 0, repo_id]),
      rows_with_positive_issue_burden = sum(part$selected_issue_total > 0),
      repositories_with_positive_issue_burden = data.table::uniqueN(part[selected_issue_total > 0, repo_id]),
      selected_file_rows = sum(part$selected_file_count),
      selected_issue_total = sum(part$selected_issue_total)
    )
  }
  data.table::rbindlist(rows)
}

run_self_test <- function() {
  stopifnot(identical(bool_to_int(c(TRUE, FALSE, NA)), c(1L, 0L, 0L)))
  stopifnot(identical(as.integer(seq.int(-6L, -2L)), c(-6L, -5L, -4L, -3L, -2L)))
  stopifnot(length(c(seq.int(-6L, -2L), seq.int(0L, 6L))) == 12L)
  cat("did_borusyak_fun_npr_threshold_quality self-test: PASS\n")
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
if (isTRUE(args$self_test)) {
  run_self_test()
  quit(save = "no", status = 0L)
}

input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
d03_summary_file <- normalizePath(require_arg(args, "d03_summary_file"), mustWork = TRUE)
d03_sample_summary_file <- normalizePath(require_arg(args, "d03_sample_summary_file"), mustWork = TRUE)
d03_global_audit_file <- normalizePath(require_arg(args, "d03_global_audit_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)

plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
primary_threshold <- as_numeric_arg(args, "primary_threshold", 1.571637)
expected_thresholds <- as_integer_arg(args, "expected_thresholds", 22L)
expected_sample_specs <- as_integer_arg(args, "expected_sample_specs", 2L)
expected_long_rows <- as_integer_arg(args, "expected_long_rows", 85118L)
sparse_min_dynamic_positive_repos <- as_integer_arg(args, "sparse_min_dynamic_positive_repos", 10L)
sparse_min_within_variation_repos <- as_integer_arg(args, "sparse_min_within_variation_repos", 20L)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
strict_primary_warnings <- as_logical_arg(args, "strict_primary_warnings", TRUE)

if (plot_min_event > -2L) abortf("plot_min_event must include pre-treatment periods.")
if (plot_max_event < 0L) abortf("plot_max_event must be non-negative.")
if (pretrend_min > pretrend_max || pretrend_max >= -1L) abortf("Pretrend range must end at or before -2.")
if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")
if (sparse_min_dynamic_positive_repos < 0L || sparse_min_within_variation_repos < 0L) {
  abortf("Sparse-support thresholds must be non-negative.")
}

required_packages <- c("data.table", "didimputation", "fixest", "ggplot2")
check_packages(required_packages)

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
plot_dir <- file.path(output_dir, "plots")
dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  static = file.path(output_dir, "quality_npr_static_effects.csv"),
  dynamic = file.path(output_dir, "quality_npr_dynamic_effects.csv"),
  pretrend_checks = file.path(output_dir, "quality_npr_pretrend_checks.csv"),
  pretrend_summary = file.path(output_dir, "quality_npr_pretrend_summary.csv"),
  diagnostics = file.path(output_dir, "quality_npr_model_diagnostics.csv"),
  failures = file.path(output_dir, "quality_npr_model_failures.csv"),
  threshold_support = file.path(output_dir, "quality_npr_threshold_support.csv"),
  event_support = file.path(output_dir, "quality_npr_event_support.csv"),
  support_policy = file.path(output_dir, "quality_npr_support_policy.csv"),
  primary_static = file.path(output_dir, "quality_npr_primary_threshold_static.csv"),
  primary_total_static = file.path(output_dir, "quality_npr_primary_total_static.csv"),
  primary_total_dynamic = file.path(output_dir, "quality_npr_primary_total_dynamic.csv"),
  total_threshold_static = file.path(output_dir, "quality_npr_total_threshold_static.csv"),
  total_threshold_dynamic = file.path(output_dir, "quality_npr_total_threshold_dynamic.csv"),
  qc = file.path(output_dir, "quality_npr_qc.csv"),
  summary = file.path(output_dir, "quality_npr_summary.csv"),
  metadata = file.path(output_dir, "quality_npr_run_metadata.csv"),
  static_plot_pdf = file.path(plot_dir, "quality_npr_total_static_across_thresholds.pdf"),
  static_plot_png = file.path(plot_dir, "quality_npr_total_static_across_thresholds.png"),
  primary_dynamic_pdf = file.path(plot_dir, "quality_npr_primary_total_dynamic.pdf"),
  primary_dynamic_png = file.path(plot_dir, "quality_npr_primary_total_dynamic.png")
)

run_started <- Sys.time()
log_message("INFO", "Reading D03 long panel: %s", input_file)
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
d03_summary <- data.table::fread(d03_summary_file, na.strings = c("", "NA", "NaN"))
d03_sample_summary <- data.table::fread(d03_sample_summary_file, na.strings = c("", "NA", "NaN"))
d03_global_audit <- data.table::fread(d03_global_audit_file, na.strings = c("", "NA", "NaN"))

validate_columns(d03_summary, c("metric", "value"))
validate_columns(d03_sample_summary, c(
  "sample_spec", "repo_month_rows", "repositories", "control_repositories",
  "treatment_repositories", "untreated_first_stage_rows", "treatment_post_rows",
  "dynamic_event_0_to_6_rows"
))
validate_columns(d03_global_audit, c(
  "sample_spec", "threshold_id", "threshold_role", "threshold", "selected_file_rows",
  "eligible_fun_file_rows", "selected_issue_total"
))

if (lookup_metric(d03_summary, "status") != "PASS") abortf("D03 summary status is not PASS.")
strict_count_check(as.integer(lookup_metric(d03_summary, "thresholds")), expected_thresholds, "D03 thresholds", strict_expected_counts)
strict_count_check(as.integer(lookup_metric(d03_summary, "sample_specs")), expected_sample_specs, "D03 sample specs", strict_expected_counts)
strict_count_check(as.integer(lookup_metric(d03_summary, "long_panel_rows")), expected_long_rows, "D03 long-panel rows", strict_expected_counts)
if (as.integer(lookup_metric(d03_summary, "density_computed")) != 0L) abortf("D03 density_computed must be zero for D04 burden analysis.")
if (abs(as.numeric(lookup_metric(d03_summary, "primary_threshold")) - primary_threshold) > 1e-12) {
  abortf("D03 primary threshold does not match D04 primary threshold.")
}

model_specs <- make_model_specs()
outcomes <- names(outcome_labels)
required_columns <- unique(c(
  "sample_spec", "threshold_id", "threshold_role", "grid_order", "delta_from_primary",
  "threshold", "comparison_operator", "npr_metric", "quality_scope", "quality_count_semantics",
  "density_computed", "repo_id", "repo_name", "dataset_source", "scope_role",
  "treatment_group", "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues", "event_time_normalized", "absorbing_treated",
  "eligible_fun_file_count", "selected_file_count", "selected_issue_total",
  "selected_issue_code_smell", "selected_issue_bug", "selected_issue_vulnerability",
  "selected_issue_high_severity", "selected_issue_maintainability_impact",
  "selected_issue_reliability_impact", "selected_issue_security_impact", outcomes
))
validate_columns(panel, required_columns)

numeric_columns <- unique(c(
  "grid_order", "delta_from_primary", "threshold", "density_computed", "repo_id",
  "treatment_group", "time_index", "event_index", "time_to_event", "is_treatment",
  "post_event", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars",
  "log_issues", "event_time_normalized", "absorbing_treated", "eligible_fun_file_count",
  "selected_file_count", unname(raw_outcome_map), outcomes
))
for (column in numeric_columns) panel[, (column) := suppressWarnings(as.numeric(get(column)))]
panel[, repo_id := as.integer(repo_id)]
panel[, time_index := as.integer(time_index)]
panel[, event_index := as.integer(event_index)]
panel[, treatment_group := as.integer(treatment_group)]

input_rows <- nrow(panel)
strict_count_check(input_rows, expected_long_rows, "D04 input rows", strict_expected_counts)

contract_mismatch_rows <- panel[
  comparison_operator != ">" |
    npr_metric != "file_npr_fun_space_by_token_weighted" |
    quality_scope != "canonical_a12_python_files_with_finite_fun_npr" |
    quality_count_semantics != "unresolved_sonarqube_issue_stock_at_historical_snapshot" |
    density_computed != 0
]
if (nrow(contract_mismatch_rows) > 0L) abortf("Found %d D03 measurement-contract mismatch rows.", nrow(contract_mismatch_rows))

sample_specs <- sort(unique(panel$sample_spec))
expected_sample_names <- sort(c("full_sample", "exclude_scope_mismatch_repos"))
if (!identical(sample_specs, expected_sample_names)) {
  abortf("Unexpected sample specifications: %s", paste(sample_specs, collapse = ", "))
}
strict_count_check(length(sample_specs), expected_sample_specs, "sample specifications", strict_expected_counts)

threshold_catalog <- unique(panel[, .(
  sample_spec, threshold_id, threshold_role, grid_order, delta_from_primary,
  threshold, comparison_operator
)])
threshold_counts <- threshold_catalog[, .N, by = sample_spec]
if (any(threshold_counts$N != expected_thresholds)) abortf("Each sample must contain exactly %d thresholds.", expected_thresholds)

threshold_identity <- threshold_catalog[, .(
  sample_count = data.table::uniqueN(sample_spec),
  role_count = data.table::uniqueN(threshold_role),
  threshold_count = data.table::uniqueN(threshold),
  operator_count = data.table::uniqueN(comparison_operator)
), by = threshold_id]
if (any(threshold_identity$sample_count != expected_sample_specs) ||
    any(threshold_identity$role_count != 1L) ||
    any(threshold_identity$threshold_count != 1L) ||
    any(threshold_identity$operator_count != 1L)) {
  abortf("Threshold identity differs across sample specifications.")
}

primary_catalog <- threshold_catalog[threshold_role == "primary"]
if (nrow(primary_catalog) != expected_sample_specs || any(abs(primary_catalog$threshold - primary_threshold) > 1e-12)) {
  abortf("Primary-threshold catalog mismatch.")
}

legacy_catalog <- threshold_catalog[threshold_role == "legacy_anchor"]
if (nrow(legacy_catalog) != expected_sample_specs || any(abs(legacy_catalog$threshold - 1.5183) > 1e-12)) {
  abortf("Legacy threshold anchor mismatch.")
}

duplicate_keys <- panel[, .N, by = .(sample_spec, threshold_id, repo_id, time_index)][N > 1L]
if (nrow(duplicate_keys) > 0L) abortf("Found %d duplicate sample-threshold-repo-time keys.", nrow(duplicate_keys))

panel[, event_time_recomputed := data.table::fifelse(
  treatment_group == 1L,
  time_index - event_index,
  NA_integer_
)]
panel[, absorbing_treated_recomputed := as.integer(
  treatment_group == 1L & event_index > 0L & time_index >= event_index
)]
timing_mismatch_rows <- panel[
  absorbing_treated != absorbing_treated_recomputed |
    (treatment_group == 1L & event_time_normalized != event_time_recomputed)
]
if (nrow(timing_mismatch_rows) > 0L) abortf("Found %d D03 timing-reconstruction mismatches.", nrow(timing_mismatch_rows))

control_event_errors <- panel[treatment_group == 0L & event_index != 0L]
treatment_event_errors <- panel[treatment_group == 1L & event_index <= 0L]
if (nrow(control_event_errors) > 0L) abortf("Found %d control rows with nonzero event_index.", nrow(control_event_errors))
if (nrow(treatment_event_errors) > 0L) abortf("Found %d treatment rows with nonpositive event_index.", nrow(treatment_event_errors))

all_model_fields <- unique(c(outcomes, unlist(lapply(model_specs, function(x) x$model_fields), use.names = FALSE)))
missing_model_rows <- panel[!stats::complete.cases(panel[, ..all_model_fields])]
if (nrow(missing_model_rows) > 0L) abortf("Found %d rows with missing D04 model fields.", nrow(missing_model_rows))
nonfinite_model_rows <- panel[
  !apply(as.data.frame(panel[, ..all_model_fields]), 1L, function(row) all(is.finite(row)))
]
if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d rows with non-finite D04 model fields.", nrow(nonfinite_model_rows))

# Validate threshold-level aggregate counts against run-x-d03 global audit.
input_global <- panel[, .(
  repo_month_rows = .N,
  eligible_fun_file_rows = sum(eligible_fun_file_count),
  selected_file_rows = sum(selected_file_count),
  selected_issue_total = sum(selected_issue_total)
), by = .(sample_spec, threshold_id)]
audit_compare <- merge(
  input_global,
  d03_global_audit[, .(
    sample_spec, threshold_id,
    audit_eligible_fun_file_rows = eligible_fun_file_rows,
    audit_selected_file_rows = selected_file_rows,
    audit_selected_issue_total = selected_issue_total
  )],
  by = c("sample_spec", "threshold_id"), all = TRUE
)
audit_compare[, mismatch :=
  is.na(eligible_fun_file_rows) | is.na(audit_eligible_fun_file_rows) |
  eligible_fun_file_rows != audit_eligible_fun_file_rows |
  selected_file_rows != audit_selected_file_rows |
  selected_issue_total != audit_selected_issue_total
]
if (any(audit_compare$mismatch)) abortf("D04 input does not reconcile to D03 global audit for %d sample-threshold rows.", sum(audit_compare$mismatch))

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
expected_dynamic_terms <- c(pretrend_values, post_values)
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)
event_support_values <- dynamic_horizon_values

# Validate threshold-invariant sample support against D03 sample summary.
sample_validation_rows <- list()
for (sample_name in sample_specs) {
  threshold_one <- threshold_catalog[sample_spec == sample_name][order(threshold)][1L]
  part <- panel[sample_spec == sample_name & threshold_id == threshold_one$threshold_id]
  actual <- data.table::data.table(
    sample_spec = sample_name,
    repo_month_rows = nrow(part),
    repositories = data.table::uniqueN(part$repo_id),
    control_repositories = data.table::uniqueN(part[treatment_group == 0L, repo_id]),
    treatment_repositories = data.table::uniqueN(part[treatment_group == 1L, repo_id]),
    untreated_first_stage_rows = nrow(part[absorbing_treated_recomputed == 0L]),
    treatment_post_rows = nrow(part[absorbing_treated_recomputed == 1L]),
    dynamic_event_0_to_6_rows = nrow(part[
      absorbing_treated_recomputed == 1L &
        event_time_recomputed >= 0L & event_time_recomputed <= plot_max_event
    ])
  )
  expected <- d03_sample_summary[sample_spec == sample_name]
  if (nrow(expected) != 1L) abortf("Missing D03 sample-summary row for %s", sample_name)
  columns <- setdiff(names(actual), "sample_spec")
  mismatches <- columns[vapply(columns, function(column) {
    as.integer(actual[[column]][[1L]]) != as.integer(expected[[column]][[1L]])
  }, logical(1))]
  sample_validation_rows[[length(sample_validation_rows) + 1L]] <- data.table::data.table(
    sample_spec = sample_name,
    mismatch_count = length(mismatches),
    mismatched_fields = paste(mismatches, collapse = "|")
  )
}
sample_validation <- data.table::rbindlist(sample_validation_rows)
if (any(sample_validation$mismatch_count > 0L)) abortf("D03 sample-support reconciliation failed.")

support_policy <- data.table::data.table(
  policy_id = "prespecified_sparse_support_flag_v1",
  apply_to_model_omission = 0L,
  prespecified_before_d04_results = 1L,
  min_dynamic_positive_repositories_required = sparse_min_dynamic_positive_repos,
  min_repositories_with_within_outcome_variation_required = sparse_min_within_variation_repos,
  rule = "Flag as sparse if min positive-issue repositories across event 0:+6 is below the first threshold OR repositories with within-panel variation in log1p selected total issue stock is below the second threshold. Never omit a frozen threshold because of this flag."
)
write_csv(support_policy, paths$support_policy)

threshold_support_rows <- list()
event_support_rows <- list()
for (sample_name in sample_specs) {
  sample_thresholds <- threshold_catalog[sample_spec == sample_name][order(threshold)]
  for (i in seq_len(nrow(sample_thresholds))) {
    threshold_row <- sample_thresholds[i]
    part <- panel[sample_spec == sample_name & threshold_id == threshold_row$threshold_id]
    support <- compute_threshold_support(
      part, post_values,
      sparse_min_dynamic_positive_repos,
      sparse_min_within_variation_repos
    )
    support[, `:=`(
      sample_spec = sample_name,
      threshold_id = threshold_row$threshold_id,
      threshold_role = threshold_row$threshold_role,
      grid_order = threshold_row$grid_order,
      delta_from_primary = threshold_row$delta_from_primary,
      threshold = threshold_row$threshold,
      comparison_operator = threshold_row$comparison_operator
    )]
    data.table::setcolorder(support, c(
      "sample_spec", "threshold_id", "threshold_role", "grid_order", "delta_from_primary",
      "threshold", "comparison_operator", setdiff(names(support), c(
        "sample_spec", "threshold_id", "threshold_role", "grid_order", "delta_from_primary",
        "threshold", "comparison_operator"
      ))
    ))
    threshold_support_rows[[length(threshold_support_rows) + 1L]] <- support

    event_support <- compute_event_support(part, event_support_values)
    event_support[, `:=`(
      sample_spec = sample_name,
      threshold_id = threshold_row$threshold_id,
      threshold_role = threshold_row$threshold_role,
      threshold = threshold_row$threshold,
      period_type = data.table::fcase(
        event_time %in% pretrend_values, "placebo_pretrend",
        event_time == -1L, "reference",
        event_time %in% post_values, "post_treatment",
        default = "other"
      )
    )]
    event_support_rows[[length(event_support_rows) + 1L]] <- event_support
  }
}
threshold_support <- data.table::rbindlist(threshold_support_rows, fill = TRUE)
event_support <- data.table::rbindlist(event_support_rows, fill = TRUE)
data.table::setorder(threshold_support, sample_spec, threshold)
data.table::setorder(event_support, sample_spec, threshold, event_time)
write_csv(threshold_support, paths$threshold_support)
write_csv(event_support, paths$event_support)

# Modeling loop.
static_rows <- list()
dynamic_rows <- list()
diagnostic_rows <- list()
job_failure_rows <- list()
job_index <- 0L

add_diagnostic <- function(job, stage, status, elapsed, warnings = character(), error_message = "", extra = "") {
  diagnostic_rows[[length(diagnostic_rows) + 1L]] <<- data.table::data.table(
    sample_spec = job$sample_spec,
    threshold_id = job$threshold_id,
    threshold_role = job$threshold_role,
    threshold = job$threshold,
    model_spec = job$model_spec,
    model_spec_label = job$model_spec_label,
    outcome = job$outcome,
    outcome_label = job$outcome_label,
    outcome_role = job$outcome_role,
    stage = stage,
    status = status,
    runtime_seconds = as.numeric(elapsed),
    warning_count = length(warnings),
    warning_messages = paste(warnings, collapse = " | "),
    error_message = error_message,
    extra = extra
  )
}

record_job_failure <- function(job, stage, status, error_message) {
  job_failure_rows[[length(job_failure_rows) + 1L]] <<- data.table::data.table(
    sample_spec = job$sample_spec,
    threshold_id = job$threshold_id,
    threshold_role = job$threshold_role,
    threshold = job$threshold,
    model_spec = job$model_spec,
    outcome = job$outcome,
    stage = stage,
    status = status,
    error_message = error_message
  )
}

for (sample_name in sample_specs) {
  sample_thresholds <- threshold_catalog[sample_spec == sample_name][order(threshold)]
  for (threshold_position in seq_len(nrow(sample_thresholds))) {
    threshold_row <- sample_thresholds[threshold_position]
    part <- panel[sample_spec == sample_name & threshold_id == threshold_row$threshold_id]
    support_row <- threshold_support[sample_spec == sample_name & threshold_id == threshold_row$threshold_id]

    log_message(
      "INFO",
      "Starting sample=%s threshold=%s (%.6f; role=%s; sparse=%d)",
      sample_name, threshold_row$threshold_id, threshold_row$threshold,
      threshold_row$threshold_role, support_row$sparse_support_flag
    )

    for (spec_name in names(model_specs)) {
      spec <- model_specs[[spec_name]]
      for (outcome in outcomes) {
        job_index <- job_index + 1L
        job <- list(
          sample_spec = sample_name,
          threshold_id = threshold_row$threshold_id,
          threshold_role = threshold_row$threshold_role,
          grid_order = threshold_row$grid_order,
          delta_from_primary = threshold_row$delta_from_primary,
          threshold = threshold_row$threshold,
          comparison_operator = threshold_row$comparison_operator,
          model_spec = spec_name,
          model_spec_label = spec$label,
          first_stage_formula = spec$first_stage_text,
          outcome = outcome,
          outcome_label = unname(outcome_labels[[outcome]]),
          outcome_role = unname(outcome_roles[[outcome]])
        )

        first_stage_capture <- fit_first_stage_diagnostic(part, outcome, spec$first_stage_text)
        if (first_stage_capture$error) {
          error_text <- first_stage_capture$value$message
          add_diagnostic(job, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text)
          record_job_failure(job, "first_stage", "failed", error_text)
          static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(
            job, "first_stage_failed", error_text,
            length(first_stage_capture$warnings), paste(first_stage_capture$warnings, collapse = " | ")
          )
          dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(
            job, expected_dynamic_terms, "first_stage_failed", error_text,
            length(first_stage_capture$warnings), paste(first_stage_capture$warnings, collapse = " | ")
          )
          next
        }

        prediction_na_treated <- sum(is.na(first_stage_capture$predictions[part$absorbing_treated_recomputed == 1L]))
        prediction_na_all <- sum(is.na(first_stage_capture$predictions))
        if (prediction_na_treated > 0L) {
          error_text <- sprintf("First-stage predictions missing for %d treated rows.", prediction_na_treated)
          add_diagnostic(
            job, "first_stage", "failed", first_stage_capture$elapsed,
            first_stage_capture$warnings, error_text,
            sprintf("prediction_na_all=%d", prediction_na_all)
          )
          record_job_failure(job, "first_stage", "failed", error_text)
          static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "first_stage_failed", error_text)
          dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(job, expected_dynamic_terms, "first_stage_failed", error_text)
          next
        }
        add_diagnostic(
          job, "first_stage", "success", first_stage_capture$elapsed,
          first_stage_capture$warnings, "",
          sprintf("nobs=%d; prediction_na_all=%d; prediction_na_treated=%d",
                  stats::nobs(first_stage_capture$value), prediction_na_all, prediction_na_treated)
        )

        static_capture <- run_did_model(part, outcome, spec$first_stage, horizon = NULL, pretrends = NULL)
        if (static_capture$error) {
          error_text <- static_capture$value$message
          add_diagnostic(job, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
          record_job_failure(job, "static", "failed", error_text)
          static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(
            job, "failed", error_text,
            length(static_capture$warnings), paste(static_capture$warnings, collapse = " | ")
          )
        } else {
          static_table <- extract_effect_table(static_capture$value, confidence_level)[term == "treat"]
          if (nrow(static_table) != 1L) {
            error_text <- sprintf("Expected one static treat term, observed %d.", nrow(static_table))
            add_diagnostic(job, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
            record_job_failure(job, "static", "failed", error_text)
            static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "failed", error_text)
          } else {
            static_table[, `:=`(
              sample_spec = job$sample_spec,
              threshold_id = job$threshold_id,
              threshold_role = job$threshold_role,
              grid_order = job$grid_order,
              delta_from_primary = job$delta_from_primary,
              threshold = job$threshold,
              comparison_operator = job$comparison_operator,
              model_spec = job$model_spec,
              model_spec_label = job$model_spec_label,
              first_stage_formula = job$first_stage_formula,
              outcome = job$outcome,
              outcome_label = job$outcome_label,
              outcome_role = job$outcome_role,
              term_type = "static_att",
              model_status = "success",
              error_message = "",
              warning_count = length(static_capture$warnings),
              warning_messages = paste(static_capture$warnings, collapse = " | ")
            )]
            static_rows[[length(static_rows) + 1L]] <- static_table
            add_diagnostic(job, "static", "success", static_capture$elapsed, static_capture$warnings)
          }
        }

        dynamic_capture <- run_did_model(
          part, outcome, spec$first_stage,
          horizon = dynamic_horizon_values,
          pretrends = pretrend_values
        )
        if (dynamic_capture$error) {
          error_text <- dynamic_capture$value$message
          add_diagnostic(job, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
          record_job_failure(job, "dynamic", "failed", error_text)
          dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(
            job, expected_dynamic_terms, "failed", error_text,
            length(dynamic_capture$warnings), paste(dynamic_capture$warnings, collapse = " | ")
          )
        } else {
          extracted <- extract_effect_table(dynamic_capture$value, confidence_level)
          extracted[, event_time := suppressWarnings(as.integer(as.character(term)))]
          extracted <- extracted[!is.na(event_time)]
          if (anyDuplicated(extracted$event_time)) {
            error_text <- "Dynamic did_imputation returned duplicate event-time terms."
            add_diagnostic(job, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
            record_job_failure(job, "dynamic", "failed", error_text)
            dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(job, expected_dynamic_terms, "failed", error_text)
          } else {
            template <- make_dynamic_template(
              job, expected_dynamic_terms, "success", "",
              length(dynamic_capture$warnings), paste(dynamic_capture$warnings, collapse = " | ")
            )
            merge_values <- extracted[, .(
              event_time,
              estimate_new = estimate,
              std_error_new = std.error,
              conf_low_new = conf.low,
              conf_high_new = conf.high,
              p_value_new = p_value,
              exp_change_new = exp_coefficient_change_pct,
              exp_low_new = exp_ci_low_pct,
              exp_high_new = exp_ci_high_pct
            )]
            template <- merge(template, merge_values, by = "event_time", all.x = TRUE, sort = FALSE)
            template[, term_present := !is.na(estimate_new)]
            template[term_present == TRUE, `:=`(
              estimate = estimate_new,
              std.error = std_error_new,
              conf.low = conf_low_new,
              conf.high = conf_high_new,
              p_value = p_value_new,
              exp_coefficient_change_pct = exp_change_new,
              exp_ci_low_pct = exp_low_new,
              exp_ci_high_pct = exp_high_new,
              ci_includes_zero = conf_low_new <= 0 & conf_high_new >= 0
            )]
            template[, c(
              "estimate_new", "std_error_new", "conf_low_new", "conf_high_new",
              "p_value_new", "exp_change_new", "exp_low_new", "exp_high_new"
            ) := NULL]
            missing_terms <- template[term_present == FALSE, event_time]
            if (length(missing_terms) > 0L) {
              template[, model_status := "partial"]
              template[, error_message := sprintf("Missing dynamic terms: %s", paste(missing_terms, collapse = ","))]
              record_job_failure(job, "dynamic", "partial", unique(template$error_message))
              add_diagnostic(
                job, "dynamic", "partial", dynamic_capture$elapsed, dynamic_capture$warnings,
                unique(template$error_message),
                sprintf("observed_terms=%d; expected_terms=%d", sum(template$term_present), length(expected_dynamic_terms))
              )
            } else {
              add_diagnostic(
                job, "dynamic", "success", dynamic_capture$elapsed, dynamic_capture$warnings,
                "", sprintf("terms=%d", length(expected_dynamic_terms))
              )
            }
            dynamic_rows[[length(dynamic_rows) + 1L]] <- template
          }
        }
      }
    }
  }
}

static_all <- data.table::rbindlist(static_rows, fill = TRUE, use.names = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_rows, fill = TRUE, use.names = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostic_rows, fill = TRUE, use.names = TRUE)
if (length(job_failure_rows) > 0L) {
  failures_all <- data.table::rbindlist(job_failure_rows, fill = TRUE, use.names = TRUE)
} else {
  failures_all <- data.table::data.table(
    sample_spec = character(), threshold_id = character(), threshold_role = character(),
    threshold = numeric(), model_spec = character(), outcome = character(), stage = character(),
    status = character(), error_message = character()
  )
}

data.table::setorder(static_all, sample_spec, threshold, model_spec, outcome)
data.table::setorder(dynamic_all, sample_spec, threshold, model_spec, outcome, event_time)
data.table::setorder(diagnostics_all, sample_spec, threshold, model_spec, outcome, stage)
write_csv(static_all, paths$static)
write_csv(dynamic_all, paths$dynamic)
write_csv(diagnostics_all, paths$diagnostics)
write_csv(failures_all, paths$failures)

pretrend_all <- dynamic_all[term_type == "placebo_pretrend"]
pretrend_summary <- pretrend_all[, .(
  expected_terms = length(pretrend_values),
  present_terms = sum(term_present),
  significant_periods = sum(term_present & !is.na(p_value) & p_value < (1 - confidence_level)),
  all_present_cis_include_zero = if (all(term_present)) all(ci_includes_zero) else NA,
  minimum_p_value = if (all(is.na(p_value))) NA_real_ else min(p_value, na.rm = TRUE),
  minimum_p_event = if (all(is.na(p_value))) NA_integer_ else event_time[which.min(p_value)][1L],
  pretrend_status = if (all(term_present)) "complete" else "incomplete"
), by = .(
  sample_spec, threshold_id, threshold_role, grid_order, delta_from_primary, threshold,
  model_spec, model_spec_label, outcome, outcome_label, outcome_role
)]
data.table::setorder(pretrend_all, sample_spec, threshold, model_spec, outcome, event_time)
data.table::setorder(pretrend_summary, sample_spec, threshold, model_spec, outcome)
write_csv(pretrend_all, paths$pretrend_checks)
write_csv(pretrend_summary, paths$pretrend_summary)

primary_static <- static_all[threshold_role == "primary"]
primary_total_static <- primary_static[outcome == "log1p_selected_issue_total"]
primary_total_dynamic <- dynamic_all[
  threshold_role == "primary" & outcome == "log1p_selected_issue_total"
]
total_threshold_static <- static_all[outcome == "log1p_selected_issue_total"]
total_threshold_dynamic <- dynamic_all[outcome == "log1p_selected_issue_total"]
write_csv(primary_static, paths$primary_static)
write_csv(primary_total_static, paths$primary_total_static)
write_csv(primary_total_dynamic, paths$primary_total_dynamic)
write_csv(total_threshold_static, paths$total_threshold_static)
write_csv(total_threshold_dynamic, paths$total_threshold_dynamic)

# Attach support columns to effect outputs for immediate interpretability.
support_attach <- threshold_support[, .(
  sample_spec, threshold_id,
  sparse_support_flag,
  sparse_support_reason,
  post_rows_with_positive_issue_burden,
  post_repositories_with_positive_issue_burden,
  dynamic_rows_with_positive_issue_burden,
  dynamic_repositories_with_positive_issue_burden,
  repositories_with_within_outcome_variation,
  min_dynamic_positive_repositories,
  zero_outcome_share,
  post_zero_outcome_share
)]
static_all <- merge(static_all, support_attach, by = c("sample_spec", "threshold_id"), all.x = TRUE, sort = FALSE)
dynamic_all <- merge(dynamic_all, support_attach, by = c("sample_spec", "threshold_id"), all.x = TRUE, sort = FALSE)
write_csv(static_all, paths$static)
write_csv(dynamic_all, paths$dynamic)

# Rebuild selected exports after support attachment.
primary_static <- static_all[threshold_role == "primary"]
primary_total_static <- primary_static[outcome == "log1p_selected_issue_total"]
primary_total_dynamic <- dynamic_all[
  threshold_role == "primary" & outcome == "log1p_selected_issue_total"
]
total_threshold_static <- static_all[outcome == "log1p_selected_issue_total"]
total_threshold_dynamic <- dynamic_all[outcome == "log1p_selected_issue_total"]
write_csv(primary_static, paths$primary_static)
write_csv(primary_total_static, paths$primary_total_static)
write_csv(primary_total_dynamic, paths$primary_total_dynamic)
write_csv(total_threshold_static, paths$total_threshold_static)
write_csv(total_threshold_dynamic, paths$total_threshold_dynamic)

# Primary gates and production QC.
model_job_count <- expected_thresholds * expected_sample_specs * length(model_specs) * length(outcomes)
expected_static_rows <- model_job_count
expected_dynamic_rows <- model_job_count * length(expected_dynamic_terms)
expected_pretrend_rows <- model_job_count * length(pretrend_values)
expected_primary_static_rows <- expected_sample_specs * length(model_specs) * length(outcomes)
expected_primary_total_static_rows <- expected_sample_specs * length(model_specs)
expected_primary_total_dynamic_rows <- expected_primary_total_static_rows * length(expected_dynamic_terms)
expected_total_threshold_static_rows <- expected_thresholds * expected_sample_specs * length(model_specs)
expected_total_threshold_dynamic_rows <- expected_total_threshold_static_rows * length(expected_dynamic_terms)
expected_threshold_support_rows <- expected_thresholds * expected_sample_specs
expected_event_support_rows <- expected_threshold_support_rows * length(event_support_values)

primary_static_failures <- primary_static[model_status != "success"]
primary_dynamic_status <- dynamic_all[threshold_role == "primary", .(
  all_terms_present = all(term_present),
  status_values = paste(sort(unique(model_status)), collapse = "|")
), by = .(sample_spec, threshold_id, model_spec, outcome)]
primary_dynamic_failures <- primary_dynamic_status[all_terms_present == FALSE | status_values != "success"]

primary_warning_jobs <- diagnostics_all[
  threshold_role == "primary" & warning_count > 0L,
  .N,
  by = .(sample_spec, threshold_id, model_spec, outcome)
]
primary_warning_job_count <- nrow(primary_warning_jobs)

nonprimary_failure_jobs <- unique(failures_all[threshold_role != "primary", .(
  sample_spec, threshold_id, model_spec, outcome
)])
nonprimary_failure_job_count <- nrow(nonprimary_failure_jobs)

qc <- data.table::data.table(
  check = c(
    "input_long_rows",
    "threshold_count",
    "sample_spec_count",
    "duplicate_sample_threshold_repo_time_keys",
    "measurement_contract_mismatch_rows",
    "timing_reconstruction_mismatch_rows",
    "missing_model_rows",
    "nonfinite_model_rows",
    "d03_global_audit_mismatch_rows",
    "d03_sample_support_mismatch_samples",
    "model_job_count",
    "static_effect_rows",
    "dynamic_effect_rows",
    "pretrend_check_rows",
    "pretrend_summary_rows",
    "threshold_support_rows",
    "event_support_rows",
    "primary_threshold_static_rows",
    "primary_total_static_rows",
    "primary_total_dynamic_rows",
    "total_threshold_static_rows",
    "total_threshold_dynamic_rows",
    "primary_static_failure_rows",
    "primary_dynamic_failure_jobs",
    "primary_warning_jobs",
    "nonprimary_failure_jobs",
    "primary_threshold_exact"
  ),
  observed = c(
    input_rows,
    data.table::uniqueN(panel$threshold_id),
    length(sample_specs),
    nrow(duplicate_keys),
    nrow(contract_mismatch_rows),
    nrow(timing_mismatch_rows),
    nrow(missing_model_rows),
    nrow(nonfinite_model_rows),
    sum(audit_compare$mismatch),
    sum(sample_validation$mismatch_count > 0L),
    model_job_count,
    nrow(static_all),
    nrow(dynamic_all),
    nrow(pretrend_all),
    nrow(pretrend_summary),
    nrow(threshold_support),
    nrow(event_support),
    nrow(primary_static),
    nrow(primary_total_static),
    nrow(primary_total_dynamic),
    nrow(total_threshold_static),
    nrow(total_threshold_dynamic),
    nrow(primary_static_failures),
    nrow(primary_dynamic_failures),
    primary_warning_job_count,
    nonprimary_failure_job_count,
    max(abs(primary_catalog$threshold - primary_threshold))
  ),
  expected = c(
    expected_long_rows,
    expected_thresholds,
    expected_sample_specs,
    0L, 0L, 0L, 0L, 0L, 0L, 0L,
    model_job_count,
    expected_static_rows,
    expected_dynamic_rows,
    expected_pretrend_rows,
    model_job_count,
    expected_threshold_support_rows,
    expected_event_support_rows,
    expected_primary_static_rows,
    expected_primary_total_static_rows,
    expected_primary_total_dynamic_rows,
    expected_total_threshold_static_rows,
    expected_total_threshold_dynamic_rows,
    0L,
    0L,
    if (strict_primary_warnings) 0L else -1L,
    -1L,
    0
  )
)
qc[, status := data.table::fifelse(
  expected < 0,
  "informational",
  data.table::fifelse(abs(as.numeric(observed) - as.numeric(expected)) < 1e-12, "pass", "fail")
)]
qc[, note := c(
  "Frozen run-x-d03 long panel.",
  "21 main-grid thresholds plus one legacy anchor.",
  "Full sample plus pre-specified two-repository exclusion sensitivity.",
  "Must be zero.",
  "D03 measurement contract must remain unchanged.",
  "Authoritative treatment timing is reconstructed from time_index and event_index.",
  "All outcomes and adjusted covariates must be complete.",
  "All outcomes and adjusted covariates must be finite.",
  "Selected file/issue counts must reconcile to D03 global audit.",
  "Threshold-invariant sample support must reconcile to D03 sample summary.",
  "22 thresholds x 2 samples x 2 model specs x 8 outcomes.",
  "One static slot per model job, including explicit NA placeholders for failures.",
  "Twelve event slots per model job: -6:-2 and 0:+6.",
  "Five placebo slots per model job.",
  "One pretrend summary per model job.",
  "One support row per sample-threshold.",
  "Event support includes -6 through +6, including reference event -1.",
  "Primary threshold x 2 samples x 2 specs x 8 outcomes.",
  "Primary total issue outcome x 2 samples x 2 specs.",
  "Primary total issue outcome x 4 models x 12 event terms.",
  "Total issue outcome across all thresholds, samples, and two specs.",
  "Total issue outcome static rows x 12 event terms.",
  "Primary threshold static models must all succeed.",
  "Primary threshold dynamic models must contain all expected terms.",
  "Warnings on primary threshold models are a hard gate when strict_primary_warnings=1.",
  "Informational only; sparse upper-threshold failures are retained rather than causing post-hoc threshold deletion.",
  "Primary threshold must equal the frozen value exactly within numerical tolerance."
)]
write_csv(qc, paths$qc)

failed_qc <- qc[status == "fail"]
nonprimary_failure_note <- if (nonprimary_failure_job_count > 0L) {
  sprintf("%d non-primary model jobs had a failure or partial dynamic result; inspect quality_npr_model_failures.csv.", nonprimary_failure_job_count)
} else {
  "No non-primary model failures."
}
run_status <- if (nonprimary_failure_job_count > 0L) "PASS_WITH_SPARSE_MODEL_FAILURES" else "PASS"

summary <- data.table::rbindlist(list(
  make_summary_row("run", "script_version", "run-x-d04-v1"),
  make_summary_row("run", "status", run_status),
  make_summary_row("design", "thresholds", expected_thresholds),
  make_summary_row("design", "sample_specs", expected_sample_specs),
  make_summary_row("design", "model_specs", paste(names(model_specs), collapse = "|")),
  make_summary_row("design", "outcomes", length(outcomes)),
  make_summary_row("design", "model_jobs", model_job_count),
  make_summary_row("design", "primary_threshold", primary_threshold),
  make_summary_row("design", "dynamic_window", "0:+6"),
  make_summary_row("design", "placebo_window", "-6:-2"),
  make_summary_row("design", "reference_event", -1L),
  make_summary_row("support", "sparse_threshold_rows", sum(threshold_support$sparse_support_flag == 1L)),
  make_summary_row("models", "nonprimary_failure_jobs", nonprimary_failure_job_count, nonprimary_failure_note),
  make_summary_row("models", "primary_static_failures", nrow(primary_static_failures)),
  make_summary_row("models", "primary_dynamic_failures", nrow(primary_dynamic_failures)),
  make_summary_row("models", "primary_warning_jobs", primary_warning_job_count),
  make_summary_row("outputs", "static_rows", nrow(static_all)),
  make_summary_row("outputs", "dynamic_rows", nrow(dynamic_all)),
  make_summary_row("qc", "hard_qc_failures", nrow(failed_qc)),
  make_summary_row("interpretation", "density_computed", 0L, "Selected-file density remains deferred until selected-file SonarQube NCLOC is available.")
), use.names = TRUE, fill = TRUE)
write_csv(summary, paths$summary)

metadata <- data.table::rbindlist(list(
  make_summary_row("run", "implementation_version", implementation_version),
  make_summary_row("run", "started", format(run_started, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "finished", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "input_file", input_file),
  make_summary_row("run", "input_sha256", sha256_file(input_file)),
  make_summary_row("run", "d03_summary_sha256", sha256_file(d03_summary_file)),
  make_summary_row("run", "d03_sample_summary_sha256", sha256_file(d03_sample_summary_file)),
  make_summary_row("run", "d03_global_audit_sha256", sha256_file(d03_global_audit_file)),
  make_summary_row("run", "script_path", script_path),
  make_summary_row("run", "script_sha256", if (is.na(script_path)) NA_character_ else sha256_file(script_path)),
  make_summary_row("software", "R", R.version.string),
  make_summary_row("software", "data.table", safe_package_version("data.table")),
  make_summary_row("software", "didimputation", safe_package_version("didimputation")),
  make_summary_row("software", "fixest", safe_package_version("fixest")),
  make_summary_row("software", "ggplot2", safe_package_version("ggplot2")),
  make_summary_row("definition", "cluster_variable", "repo_id"),
  make_summary_row("definition", "treatment", "absorbing treatment reconstructed as treatment_group==1 & event_index>0 & time_index>=event_index"),
  make_summary_row("definition", "adjusted_first_stage", model_specs$adjusted_burden$first_stage_text),
  make_summary_row("definition", "fe_only_first_stage", model_specs$fe_only_burden$first_stage_text),
  make_summary_row("definition", "primary_outcome", "log1p_selected_issue_total"),
  make_summary_row("definition", "quality_semantics", "unresolved SonarQube issue burden among Python files exceeding a frozen contemporaneous FUN-NPR threshold"),
  make_summary_row("definition", "ncloc_caution", "ncloc_py_sonarqube is a whole-snapshot repository-size covariate in adjusted models, not a selected-file density denominator."),
  make_summary_row("definition", "percent_transform_caution", "exp(beta)-1 is reported on a log1p outcome and is not an exact arithmetic percentage change in raw issue counts."),
  make_summary_row("definition", "sparse_support_policy", support_policy$rule[[1L]]),
  make_summary_row("qc", "hard_qc_failures", nrow(failed_qc))
), fill = TRUE)
write_csv(metadata, paths$metadata)

# Plots are descriptive presentations of the frozen estimates; no threshold is selected from them.
plot_static_data <- total_threshold_static[model_status == "success"]
if (nrow(plot_static_data) > 0L) {
  plot_static_data[, series := interaction(sample_spec, model_spec, sep = " / ", lex.order = TRUE)]
  p_static <- ggplot2::ggplot(
    plot_static_data,
    ggplot2::aes(x = threshold, y = estimate, linetype = series, shape = series)
  ) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_vline(xintercept = primary_threshold, linewidth = 0.4, linetype = "dotted") +
    ggplot2::geom_line() +
    ggplot2::geom_point(size = 1.8) +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.01) +
    ggplot2::labs(
      title = "Quality burden DiD across frozen FUN-NPR thresholds",
      subtitle = "Total selected-file unresolved SonarQube issue stock",
      x = "FUN-NPR threshold",
      y = "Static ATT on log1p selected issue burden",
      linetype = "Sample / specification",
      shape = "Sample / specification",
      caption = "Dotted line: frozen primary threshold 1.571637. Sparse thresholds are retained."
    ) +
    ggplot2::theme_minimal(base_size = 10)
  ggplot2::ggsave(paths$static_plot_pdf, p_static, width = 9.5, height = 5.7)
  ggplot2::ggsave(paths$static_plot_png, p_static, width = 9.5, height = 5.7, dpi = 160)
}

plot_dynamic_data <- primary_total_dynamic[term_present == TRUE]
if (nrow(plot_dynamic_data) > 0L) {
  plot_dynamic_data[, series := interaction(sample_spec, model_spec, sep = " / ", lex.order = TRUE)]
  p_dynamic <- ggplot2::ggplot(
    plot_dynamic_data,
    ggplot2::aes(x = event_time, y = estimate, linetype = series, shape = series)
  ) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_vline(xintercept = -0.5, linewidth = 0.4, linetype = "dotted") +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.12, position = ggplot2::position_dodge(width = 0.18)) +
    ggplot2::geom_point(position = ggplot2::position_dodge(width = 0.18), size = 1.8) +
    ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.18)) +
    ggplot2::scale_x_continuous(breaks = expected_dynamic_terms) +
    ggplot2::labs(
      title = "Primary-threshold Quality x FUN-NPR event study",
      subtitle = "Frozen threshold T = 1.571637; full and pre-specified scope-sensitivity samples",
      x = "Months relative to first observed Cursor adoption",
      y = "DiD coefficient on log1p selected issue burden",
      linetype = "Sample / specification",
      shape = "Sample / specification",
      caption = "Event -1 is omitted; repository-clustered standard errors."
    ) +
    ggplot2::theme_minimal(base_size = 10)
  ggplot2::ggsave(paths$primary_dynamic_pdf, p_dynamic, width = 9.5, height = 5.7)
  ggplot2::ggsave(paths$primary_dynamic_png, p_dynamic, width = 9.5, height = 5.7, dpi = 160)
}

if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("D04 hard QC failed: %s", paste(failed_qc$check, collapse = ", "))
}

log_message(
  "INFO",
  "Completed run-x-d04 %s: status=%s; jobs=%d; static=%d; dynamic=%d; nonprimary failures=%d; hard QC failures=%d",
  implementation_version, run_status, model_job_count, nrow(static_all), nrow(dynamic_all),
  nonprimary_failure_job_count, nrow(failed_qc)
)
