#!/usr/bin/env Rscript

# ============================================================
# run-x-g06 v1: NPR-threshold sensitivity for dynamic panel GMM
# ============================================================
#
# Purpose:
#   Re-estimate the reverse-direction quality -> velocity dynamic-panel GMM
#   across the prespecified 21-point NPR threshold grid already constructed
#   by run-x-d03.
#
# Scientific guardrails:
#   - The prespecified primary threshold remains 1.571637.
#   - Main thresholds span primary +/- 0.50 in exact 0.05 increments.
#   - The D03 legacy anchor 1.5183 is intentionally excluded from this sweep.
#   - Every main-grid threshold is reported; no threshold is selected using
#     GMM significance.
#   - The GMM specification and full-sample repo-month membership are identical
#     at every threshold.
#   - The primary-threshold result must reproduce run-x-e02 full-sample GMM.
#   - If a non-primary sparse-threshold model fails, record the failure and
#     continue. A primary-threshold model failure is a hard error.
#
# Input quality definition at threshold tau:
#   log1p(sum of unresolved SonarQube issues among Python files whose
#   file_npr_fun_space_by_token_weighted > tau in the historical snapshot).
#
# Model:
#   Velocity_t ~ Velocity_{t-1} + NPRQuality_{t-1} + treatment_t + controls_t
#   Instruments: Velocity_{t-2}
#   effect="twoways", model="twosteps", transformation="d", collapse=FALSE
#
# Inputs:
#   - D03 NPR threshold-long quality panel
#   - D03 summary/sample/global-audit artifacts
#   - B06 authoritative whole-Python velocity/covariate panel
#   - E02 coefficients for exact primary-threshold reproduction
#
# This script is self-contained. It reuses validated analysis logic from the
# existing E02 NPR GMM and E03 threshold-sensitivity analyses, but it does not
# call any prior experiment script.
# ============================================================

options(stringsAsFactors = FALSE, warn = 1)

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)

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

as_integer_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.integer(value))
  if (is.na(result)) abortf("Argument --%s must be integer-compatible", gsub("_", "-", name, fixed = TRUE))
  result
}

as_numeric_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.numeric(value))
  if (is.na(result)) abortf("Argument --%s must be numeric", gsub("_", "-", name, fixed = TRUE))
  result
}

as_logical_arg <- function(args, name, default = TRUE) {
  value <- args[[name]]
  if (is.null(value)) return(isTRUE(default))
  text <- tolower(trimws(as.character(value)))
  if (text %in% c("1", "true", "yes", "y", "on")) return(TRUE)
  if (text %in% c("0", "false", "no", "n", "off")) return(FALSE)
  abortf("Argument --%s must be boolean-like", gsub("_", "-", name, fixed = TRUE))
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing) > 0L) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

safe_package_version <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) return(NA_character_)
  as.character(utils::packageVersion(package))
}

sha256_file <- function(path) {
  if (is.na(path) || !nzchar(path) || !file.exists(path)) return(NA_character_)
  tool <- Sys.which("sha256sum")
  if (!nzchar(tool)) return(NA_character_)
  output <- suppressWarnings(system2(tool, path, stdout = TRUE, stderr = TRUE))
  if (!length(output)) return(NA_character_)
  strsplit(output[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
}

strict_count_check <- function(actual, expected, label, strict = TRUE) {
  if (identical(as.integer(actual), as.integer(expected))) return(invisible(TRUE))
  text <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, actual)
  if (strict) abortf("%s", text) else log_message("WARNING", "%s", text)
  invisible(FALSE)
}

bool_to_int <- function(x) {
  if (is.logical(x)) return(as.integer(replace(x, is.na(x), FALSE)))
  text <- tolower(trimws(as.character(x)))
  result <- rep(NA_integer_, length(text))
  result[text %in% c("1", "true", "t", "yes", "y")] <- 1L
  result[text %in% c("0", "false", "f", "no", "n", "", "na", "nan", "none")] <- 0L
  numeric_value <- suppressWarnings(as.numeric(text))
  idx <- is.na(result) & !is.na(numeric_value)
  result[idx] <- as.integer(numeric_value[idx] != 0)
  result[is.na(result)] <- 0L
  result
}

values_match <- function(left, right, tolerance = 1e-10) {
  left_num <- suppressWarnings(as.numeric(left))
  right_num <- suppressWarnings(as.numeric(right))
  numeric_compatible <- all((is.na(left) | !is.na(left_num)) & (is.na(right) | !is.na(right_num)))
  if (numeric_compatible) {
    return((is.na(left_num) & is.na(right_num)) |
      (!is.na(left_num) & !is.na(right_num) & abs(left_num - right_num) <= tolerance))
  }
  left_chr <- as.character(left)
  right_chr <- as.character(right)
  (is.na(left_chr) & is.na(right_chr)) | (!is.na(left_chr) & !is.na(right_chr) & left_chr == right_chr)
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
  list(
    value = value,
    warnings = unique(warnings),
    elapsed = proc.time()[[3L]] - started,
    error = inherits(value, "captured_error")
  )
}

extract_htest <- function(test, threshold_id, threshold, diagnostic_name, primary_analysis) {
  if (is.null(test)) {
    return(data.table::data.table(
      threshold_id = threshold_id,
      threshold = threshold,
      primary_analysis = primary_analysis,
      diagnostic = diagnostic_name,
      statistic = NA_real_, parameter = NA_real_, p_value = NA_real_,
      method = NA_character_, status = "missing"
    ))
  }
  statistic <- if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_
  parameter <- if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_
  p_value <- if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_
  method <- if (!is.null(test$method)) as.character(test$method) else NA_character_
  data.table::data.table(
    threshold_id = threshold_id,
    threshold = threshold,
    primary_analysis = primary_analysis,
    diagnostic = diagnostic_name,
    statistic = statistic,
    parameter = parameter,
    p_value = p_value,
    method = method,
    status = ifelse(is.finite(statistic) && is.finite(p_value), "available", "missing")
  )
}

failed_diagnostics <- function(threshold_id, threshold, primary_analysis, message) {
  data.table::data.table(
    threshold_id = rep(threshold_id, 3L),
    threshold = rep(threshold, 3L),
    primary_analysis = rep(primary_analysis, 3L),
    diagnostic = c("sargan", "ar1", "ar2"),
    statistic = NA_real_, parameter = NA_real_, p_value = NA_real_,
    method = NA_character_, status = "model_failed",
    warning_count = 0L, warning_messages = message
  )
}

extract_coefficients <- function(summary_object, threshold_id, threshold, threshold_role, confidence_level, primary_threshold) {
  matrix <- as.matrix(summary_object$coefficients)
  if (is.null(matrix) || nrow(matrix) == 0L) abortf("No coefficient matrix returned at threshold %.6f", threshold)
  cn <- colnames(matrix)
  estimate_col <- which(tolower(cn) == "estimate")[1L]
  se_col <- grep("std\\.?[[:space:]]*error", cn, ignore.case = TRUE)[1L]
  p_col <- grep("pr\\(", cn, ignore.case = TRUE)[1L]
  if (is.na(estimate_col) || is.na(se_col)) abortf("Could not identify estimate/SE columns at threshold %.6f", threshold)
  estimate <- as.numeric(matrix[, estimate_col])
  std_error <- as.numeric(matrix[, se_col])
  p_value <- if (!is.na(p_col)) as.numeric(matrix[, p_col]) else 2 * stats::pnorm(-abs(estimate / std_error))
  alpha <- 1 - confidence_level
  critical <- stats::qnorm(1 - alpha / 2)
  terms <- rownames(matrix)
  primary_term <- "lag(log1p_selected_issue_total, 1)"
  data.table::data.table(
    threshold_id = threshold_id,
    threshold = threshold,
    threshold_role = threshold_role,
    primary_analysis = as.integer(abs(threshold - primary_threshold) <= 1e-12),
    model = "npr_threshold_quality_to_velocity",
    direction = "NPRQuality_{t-1} -> Velocity_t",
    term = terms,
    estimate = estimate,
    std_error = std_error,
    conf_low = estimate - critical * std_error,
    conf_high = estimate + critical * std_error,
    p_value = p_value,
    significant = !is.na(p_value) & p_value < alpha,
    is_primary_interaction_term = terms == primary_term
  )
}

extract_dimensions <- function(model) {
  stats_nobs <- tryCatch(as.integer(stats::nobs(model)), error = function(e) NA_integer_)
  instrument_columns <- integer()
  if (is.list(model$W) && length(model$W) > 0L) {
    instrument_columns <- vapply(model$W, function(x) if (is.null(dim(x))) 0L else ncol(x), integer(1))
    instrument_columns <- instrument_columns[instrument_columns > 0L]
  }
  list(
    stats_nobs = stats_nobs,
    instrument_count = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_min = if (length(instrument_columns)) min(instrument_columns) else NA_integer_,
    instrument_columns_max = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_unique = if (length(instrument_columns)) paste(sort(unique(instrument_columns)), collapse = "|") else "",
    pgmm_internal_repository_slots = if (is.list(model$model)) length(model$model) else NA_integer_,
    pgmm_internal_matrix_rows = if (is.list(model$model)) sum(vapply(model$model, function(x) if (is.null(dim(x))) 0L else nrow(x), integer(1))) else NA_integer_
  )
}

make_key <- function(repo_id, time_index) paste(repo_id, time_index, sep = "::")

exact_calendar_support <- function(panel) {
  keys <- unique(make_key(panel$repo_id, panel$time_index))
  panel[
    make_key(repo_id, time_index - 1L) %in% keys &
      make_key(repo_id, time_index - 2L) %in% keys
  ]
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
b06_panel_file <- normalizePath(require_arg(args, "b06_panel_file"), mustWork = TRUE)
d03_summary_file <- normalizePath(require_arg(args, "d03_summary_file"), mustWork = TRUE)
d03_sample_summary_file <- normalizePath(require_arg(args, "d03_sample_summary_file"), mustWork = TRUE)
d03_global_audit_file <- normalizePath(require_arg(args, "d03_global_audit_file"), mustWork = TRUE)
e02_reference_coefficients_file <- normalizePath(require_arg(args, "e02_reference_coefficients_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
primary_threshold <- as_numeric_arg(args, "primary_threshold", 1.571637)
threshold_radius <- as_numeric_arg(args, "threshold_radius", 0.50)
threshold_step <- as_numeric_arg(args, "threshold_step", 0.05)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
reference_tolerance <- as_numeric_arg(args, "reference_tolerance", 1e-10)
expected_long_rows <- as_integer_arg(args, "expected_long_rows", 85118L)
expected_d03_thresholds <- as_integer_arg(args, "expected_d03_thresholds", 22L)
expected_sample_specs <- as_integer_arg(args, "expected_sample_specs", 2L)
expected_main_thresholds <- as_integer_arg(args, "expected_main_thresholds", 21L)
expected_rows_per_threshold <- as_integer_arg(args, "expected_rows_per_threshold", 1954L)
expected_repositories <- as_integer_arg(args, "expected_repositories", 167L)
expected_treatment_repositories <- as_integer_arg(args, "expected_treatment_repositories", 63L)
expected_control_repositories <- as_integer_arg(args, "expected_control_repositories", 104L)
expected_active_rows <- as_integer_arg(args, "expected_active_rows", 1631L)
expected_active_repositories <- as_integer_arg(args, "expected_active_repositories", 146L)
expected_active_treatment_repositories <- as_integer_arg(args, "expected_active_treatment_repositories", 61L)
expected_active_control_repositories <- as_integer_arg(args, "expected_active_control_repositories", 85L)
expected_primary_selected_files <- as_integer_arg(args, "expected_primary_selected_files", 13739L)
expected_primary_issue_stock <- as_integer_arg(args, "expected_primary_issue_stock", 20306L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", 11L)
expected_legacy_mismatch_repositories <- as_integer_arg(args, "expected_legacy_mismatch_repositories", 3L)

if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1")
if (threshold_radius <= 0 || threshold_step <= 0) abortf("threshold radius and step must be positive")
ratio <- threshold_radius / threshold_step
if (abs(ratio - round(ratio)) > 1e-12) abortf("threshold_radius must be an exact multiple of threshold_step")

expected_grid <- primary_threshold + seq.int(-as.integer(round(ratio)), as.integer(round(ratio))) * threshold_step
if (length(expected_grid) != expected_main_thresholds) {
  abortf("Expected %d main thresholds but constructed %d", expected_main_thresholds, length(expected_grid))
}

check_packages(c("data.table", "plm"))
suppressPackageStartupMessages(library(plm))
if (!exists("plm", mode = "function", inherits = TRUE)) abortf("plm() is not visible after package attachment")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  coefficients = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_coefficients.csv"),
  primary_summary = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_primary_summary.csv"),
  diagnostics = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_diagnostics.csv"),
  instrument_qc = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_instrument_qc.csv"),
  support = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_support_diagnostics.csv"),
  threshold_input_audit = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_input_audit.csv"),
  b06_join_audit = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_b06_join_audit.csv"),
  legacy_audit = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_legacy_flag_audit.csv"),
  calendar_gap_audit = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_calendar_gap_audit.csv"),
  reproduction = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_e02_reproduction.csv"),
  model_failures = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_model_failures.csv"),
  qc = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_qc.csv"),
  metadata = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_run_metadata.csv"),
  models = file.path(output_dir, "dynamic_panel_gmm_npr_threshold_models.rds")
)

run_started <- Sys.time()
log_message("INFO", "Reading D03 NPR threshold panel: %s", input_file)
long_panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
required_d03 <- c(
  "sample_spec", "threshold_id", "threshold_role", "threshold", "comparison_operator",
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor",
  "log1p_selected_issue_total", "selected_issue_total", "selected_file_count", "eligible_fun_file_count",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
validate_columns(long_panel, required_d03, "D03 long panel")
strict_count_check(nrow(long_panel), expected_long_rows, "D03 long-panel rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(long_panel$threshold_id), expected_d03_thresholds, "D03 threshold specifications", strict_expected_counts)
strict_count_check(data.table::uniqueN(long_panel$sample_spec), expected_sample_specs, "D03 sample specifications", strict_expected_counts)

# Validate upstream D03 summary/sample/global-audit artifacts before fitting.
d03_summary <- data.table::fread(d03_summary_file, na.strings = c("", "NA", "NaN"))
validate_columns(d03_summary, c("metric", "value"), "D03 summary")
summary_lookup <- setNames(as.character(d03_summary$value), as.character(d03_summary$metric))
if (!identical(summary_lookup[["status"]], "PASS")) abortf("D03 summary status is not PASS")
if (abs(as.numeric(summary_lookup[["primary_threshold"]]) - primary_threshold) > 1e-12) abortf("D03 primary-threshold summary mismatch")

d03_sample_summary <- data.table::fread(d03_sample_summary_file, na.strings = c("", "NA", "NaN"))
validate_columns(d03_sample_summary, c("sample_spec", "repo_month_rows", "repositories", "control_repositories", "treatment_repositories"), "D03 sample summary")
full_sample_summary <- d03_sample_summary[sample_spec == "full_sample"]
if (nrow(full_sample_summary) != 1L) abortf("D03 sample summary must contain exactly one full_sample row")
strict_count_check(full_sample_summary$repo_month_rows, expected_rows_per_threshold, "D03 full-sample rows", strict_expected_counts)
strict_count_check(full_sample_summary$repositories, expected_repositories, "D03 full-sample repositories", strict_expected_counts)
strict_count_check(full_sample_summary$treatment_repositories, expected_treatment_repositories, "D03 full-sample treatment repositories", strict_expected_counts)
strict_count_check(full_sample_summary$control_repositories, expected_control_repositories, "D03 full-sample control repositories", strict_expected_counts)

global_audit <- data.table::fread(d03_global_audit_file, na.strings = c("", "NA", "NaN"))
validate_columns(global_audit, c(
  "sample_spec", "threshold_id", "threshold", "comparison_operator", "repo_month_rows",
  "repositories", "selected_file_rows", "selected_issue_total"
), "D03 global audit")
global_full <- data.table::copy(global_audit[sample_spec == "full_sample" & comparison_operator == ">"])
global_full[, threshold_numeric := as.numeric(threshold)]
if (anyNA(global_full$threshold_numeric)) abortf("D03 global audit contains non-numeric thresholds")
global_full[, main_grid := vapply(threshold_numeric, function(x) any(abs(x - expected_grid) <= 1e-10), logical(1))]
main_global <- global_full[main_grid == TRUE]
data.table::setorder(main_global, threshold_numeric)
if (nrow(main_global) != expected_main_thresholds) abortf("Expected %d D03 full-sample main-grid audit rows; observed %d", expected_main_thresholds, nrow(main_global))
if (any(abs(main_global$threshold_numeric - expected_grid) > 1e-10)) abortf("D03 main threshold grid does not match primary +/- radius in 0.05 increments")
if (any(main_global$repo_month_rows != expected_rows_per_threshold)) abortf("D03 main-grid global audit has unexpected repo-month row counts")
if (any(main_global$repositories != expected_repositories)) abortf("D03 main-grid global audit has unexpected repository counts")

selected_file_diff <- diff(as.numeric(main_global$selected_file_rows))
selected_issue_diff <- diff(as.numeric(main_global$selected_issue_total))
if (any(selected_file_diff > 0)) abortf("D03 selected-file support increases as NPR threshold increases")
if (any(selected_issue_diff > 0)) abortf("D03 selected-issue support increases as NPR threshold increases")

primary_global <- main_global[abs(threshold_numeric - primary_threshold) <= 1e-12]
if (nrow(primary_global) != 1L) abortf("Expected exactly one primary row in D03 full-sample global audit")
strict_count_check(primary_global$selected_file_rows, expected_primary_selected_files, "primary selected files", strict_expected_counts)
strict_count_check(primary_global$selected_issue_total, expected_primary_issue_stock, "primary selected issue stock", strict_expected_counts)
write_csv(main_global[, .(
  threshold_id, threshold = threshold_numeric, comparison_operator, repo_month_rows, repositories,
  selected_file_rows, selected_issue_total
)], paths$threshold_input_audit)

# Select only the prespecified 21-point main grid and only the full sample.
main_panel <- data.table::copy(long_panel[sample_spec == "full_sample" & comparison_operator == ">"])
main_panel[, threshold_numeric := as.numeric(threshold)]
main_panel[, main_grid := vapply(threshold_numeric, function(x) any(abs(x - expected_grid) <= 1e-10), logical(1))]
main_panel <- main_panel[main_grid == TRUE]
if (nrow(main_panel) != expected_rows_per_threshold * expected_main_thresholds) {
  abortf("Unexpected D03 main-grid row count: expected %d, observed %d", expected_rows_per_threshold * expected_main_thresholds, nrow(main_panel))
}
if (data.table::uniqueN(main_panel$threshold_id) != expected_main_thresholds) abortf("D03 main panel does not contain exactly 21 threshold IDs")
if (any(main_panel$comparison_operator != ">")) abortf("G06 requires strict NPR > threshold")

# Each threshold must retain the same zero-inclusive full repo-month sample.
threshold_key_qc <- main_panel[, .(
  rows = .N,
  repositories = data.table::uniqueN(repo_id),
  duplicate_repo_time = .N - data.table::uniqueN(paste(repo_id, time_index, sep = "::")),
  selected_file_rows = sum(as.numeric(selected_file_count)),
  selected_issue_total = sum(as.numeric(selected_issue_total))
), by = .(threshold_id, threshold = threshold_numeric, threshold_role)]
data.table::setorder(threshold_key_qc, threshold)
if (any(threshold_key_qc$rows != expected_rows_per_threshold)) abortf("One or more G06 thresholds do not contain 1,954 rows")
if (any(threshold_key_qc$repositories != expected_repositories)) abortf("One or more G06 thresholds do not contain 167 repositories")
if (any(threshold_key_qc$duplicate_repo_time != 0L)) abortf("One or more G06 thresholds contain duplicate repo-month keys")
if (any(abs(threshold_key_qc$threshold - expected_grid) > 1e-10)) abortf("Threshold order/grid mismatch in D03 main panel")

# The long panel and global audit must agree on support at every threshold.
support_compare <- merge(
  threshold_key_qc,
  main_global[, .(
    threshold = threshold_numeric,
    audit_selected_file_rows = as.numeric(selected_file_rows),
    audit_selected_issue_total = as.numeric(selected_issue_total)
  )],
  by = "threshold", all = TRUE, sort = TRUE
)
if (nrow(support_compare) != expected_main_thresholds || anyNA(support_compare$threshold_id)) abortf("D03 main-panel/global-audit threshold reconciliation failed")
if (any(abs(support_compare$selected_file_rows - support_compare$audit_selected_file_rows) > 1e-12)) abortf("D03 selected-file totals disagree with global audit")
if (any(abs(support_compare$selected_issue_total - support_compare$audit_selected_issue_total) > 1e-12)) abortf("D03 selected-issue totals disagree with global audit")

# Join authoritative B06 velocity once across all threshold rows and audit every
# overlapping field. D03 remains authoritative for detector-localized outcomes.
log_message("INFO", "Reading B06 whole-Python velocity/covariate panel: %s", b06_panel_file)
b06 <- data.table::fread(b06_panel_file, na.strings = c("", "NA", "NaN"))
b06_required <- c(
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor", "log_lines_added_py_source",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
validate_columns(b06, b06_required, "B06")
strict_count_check(nrow(b06), expected_rows_per_threshold, "B06 rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(b06$repo_id), expected_repositories, "B06 repositories", strict_expected_counts)

main_panel[, `:=`(repo_id = as.integer(repo_id), time_index = as.integer(time_index))]
b06[, `:=`(repo_id = as.integer(repo_id), time_index = as.integer(time_index))]
if (anyNA(main_panel$repo_id) || anyNA(main_panel$time_index) || anyNA(b06$repo_id) || anyNA(b06$time_index)) abortf("repo_id/time_index must be integer-compatible and complete")
if (nrow(b06[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("B06 has duplicate repo-month keys")

join_compare_fields <- c(
  "repo_name", "dataset_source", "scope_role", "treatment_group", "time",
  "event", "event_index", "time_to_event", "is_treatment", "post_event", "cursor",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
b06_lookup_fields <- c("repo_id", "time_index", "log_lines_added_py_source", join_compare_fields)
b06_lookup <- data.table::copy(b06[, ..b06_lookup_fields])
for (field in setdiff(b06_lookup_fields, c("repo_id", "time_index"))) {
  data.table::setnames(b06_lookup, field, paste0("b06__", field))
}
rows_before_join <- nrow(main_panel)
main_panel <- merge(main_panel, b06_lookup, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
if (nrow(main_panel) != rows_before_join) abortf("B06 join changed G06 main-grid row count")
missing_velocity <- sum(is.na(main_panel$b06__log_lines_added_py_source))

join_audit_parts <- list(
  data.table::data.table(field = "rows_before_join", mismatches = 0L, observed = rows_before_join, expected = rows_before_join, status = "pass"),
  data.table::data.table(field = "rows_after_join", mismatches = 0L, observed = nrow(main_panel), expected = rows_before_join, status = ifelse(nrow(main_panel) == rows_before_join, "pass", "fail")),
  data.table::data.table(field = "missing_b06_velocity_rows", mismatches = missing_velocity, observed = missing_velocity, expected = 0L, status = ifelse(missing_velocity == 0L, "pass", "fail"))
)
for (field in join_compare_fields) {
  equal <- values_match(main_panel[[field]], main_panel[[paste0("b06__", field)]])
  mismatch_count <- sum(!equal)
  join_audit_parts[[length(join_audit_parts) + 1L]] <- data.table::data.table(
    field = field, mismatches = mismatch_count, observed = mismatch_count, expected = 0L,
    status = ifelse(mismatch_count == 0L, "pass", "fail")
  )
}
b06_join_audit <- data.table::rbindlist(join_audit_parts, use.names = TRUE, fill = TRUE)
write_csv(b06_join_audit, paths$b06_join_audit)
if (any(b06_join_audit$status == "fail")) abortf("B06 join/provenance audit failed: %s", paste(b06_join_audit[status == "fail", field], collapse = ", "))

main_panel[, log_lines_added_py_source := b06__log_lines_added_py_source]
drop_b06_columns <- grep("^b06__", names(main_panel), value = TRUE)
main_panel[, (drop_b06_columns) := NULL]

# Treatment/timing fields are threshold-invariant, so audit them once on the
# primary threshold and require the known full-sample counts.
primary_panel <- data.table::copy(main_panel[abs(threshold_numeric - primary_threshold) <= 1e-12])
if (nrow(primary_panel) != expected_rows_per_threshold) abortf("Primary G06 panel does not contain 1,954 rows")
primary_panel[, `:=`(
  treatment_group = as.integer(treatment_group),
  event_index = as.integer(event_index),
  time_index = as.integer(time_index)
)]
primary_panel[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
primary_panel[, legacy_cursor_flag := bool_to_int(cursor)]
primary_panel[, legacy_is_treatment := as.integer(replace(is_treatment, is.na(is_treatment), 0))]
primary_panel[, legacy_post_event := as.integer(replace(post_event, is.na(post_event), 0))]
primary_panel[, `:=`(
  mismatch_cursor = legacy_cursor_flag != absorbing_treated,
  mismatch_is_treatment = legacy_is_treatment != absorbing_treated,
  mismatch_post_event = legacy_post_event != absorbing_treated
)]
primary_panel[, legacy_mismatch_any := mismatch_cursor | mismatch_is_treatment | mismatch_post_event]
legacy_audit <- primary_panel[legacy_mismatch_any == TRUE, .(
  repo_id, repo_name, time, time_index, event, event_index, time_to_event,
  absorbing_treated, legacy_cursor = cursor, legacy_cursor_flag,
  legacy_is_treatment, legacy_post_event,
  mismatch_cursor, mismatch_is_treatment, mismatch_post_event,
  scope_role, treatment_group
)]
write_csv(legacy_audit, paths$legacy_audit)
strict_count_check(nrow(legacy_audit), expected_legacy_mismatch_rows, "legacy mismatch rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(legacy_audit$repo_id), expected_legacy_mismatch_repositories, "legacy mismatch repositories", strict_expected_counts)

primary_repo_count <- data.table::uniqueN(primary_panel$repo_id)
primary_treatment_repos <- data.table::uniqueN(primary_panel[treatment_group == 1L, repo_id])
primary_control_repos <- data.table::uniqueN(primary_panel[treatment_group == 0L, repo_id])
strict_count_check(primary_repo_count, expected_repositories, "repositories", strict_expected_counts)
strict_count_check(primary_treatment_repos, expected_treatment_repositories, "treatment repositories", strict_expected_counts)
strict_count_check(primary_control_repos, expected_control_repositories, "control repositories", strict_expected_counts)

# Calendar-gap audit is also threshold-invariant.
data.table::setorder(primary_panel, repo_id, time_index)
primary_panel[, previous_time_index := data.table::shift(time_index), by = repo_id]
primary_panel[, calendar_gap := time_index - previous_time_index]
calendar_gap_audit <- primary_panel[!is.na(previous_time_index) & calendar_gap != 1L, .(
  repo_id, repo_name, previous_time_index, time_index, calendar_gap, time
)]
write_csv(calendar_gap_audit, paths$calendar_gap_audit)

formula_text <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)

coefficients_all <- list()
diagnostics_all <- list()
instrument_all <- list()
support_all <- list()
summary_all <- list()
qc_all <- list()
models <- list()
model_failures <- data.table::data.table(
  threshold_id = character(), threshold = numeric(), primary_analysis = integer(),
  stage = character(), message = character()
)

threshold_table <- unique(main_panel[, .(threshold_id, threshold = threshold_numeric, threshold_role)])
data.table::setorder(threshold_table, threshold)

for (row_index in seq_len(nrow(threshold_table))) {
  threshold_id_value <- as.character(threshold_table$threshold_id[[row_index]])
  threshold_value <- as.numeric(threshold_table$threshold[[row_index]])
  threshold_role_value <- as.character(threshold_table$threshold_role[[row_index]])
  primary_analysis_value <- as.integer(abs(threshold_value - primary_threshold) <= 1e-12)

  panel <- data.table::copy(main_panel[threshold_id == threshold_id_value & abs(threshold_numeric - threshold_value) <= 1e-12])
  if (nrow(panel) != expected_rows_per_threshold) abortf("Threshold %.6f has %d rows", threshold_value, nrow(panel))
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("Duplicate repo-month rows at threshold %.6f", threshold_value)

  numeric_fields <- c(
    "repo_id", "time_index", "event_index", "treatment_group",
    "log_lines_added_py_source", "log1p_selected_issue_total", "selected_issue_total", "selected_file_count",
    "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
  )
  for (field in numeric_fields) panel[, (field) := suppressWarnings(as.numeric(get(field)))]
  if (anyNA(panel[, ..numeric_fields])) abortf("Missing/non-numeric GMM field at threshold %.6f", threshold_value)
  if (any(panel$selected_issue_total < 0) || any(panel$selected_file_count < 0) || any(panel$ncloc_py_sonarqube < 0)) abortf("Negative count/size at threshold %.6f", threshold_value)

  log_mismatch <- sum(abs(panel$log1p_selected_issue_total - log1p(panel$selected_issue_total)) > 1e-12)
  if (log_mismatch > 0L) abortf("log1p selected-issue mismatch at threshold %.6f", threshold_value)

  panel[, `:=`(
    repo_id = as.integer(repo_id),
    time_index = as.integer(time_index),
    event_index = as.integer(event_index),
    treatment_group = as.integer(treatment_group),
    log_ncloc_py_sonarqube = log1p(ncloc_py_sonarqube)
  )]
  panel[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]

  active <- exact_calendar_support(panel)
  active_rows <- nrow(active)
  active_repos <- data.table::uniqueN(active$repo_id)
  active_treatment_repos <- data.table::uniqueN(active[treatment_group == 1L, repo_id])
  active_control_repos <- data.table::uniqueN(active[treatment_group == 0L, repo_id])
  active_post_rows <- nrow(active[absorbing_treated == 1L])
  if (active_rows != expected_active_rows || active_repos != expected_active_repositories) {
    abortf("Exact-calendar support mismatch at threshold %.6f: rows=%d repos=%d", threshold_value, active_rows, active_repos)
  }
  if (active_treatment_repos != expected_active_treatment_repositories || active_control_repos != expected_active_control_repositories) {
    abortf("Active treatment/control repository mismatch at threshold %.6f", threshold_value)
  }

  source_variation_repos <- panel[, .(quality_unique = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][quality_unique > 1L, .N]
  active_variation_repos <- active[, .(quality_unique = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][quality_unique > 1L, .N]
  support_row <- data.table::data.table(
    threshold_id = threshold_id_value,
    threshold = threshold_value,
    threshold_role = threshold_role_value,
    primary_analysis = primary_analysis_value,
    source_rows = nrow(panel),
    source_repositories = data.table::uniqueN(panel$repo_id),
    active_rows = active_rows,
    active_repositories = active_repos,
    active_treatment_repositories = active_treatment_repos,
    active_control_repositories = active_control_repos,
    active_post_treatment_rows = active_post_rows,
    selected_file_rows = sum(panel$selected_file_count),
    selected_issue_total = sum(panel$selected_issue_total),
    repo_months_with_selected_files = nrow(panel[selected_file_count > 0]),
    repo_months_with_positive_issue_stock = nrow(panel[selected_issue_total > 0]),
    active_rows_with_positive_issue_stock = nrow(active[selected_issue_total > 0]),
    zero_issue_share_source = mean(panel$selected_issue_total == 0),
    zero_issue_share_active = mean(active$selected_issue_total == 0),
    repositories_with_within_quality_variation_source = source_variation_repos,
    repositories_with_within_quality_variation_active = active_variation_repos
  )
  support_all[[threshold_id_value]] <- support_row

  estimation_data <- panel[, .(
    repo_id, time_index, log_lines_added_py_source, log1p_selected_issue_total,
    absorbing_treated, log_ncloc_py_sonarqube,
    log_age, log_contributors, log_stars, log_issues
  )]
  data.table::setorder(estimation_data, repo_id, time_index)
  pdata <- plm::pdata.frame(as.data.frame(estimation_data), index = c("repo_id", "time_index"), drop.index = FALSE, row.names = FALSE)
  formula <- stats::as.formula(formula_text)

  log_message("INFO", "Fitting NPR threshold %.6f (%s)", threshold_value, threshold_id_value)
  fit_capture <- capture_evaluation(
    plm::pgmm(
      formula,
      data = pdata,
      effect = "twoways",
      model = "twosteps",
      transformation = "d",
      collapse = FALSE
    )
  )

  if (fit_capture$error) {
    message_text <- fit_capture$value$message
    model_failures <- data.table::rbindlist(list(model_failures, data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      stage = "pgmm", message = message_text
    )), use.names = TRUE)
    if (primary_analysis_value == 1L) abortf("Primary-threshold pgmm failed: %s", message_text)

    diagnostics_all[[threshold_id_value]] <- failed_diagnostics(threshold_id_value, threshold_value, primary_analysis_value, message_text)
    instrument_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      model = "npr_threshold_quality_to_velocity", collapse = FALSE, instrument_specification = "lag(velocity,2)",
      minimum_calendar_support_rows = active_rows, minimum_calendar_support_repositories = active_repos,
      stats_nobs = NA_integer_, instrument_count = NA_integer_, instrument_ratio_denominator = active_repos,
      instrument_to_repository_ratio = NA_real_, instrument_proliferation_flag = NA,
      runtime_seconds = fit_capture$elapsed, warning_count = length(fit_capture$warnings),
      warning_messages = paste(fit_capture$warnings, collapse = " | "), fit_status = "failed"
    )
    summary_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, threshold_role = threshold_role_value,
      primary_analysis = primary_analysis_value, fit_status = "failed", estimate = NA_real_, std_error = NA_real_,
      conf_low = NA_real_, conf_high = NA_real_, p_value = NA_real_, significant = NA,
      failure_message = message_text
    )
    qc_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value,
      check = c("source_rows", "active_rows", "model_fit"),
      observed = c(nrow(panel), active_rows, NA_real_),
      expected = c(expected_rows_per_threshold, expected_active_rows, NA_real_),
      status = c("pass", "pass", "caution"),
      note = c("Full D03 repo-month sample.", "Exact calendar t-1/t-2 support.", paste0("Non-primary sparse-threshold pgmm failure: ", message_text))
    )
    next
  }

  summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
  if (summary_capture$error) {
    message_text <- summary_capture$value$message
    model_failures <- data.table::rbindlist(list(model_failures, data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      stage = "robust_summary", message = message_text
    )), use.names = TRUE)
    if (primary_analysis_value == 1L) abortf("Primary-threshold robust summary failed: %s", message_text)

    diagnostics_all[[threshold_id_value]] <- failed_diagnostics(threshold_id_value, threshold_value, primary_analysis_value, message_text)
    instrument_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      model = "npr_threshold_quality_to_velocity", collapse = FALSE, instrument_specification = "lag(velocity,2)",
      minimum_calendar_support_rows = active_rows, minimum_calendar_support_repositories = active_repos,
      stats_nobs = NA_integer_, instrument_count = NA_integer_, instrument_ratio_denominator = active_repos,
      instrument_to_repository_ratio = NA_real_, instrument_proliferation_flag = NA,
      runtime_seconds = fit_capture$elapsed + summary_capture$elapsed,
      warning_count = length(unique(c(fit_capture$warnings, summary_capture$warnings))),
      warning_messages = paste(unique(c(fit_capture$warnings, summary_capture$warnings)), collapse = " | "), fit_status = "failed"
    )
    summary_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, threshold_role = threshold_role_value,
      primary_analysis = primary_analysis_value, fit_status = "failed", estimate = NA_real_, std_error = NA_real_,
      conf_low = NA_real_, conf_high = NA_real_, p_value = NA_real_, significant = NA,
      failure_message = message_text
    )
    qc_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value,
      check = c("source_rows", "active_rows", "model_fit"),
      observed = c(nrow(panel), active_rows, NA_real_),
      expected = c(expected_rows_per_threshold, expected_active_rows, NA_real_),
      status = c("pass", "pass", "caution"),
      note = c("Full D03 repo-month sample.", "Exact calendar t-1/t-2 support.", paste0("Non-primary sparse-threshold summary failure: ", message_text))
    )
    next
  }

  coefficient_capture <- capture_evaluation(
    extract_coefficients(summary_capture$value, threshold_id_value, threshold_value, threshold_role_value, confidence_level, primary_threshold)
  )
  if (coefficient_capture$error) {
    message_text <- coefficient_capture$value$message
    model_failures <- data.table::rbindlist(list(model_failures, data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      stage = "coefficient_extraction", message = message_text
    )), use.names = TRUE)
    if (primary_analysis_value == 1L) abortf("Primary threshold coefficient extraction failed: %s", message_text)

    diagnostics_all[[threshold_id_value]] <- failed_diagnostics(threshold_id_value, threshold_value, primary_analysis_value, message_text)
    instrument_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      model = "npr_threshold_quality_to_velocity", collapse = FALSE, instrument_specification = "lag(velocity,2)",
      minimum_calendar_support_rows = active_rows, minimum_calendar_support_repositories = active_repos,
      stats_nobs = NA_integer_, instrument_count = NA_integer_, instrument_ratio_denominator = active_repos,
      instrument_to_repository_ratio = NA_real_, instrument_proliferation_flag = NA,
      runtime_seconds = fit_capture$elapsed + summary_capture$elapsed + coefficient_capture$elapsed,
      warning_count = length(unique(c(fit_capture$warnings, summary_capture$warnings, coefficient_capture$warnings))),
      warning_messages = paste(unique(c(fit_capture$warnings, summary_capture$warnings, coefficient_capture$warnings)), collapse = " | "),
      fit_status = "failed"
    )
    summary_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, threshold_role = threshold_role_value,
      primary_analysis = primary_analysis_value, fit_status = "failed", estimate = NA_real_, std_error = NA_real_,
      conf_low = NA_real_, conf_high = NA_real_, p_value = NA_real_, significant = NA,
      failure_message = message_text
    )
    qc_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value,
      check = c("source_rows", "active_rows", "model_fit"),
      observed = c(nrow(panel), active_rows, NA_real_),
      expected = c(expected_rows_per_threshold, expected_active_rows, NA_real_),
      status = c("pass", "pass", "caution"),
      note = c("Full D03 repo-month sample.", "Exact calendar t-1/t-2 support.", paste0("Non-primary coefficient extraction failure: ", message_text))
    )
    next
  }

  coefficients <- coefficient_capture$value
  primary_term_row <- coefficients[is_primary_interaction_term == TRUE]
  if (nrow(primary_term_row) != 1L) {
    message_text <- sprintf("Expected exactly one lagged NPR-quality coefficient; observed %d", nrow(primary_term_row))
    if (primary_analysis_value == 1L) abortf("Primary threshold coefficient extraction failed: %s", message_text)
    model_failures <- data.table::rbindlist(list(model_failures, data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      stage = "coefficient_extraction", message = message_text
    )), use.names = TRUE)
    diagnostics_all[[threshold_id_value]] <- failed_diagnostics(threshold_id_value, threshold_value, primary_analysis_value, message_text)
    instrument_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
      model = "npr_threshold_quality_to_velocity", collapse = FALSE, instrument_specification = "lag(velocity,2)",
      minimum_calendar_support_rows = active_rows, minimum_calendar_support_repositories = active_repos,
      stats_nobs = NA_integer_, instrument_count = NA_integer_, instrument_ratio_denominator = active_repos,
      instrument_to_repository_ratio = NA_real_, instrument_proliferation_flag = NA,
      runtime_seconds = fit_capture$elapsed + summary_capture$elapsed + coefficient_capture$elapsed,
      warning_count = length(unique(c(fit_capture$warnings, summary_capture$warnings, coefficient_capture$warnings))),
      warning_messages = paste(unique(c(fit_capture$warnings, summary_capture$warnings, coefficient_capture$warnings)), collapse = " | "),
      fit_status = "failed"
    )
    summary_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value, threshold_role = threshold_role_value,
      primary_analysis = primary_analysis_value, fit_status = "failed", estimate = NA_real_, std_error = NA_real_,
      conf_low = NA_real_, conf_high = NA_real_, p_value = NA_real_, significant = NA, failure_message = message_text
    )
    qc_all[[threshold_id_value]] <- data.table::data.table(
      threshold_id = threshold_id_value, threshold = threshold_value,
      check = c("source_rows", "active_rows", "model_fit"), observed = c(nrow(panel), active_rows, NA_real_),
      expected = c(expected_rows_per_threshold, expected_active_rows, NA_real_), status = c("pass", "pass", "caution"),
      note = c("Full D03 repo-month sample.", "Exact calendar t-1/t-2 support.", paste0("Non-primary primary-term extraction failure: ", message_text))
    )
    next
  }

  all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings))
  diagnostics <- data.table::rbindlist(list(
    extract_htest(summary_capture$value$sargan, threshold_id_value, threshold_value, "sargan", primary_analysis_value),
    extract_htest(summary_capture$value$m1, threshold_id_value, threshold_value, "ar1", primary_analysis_value),
    extract_htest(summary_capture$value$m2, threshold_id_value, threshold_value, "ar2", primary_analysis_value)
  ), use.names = TRUE, fill = TRUE)
  diagnostics[, `:=`(
    warning_count = length(all_warnings),
    warning_messages = paste(all_warnings, collapse = " | ")
  )]

  dimensions <- extract_dimensions(fit_capture$value)
  instrument_ratio <- if (is.finite(dimensions$instrument_count) && active_repos > 0L) dimensions$instrument_count / active_repos else NA_real_
  instrument <- data.table::data.table(
    threshold_id = threshold_id_value, threshold = threshold_value, primary_analysis = primary_analysis_value,
    model = "npr_threshold_quality_to_velocity", collapse = FALSE, instrument_specification = "lag(velocity,2)",
    minimum_calendar_support_rows = active_rows, minimum_calendar_support_repositories = active_repos,
    stats_nobs = dimensions$stats_nobs, instrument_count = dimensions$instrument_count,
    instrument_columns_min = dimensions$instrument_columns_min, instrument_columns_max = dimensions$instrument_columns_max,
    instrument_columns_unique = dimensions$instrument_columns_unique,
    instrument_ratio_denominator = active_repos, instrument_to_repository_ratio = instrument_ratio,
    instrument_proliferation_flag = is.finite(instrument_ratio) && instrument_ratio >= 1,
    pgmm_internal_matrix_rows = dimensions$pgmm_internal_matrix_rows,
    pgmm_internal_repository_slots = dimensions$pgmm_internal_repository_slots,
    runtime_seconds = fit_capture$elapsed + summary_capture$elapsed,
    warning_count = length(all_warnings), warning_messages = paste(all_warnings, collapse = " | "),
    fit_status = "success"
  )

  diag_missing <- diagnostics[status != "available", .N]
  ar1_p <- diagnostics[diagnostic == "ar1", p_value][1L]
  ar2_p <- diagnostics[diagnostic == "ar2", p_value][1L]
  sargan_p <- diagnostics[diagnostic == "sargan", p_value][1L]

  threshold_qc <- data.table::data.table(
    threshold_id = threshold_id_value,
    threshold = threshold_value,
    check = c(
      "source_rows", "source_repositories", "active_rows", "active_repositories",
      "stats_nobs_matches_active_rows", "primary_term_rows", "diagnostics_available",
      "ar1_expected_pattern", "ar2_no_second_order_serial_correlation", "sargan_overidentification",
      "model_warning_count", "instrument_ratio"
    ),
    observed = c(
      nrow(panel), data.table::uniqueN(panel$repo_id), active_rows, active_repos,
      dimensions$stats_nobs, nrow(primary_term_row), diag_missing,
      ar1_p, ar2_p, sargan_p, length(all_warnings), instrument_ratio
    ),
    expected = c(
      expected_rows_per_threshold, expected_repositories, expected_active_rows, expected_active_repositories,
      expected_active_rows, 1, 0, NA, NA, NA, 0, NA
    ),
    status = c(
      ifelse(nrow(panel) == expected_rows_per_threshold, "pass", "fail"),
      ifelse(data.table::uniqueN(panel$repo_id) == expected_repositories, "pass", "fail"),
      ifelse(active_rows == expected_active_rows, "pass", "fail"),
      ifelse(active_repos == expected_active_repositories, "pass", "fail"),
      ifelse(is.finite(dimensions$stats_nobs) && dimensions$stats_nobs == expected_active_rows, "pass", "fail"),
      ifelse(nrow(primary_term_row) == 1L, "pass", "fail"),
      ifelse(diag_missing == 0L, "pass", "fail"),
      ifelse(is.finite(ar1_p) && ar1_p < 0.05, "pass", "caution"),
      ifelse(is.finite(ar2_p) && ar2_p >= 0.05, "pass", "caution"),
      ifelse(is.finite(sargan_p) && sargan_p >= 0.05, "pass", "caution"),
      ifelse(length(all_warnings) == 0L, "pass", "caution"),
      ifelse(is.finite(instrument_ratio) && instrument_ratio < 1, "pass", "caution")
    ),
    note = c(
      "Full D03 repo-month sample.", "Full-sample repository membership.",
      "Exact calendar t-1/t-2 support.", "Exact-calendar active repositories.",
      "pgmm N should equal exact-calendar support.", "Exactly one lagged NPR-quality coefficient.",
      "Sargan, AR(1), and AR(2) should be returned.", "Difference-GMM commonly yields AR(1).",
      "AR(2) p<.05 cautions lag-instrument validity.", "Sargan p<.05 cautions overidentification validity.",
      "Model warnings are retained for review.", "Instrument count should remain below active repository count."
    )
  )

  coefficients_all[[threshold_id_value]] <- coefficients
  diagnostics_all[[threshold_id_value]] <- diagnostics
  instrument_all[[threshold_id_value]] <- instrument
  summary_all[[threshold_id_value]] <- data.table::data.table(
    threshold_id = threshold_id_value,
    threshold = threshold_value,
    threshold_role = threshold_role_value,
    primary_analysis = primary_analysis_value,
    fit_status = "success",
    estimate = primary_term_row$estimate[[1L]],
    std_error = primary_term_row$std_error[[1L]],
    conf_low = primary_term_row$conf_low[[1L]],
    conf_high = primary_term_row$conf_high[[1L]],
    p_value = primary_term_row$p_value[[1L]],
    significant = primary_term_row$significant[[1L]],
    failure_message = ""
  )
  qc_all[[threshold_id_value]] <- threshold_qc
  models[[threshold_id_value]] <- fit_capture$value
}

coefficients_output <- if (length(coefficients_all)) data.table::rbindlist(coefficients_all, use.names = TRUE, fill = TRUE) else data.table::data.table()
diagnostics_output <- data.table::rbindlist(diagnostics_all, use.names = TRUE, fill = TRUE)
instrument_output <- data.table::rbindlist(instrument_all, use.names = TRUE, fill = TRUE)
support_output <- data.table::rbindlist(support_all, use.names = TRUE, fill = TRUE)
summary_output <- data.table::rbindlist(summary_all, use.names = TRUE, fill = TRUE)
qc_output <- data.table::rbindlist(qc_all, use.names = TRUE, fill = TRUE)

data.table::setorder(support_output, threshold)
data.table::setorder(summary_output, threshold)
data.table::setorder(diagnostics_output, threshold, diagnostic)
data.table::setorder(instrument_output, threshold)
data.table::setorder(qc_output, threshold, check)

# Require one summary/support row for every prespecified threshold even if a
# non-primary sparse model failed.
if (nrow(summary_output) != expected_main_thresholds) abortf("G06 threshold summary does not contain exactly 21 rows")
if (nrow(support_output) != expected_main_thresholds) abortf("G06 support output does not contain exactly 21 rows")
if (any(abs(summary_output$threshold - expected_grid) > 1e-10)) abortf("G06 result threshold grid is incomplete or out of order")

# Exact E02 full-sample reproduction at the primary NPR threshold.
e02_reference <- data.table::fread(e02_reference_coefficients_file, na.strings = c("", "NA", "NaN"))
validate_columns(e02_reference, c("sample_spec", "term", "estimate", "std_error", "p_value", "is_primary_interaction_term"), "E02 coefficients")
e02_primary <- e02_reference[
  sample_spec == "full_sample" &
    bool_to_int(is_primary_interaction_term) == 1L &
    term == "lag(log1p_selected_issue_total, 1)"
]
if (nrow(e02_primary) != 1L) abortf("Expected exactly one E02 full-sample primary NPR-quality coefficient")
g06_primary <- summary_output[abs(threshold - primary_threshold) <= 1e-12 & fit_status == "success"]
if (nrow(g06_primary) != 1L) abortf("Expected exactly one successful G06 primary-threshold result")
reproduction <- data.table::data.table(
  metric = c("estimate", "std_error", "p_value"),
  e02_full_sample = c(e02_primary$estimate[[1L]], e02_primary$std_error[[1L]], e02_primary$p_value[[1L]]),
  g06_primary = c(g06_primary$estimate[[1L]], g06_primary$std_error[[1L]], g06_primary$p_value[[1L]])
)
reproduction[, absolute_difference := abs(as.numeric(e02_full_sample) - as.numeric(g06_primary))]
reproduction[, tolerance := reference_tolerance]
reproduction[, status := ifelse(absolute_difference <= reference_tolerance, "pass", "fail")]
if (any(reproduction$status == "fail")) abortf("G06 primary threshold failed exact E02 full-sample reproduction")

# Any successful-threshold hard QC failure is fatal. Model failures at
# non-primary sparse thresholds are retained as cautions by design.
failed_qc <- qc_output[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("G06 threshold GMM QC contains hard failures: %s", paste(paste(failed_qc$threshold_id, failed_qc$check, sep = "/"), collapse = ", "))
}

# Merge support diagnostics into the one-row-per-threshold result file to make
# the downstream G07 figure and reviewer-facing support checks straightforward.
summary_output <- merge(
  summary_output,
  support_output[, .(
    threshold_id,
    selected_file_rows,
    selected_issue_total,
    repo_months_with_selected_files,
    repo_months_with_positive_issue_stock,
    active_rows_with_positive_issue_stock,
    zero_issue_share_source,
    zero_issue_share_active,
    repositories_with_within_quality_variation_source,
    repositories_with_within_quality_variation_active
  )],
  by = "threshold_id", all.x = TRUE, sort = FALSE
)
data.table::setorder(summary_output, threshold)

write_csv(coefficients_output, paths$coefficients)
write_csv(summary_output, paths$primary_summary)
write_csv(diagnostics_output, paths$diagnostics)
write_csv(instrument_output, paths$instrument_qc)
write_csv(support_output, paths$support)
write_csv(reproduction, paths$reproduction)
write_csv(model_failures, paths$model_failures)
write_csv(qc_output, paths$qc)
saveRDS(models, paths$models)

run_finished <- Sys.time()
metadata <- data.table::data.table(
  section = c(
    rep("run", 14), rep("definition", 17), rep("qc", 5), rep("software", 3)
  ),
  metric = c(
    "run_prefix", "implementation_version", "started", "finished", "runtime_seconds",
    "input_file", "input_sha256", "b06_panel_file", "b06_panel_sha256",
    "d03_summary_file", "d03_summary_sha256", "d03_global_audit_file", "d03_global_audit_sha256",
    "e02_reference_coefficients_file",
    "analysis_scope", "detector", "npr_metric", "sample_spec", "primary_threshold",
    "threshold_radius", "threshold_step", "main_threshold_count", "legacy_anchor_policy",
    "comparison_operator", "localized_quality", "velocity", "treatment", "size_control",
    "other_controls", "gmm_specification", "formula",
    "thresholds_successful", "thresholds_failed", "failed_hard_qc", "caution_qc_rows", "e02_reproduction_status",
    "R", "data.table", "plm"
  ),
  value = c(
    "run-x-g06", implementation_version,
    format(run_started, "%Y-%m-%d %H:%M:%S %Z"), format(run_finished, "%Y-%m-%d %H:%M:%S %Z"),
    as.numeric(difftime(run_finished, run_started, units = "secs")),
    input_file, sha256_file(input_file), b06_panel_file, sha256_file(b06_panel_file),
    d03_summary_file, sha256_file(d03_summary_file), d03_global_audit_file, sha256_file(d03_global_audit_file),
    e02_reference_coefficients_file,
    "npr_threshold_sensitivity_quality_to_velocity", "AGCDetector_NPR", "file_npr_fun_space_by_token_weighted", "full_sample",
    sprintf("%.6f", primary_threshold), sprintf("%.2f", threshold_radius), sprintf("%.2f", threshold_step), expected_main_thresholds,
    "exclude D03 legacy anchor 1.5183 from the main sweep", ">", "log1p_selected_issue_total", "log_lines_added_py_source",
    "absorbing_treated", "log1p(ncloc_py_sonarqube)", "log_age|log_contributors|log_stars|log_issues",
    "twoways; twosteps; difference GMM; lag(velocity,2); collapse=FALSE", formula_text,
    sum(summary_output$fit_status == "success"), sum(summary_output$fit_status != "success"), nrow(failed_qc),
    nrow(qc_output[status == "caution"]), ifelse(all(reproduction$status == "pass"), "PASS", "FAIL"),
    R.version.string, safe_package_version("data.table"), safe_package_version("plm")
  )
)
write_csv(metadata, paths$metadata)

log_message(
  "INFO",
  "Completed run-x-g06 %s: thresholds=%d; successful=%d; failed=%d; significant=%d; cautions=%d",
  implementation_version, nrow(summary_output), sum(summary_output$fit_status == "success"),
  sum(summary_output$fit_status != "success"),
  sum(summary_output$significant == TRUE, na.rm = TRUE), nrow(qc_output[status == "caution"])
)
