#!/usr/bin/env Rscript

# ============================================================
# run-x-h06 v1: Borusyak DiD for frozen ML C_FUN-selected quality burden
# ============================================================
#
# Purpose:
#   Estimate Cursor-adoption effects on unresolved SonarQube issue burden
#   concentrated in historical Python files selected by the frozen run-x-a07
#   C_FUN ML AGC-like file rule and aggregated by run-x-h05.
#
# Primary analysis:
#   sample_spec  = full_sample
#   mapping_spec = all_ml_files
#   outcome      = log1p_selected_issue_total
#   ML file rule = file_ml_cfun_agc_share_space_by_token_weighted > 0.50
#
# Pre-specified robustness analyses:
#   - Exclude A05-v3/A07 C_FUN mapping-warning files.
#   - Exclude the two repositories frozen by the prior scope sensitivity.
#   - Apply both exclusions together.
#
# Estimation design copied from the validated run-x-d06 implementation
# (itself derived from run-x-d04 / run-x-b07):
#   - didimputation::did_imputation.
#   - Repository-clustered standard errors.
#   - Static ATT over all post-adoption observations.
#   - Dynamic post-treatment effects at event 0 through +6.
#   - Package-native placebo terms at event -6 through -2.
#   - Event -1 omitted as the reference period.
#   - Treatment timing reconstructed only from event_index and time_index.
#
# Density:
#   Not estimated. ncloc_py_sonarqube remains a whole-snapshot repository-size
#   covariate in adjusted models, not a selected-file density denominator.
#
# Interpretation:
#   The outcome is unresolved SonarQube issue stock among files classified as
#   C_FUN ML-AGC-like by the frozen detector/file rule. It is not a calibrated defect
#   rate and does not prove that any selected file was AI-generated.
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
  log1p_selected_issue_total = "C_FUN ML-selected total unresolved issue stock",
  log1p_selected_issue_code_smell = "C_FUN ML-selected code-smell stock",
  log1p_selected_issue_bug = "C_FUN ML-selected bug stock",
  log1p_selected_issue_vulnerability = "C_FUN ML-selected vulnerability stock",
  log1p_selected_issue_high_severity = "C_FUN ML-selected BLOCKER+CRITICAL stock",
  log1p_selected_issue_maintainability_impact = "C_FUN ML-selected maintainability-impact stock",
  log1p_selected_issue_reliability_impact = "C_FUN ML-selected reliability-impact stock",
  log1p_selected_issue_security_impact = "C_FUN ML-selected security-impact stock"
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

derive_analysis_role <- function(sample_spec, mapping_spec) {
  if (sample_spec == "full_sample" && mapping_spec == "all_ml_files") return("primary")
  if (sample_spec == "full_sample" && mapping_spec == "exclude_mapping_warning_files") return("mapping_robustness")
  if (sample_spec == "exclude_scope_mismatch_repos" && mapping_spec == "all_ml_files") return("scope_robustness")
  if (sample_spec == "exclude_scope_mismatch_repos" && mapping_spec == "exclude_mapping_warning_files") return("combined_robustness")
  "unexpected"
}

make_static_placeholder <- function(job, model_status, error_message = "", warning_count = 0L, warning_messages = "") {
  data.table::data.table(
    sample_spec = job$sample_spec,
    mapping_spec = job$mapping_spec,
    analysis_role = job$analysis_role,
    primary_analysis = job$primary_analysis,
    ml_primary_metric = job$ml_primary_metric,
    ml_primary_operator = job$ml_primary_operator,
    ml_primary_threshold = job$ml_primary_threshold,
    model_spec = job$model_spec,
    model_spec_label = job$model_spec_label,
    first_stage_formula = job$first_stage_formula,
    outcome = job$outcome,
    outcome_label = job$outcome_label,
    outcome_role = job$outcome_role,
    term = "treat",
    term_type = "static_att",
    estimate = NA_real_, std.error = NA_real_, conf.low = NA_real_, conf.high = NA_real_, p_value = NA_real_,
    exp_coefficient_change_pct = NA_real_, exp_ci_low_pct = NA_real_, exp_ci_high_pct = NA_real_,
    model_status = model_status,
    error_message = error_message,
    warning_count = as.integer(warning_count),
    warning_messages = warning_messages
  )
}

make_dynamic_template <- function(job, expected_terms, model_status, error_message = "", warning_count = 0L, warning_messages = "") {
  data.table::data.table(
    sample_spec = job$sample_spec,
    mapping_spec = job$mapping_spec,
    analysis_role = job$analysis_role,
    primary_analysis = job$primary_analysis,
    ml_primary_metric = job$ml_primary_metric,
    ml_primary_operator = job$ml_primary_operator,
    ml_primary_threshold = job$ml_primary_threshold,
    model_spec = job$model_spec,
    model_spec_label = job$model_spec_label,
    first_stage_formula = job$first_stage_formula,
    outcome = job$outcome,
    outcome_label = job$outcome_label,
    outcome_role = job$outcome_role,
    event_time = as.integer(expected_terms),
    term = as.character(expected_terms),
    term_type = ifelse(expected_terms < 0L, "placebo_pretrend", "post_treatment"),
    estimate = NA_real_, std.error = NA_real_, conf.low = NA_real_, conf.high = NA_real_, p_value = NA_real_,
    exp_coefficient_change_pct = NA_real_, exp_ci_low_pct = NA_real_, exp_ci_high_pct = NA_real_,
    ci_includes_zero = NA,
    term_present = FALSE,
    model_status = model_status,
    error_message = error_message,
    warning_count = as.integer(warning_count),
    warning_messages = warning_messages
  )
}

compute_analysis_support <- function(data, post_values, sparse_min_dynamic_positive_repos, sparse_min_within_variation_repos) {
  primary_raw <- "selected_issue_total"
  primary_log <- "log1p_selected_issue_total"
  post <- data[absorbing_treated_recomputed == 1L]
  dynamic <- data[
    absorbing_treated_recomputed == 1L &
      event_time_recomputed >= min(post_values) & event_time_recomputed <= max(post_values)
  ]
  within <- data[, .(distinct_outcome_values = data.table::uniqueN(get(primary_log))), by = .(repo_id, treatment_group)]
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
  sparse_reasons <- character()
  if (min_dynamic_positive_repositories < sparse_min_dynamic_positive_repos) {
    sparse_reasons <- c(sparse_reasons, "low_dynamic_positive_repo_support")
  }
  if (repositories_with_within_variation < sparse_min_within_variation_repos) {
    sparse_reasons <- c(sparse_reasons, "low_within_repo_outcome_variation")
  }
  data.table::data.table(
    repo_month_rows = nrow(data),
    repositories = data.table::uniqueN(data$repo_id),
    treatment_repositories = data.table::uniqueN(data[treatment_group == 1L, repo_id]),
    control_repositories = data.table::uniqueN(data[treatment_group == 0L, repo_id]),
    selected_file_rows = sum(data$selected_file_count),
    selected_issue_total = sum(data$selected_issue_total),
    zero_outcome_share = mean(data$selected_issue_total == 0),
    post_zero_outcome_share = if (nrow(post) > 0L) mean(post$selected_issue_total == 0) else NA_real_,
    post_rows_with_positive_issue_burden = nrow(post[get(primary_raw) > 0]),
    post_repositories_with_positive_issue_burden = data.table::uniqueN(post[get(primary_raw) > 0, repo_id]),
    dynamic_rows_with_positive_issue_burden = nrow(dynamic[get(primary_raw) > 0]),
    dynamic_repositories_with_positive_issue_burden = data.table::uniqueN(dynamic[get(primary_raw) > 0, repo_id]),
    repositories_with_within_outcome_variation = repositories_with_within_variation,
    treatment_repositories_with_within_outcome_variation = data.table::uniqueN(within_vary[treatment_group == 1L, repo_id]),
    control_repositories_with_within_outcome_variation = data.table::uniqueN(within_vary[treatment_group == 0L, repo_id]),
    min_dynamic_positive_repositories = min_dynamic_positive_repositories,
    sparse_support_flag = as.integer(length(sparse_reasons) > 0L),
    sparse_support_reason = paste(sparse_reasons, collapse = "|")
  )
}

compute_event_support <- function(data, event_values) {
  rows <- list()
  for (event_value in event_values) {
    part <- data[treatment_group == 1L & event_time_recomputed == event_value]
    rows[[length(rows) + 1L]] <- data.table::data.table(
      event_time = as.integer(event_value),
      repository_month_rows = nrow(part),
      repositories = data.table::uniqueN(part$repo_id),
      selected_file_rows = sum(part$selected_file_count),
      selected_issue_total = sum(part$selected_issue_total),
      repositories_with_positive_issue_burden = data.table::uniqueN(part[selected_issue_total > 0, repo_id])
    )
  }
  data.table::rbindlist(rows)
}

run_self_test <- function() {
  stopifnot(identical(derive_analysis_role("full_sample", "all_ml_files"), "primary"))
  stopifnot(identical(derive_analysis_role("full_sample", "exclude_mapping_warning_files"), "mapping_robustness"))
  stopifnot(identical(derive_analysis_role("exclude_scope_mismatch_repos", "all_ml_files"), "scope_robustness"))
  stopifnot(identical(derive_analysis_role("exclude_scope_mismatch_repos", "exclude_mapping_warning_files"), "combined_robustness"))
  stopifnot(identical(as.integer(seq.int(-6L, -2L)), c(-6L, -5L, -4L, -3L, -2L)))
  stopifnot(length(c(seq.int(-6L, -2L), seq.int(0L, 6L))) == 12L)
  cat("did_borusyak_ml_quality self-test: PASS\n")
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
if (isTRUE(args$self_test)) {
  run_self_test()
  quit(save = "no", status = 0L)
}

input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
h05_summary_file <- normalizePath(require_arg(args, "h05_summary_file"), mustWork = TRUE)
h05_sample_summary_file <- normalizePath(require_arg(args, "h05_sample_summary_file"), mustWork = TRUE)
h05_global_audit_file <- normalizePath(require_arg(args, "h05_global_audit_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)

plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
primary_threshold <- as_numeric_arg(args, "primary_threshold", 0.50)
expected_sample_specs <- as_integer_arg(args, "expected_sample_specs", 2L)
expected_mapping_specs <- as_integer_arg(args, "expected_mapping_specs", 2L)
expected_analysis_specs <- as_integer_arg(args, "expected_analysis_specs", 4L)
expected_long_rows <- as_integer_arg(args, "expected_long_rows", 7738L)
sparse_min_dynamic_positive_repos <- as_integer_arg(args, "sparse_min_dynamic_positive_repos", 10L)
sparse_min_within_variation_repos <- as_integer_arg(args, "sparse_min_within_variation_repos", 20L)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
strict_primary_warnings <- as_logical_arg(args, "strict_primary_warnings", TRUE)

if (plot_min_event > -2L) abortf("plot_min_event must include pre-treatment periods.")
if (plot_max_event < 0L) abortf("plot_max_event must be non-negative.")
if (pretrend_min > pretrend_max || pretrend_max >= -1L) abortf("Pretrend range must end at or before -2.")
if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")

required_packages <- c("data.table", "didimputation", "fixest", "ggplot2")
check_packages(required_packages)

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
plot_dir <- file.path(output_dir, "plots")
dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  static = file.path(output_dir, "quality_ml_cfun_static_effects.csv"),
  dynamic = file.path(output_dir, "quality_ml_cfun_dynamic_effects.csv"),
  pretrend_checks = file.path(output_dir, "quality_ml_cfun_pretrend_checks.csv"),
  pretrend_summary = file.path(output_dir, "quality_ml_cfun_pretrend_summary.csv"),
  diagnostics = file.path(output_dir, "quality_ml_cfun_model_diagnostics.csv"),
  failures = file.path(output_dir, "quality_ml_cfun_model_failures.csv"),
  analysis_support = file.path(output_dir, "quality_ml_cfun_analysis_support.csv"),
  event_support = file.path(output_dir, "quality_ml_cfun_event_support.csv"),
  support_policy = file.path(output_dir, "quality_ml_cfun_support_policy.csv"),
  primary_static = file.path(output_dir, "quality_ml_cfun_primary_static.csv"),
  primary_total_static = file.path(output_dir, "quality_ml_cfun_primary_total_static.csv"),
  primary_total_dynamic = file.path(output_dir, "quality_ml_cfun_primary_total_dynamic.csv"),
  total_static_by_analysis = file.path(output_dir, "quality_ml_cfun_total_static_by_analysis.csv"),
  total_dynamic_by_analysis = file.path(output_dir, "quality_ml_cfun_total_dynamic_by_analysis.csv"),
  qc = file.path(output_dir, "quality_ml_cfun_qc.csv"),
  summary = file.path(output_dir, "quality_ml_cfun_summary.csv"),
  metadata = file.path(output_dir, "quality_ml_cfun_run_metadata.csv"),
  static_plot_pdf = file.path(plot_dir, "quality_ml_cfun_total_static_by_analysis.pdf"),
  static_plot_png = file.path(plot_dir, "quality_ml_cfun_total_static_by_analysis.png"),
  primary_dynamic_pdf = file.path(plot_dir, "quality_ml_cfun_primary_total_dynamic.pdf"),
  primary_dynamic_png = file.path(plot_dir, "quality_ml_cfun_primary_total_dynamic.png")
)

run_started <- Sys.time()
log_message("INFO", "Reading H05 panel: %s", input_file)
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
h05_summary <- data.table::fread(h05_summary_file, na.strings = c("", "NA", "NaN"))
h05_sample_summary <- data.table::fread(h05_sample_summary_file, na.strings = c("", "NA", "NaN"))
h05_global_audit <- data.table::fread(h05_global_audit_file, na.strings = c("", "NA", "NaN"))

validate_columns(h05_summary, c("metric", "value"))
validate_columns(h05_sample_summary, c(
  "sample_spec", "mapping_spec", "repo_month_rows", "repositories",
  "treatment_repositories", "control_repositories", "repo_months_with_selected_files",
  "selected_file_rows", "selected_issue_total"
))
validate_columns(h05_global_audit, c(
  "sample_spec", "mapping_spec", "repo_month_rows", "repositories", "eligible_file_rows",
  "selected_file_rows", "selected_unique_snapshot_files", "selected_issue_total"
))

if (lookup_metric(h05_summary, "status") != "PASS") abortf("H05 summary status is not PASS.")
if (lookup_metric(h05_summary, "script_version") != "run-x-h05-v1") abortf("Unexpected H05 script_version; expected run-x-h05-v1.")
strict_count_check(as.integer(lookup_metric(h05_summary, "sample_specs")), expected_sample_specs, "H05 sample specs", strict_expected_counts)
strict_count_check(as.integer(lookup_metric(h05_summary, "mapping_specs")), expected_mapping_specs, "H05 mapping specs", strict_expected_counts)
strict_count_check(as.integer(lookup_metric(h05_summary, "b06_repo_month_rows")), 1954L, "H05 B06 repo-month rows", strict_expected_counts)
if (as.integer(lookup_metric(h05_summary, "density_computed")) != 0L) abortf("H05 density_computed must be zero for H06 burden analysis.")
if (abs(as.numeric(lookup_metric(h05_summary, "primary_ml_threshold")) - primary_threshold) > 1e-12) abortf("H05 primary ML threshold does not match H06.")
if (lookup_metric(h05_summary, "primary_ml_operator") != ">") abortf("H05 primary ML operator must be strict >.")
if (lookup_metric(h05_summary, "primary_ml_metric") != "file_ml_cfun_agc_share_space_by_token_weighted") abortf("Unexpected H05 primary ML metric.")

model_specs <- make_model_specs()
outcomes <- names(outcome_labels)
required_columns <- unique(c(
  "sample_spec", "mapping_spec", "primary_analysis", "ml_primary_metric", "ml_primary_operator", "ml_primary_threshold",
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group", "time", "time_index", "event", "event_index",
  "time_to_event", "is_treatment", "post_event", "cursor", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars",
  "log_issues", "event_time_normalized", "absorbing_treated", "eligible_ml_file_count", "selected_file_count",
  "mapping_warning_selected_file_count", "selected_issue_total", "selected_issue_code_smell", "selected_issue_bug",
  "selected_issue_vulnerability", "selected_issue_high_severity", "selected_issue_maintainability_impact",
  "selected_issue_reliability_impact", "selected_issue_security_impact", outcomes
))
validate_columns(panel, required_columns)

numeric_columns <- unique(c(
  "primary_analysis", "ml_primary_threshold", "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "is_treatment", "post_event", "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  "event_time_normalized", "absorbing_treated", "eligible_ml_file_count", "selected_file_count",
  "mapping_warning_selected_file_count", unname(raw_outcome_map), outcomes
))
for (column in numeric_columns) panel[, (column) := suppressWarnings(as.numeric(get(column)))]
panel[, repo_id := as.integer(repo_id)]
panel[, time_index := as.integer(time_index)]
panel[, event_index := as.integer(event_index)]
panel[, treatment_group := as.integer(treatment_group)]
panel[, primary_analysis := as.integer(primary_analysis)]

input_rows <- nrow(panel)
strict_count_check(input_rows, expected_long_rows, "H06 input rows", strict_expected_counts)

contract_mismatch_rows <- panel[
  ml_primary_operator != ">" |
    ml_primary_metric != "file_ml_cfun_agc_share_space_by_token_weighted" |
    abs(ml_primary_threshold - primary_threshold) > 1e-12
]
if (nrow(contract_mismatch_rows) > 0L) abortf("Found %d H05 ML-contract mismatch rows.", nrow(contract_mismatch_rows))

sample_specs <- sort(unique(panel$sample_spec))
mapping_specs <- sort(unique(panel$mapping_spec))
expected_sample_names <- sort(c("full_sample", "exclude_scope_mismatch_repos"))
expected_mapping_names <- sort(c("all_ml_files", "exclude_mapping_warning_files"))
if (!identical(sample_specs, expected_sample_names)) abortf("Unexpected sample specifications: %s", paste(sample_specs, collapse = ", "))
if (!identical(mapping_specs, expected_mapping_names)) abortf("Unexpected mapping specifications: %s", paste(mapping_specs, collapse = ", "))
strict_count_check(length(sample_specs), expected_sample_specs, "sample specifications", strict_expected_counts)
strict_count_check(length(mapping_specs), expected_mapping_specs, "mapping specifications", strict_expected_counts)

analysis_catalog <- unique(panel[, .(sample_spec, mapping_spec, primary_analysis, ml_primary_metric, ml_primary_operator, ml_primary_threshold)])
analysis_catalog[, analysis_role := mapply(derive_analysis_role, sample_spec, mapping_spec)]
if (any(analysis_catalog$analysis_role == "unexpected")) abortf("Unexpected sample/mapping combination found.")
strict_count_check(nrow(analysis_catalog), expected_analysis_specs, "analysis specifications", strict_expected_counts)
if (sum(analysis_catalog$analysis_role == "primary") != 1L) abortf("Expected exactly one primary analysis configuration.")
if (sum(analysis_catalog$primary_analysis == 1L) != 1L) abortf("H05 primary_analysis must identify exactly one configuration.")
primary_catalog <- analysis_catalog[analysis_role == "primary"]
if (primary_catalog$primary_analysis[[1L]] != 1L) abortf("H05 primary_analysis flag does not match the frozen primary configuration.")

analysis_counts <- panel[, .N, by = .(sample_spec, mapping_spec)]
if (analysis_counts[sample_spec == "full_sample", any(N != 1954L)]) abortf("Both full-sample mapping specifications must have 1,954 rows.")
if (analysis_counts[sample_spec == "exclude_scope_mismatch_repos", any(N != 1915L)]) abortf("Both scope-sensitivity mapping specifications must have 1,915 rows.")

duplicate_keys <- panel[, .N, by = .(sample_spec, mapping_spec, repo_id, time_index)][N > 1L]
if (nrow(duplicate_keys) > 0L) abortf("Found %d duplicate sample-mapping-repo-time keys.", nrow(duplicate_keys))

panel[, event_time_recomputed := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
panel[, absorbing_treated_recomputed := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
timing_mismatch_rows <- panel[
  absorbing_treated != absorbing_treated_recomputed |
    (treatment_group == 1L & event_time_normalized != event_time_recomputed)
]
if (nrow(timing_mismatch_rows) > 0L) abortf("Found %d H05 timing-reconstruction mismatches.", nrow(timing_mismatch_rows))
if (nrow(panel[treatment_group == 0L & event_index != 0L]) > 0L) abortf("Found control rows with nonzero event_index.")
if (nrow(panel[treatment_group == 1L & event_index <= 0L]) > 0L) abortf("Found treatment rows with nonpositive event_index.")

all_model_fields <- unique(c(outcomes, unlist(lapply(model_specs, function(x) x$model_fields), use.names = FALSE)))
missing_model_rows <- panel[!stats::complete.cases(panel[, ..all_model_fields])]
if (nrow(missing_model_rows) > 0L) abortf("Found %d rows with missing H06 model fields.", nrow(missing_model_rows))
nonfinite_model_rows <- panel[!apply(as.data.frame(panel[, ..all_model_fields]), 1L, function(row) all(is.finite(row)))]
if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d rows with non-finite H06 model fields.", nrow(nonfinite_model_rows))

# Reconcile the H05 panel to its frozen global audit before estimation.
input_global <- panel[, .(
  repo_month_rows = .N,
  repositories = data.table::uniqueN(repo_id),
  eligible_file_rows = sum(eligible_ml_file_count),
  selected_file_rows = sum(selected_file_count),
  selected_issue_total = sum(selected_issue_total)
), by = .(sample_spec, mapping_spec)]
audit_compare <- merge(
  input_global,
  h05_global_audit[, .(
    sample_spec, mapping_spec,
    audit_repo_month_rows = repo_month_rows,
    audit_repositories = repositories,
    audit_eligible_file_rows = eligible_file_rows,
    audit_selected_file_rows = selected_file_rows,
    audit_selected_issue_total = selected_issue_total
  )],
  by = c("sample_spec", "mapping_spec"), all = TRUE
)
audit_compare[, mismatch :=
  is.na(repo_month_rows) | is.na(audit_repo_month_rows) |
  repo_month_rows != audit_repo_month_rows |
  repositories != audit_repositories |
  eligible_file_rows != audit_eligible_file_rows |
  selected_file_rows != audit_selected_file_rows |
  selected_issue_total != audit_selected_issue_total
]
if (any(audit_compare$mismatch)) abortf("H06 input does not reconcile to H05 global audit for %d configurations.", sum(audit_compare$mismatch))

# Reconcile the H05 sample summary independently.
sample_compare <- merge(
  panel[, .(
    repo_month_rows = .N,
    repositories = data.table::uniqueN(repo_id),
    treatment_repositories = data.table::uniqueN(repo_id[treatment_group == 1L]),
    control_repositories = data.table::uniqueN(repo_id[treatment_group == 0L]),
    repo_months_with_selected_files = sum(selected_file_count > 0),
    selected_file_rows = sum(selected_file_count),
    selected_issue_total = sum(selected_issue_total)
  ), by = .(sample_spec, mapping_spec)],
  h05_sample_summary,
  by = c("sample_spec", "mapping_spec"), suffixes = c("_input", "_audit"), all = TRUE
)
summary_fields <- c("repo_month_rows", "repositories", "treatment_repositories", "control_repositories", "repo_months_with_selected_files", "selected_file_rows", "selected_issue_total")
mismatch_matrix <- do.call(cbind, lapply(summary_fields, function(field) {
  left <- sample_compare[[paste0(field, "_input")]]
  right <- sample_compare[[paste0(field, "_audit")]]
  is.na(left) | is.na(right) | left != right
}))
sample_compare[, mismatch_count := rowSums(mismatch_matrix)]
if (any(sample_compare$mismatch_count > 0L)) abortf("H05 sample-summary reconciliation failed.")

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
expected_dynamic_terms <- c(pretrend_values, post_values)
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)
event_support_values <- dynamic_horizon_values

support_policy <- data.table::data.table(
  policy_id = "prespecified_ml_support_flag_v1",
  apply_to_model_omission = 0L,
  prespecified_before_h06_results = 1L,
  min_dynamic_positive_repositories_required = sparse_min_dynamic_positive_repos,
  min_repositories_with_within_outcome_variation_required = sparse_min_within_variation_repos,
  rule = "Flag low support if the minimum positive-issue repository count across event 0:+6 is below the first threshold OR repositories with within-panel variation in log1p selected total issue stock are below the second threshold. Never omit a frozen H05 analysis configuration because of this flag."
)
write_csv(support_policy, paths$support_policy)

analysis_support_rows <- list()
event_support_rows <- list()
for (i in seq_len(nrow(analysis_catalog))) {
  config <- analysis_catalog[i]
  part <- panel[sample_spec == config$sample_spec & mapping_spec == config$mapping_spec]
  support <- compute_analysis_support(part, post_values, sparse_min_dynamic_positive_repos, sparse_min_within_variation_repos)
  support[, `:=`(
    sample_spec = config$sample_spec,
    mapping_spec = config$mapping_spec,
    analysis_role = config$analysis_role,
    primary_analysis = config$primary_analysis
  )]
  analysis_support_rows[[length(analysis_support_rows) + 1L]] <- support

  event_support <- compute_event_support(part, event_support_values)
  event_support[, `:=`(
    sample_spec = config$sample_spec,
    mapping_spec = config$mapping_spec,
    analysis_role = config$analysis_role,
    primary_analysis = config$primary_analysis,
    period_type = data.table::fcase(
      event_time %in% pretrend_values, "placebo_pretrend",
      event_time == -1L, "reference",
      event_time %in% post_values, "post_treatment",
      default = "other"
    )
  )]
  event_support_rows[[length(event_support_rows) + 1L]] <- event_support
}
analysis_support <- data.table::rbindlist(analysis_support_rows, fill = TRUE)
event_support <- data.table::rbindlist(event_support_rows, fill = TRUE)
data.table::setorder(analysis_support, primary_analysis, sample_spec, mapping_spec)
data.table::setorder(event_support, sample_spec, mapping_spec, event_time)
write_csv(analysis_support, paths$analysis_support)
write_csv(event_support, paths$event_support)

# Modeling loop.
static_rows <- list()
dynamic_rows <- list()
diagnostic_rows <- list()
job_failure_rows <- list()

add_diagnostic <- function(job, stage, status, elapsed, warnings = character(), error_message = "", extra = "") {
  diagnostic_rows[[length(diagnostic_rows) + 1L]] <<- data.table::data.table(
    sample_spec = job$sample_spec, mapping_spec = job$mapping_spec, analysis_role = job$analysis_role,
    primary_analysis = job$primary_analysis, model_spec = job$model_spec, model_spec_label = job$model_spec_label,
    outcome = job$outcome, outcome_label = job$outcome_label, outcome_role = job$outcome_role,
    stage = stage, status = status, runtime_seconds = as.numeric(elapsed), warning_count = length(warnings),
    warning_messages = paste(warnings, collapse = " | "), error_message = error_message, extra = extra
  )
}

record_job_failure <- function(job, stage, status, error_message) {
  job_failure_rows[[length(job_failure_rows) + 1L]] <<- data.table::data.table(
    sample_spec = job$sample_spec, mapping_spec = job$mapping_spec, analysis_role = job$analysis_role,
    primary_analysis = job$primary_analysis, model_spec = job$model_spec, outcome = job$outcome,
    stage = stage, status = status, error_message = error_message
  )
}

for (i in seq_len(nrow(analysis_catalog))) {
  config <- analysis_catalog[i]
  part <- panel[sample_spec == config$sample_spec & mapping_spec == config$mapping_spec]
  log_message("INFO", "Starting sample=%s mapping=%s role=%s", config$sample_spec, config$mapping_spec, config$analysis_role)

  for (spec_name in names(model_specs)) {
    spec <- model_specs[[spec_name]]
    for (outcome in outcomes) {
      job <- list(
        sample_spec = config$sample_spec,
        mapping_spec = config$mapping_spec,
        analysis_role = config$analysis_role,
        primary_analysis = as.integer(config$primary_analysis),
        ml_primary_metric = config$ml_primary_metric,
        ml_primary_operator = config$ml_primary_operator,
        ml_primary_threshold = as.numeric(config$ml_primary_threshold),
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
        static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "first_stage_failed", error_text)
        dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(job, expected_dynamic_terms, "first_stage_failed", error_text)
        next
      }
      prediction_na_treated <- sum(is.na(first_stage_capture$predictions[part$absorbing_treated_recomputed == 1L]))
      prediction_na_all <- sum(is.na(first_stage_capture$predictions))
      if (prediction_na_treated > 0L) {
        error_text <- sprintf("First-stage predictions missing for %d treated rows.", prediction_na_treated)
        add_diagnostic(job, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text, sprintf("prediction_na_all=%d", prediction_na_all))
        record_job_failure(job, "first_stage", "failed", error_text)
        static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "first_stage_failed", error_text)
        dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(job, expected_dynamic_terms, "first_stage_failed", error_text)
        next
      }
      add_diagnostic(job, "first_stage", "success", first_stage_capture$elapsed, first_stage_capture$warnings, "", sprintf("nobs=%d; prediction_na_all=%d; prediction_na_treated=%d", stats::nobs(first_stage_capture$value), prediction_na_all, prediction_na_treated))

      static_capture <- run_did_model(part, outcome, spec$first_stage, horizon = NULL, pretrends = NULL)
      if (static_capture$error) {
        error_text <- static_capture$value$message
        add_diagnostic(job, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
        record_job_failure(job, "static", "failed", error_text)
        static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "failed", error_text, length(static_capture$warnings), paste(static_capture$warnings, collapse = " | "))
      } else {
        static_table <- extract_effect_table(static_capture$value, confidence_level)[term == "treat"]
        if (nrow(static_table) != 1L) {
          error_text <- sprintf("Expected one static treat term, observed %d.", nrow(static_table))
          add_diagnostic(job, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
          record_job_failure(job, "static", "failed", error_text)
          static_rows[[length(static_rows) + 1L]] <- make_static_placeholder(job, "failed", error_text)
        } else {
          static_table[, `:=`(
            sample_spec = job$sample_spec, mapping_spec = job$mapping_spec, analysis_role = job$analysis_role,
            primary_analysis = job$primary_analysis, ml_primary_metric = job$ml_primary_metric,
            ml_primary_operator = job$ml_primary_operator, ml_primary_threshold = job$ml_primary_threshold,
            model_spec = job$model_spec, model_spec_label = job$model_spec_label,
            first_stage_formula = job$first_stage_formula, outcome = job$outcome,
            outcome_label = job$outcome_label, outcome_role = job$outcome_role,
            term_type = "static_att", model_status = "success", error_message = "",
            warning_count = length(static_capture$warnings), warning_messages = paste(static_capture$warnings, collapse = " | ")
          )]
          static_rows[[length(static_rows) + 1L]] <- static_table
          add_diagnostic(job, "static", "success", static_capture$elapsed, static_capture$warnings)
        }
      }

      dynamic_capture <- run_did_model(part, outcome, spec$first_stage, horizon = dynamic_horizon_values, pretrends = pretrend_values)
      if (dynamic_capture$error) {
        error_text <- dynamic_capture$value$message
        add_diagnostic(job, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
        record_job_failure(job, "dynamic", "failed", error_text)
        dynamic_rows[[length(dynamic_rows) + 1L]] <- make_dynamic_template(job, expected_dynamic_terms, "failed", error_text, length(dynamic_capture$warnings), paste(dynamic_capture$warnings, collapse = " | "))
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
          template <- make_dynamic_template(job, expected_dynamic_terms, "success", "", length(dynamic_capture$warnings), paste(dynamic_capture$warnings, collapse = " | "))
          merge_values <- extracted[, .(
            event_time, estimate_new = estimate, std_error_new = std.error, conf_low_new = conf.low,
            conf_high_new = conf.high, p_value_new = p_value, exp_change_new = exp_coefficient_change_pct,
            exp_low_new = exp_ci_low_pct, exp_high_new = exp_ci_high_pct
          )]
          template <- merge(template, merge_values, by = "event_time", all.x = TRUE, sort = FALSE)
          template[, term_present := !is.na(estimate_new)]
          template[term_present == TRUE, `:=`(
            estimate = estimate_new, std.error = std_error_new, conf.low = conf_low_new, conf.high = conf_high_new,
            p_value = p_value_new, exp_coefficient_change_pct = exp_change_new, exp_ci_low_pct = exp_low_new,
            exp_ci_high_pct = exp_high_new, ci_includes_zero = conf_low_new <= 0 & conf_high_new >= 0
          )]
          template[, c("estimate_new", "std_error_new", "conf_low_new", "conf_high_new", "p_value_new", "exp_change_new", "exp_low_new", "exp_high_new") := NULL]
          missing_terms <- template[term_present == FALSE, event_time]
          if (length(missing_terms) > 0L) {
            template[, model_status := "partial"]
            template[, error_message := sprintf("Missing dynamic terms: %s", paste(missing_terms, collapse = ","))]
            record_job_failure(job, "dynamic", "partial", unique(template$error_message))
            add_diagnostic(job, "dynamic", "partial", dynamic_capture$elapsed, dynamic_capture$warnings, unique(template$error_message), sprintf("observed_terms=%d; expected_terms=%d", sum(template$term_present), length(expected_dynamic_terms)))
          } else {
            add_diagnostic(job, "dynamic", "success", dynamic_capture$elapsed, dynamic_capture$warnings, "", sprintf("terms=%d", length(expected_dynamic_terms)))
          }
          dynamic_rows[[length(dynamic_rows) + 1L]] <- template
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
    sample_spec = character(), mapping_spec = character(), analysis_role = character(), primary_analysis = integer(),
    model_spec = character(), outcome = character(), stage = character(), status = character(), error_message = character()
  )
}

data.table::setorder(static_all, primary_analysis, sample_spec, mapping_spec, model_spec, outcome)
data.table::setorder(dynamic_all, primary_analysis, sample_spec, mapping_spec, model_spec, outcome, event_time)
data.table::setorder(diagnostics_all, primary_analysis, sample_spec, mapping_spec, model_spec, outcome, stage)

# Attach support columns for immediate interpretation.
support_attach <- analysis_support[, .(
  sample_spec, mapping_spec, sparse_support_flag, sparse_support_reason,
  post_rows_with_positive_issue_burden, post_repositories_with_positive_issue_burden,
  dynamic_rows_with_positive_issue_burden, dynamic_repositories_with_positive_issue_burden,
  repositories_with_within_outcome_variation, min_dynamic_positive_repositories,
  zero_outcome_share, post_zero_outcome_share
)]
static_all <- merge(static_all, support_attach, by = c("sample_spec", "mapping_spec"), all.x = TRUE, sort = FALSE)
dynamic_all <- merge(dynamic_all, support_attach, by = c("sample_spec", "mapping_spec"), all.x = TRUE, sort = FALSE)

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
), by = .(sample_spec, mapping_spec, analysis_role, primary_analysis, model_spec, model_spec_label, outcome, outcome_label, outcome_role)]
write_csv(pretrend_all, paths$pretrend_checks)
write_csv(pretrend_summary, paths$pretrend_summary)

primary_static <- static_all[primary_analysis == 1L]
primary_total_static <- primary_static[outcome == "log1p_selected_issue_total"]
primary_total_dynamic <- dynamic_all[primary_analysis == 1L & outcome == "log1p_selected_issue_total"]
total_static_by_analysis <- static_all[outcome == "log1p_selected_issue_total"]
total_dynamic_by_analysis <- dynamic_all[outcome == "log1p_selected_issue_total"]
write_csv(primary_static, paths$primary_static)
write_csv(primary_total_static, paths$primary_total_static)
write_csv(primary_total_dynamic, paths$primary_total_dynamic)
write_csv(total_static_by_analysis, paths$total_static_by_analysis)
write_csv(total_dynamic_by_analysis, paths$total_dynamic_by_analysis)

model_job_count <- expected_analysis_specs * length(model_specs) * length(outcomes)
expected_static_rows <- model_job_count
expected_dynamic_rows <- model_job_count * length(expected_dynamic_terms)
expected_pretrend_rows <- model_job_count * length(pretrend_values)
expected_primary_static_rows <- length(model_specs) * length(outcomes)
expected_primary_total_static_rows <- length(model_specs)
expected_primary_total_dynamic_rows <- length(model_specs) * length(expected_dynamic_terms)
expected_total_static_rows <- expected_analysis_specs * length(model_specs)
expected_total_dynamic_rows <- expected_total_static_rows * length(expected_dynamic_terms)
expected_support_rows <- expected_analysis_specs
expected_event_support_rows <- expected_analysis_specs * length(event_support_values)

primary_static_failures <- primary_static[model_status != "success"]
primary_dynamic_status <- dynamic_all[primary_analysis == 1L, .(
  all_terms_present = all(term_present),
  status_values = paste(sort(unique(model_status)), collapse = "|")
), by = .(sample_spec, mapping_spec, model_spec, outcome)]
primary_dynamic_failures <- primary_dynamic_status[all_terms_present == FALSE | status_values != "success"]
primary_warning_jobs <- diagnostics_all[primary_analysis == 1L & warning_count > 0L, .N, by = .(sample_spec, mapping_spec, model_spec, outcome)]
primary_warning_job_count <- nrow(primary_warning_jobs)
robustness_failure_jobs <- unique(failures_all[primary_analysis != 1L, .(sample_spec, mapping_spec, model_spec, outcome)])
robustness_failure_job_count <- nrow(robustness_failure_jobs)

qc <- data.table::data.table(
  check = c(
    "input_long_rows", "sample_spec_count", "mapping_spec_count", "analysis_spec_count",
    "duplicate_sample_mapping_repo_time_keys", "measurement_contract_mismatch_rows", "timing_reconstruction_mismatch_rows",
    "missing_model_rows", "nonfinite_model_rows", "h05_global_audit_mismatch_rows", "h05_sample_summary_mismatch_rows",
    "model_job_count", "static_effect_rows", "dynamic_effect_rows", "pretrend_check_rows", "pretrend_summary_rows",
    "analysis_support_rows", "event_support_rows", "primary_static_rows", "primary_total_static_rows",
    "primary_total_dynamic_rows", "total_static_by_analysis_rows", "total_dynamic_by_analysis_rows",
    "primary_static_failure_rows", "primary_dynamic_failure_jobs", "primary_warning_jobs",
    "primary_analysis_configuration_count", "primary_threshold_exact"
  ),
  observed = c(
    input_rows, length(sample_specs), length(mapping_specs), nrow(analysis_catalog), nrow(duplicate_keys), nrow(contract_mismatch_rows),
    nrow(timing_mismatch_rows), nrow(missing_model_rows), nrow(nonfinite_model_rows), sum(audit_compare$mismatch),
    sum(sample_compare$mismatch_count > 0L), model_job_count, nrow(static_all), nrow(dynamic_all), nrow(pretrend_all),
    nrow(pretrend_summary), nrow(analysis_support), nrow(event_support), nrow(primary_static), nrow(primary_total_static),
    nrow(primary_total_dynamic), nrow(total_static_by_analysis), nrow(total_dynamic_by_analysis), nrow(primary_static_failures),
    nrow(primary_dynamic_failures), primary_warning_job_count, sum(analysis_catalog$primary_analysis == 1L),
    max(abs(analysis_catalog$ml_primary_threshold - primary_threshold))
  ),
  expected = c(
    expected_long_rows, expected_sample_specs, expected_mapping_specs, expected_analysis_specs,
    0L, 0L, 0L, 0L, 0L, 0L, 0L,
    model_job_count, expected_static_rows, expected_dynamic_rows, expected_pretrend_rows, model_job_count,
    expected_support_rows, expected_event_support_rows, expected_primary_static_rows, expected_primary_total_static_rows,
    expected_primary_total_dynamic_rows, expected_total_static_rows, expected_total_dynamic_rows,
    0L, 0L, if (strict_primary_warnings) 0L else -1L, 1L, 0
  )
)
qc[, status := data.table::fifelse(expected < 0, "informational", data.table::fifelse(abs(as.numeric(observed) - as.numeric(expected)) < 1e-12, "pass", "fail"))]
qc[, note := c(
  "Frozen run-x-h05 long panel.",
  "Full sample plus pre-specified two-repository exclusion sensitivity.",
  "All files plus pre-specified mapping-warning exclusion sensitivity.",
  "Exactly four frozen sample x mapping configurations.",
  "Must be zero.",
  "Frozen ML file rule must remain unchanged.",
  "Authoritative treatment timing is reconstructed from time_index and event_index.",
  "All outcomes and adjusted covariates must be complete.",
  "All outcomes and adjusted covariates must be finite.",
  "Selected file/issue counts must reconcile to H05 global audit.",
  "H05 sample/mapping support must reconcile to H05 sample summary.",
  "4 analysis configurations x 2 model specs x 8 outcomes.",
  "One static slot per model job.",
  "Twelve event slots per model job: -6:-2 and 0:+6.",
  "Five placebo slots per model job.",
  "One pretrend summary per model job.",
  "One support row per frozen analysis configuration.",
  "Event support includes -6 through +6, including reference event -1.",
  "Primary configuration x 2 specs x 8 outcomes.",
  "Primary total issue outcome x 2 specs.",
  "Primary total issue outcome x 2 specs x 12 event terms.",
  "Total issue outcome across all four frozen configurations and two specs.",
  "Total issue dynamic rows across all four configurations and two specs.",
  "Primary static models must all succeed.",
  "Primary dynamic models must contain all expected terms.",
  "Warnings on primary models are a hard gate when strict_primary_warnings=1.",
  "Exactly one frozen primary configuration: full_sample x all_ml_files.",
  "ML threshold must equal frozen 0.50 exactly within numerical tolerance."
)]
write_csv(qc, paths$qc)

failed_qc <- qc[status == "fail"]
run_status <- if (robustness_failure_job_count > 0L) "PASS_WITH_ROBUSTNESS_MODEL_FAILURES" else "PASS"
summary <- data.table::rbindlist(list(
  make_summary_row("run", "script_version", "run-x-h06-v1"),
  make_summary_row("run", "status", run_status),
  make_summary_row("design", "sample_specs", expected_sample_specs),
  make_summary_row("design", "mapping_specs", expected_mapping_specs),
  make_summary_row("design", "analysis_specs", expected_analysis_specs),
  make_summary_row("design", "model_specs", paste(names(model_specs), collapse = "|")),
  make_summary_row("design", "outcomes", length(outcomes)),
  make_summary_row("design", "model_jobs", model_job_count),
  make_summary_row("design", "primary_sample_spec", "full_sample"),
  make_summary_row("design", "primary_mapping_spec", "all_ml_files"),
  make_summary_row("design", "primary_threshold", primary_threshold),
  make_summary_row("design", "dynamic_window", "0:+6"),
  make_summary_row("design", "placebo_window", "-6:-2"),
  make_summary_row("design", "reference_event", -1L),
  make_summary_row("support", "low_support_analysis_specs", sum(analysis_support$sparse_support_flag == 1L)),
  make_summary_row("models", "robustness_failure_jobs", robustness_failure_job_count),
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
  make_summary_row("run", "h05_summary_sha256", sha256_file(h05_summary_file)),
  make_summary_row("run", "h05_sample_summary_sha256", sha256_file(h05_sample_summary_file)),
  make_summary_row("run", "h05_global_audit_sha256", sha256_file(h05_global_audit_file)),
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
  make_summary_row("definition", "primary_analysis", "full_sample x all_ml_files"),
  make_summary_row("definition", "ml_file_rule", "file_ml_cfun_agc_share_space_by_token_weighted > 0.50"),
  make_summary_row("definition", "quality_semantics", "unresolved SonarQube issue burden among historical Python files selected by the frozen C_FUN ML AGC-like file rule"),
  make_summary_row("definition", "ncloc_caution", "ncloc_py_sonarqube is a whole-snapshot repository-size covariate in adjusted models, not a selected-file density denominator."),
  make_summary_row("definition", "percent_transform_caution", "exp(beta)-1 is reported on a log1p outcome and is not an exact arithmetic percentage change in raw issue counts."),
  make_summary_row("definition", "support_policy", support_policy$rule[[1L]]),
  make_summary_row("qc", "hard_qc_failures", nrow(failed_qc))
), fill = TRUE)
write_csv(metadata, paths$metadata)

# Descriptive presentation plots only; no analysis configuration is selected from them.
plot_static_data <- total_static_by_analysis[model_status == "success"]
if (nrow(plot_static_data) > 0L) {
  plot_static_data[, analysis_label := paste(sample_spec, mapping_spec, sep = " / ")]
  p_static <- ggplot2::ggplot(
    plot_static_data,
    ggplot2::aes(x = analysis_label, y = estimate, shape = model_spec)
  ) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.15, position = ggplot2::position_dodge(width = 0.35)) +
    ggplot2::geom_point(position = ggplot2::position_dodge(width = 0.35), size = 2) +
    ggplot2::labs(
      title = "ML C_FUN-selected quality burden DiD across frozen robustness configurations",
      subtitle = "Total unresolved SonarQube issue stock; primary = full_sample / all_ml_files",
      x = "Frozen analysis configuration",
      y = "Static ATT on log1p selected issue burden",
      shape = "First-stage specification",
      caption = "All configurations were specified before H06 causal estimates."
    ) +
    ggplot2::theme_minimal(base_size = 10) +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 25, hjust = 1))
  ggplot2::ggsave(paths$static_plot_pdf, p_static, width = 9.5, height = 5.7)
  ggplot2::ggsave(paths$static_plot_png, p_static, width = 9.5, height = 5.7, dpi = 160)
}

plot_dynamic_data <- primary_total_dynamic[term_present == TRUE]
if (nrow(plot_dynamic_data) > 0L) {
  p_dynamic <- ggplot2::ggplot(
    plot_dynamic_data,
    ggplot2::aes(x = event_time, y = estimate, linetype = model_spec, shape = model_spec)
  ) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_vline(xintercept = -0.5, linewidth = 0.4, linetype = "dotted") +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.12, position = ggplot2::position_dodge(width = 0.18)) +
    ggplot2::geom_point(position = ggplot2::position_dodge(width = 0.18), size = 1.8) +
    ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.18)) +
    ggplot2::scale_x_continuous(breaks = expected_dynamic_terms) +
    ggplot2::labs(
      title = "Primary ML C_FUN-selected quality event study",
      subtitle = "full_sample / all_ml_files; frozen weighted AGC share > 0.50",
      x = "Months relative to first observed Cursor adoption",
      y = "DiD coefficient on log1p selected issue burden",
      linetype = "First-stage specification",
      shape = "First-stage specification",
      caption = "Event -1 omitted; repository-clustered standard errors."
    ) +
    ggplot2::theme_minimal(base_size = 10)
  ggplot2::ggsave(paths$primary_dynamic_pdf, p_dynamic, width = 9.5, height = 5.7)
  ggplot2::ggsave(paths$primary_dynamic_png, p_dynamic, width = 9.5, height = 5.7, dpi = 160)
}

if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("H06 hard QC failed: %s", paste(failed_qc$check, collapse = ", "))
}

log_message(
  "INFO",
  "Completed run-x-h06 %s: status=%s; jobs=%d; static=%d; dynamic=%d; robustness failures=%d; hard QC failures=%d",
  implementation_version, run_status, model_job_count, nrow(static_all), nrow(dynamic_all),
  robustness_failure_job_count, nrow(failed_qc)
)
