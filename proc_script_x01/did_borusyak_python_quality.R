#!/usr/bin/env Rscript

# ============================================================
# run-x-b07 v1: Borusyak DiD for Python-only SonarQube quality
# ============================================================
#
# Purpose:
#   Estimate Cursor-adoption effects on Python-only SonarQube static-analysis
#   issue stock prepared by run-x-b06. The analysis mirrors the established
#   monthly Python-velocity DiD treatment timing and support while separating
#   three questions:
#
#   1. adjusted_burden
#      Total Python issue stock with Python NCLOC and contemporaneous project
#      covariates in the first stage.
#   2. fe_only_burden
#      The same issue-stock outcomes with repository and calendar-month fixed
#      effects only.
#   3. fe_only_density
#      Python issues per KLOC with repository and calendar-month fixed effects
#      only. This is a size-normalized robustness analysis, not a replacement
#      for the original-style warning-burden outcome.
#
# Treatment definition:
#   - event_time_normalized = time_index - event_index for treatment repos.
#   - absorbing_treated = 1 only when time_index >= event_index.
#   - legacy cursor/is_treatment/post_event columns are audit-only.
#
# Estimation design:
#   - Borusyak et al. did_imputation.
#   - repository-clustered standard errors.
#   - static ATT over all post-adoption observations.
#   - dynamic post-treatment effects event 0 through +6.
#   - package-native placebo terms event -6 through -2.
#   - event -1 omitted as the reference period.
#
# Input:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Outputs:
#   repo_x01/run-x-b07/
#
# This script is self-contained. It reuses the validated statistical logic of
# the prior b03 implementation but does not call any prior experiment script.
# ============================================================

options(stringsAsFactors = FALSE, warn = 1)
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
    if (!startsWith(token, "--")) {
      abortf("Unexpected positional argument: %s", token)
    }
    key <- sub("^--", "", token)
    key <- gsub("-", "_", key, fixed = TRUE)
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
  if (length(missing) > 0L) {
    abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
  }
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
  result[is.na(result) & !is.na(numeric_value)] <- as.integer(numeric_value[is.na(result) & !is.na(numeric_value)] != 0)
  result[is.na(result)] <- 0L
  result
}

make_summary_row <- function(section, metric, value, note = "") {
  data.table::data.table(section = section, metric = metric, value = as.character(value), note = note)
}

strict_count_check <- function(actual, expected, label, strict) {
  if (is.na(expected) || expected < 0L) return(invisible(TRUE))
  if (!identical(as.integer(actual), as.integer(expected))) {
    text <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, actual)
    if (strict) abortf("%s", text) else log_message("WARNING", "%s", text)
  }
  invisible(TRUE)
}

validate_columns <- function(data, required) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("Input is missing required columns: %s", paste(missing, collapse = ", "))
}

extract_effect_table <- function(result, outcome_name, confidence_level, term_type = NULL) {
  table <- data.table::as.data.table(result)
  required <- c("term", "estimate", "std.error", "conf.low", "conf.high")
  validate_columns(table, required)
  table[, outcome := outcome_name]
  alpha <- 1 - confidence_level
  critical_value <- stats::qnorm(1 - alpha / 2)
  table[, conf.low := estimate - critical_value * std.error]
  table[, conf.high := estimate + critical_value * std.error]
  table[, p_value := ifelse(is.finite(std.error) & std.error > 0,
                            2 * stats::pnorm(-abs(estimate / std.error)), NA_real_)]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table[, significant := !is.na(p_value) & p_value < alpha]
  if (!is.null(term_type)) table[, term_type := term_type]
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

# ----------------------------
# Quality-analysis definitions
# ----------------------------

make_model_specs <- function() {
  burden_outcomes <- c(
    "log_issue_total_py_sonarqube",
    "log_issue_code_smell_py_sonarqube",
    "log_issue_bug_py_sonarqube",
    "log_issue_vulnerability_py_sonarqube",
    "log_issue_maintainability_impact_py_sonarqube",
    "log_issue_reliability_impact_py_sonarqube",
    "log_issue_security_impact_py_sonarqube",
    "log_issue_high_severity_py_sonarqube"
  )
  density_outcomes <- c(
    "log_issues_per_kloc_py_sonarqube",
    "log_issue_code_smell_per_kloc_py_sonarqube",
    "log_issue_bug_per_kloc_py_sonarqube",
    "log_issue_vulnerability_per_kloc_py_sonarqube",
    "log_issue_maintainability_impact_per_kloc_py_sonarqube",
    "log_issue_reliability_impact_per_kloc_py_sonarqube",
    "log_issue_security_impact_per_kloc_py_sonarqube",
    "log_issue_high_severity_per_kloc_py_sonarqube"
  )

  list(
    adjusted_burden = list(
      label = "Adjusted burden",
      family = "burden",
      primary = "log_issue_total_py_sonarqube",
      outcomes = burden_outcomes,
      first_stage = ~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index,
      first_stage_text = "~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index",
      model_fields = c("log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues")
    ),
    fe_only_burden = list(
      label = "FE-only burden",
      family = "burden",
      primary = "log_issue_total_py_sonarqube",
      outcomes = burden_outcomes,
      first_stage = ~ 1 | repo_id + time_index,
      first_stage_text = "~ 1 | repo_id + time_index",
      model_fields = character()
    ),
    fe_only_density = list(
      label = "FE-only density",
      family = "density",
      primary = "log_issues_per_kloc_py_sonarqube",
      outcomes = density_outcomes,
      first_stage = ~ 1 | repo_id + time_index,
      first_stage_text = "~ 1 | repo_id + time_index",
      model_fields = character()
    )
  )
}

outcome_labels <- c(
  log_issue_total_py_sonarqube = "Python SonarQube Total Issue Stock",
  log_issue_code_smell_py_sonarqube = "Python SonarQube Code Smell Stock",
  log_issue_bug_py_sonarqube = "Python SonarQube Bug Stock",
  log_issue_vulnerability_py_sonarqube = "Python SonarQube Vulnerability Stock",
  log_issue_maintainability_impact_py_sonarqube = "Python Maintainability-Impact Issue Stock",
  log_issue_reliability_impact_py_sonarqube = "Python Reliability-Impact Issue Stock",
  log_issue_security_impact_py_sonarqube = "Python Security-Impact Issue Stock",
  log_issue_high_severity_py_sonarqube = "Python BLOCKER+CRITICAL Issue Stock",
  log_issues_per_kloc_py_sonarqube = "Python SonarQube Issues per KLOC",
  log_issue_code_smell_per_kloc_py_sonarqube = "Python Code Smells per KLOC",
  log_issue_bug_per_kloc_py_sonarqube = "Python Bugs per KLOC",
  log_issue_vulnerability_per_kloc_py_sonarqube = "Python Vulnerabilities per KLOC",
  log_issue_maintainability_impact_per_kloc_py_sonarqube = "Python Maintainability-Impact Issues per KLOC",
  log_issue_reliability_impact_per_kloc_py_sonarqube = "Python Reliability-Impact Issues per KLOC",
  log_issue_security_impact_per_kloc_py_sonarqube = "Python Security-Impact Issues per KLOC",
  log_issue_high_severity_per_kloc_py_sonarqube = "Python BLOCKER+CRITICAL Issues per KLOC"
)

outcome_roles <- c(
  log_issue_total_py_sonarqube = "primary_burden",
  log_issue_code_smell_py_sonarqube = "type_robustness",
  log_issue_bug_py_sonarqube = "type_robustness",
  log_issue_vulnerability_py_sonarqube = "type_robustness",
  log_issue_maintainability_impact_py_sonarqube = "impact_robustness",
  log_issue_reliability_impact_py_sonarqube = "impact_robustness",
  log_issue_security_impact_py_sonarqube = "impact_robustness",
  log_issue_high_severity_py_sonarqube = "severity_robustness",
  log_issues_per_kloc_py_sonarqube = "primary_density",
  log_issue_code_smell_per_kloc_py_sonarqube = "type_density_robustness",
  log_issue_bug_per_kloc_py_sonarqube = "type_density_robustness",
  log_issue_vulnerability_per_kloc_py_sonarqube = "type_density_robustness",
  log_issue_maintainability_impact_per_kloc_py_sonarqube = "impact_density_robustness",
  log_issue_reliability_impact_per_kloc_py_sonarqube = "impact_density_robustness",
  log_issue_security_impact_per_kloc_py_sonarqube = "impact_density_robustness",
  log_issue_high_severity_per_kloc_py_sonarqube = "severity_density_robustness"
)

make_pretrend_summary <- function(table, confidence_level) {
  alpha <- 1 - confidence_level
  table[, .(
    pretrend_terms = .N,
    periods_excluding_zero = sum(!ci_includes_zero, na.rm = TRUE),
    significant_periods = sum(!is.na(p_value) & p_value < alpha),
    all_cis_include_zero = all(ci_includes_zero),
    minimum_p_value = if (all(is.na(p_value))) NA_real_ else min(p_value, na.rm = TRUE),
    minimum_p_event = if (all(is.na(p_value))) NA_integer_ else event_time[which.min(p_value)][1L]
  ), by = .(model_spec, model_spec_label, outcome_family, outcome, outcome_label, outcome_role)]
}

plot_primary_burden <- function(dynamic_all, output_pdf, output_png) {
  data <- dynamic_all[
    outcome == "log_issue_total_py_sonarqube" &
    model_spec %in% c("adjusted_burden", "fe_only_burden")
  ]
  data[, model_display := factor(model_spec_label, levels = c("Adjusted burden", "FE-only burden"))]
  p <- ggplot2::ggplot(
    data,
    ggplot2::aes(x = event_time, y = estimate, shape = model_display, linetype = model_display)
  ) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_vline(xintercept = -0.5, linewidth = 0.4, linetype = "dotted") +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.15, position = ggplot2::position_dodge(width = 0.2)) +
    ggplot2::geom_point(position = ggplot2::position_dodge(width = 0.2), size = 2) +
    ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.2)) +
    ggplot2::scale_x_continuous(breaks = sort(unique(data$event_time))) +
    ggplot2::labs(
      title = "Python SonarQube issue-stock event study",
      subtitle = "Adjusted burden versus repository/month FE-only burden",
      x = "Months relative to first observed Cursor adoption",
      y = "DiD coefficient on log1p(issue stock)",
      shape = "Specification",
      linetype = "Specification",
      caption = "Event -1 is the omitted reference period; repository-clustered standard errors."
    ) +
    ggplot2::theme_minimal(base_size = 11)
  ggplot2::ggsave(output_pdf, p, width = 9, height = 5.5)
  ggplot2::ggsave(output_png, p, width = 9, height = 5.5, dpi = 160)
}

plot_primary_density <- function(dynamic_all, output_pdf, output_png) {
  data <- dynamic_all[
    outcome == "log_issues_per_kloc_py_sonarqube" & model_spec == "fe_only_density"
  ]
  p <- ggplot2::ggplot(data, ggplot2::aes(x = event_time, y = estimate)) +
    ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
    ggplot2::geom_vline(xintercept = -0.5, linewidth = 0.4, linetype = "dotted") +
    ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.15) +
    ggplot2::geom_point(size = 2) +
    ggplot2::geom_line() +
    ggplot2::scale_x_continuous(breaks = sort(unique(data$event_time))) +
    ggplot2::labs(
      title = "Python SonarQube issue-density event study",
      subtitle = "Repository and calendar-month fixed effects only",
      x = "Months relative to first observed Cursor adoption",
      y = "DiD coefficient on log1p(issues per KLOC)",
      caption = "Event -1 is the omitted reference period; repository-clustered standard errors."
    ) +
    ggplot2::theme_minimal(base_size = 11)
  ggplot2::ggsave(output_pdf, p, width = 9, height = 5.5)
  ggplot2::ggsave(output_png, p, width = 9, height = 5.5, dpi = 160)
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)

plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_rows <- as_integer_arg(args, "expected_rows", -1L)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", -1L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", -1L)
expected_untreated_rows <- as_integer_arg(args, "expected_untreated_rows", -1L)
expected_treated_rows <- as_integer_arg(args, "expected_treated_rows", -1L)
expected_dynamic_treated_rows <- as_integer_arg(args, "expected_dynamic_treated_rows", -1L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", -1L)
expected_legacy_mismatch_repos <- as_integer_arg(args, "expected_legacy_mismatch_repos", -1L)

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
  static = file.path(output_dir, "python_quality_static_effects.csv"),
  dynamic = file.path(output_dir, "python_quality_dynamic_effects.csv"),
  pretrend_checks = file.path(output_dir, "python_quality_pretrend_checks.csv"),
  pretrend_summary = file.path(output_dir, "python_quality_pretrend_summary.csv"),
  primary_three_spec = file.path(output_dir, "python_quality_primary_three_spec_summary.csv"),
  primary_key_terms = file.path(output_dir, "python_quality_primary_key_terms.csv"),
  covariate_static = file.path(output_dir, "python_quality_covariate_sensitivity_static.csv"),
  covariate_dynamic = file.path(output_dir, "python_quality_covariate_sensitivity_dynamic.csv"),
  diagnostics = file.path(output_dir, "python_quality_diagnostics.csv"),
  sample_summary = file.path(output_dir, "python_quality_sample_summary.csv"),
  event_support = file.path(output_dir, "python_quality_event_support.csv"),
  cohort_support = file.path(output_dir, "python_quality_cohort_support.csv"),
  legacy_audit = file.path(output_dir, "python_quality_legacy_flag_audit.csv"),
  qc = file.path(output_dir, "python_quality_qc.csv"),
  metadata = file.path(output_dir, "python_quality_run_metadata.csv"),
  primary_burden_pdf = file.path(plot_dir, "python_quality_primary_burden_dynamic.pdf"),
  primary_burden_png = file.path(plot_dir, "python_quality_primary_burden_dynamic.png"),
  primary_density_pdf = file.path(plot_dir, "python_quality_primary_density_dynamic.pdf"),
  primary_density_png = file.path(plot_dir, "python_quality_primary_density_dynamic.png")
)

run_started <- Sys.time()
log_message("INFO", "Reading Python quality panel: %s", input_file)
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
model_specs <- make_model_specs()
all_outcomes <- unique(unlist(lapply(model_specs, function(x) x$outcomes), use.names = FALSE))

required_columns <- unique(c(
  "repo_id", "repo_name", "scope_role", "treatment_group", "time", "time_index",
  "event", "event_index", "time_to_event", "is_treatment", "post_event", "cursor",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  "quality_did_complete", "quality_scope", "quality_count_semantics",
  "quality_primary_outcome", "quality_density_outcome", "quality_metric_version",
  all_outcomes
))
validate_columns(panel, required_columns)

# Validate the run-x-b06 measurement contract before fitting any model.
metadata_mismatches <- c(
  quality_did_complete = sum(bool_to_int(panel$quality_did_complete) != 1L),
  quality_scope = sum(is.na(panel$quality_scope) | panel$quality_scope != "python_only_sonar_inclusions"),
  quality_count_semantics = sum(is.na(panel$quality_count_semantics) | panel$quality_count_semantics != "unresolved_issue_stock_at_historical_snapshot"),
  quality_primary_outcome = sum(is.na(panel$quality_primary_outcome) | panel$quality_primary_outcome != "log_issue_total_py_sonarqube"),
  quality_density_outcome = sum(is.na(panel$quality_density_outcome) | panel$quality_density_outcome != "log_issues_per_kloc_py_sonarqube"),
  quality_metric_version = sum(is.na(panel$quality_metric_version) | panel$quality_metric_version != "v1")
)
if (any(metadata_mismatches > 0L)) {
  abortf("B06 quality metadata mismatch: %s", paste(names(metadata_mismatches), metadata_mismatches, sep = "=", collapse = "; "))
}

numeric_columns <- unique(c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "is_treatment", "post_event", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues", all_outcomes
))
for (column in numeric_columns) panel[, (column) := suppressWarnings(as.numeric(get(column)))]

if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) {
  abortf("repo_id, time_index, and event_index must be complete numeric columns.")
}
panel[, repo_id := as.integer(repo_id)]
panel[, time_index := as.integer(time_index)]
panel[, event_index := as.integer(event_index)]
panel[, treatment_group := as.integer(treatment_group)]

panel[, event_time_normalized := data.table::fifelse(
  treatment_group == 1L,
  time_index - event_index,
  NA_integer_
)]
panel[, absorbing_treated := as.integer(
  treatment_group == 1L & event_index > 0L & time_index >= event_index
)]
panel[, legacy_cursor_flag := bool_to_int(cursor)]
panel[, legacy_is_treatment := as.integer(replace(is_treatment, is.na(is_treatment), 0))]
panel[, legacy_post_event := as.integer(replace(post_event, is.na(post_event), 0))]
panel[, mismatch_cursor := legacy_cursor_flag != absorbing_treated]
panel[, mismatch_is_treatment := legacy_is_treatment != absorbing_treated]
panel[, mismatch_post_event := legacy_post_event != absorbing_treated]
panel[, legacy_mismatch_any := mismatch_cursor | mismatch_is_treatment | mismatch_post_event]

input_rows <- nrow(panel)
repo_count <- data.table::uniqueN(panel$repo_id)
treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])
treatment_rows <- nrow(panel[treatment_group == 1L])
control_rows <- nrow(panel[treatment_group == 0L])
untreated_rows <- nrow(panel[absorbing_treated == 0L])
treated_rows <- nrow(panel[absorbing_treated == 1L])
dynamic_treated_rows <- nrow(panel[
  absorbing_treated == 1L & event_time_normalized >= 0L & event_time_normalized <= plot_max_event
])

strict_count_check(input_rows, expected_rows, "input rows", strict_expected_counts)
strict_count_check(treatment_repos, expected_treatment_repos, "treatment repositories", strict_expected_counts)
strict_count_check(control_repos, expected_control_repos, "control repositories", strict_expected_counts)
strict_count_check(untreated_rows, expected_untreated_rows, "untreated first-stage rows", strict_expected_counts)
strict_count_check(treated_rows, expected_treated_rows, "treated rows", strict_expected_counts)
strict_count_check(dynamic_treated_rows, expected_dynamic_treated_rows, "dynamic treated rows", strict_expected_counts)

duplicate_rows <- panel[, .N, by = .(repo_id, time_index)][N > 1L]
if (nrow(duplicate_rows) > 0L) abortf("Found %d duplicate repo_id-time_index keys.", nrow(duplicate_rows))

role_mismatch <- panel[
  (scope_role == "treatment" & treatment_group != 1L) |
  (scope_role == "control" & treatment_group != 0L)
]
if (nrow(role_mismatch) > 0L) abortf("Found %d scope_role/treatment_group inconsistencies.", nrow(role_mismatch))

control_event_errors <- panel[treatment_group == 0L & event_index != 0L]
treatment_event_errors <- panel[treatment_group == 1L & event_index <= 0L]
if (nrow(control_event_errors) > 0L) abortf("Found %d control rows with nonzero event_index.", nrow(control_event_errors))
if (nrow(treatment_event_errors) > 0L) abortf("Found %d treatment rows with nonpositive event_index.", nrow(treatment_event_errors))

timing_errors <- panel[
  treatment_group == 1L &
  (is.na(time_to_event) | as.integer(time_to_event) != event_time_normalized)
]
if (nrow(timing_errors) > 0L) abortf("Found %d normalized event-time errors.", nrow(timing_errors))

# All quality outcomes and adjusted covariates must be finite on the common panel.
all_model_fields <- unique(c(all_outcomes, model_specs$adjusted_burden$model_fields))
missing_model_rows <- panel[!stats::complete.cases(panel[, ..all_model_fields])]
if (nrow(missing_model_rows) > 0L) abortf("Found %d rows with missing quality model fields.", nrow(missing_model_rows))
nonfinite_model_rows <- panel[
  !apply(as.data.frame(panel[, ..all_model_fields]), 1L, function(row) all(is.finite(row)))
]
if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d rows with non-finite quality model fields.", nrow(nonfinite_model_rows))

legacy_audit <- panel[legacy_mismatch_any == TRUE, .(
  repo_id, repo_name, time, time_index, event, event_index,
  time_to_event, event_time_normalized, absorbing_treated,
  legacy_cursor = cursor, legacy_cursor_flag,
  legacy_is_treatment, legacy_post_event,
  mismatch_cursor, mismatch_is_treatment, mismatch_post_event,
  scope_role, treatment_group
)]
data.table::setorder(legacy_audit, repo_name, time_index)
legacy_mismatch_rows <- nrow(legacy_audit)
legacy_mismatch_repos <- data.table::uniqueN(legacy_audit$repo_id)
strict_count_check(legacy_mismatch_rows, expected_legacy_mismatch_rows, "legacy mismatch rows", strict_expected_counts)
strict_count_check(legacy_mismatch_repos, expected_legacy_mismatch_repos, "legacy mismatch repositories", strict_expected_counts)
write_csv(legacy_audit, paths$legacy_audit)

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)

all_event_support <- panel[treatment_group == 1L, .(
  treatment_rows = .N,
  treatment_repositories = data.table::uniqueN(repo_id)
), by = .(event_time = as.integer(event_time_normalized))]
all_event_support[, period_type := data.table::fcase(
  event_time %in% pretrend_values, "placebo_pretrend",
  event_time == -1L, "reference",
  event_time >= 0L, "post_treatment",
  default = "other_pre_treatment"
)]
all_event_support[, in_pretrend_window := event_time %in% pretrend_values]
all_event_support[, in_dynamic_post_window := event_time %in% post_values]
data.table::setorder(all_event_support, event_time)
write_csv(all_event_support, paths$event_support)

cohort_support <- panel[treatment_group == 1L, .(
  treatment_repositories = data.table::uniqueN(repo_id),
  total_rows = .N,
  pre_treatment_rows = sum(event_time_normalized < 0L),
  treated_rows = sum(event_time_normalized >= 0L),
  dynamic_0_to_max_rows = sum(event_time_normalized >= 0L & event_time_normalized <= plot_max_event),
  min_event_time = min(event_time_normalized),
  max_event_time = max(event_time_normalized)
), by = .(event, event_index)]
data.table::setorder(cohort_support, event_index)
write_csv(cohort_support, paths$cohort_support)

sample_summary <- data.table::rbindlist(list(
  make_summary_row("definition", "quality_scope", "python_only_sonar_inclusions"),
  make_summary_row("definition", "count_semantics", "unresolved_issue_stock_at_historical_snapshot"),
  make_summary_row("definition", "primary_burden_outcome", "log_issue_total_py_sonarqube"),
  make_summary_row("definition", "primary_density_outcome", "log_issues_per_kloc_py_sonarqube"),
  make_summary_row("definition", "model_specs", paste(names(model_specs), collapse = "|")),
  make_summary_row("input", "rows", input_rows),
  make_summary_row("input", "repositories", repo_count),
  make_summary_row("input", "treatment_rows", treatment_rows),
  make_summary_row("input", "control_rows", control_rows),
  make_summary_row("input", "treatment_repositories", treatment_repos),
  make_summary_row("input", "control_repositories", control_repos),
  make_summary_row("sample", "untreated_first_stage_rows", untreated_rows),
  make_summary_row("sample", "treated_static_rows", treated_rows),
  make_summary_row("sample", "treated_dynamic_0_to_max_rows", dynamic_treated_rows),
  make_summary_row("qc", "duplicate_repo_time_rows", nrow(duplicate_rows)),
  make_summary_row("qc", "normalized_timing_errors", nrow(timing_errors)),
  make_summary_row("qc", "missing_model_rows", nrow(missing_model_rows)),
  make_summary_row("qc", "nonfinite_model_rows", nrow(nonfinite_model_rows)),
  make_summary_row("qc", "legacy_mismatch_rows", legacy_mismatch_rows, "Audit only; normalized timing is authoritative."),
  make_summary_row("qc", "legacy_mismatch_repositories", legacy_mismatch_repos)
), use.names = TRUE)
write_csv(sample_summary, paths$sample_summary)

static_tables <- list()
dynamic_tables <- list()
pretrend_tables <- list()
diagnostics <- list()
model_errors <- character()

add_diagnostic <- function(spec_name, outcome, model_type, status, elapsed, warnings = character(), error_message = "", result_terms = NA_integer_, extra = "") {
  spec <- model_specs[[spec_name]]
  diagnostics[[length(diagnostics) + 1L]] <<- data.table::data.table(
    model_spec = spec_name,
    model_spec_label = spec$label,
    outcome_family = spec$family,
    first_stage_formula = spec$first_stage_text,
    outcome = outcome,
    outcome_label = unname(outcome_labels[[outcome]]),
    outcome_role = unname(outcome_roles[[outcome]]),
    model_type = model_type,
    status = status,
    runtime_seconds = as.numeric(elapsed),
    warning_count = length(warnings),
    warning_messages = paste(warnings, collapse = " | "),
    error_message = error_message,
    input_rows = input_rows,
    untreated_rows = untreated_rows,
    treated_rows = treated_rows,
    result_terms = as.integer(result_terms),
    extra = extra
  )
}

for (spec_name in names(model_specs)) {
  spec <- model_specs[[spec_name]]
  log_message("INFO", "Starting model specification: %s", spec_name)

  for (outcome in spec$outcomes) {
    outcome_label_value <- unname(outcome_labels[[outcome]])
    outcome_role_value <- unname(outcome_roles[[outcome]])
    if (is.null(outcome_label_value) || is.na(outcome_label_value)) abortf("Missing label for outcome: %s", outcome)

    log_message("INFO", "Fitting first-stage diagnostic for %s under %s", outcome, spec_name)
    first_stage_capture <- fit_first_stage_diagnostic(panel, outcome, spec$first_stage_text)
    if (first_stage_capture$error) {
      error_text <- first_stage_capture$value$message
      add_diagnostic(spec_name, outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text)
      model_errors <- c(model_errors, sprintf("%s/%s first_stage: %s", spec_name, outcome, error_text))
      next
    }
    prediction_na_treated <- sum(is.na(first_stage_capture$predictions[panel$absorbing_treated == 1L]))
    prediction_na_all <- sum(is.na(first_stage_capture$predictions))
    if (prediction_na_treated > 0L) {
      error_text <- sprintf("First-stage predictions missing for %d treated rows.", prediction_na_treated)
      add_diagnostic(spec_name, outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text,
                     extra = sprintf("prediction_na_all=%d", prediction_na_all))
      model_errors <- c(model_errors, sprintf("%s/%s first_stage: %s", spec_name, outcome, error_text))
      next
    }
    add_diagnostic(
      spec_name, outcome, "first_stage", "success", first_stage_capture$elapsed,
      first_stage_capture$warnings, result_terms = length(stats::coef(first_stage_capture$value)),
      extra = sprintf("nobs=%d; prediction_na_all=%d; prediction_na_treated=%d",
                      stats::nobs(first_stage_capture$value), prediction_na_all, prediction_na_treated)
    )

    log_message("INFO", "Running static did_imputation for %s under %s", outcome, spec_name)
    static_capture <- run_did_model(panel, outcome, spec$first_stage, horizon = NULL, pretrends = NULL)
    if (static_capture$error) {
      error_text <- static_capture$value$message
      add_diagnostic(spec_name, outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
      model_errors <- c(model_errors, sprintf("%s/%s static: %s", spec_name, outcome, error_text))
      next
    }
    static_table <- extract_effect_table(static_capture$value, outcome, confidence_level)[term == "treat"]
    if (nrow(static_table) != 1L) {
      error_text <- sprintf("Expected one static treat term, observed %d.", nrow(static_table))
      add_diagnostic(spec_name, outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text, nrow(static_table))
      model_errors <- c(model_errors, sprintf("%s/%s static: %s", spec_name, outcome, error_text))
      next
    }
    static_table[, `:=`(
      model_spec = spec_name,
      model_spec_label = spec$label,
      outcome_family = spec$family,
      first_stage_formula = spec$first_stage_text,
      outcome_label = outcome_label_value,
      outcome_role = outcome_role_value,
      term_type = "static_att",
      treated_observations = treated_rows,
      first_stage_observations = untreated_rows,
      treatment_repositories = treatment_repos,
      control_repositories = control_repos,
      percent_interpretation = "100*(exp(beta)-1) on the corresponding log1p outcome scale"
    )]
    static_tables[[paste(spec_name, outcome, sep = "__")]] <- static_table
    add_diagnostic(spec_name, outcome, "static", "success", static_capture$elapsed, static_capture$warnings, result_terms = 1L)

    log_message("INFO", "Running dynamic did_imputation for %s under %s", outcome, spec_name)
    dynamic_capture <- run_did_model(
      panel, outcome, spec$first_stage,
      horizon = dynamic_horizon_values,
      pretrends = pretrend_values
    )
    if (dynamic_capture$error) {
      error_text <- dynamic_capture$value$message
      add_diagnostic(spec_name, outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
      model_errors <- c(model_errors, sprintf("%s/%s dynamic: %s", spec_name, outcome, error_text))
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
    if (nrow(dynamic_table) != expected_dynamic_terms) {
      error_text <- sprintf("Expected %d dynamic/pretrend terms, observed %d.", expected_dynamic_terms, nrow(dynamic_table))
      add_diagnostic(spec_name, outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text, nrow(dynamic_table))
      model_errors <- c(model_errors, sprintf("%s/%s dynamic: %s", spec_name, outcome, error_text))
      next
    }
    support_for_merge <- all_event_support[, .(event_time, support_rows = treatment_rows, support_repositories = treatment_repositories)]
    dynamic_table <- merge(dynamic_table, support_for_merge, by = "event_time", all.x = TRUE, sort = FALSE)
    dynamic_table[, `:=`(
      model_spec = spec_name,
      model_spec_label = spec$label,
      outcome_family = spec$family,
      first_stage_formula = spec$first_stage_text,
      outcome_label = outcome_label_value,
      outcome_role = outcome_role_value,
      ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0,
      percent_interpretation = "100*(exp(beta)-1) on the corresponding log1p outcome scale"
    )]
    data.table::setorder(dynamic_table, event_time)
    dynamic_tables[[paste(spec_name, outcome, sep = "__")]] <- dynamic_table
    pretrend_tables[[paste(spec_name, outcome, sep = "__")]] <- dynamic_table[term_type == "placebo_pretrend"]
    add_diagnostic(
      spec_name, outcome, "dynamic", "success", dynamic_capture$elapsed,
      dynamic_capture$warnings, result_terms = nrow(dynamic_table),
      extra = sprintf("horizon=%s; pretrends=%s; reference=-1 omitted",
                      paste(dynamic_horizon_values, collapse = ","), paste(pretrend_values, collapse = ","))
    )
  }
}

if (length(model_errors) > 0L) {
  diagnostics_dt <- data.table::rbindlist(diagnostics, fill = TRUE)
  write_csv(diagnostics_dt, paths$diagnostics)
  abortf("One or more quality models failed: %s", paste(model_errors, collapse = " || "))
}

static_all <- data.table::rbindlist(static_tables, fill = TRUE, use.names = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, fill = TRUE, use.names = TRUE)
pretrend_all <- data.table::rbindlist(pretrend_tables, fill = TRUE, use.names = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostics, fill = TRUE, use.names = TRUE)
pretrend_summary <- make_pretrend_summary(pretrend_all, confidence_level)

data.table::setorder(static_all, model_spec, outcome)
data.table::setorder(dynamic_all, model_spec, outcome, event_time)
data.table::setorder(pretrend_all, model_spec, outcome, event_time)
data.table::setorder(pretrend_summary, model_spec, outcome)

write_csv(static_all, paths$static)
write_csv(dynamic_all, paths$dynamic)
write_csv(pretrend_all, paths$pretrend_checks)
write_csv(pretrend_summary, paths$pretrend_summary)
write_csv(diagnostics_all, paths$diagnostics)

primary_three_spec <- static_all[
  (model_spec %in% c("adjusted_burden", "fe_only_burden") & outcome == "log_issue_total_py_sonarqube") |
  (model_spec == "fe_only_density" & outcome == "log_issues_per_kloc_py_sonarqube")
]
primary_three_spec[, spec_order := match(model_spec, c("adjusted_burden", "fe_only_burden", "fe_only_density"))]
data.table::setorder(primary_three_spec, spec_order)
primary_three_spec[, spec_order := NULL]
write_csv(primary_three_spec, paths$primary_three_spec)

key_events <- c(-4L, -3L, -2L, 0L, 1L, 2L, 3L, 4L)
primary_key_terms <- dynamic_all[
  event_time %in% key_events & (
    (model_spec %in% c("adjusted_burden", "fe_only_burden") & outcome == "log_issue_total_py_sonarqube") |
    (model_spec == "fe_only_density" & outcome == "log_issues_per_kloc_py_sonarqube")
  )
]
data.table::setorder(primary_key_terms, model_spec, event_time)
write_csv(primary_key_terms, paths$primary_key_terms)

adjusted_static <- static_all[model_spec == "adjusted_burden", .(
  outcome, outcome_label, adjusted_estimate = estimate, adjusted_std_error = std.error,
  adjusted_conf_low = conf.low, adjusted_conf_high = conf.high, adjusted_p_value = p_value
)]
fe_static <- static_all[model_spec == "fe_only_burden", .(
  outcome, fe_only_estimate = estimate, fe_only_std_error = std.error,
  fe_only_conf_low = conf.low, fe_only_conf_high = conf.high, fe_only_p_value = p_value
)]
covariate_static <- merge(adjusted_static, fe_static, by = "outcome", all = TRUE, sort = FALSE)
covariate_static[, estimate_difference_fe_minus_adjusted := fe_only_estimate - adjusted_estimate]
data.table::setorder(covariate_static, outcome)
write_csv(covariate_static, paths$covariate_static)

adjusted_dynamic <- dynamic_all[model_spec == "adjusted_burden", .(
  outcome, outcome_label, event_time, term_type,
  adjusted_estimate = estimate, adjusted_std_error = std.error,
  adjusted_conf_low = conf.low, adjusted_conf_high = conf.high, adjusted_p_value = p_value
)]
fe_dynamic <- dynamic_all[model_spec == "fe_only_burden", .(
  outcome, event_time, term_type,
  fe_only_estimate = estimate, fe_only_std_error = std.error,
  fe_only_conf_low = conf.low, fe_only_conf_high = conf.high, fe_only_p_value = p_value
)]
covariate_dynamic <- merge(
  adjusted_dynamic, fe_dynamic,
  by = c("outcome", "event_time", "term_type"), all = TRUE, sort = FALSE
)
covariate_dynamic[, estimate_difference_fe_minus_adjusted := fe_only_estimate - adjusted_estimate]
data.table::setorder(covariate_dynamic, outcome, event_time)
write_csv(covariate_dynamic, paths$covariate_dynamic)

expected_models <- 24L
expected_dynamic_terms_per_model <- length(pretrend_values) + length(post_values)
expected_static_rows <- expected_models
expected_dynamic_rows <- expected_models * expected_dynamic_terms_per_model
expected_pretrend_rows <- expected_models * length(pretrend_values)
expected_pretrend_summary_rows <- expected_models
expected_primary_rows <- 3L
expected_key_rows <- 3L * length(key_events)
expected_covariate_static_rows <- 8L
expected_covariate_dynamic_rows <- 8L * expected_dynamic_terms_per_model

qc <- data.table::data.table(
  check = c(
    "input_rows", "treatment_repositories", "control_repositories",
    "untreated_first_stage_rows", "treated_static_rows", "dynamic_treated_rows_0_to_6",
    "duplicate_repo_time_rows", "normalized_timing_errors",
    "legacy_mismatch_rows", "legacy_mismatch_repositories",
    "metadata_mismatch_total", "model_failure_count", "model_warning_count",
    "static_effect_rows", "dynamic_effect_rows", "pretrend_check_rows",
    "pretrend_summary_rows", "primary_three_spec_rows", "primary_key_term_rows",
    "covariate_static_comparison_rows", "covariate_dynamic_comparison_rows"
  ),
  observed = c(
    input_rows, treatment_repos, control_repos,
    untreated_rows, treated_rows, dynamic_treated_rows,
    nrow(duplicate_rows), nrow(timing_errors),
    legacy_mismatch_rows, legacy_mismatch_repos,
    sum(metadata_mismatches), length(model_errors), sum(diagnostics_all$warning_count),
    nrow(static_all), nrow(dynamic_all), nrow(pretrend_all),
    nrow(pretrend_summary), nrow(primary_three_spec), nrow(primary_key_terms),
    nrow(covariate_static), nrow(covariate_dynamic)
  ),
  expected = c(
    expected_rows, expected_treatment_repos, expected_control_repos,
    expected_untreated_rows, expected_treated_rows, expected_dynamic_treated_rows,
    0L, 0L,
    expected_legacy_mismatch_rows, expected_legacy_mismatch_repos,
    0L, 0L, 0L,
    expected_static_rows, expected_dynamic_rows, expected_pretrend_rows,
    expected_pretrend_summary_rows, expected_primary_rows, expected_key_rows,
    expected_covariate_static_rows, expected_covariate_dynamic_rows
  )
)
qc[, status := data.table::fifelse(
  is.na(expected) | expected < 0,
  "informational",
  data.table::fifelse(as.numeric(observed) == as.numeric(expected), "pass", "fail")
)]
qc[, note := c(
  "Full run-x-b06 monthly panel.",
  "Treatment repositories.", "Never-treated control repositories.",
  "Controls plus pre-adoption treatment rows.", "All post-adoption rows.",
  "Post-adoption rows in event 0:+6.",
  "Must be zero.", "Normalized timing must match time_to_event.",
  "Legacy mismatch is audit-only.", "Legacy mismatch is audit-only.",
  "B06 measurement contract must match exactly.", "No model may fail.",
  "Warnings are treated as QC failures for this production run.",
  "3 specs x 8 outcomes.", "24 models x 12 reported dynamic/placebo terms.",
  "24 models x 5 placebo terms.", "One summary per model.",
  "Adjusted burden, FE-only burden, FE-only density.",
  "Three primary specifications x eight key event times.",
  "Eight burden outcomes: FE-only versus adjusted.",
  "Eight burden outcomes x twelve event terms."
)]
write_csv(qc, paths$qc)

failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("B07 QC failed: %s", paste(failed_qc$check, collapse = ", "))
}

plot_primary_burden(dynamic_all, paths$primary_burden_pdf, paths$primary_burden_png)
plot_primary_density(dynamic_all, paths$primary_density_pdf, paths$primary_density_png)

metadata <- data.table::rbindlist(list(
  make_summary_row("run", "implementation_version", implementation_version),
  make_summary_row("run", "started", format(run_started, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "finished", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "input_file", input_file),
  make_summary_row("run", "input_sha256", sha256_file(input_file)),
  make_summary_row("run", "script_path", script_path),
  make_summary_row("run", "script_sha256", if (is.na(script_path)) NA_character_ else sha256_file(script_path)),
  make_summary_row("software", "R", R.version.string),
  make_summary_row("software", "data.table", safe_package_version("data.table")),
  make_summary_row("software", "didimputation", safe_package_version("didimputation")),
  make_summary_row("software", "fixest", safe_package_version("fixest")),
  make_summary_row("software", "ggplot2", safe_package_version("ggplot2")),
  make_summary_row("definition", "cluster_variable", "repo_id"),
  make_summary_row("definition", "reference_event", -1L),
  make_summary_row("definition", "dynamic_window", sprintf("%d:%d", plot_min_event, plot_max_event)),
  make_summary_row("definition", "pretrend_window", sprintf("%d:%d", pretrend_min, pretrend_max)),
  make_summary_row("definition", "quality_scope", "Python .py only via SonarQube inclusions"),
  make_summary_row("definition", "count_semantics", "unresolved issue stock at historical snapshot"),
  make_summary_row("definition", "adjusted_first_stage", model_specs$adjusted_burden$first_stage_text),
  make_summary_row("definition", "fe_only_first_stage", model_specs$fe_only_burden$first_stage_text),
  make_summary_row("definition", "percent_transform_caution", "exp(beta)-1 is reported on a log1p outcome and should not be interpreted as an exact arithmetic percentage change in raw issue counts."),
  make_summary_row("qc", "failed_checks", nrow(failed_qc))
), fill = TRUE)
write_csv(metadata, paths$metadata)

log_message(
  "INFO",
  "Completed run-x-b07 %s: static=%d; dynamic=%d; pretrend=%d; primary_specs=%d; QC failures=%d",
  implementation_version, nrow(static_all), nrow(dynamic_all), nrow(pretrend_all), nrow(primary_three_spec), nrow(failed_qc)
)
