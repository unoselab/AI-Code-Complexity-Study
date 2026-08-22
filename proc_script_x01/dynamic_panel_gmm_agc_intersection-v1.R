#!/usr/bin/env Rscript

# ============================================================
# run-x-e05 v1: Dynamic panel GMM for NPR-intersection-ML quality burden
# ============================================================
#
# Purpose:
#   Estimate whether unresolved Python static-analysis issue burden localized
#   to the intersection of the frozen NPR-selected and ML-selected file sets predicts
#   lower subsequent whole-Python development velocity.
#
# Frozen intersection contract:
#   NPR file rule: file_npr_fun_space_by_token_weighted > 1.571637
#   ML file rule:  file_ml_agc_share_space_by_token_weighted > 0.50
#   Intersection rule: NPR selected AND ML selected
#   Double count:  a file selected by both detectors contributes once
#
# GMM model:
#   Velocity_t ~ Velocity_{t-1} + IntersectionQuality_{t-1} + treatment_t + controls_t
#   GMM instrument: Velocity_{t-2}
#   effect=twoways, model=twosteps, transformation=d, collapse=FALSE
#
# Inputs:
#   - E05 intersection repo-month panel produced by build_agc_detector_intersection_gmm_panel-v1.py
#   - B06 authoritative whole-Python velocity/covariate panel
#
# This script is self-contained. It reuses the validated E02/E03 estimator and
# QC design but does not call a prior experiment script.
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
  value <- args[[name]]
  if (is.null(value)) return(as.integer(default))
  result <- suppressWarnings(as.integer(value))
  if (is.na(result)) abortf("Argument --%s must be integer-compatible", gsub("_", "-", name, fixed = TRUE))
  result
}

as_numeric_arg <- function(args, name, default) {
  value <- args[[name]]
  if (is.null(value)) return(as.numeric(default))
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

safe_package_version <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) return(NA_character_)
  as.character(utils::packageVersion(package))
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing) > 0L) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

sha256_file <- function(path) {
  if (is.na(path) || !nzchar(path) || !file.exists(path)) return(NA_character_)
  command <- Sys.which("sha256sum")
  if (!nzchar(command)) return(NA_character_)
  output <- suppressWarnings(system2(command, path, stdout = TRUE, stderr = TRUE))
  if (length(output) == 0L) return(NA_character_)
  strsplit(output[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_csv <- function(data, path) {
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
  use_numeric <- is.na(result) & !is.na(numeric_value)
  result[use_numeric] <- as.integer(numeric_value[use_numeric] != 0)
  result[is.na(result)] <- 0L
  result
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
}

strict_count_check <- function(actual, expected, label, strict) {
  if (identical(as.integer(actual), as.integer(expected))) return(invisible(TRUE))
  text <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, actual)
  if (strict) abortf("%s", text) else log_message("WARNING", "%s", text)
  invisible(FALSE)
}

coerce_numeric_with_audit <- function(data, columns) {
  rows <- vector("list", length(columns))
  for (idx in seq_along(columns)) {
    column <- columns[[idx]]
    before <- data[[column]]
    before_missing <- is.na(before) | trimws(as.character(before)) == ""
    converted <- suppressWarnings(as.numeric(before))
    generated_na <- sum(!before_missing & is.na(converted))
    data[, (column) := converted]
    rows[[idx]] <- data.table::data.table(
      column = column,
      missing_before = sum(before_missing),
      missing_after = sum(is.na(converted)),
      coercion_generated_na = generated_na
    )
  }
  data.table::rbindlist(rows)
}

extract_htest <- function(test, model_name, diagnostic_name) {
  if (is.null(test)) {
    return(data.table::data.table(
      model = model_name, diagnostic = diagnostic_name,
      statistic = NA_real_, parameter = NA_real_, p_value = NA_real_,
      method = NA_character_, status = "missing"
    ))
  }
  statistic <- if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_
  parameter <- if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_
  p_value <- if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_
  method <- if (!is.null(test$method)) as.character(test$method) else NA_character_
  data.table::data.table(
    model = model_name, diagnostic = diagnostic_name,
    statistic = statistic, parameter = parameter, p_value = p_value,
    method = method, status = ifelse(is.finite(statistic) && is.finite(p_value), "available", "missing")
  )
}

extract_coefficients <- function(summary_object, model_name, direction, primary_term, confidence_level) {
  matrix <- as.matrix(summary_object$coefficients)
  if (is.null(matrix) || nrow(matrix) == 0L) abortf("No coefficient matrix returned")
  cn <- colnames(matrix)
  estimate_col <- which(tolower(cn) == "estimate")[1L]
  se_col <- grep("std\\.?[[:space:]]*error", cn, ignore.case = TRUE)[1L]
  p_col <- grep("pr\\(", cn, ignore.case = TRUE)[1L]
  if (is.na(estimate_col) || is.na(se_col)) abortf("Could not identify estimate/SE columns")
  estimate <- as.numeric(matrix[, estimate_col])
  std_error <- as.numeric(matrix[, se_col])
  p_value <- if (!is.na(p_col)) as.numeric(matrix[, p_col]) else 2 * stats::pnorm(-abs(estimate / std_error))
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  terms <- rownames(matrix)
  data.table::data.table(
    model = model_name,
    direction = direction,
    term = terms,
    estimate = estimate,
    std_error = std_error,
    conf_low = estimate - critical * std_error,
    conf_high = estimate + critical * std_error,
    p_value = p_value,
    significant = !is.na(p_value) & p_value < (1 - confidence_level),
    is_primary_interaction_term = terms == primary_term
  )
}

extract_model_dimensions <- function(model) {
  stats_nobs <- tryCatch(as.integer(stats::nobs(model)), error = function(e) NA_integer_)
  internal_rows <- NA_integer_
  repository_slots <- NA_integer_
  if (is.list(model$model)) {
    repository_slots <- length(model$model)
    row_counts <- vapply(model$model, function(x) if (is.null(dim(x))) 0L else nrow(x), integer(1))
    internal_rows <- sum(row_counts)
  }
  instrument_columns <- integer()
  if (is.list(model$W) && length(model$W) > 0L) {
    instrument_columns <- vapply(model$W, function(x) if (is.null(dim(x))) 0L else ncol(x), integer(1))
  }
  instrument_columns <- instrument_columns[instrument_columns > 0L]
  list(
    stats_nobs = stats_nobs,
    pgmm_internal_matrix_rows = internal_rows,
    pgmm_internal_repository_slots = repository_slots,
    instrument_columns_min = if (length(instrument_columns)) min(instrument_columns) else NA_integer_,
    instrument_columns_max = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_unique = if (length(instrument_columns)) paste(sort(unique(instrument_columns)), collapse = "|") else "",
    instrument_count_for_ratio = if (length(instrument_columns)) max(instrument_columns) else NA_integer_
  )
}

make_key <- function(repo_id, time_index) paste(repo_id, time_index, sep = "::")

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
b06_panel_file <- normalizePath(require_arg(args, "b06_panel_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_rows <- as_integer_arg(args, "expected_rows", 1954L)
expected_repositories <- as_integer_arg(args, "expected_repositories", 167L)
expected_treatment_repositories <- as_integer_arg(args, "expected_treatment_repositories", 63L)
expected_control_repositories <- as_integer_arg(args, "expected_control_repositories", 104L)
expected_active_rows <- as_integer_arg(args, "expected_active_rows", 1631L)
expected_active_repositories <- as_integer_arg(args, "expected_active_repositories", 146L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", 11L)
expected_legacy_mismatch_repositories <- as_integer_arg(args, "expected_legacy_mismatch_repositories", 3L)

if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1")
check_packages(c("data.table", "plm"))
suppressPackageStartupMessages(library(plm))
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  coefficients = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_coefficients.csv"),
  primary_summary = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_primary_summary.csv"),
  diagnostics = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_diagnostics.csv"),
  sample_qc = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_sample_qc.csv"),
  instrument_qc = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_instrument_qc.csv"),
  b06_join_audit = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_b06_join_audit.csv"),
  numeric_audit = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_numeric_coercion_audit.csv"),
  calendar_gap_audit = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_calendar_gap_audit.csv"),
  legacy_audit = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_legacy_flag_audit.csv"),
  qc = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_qc.csv"),
  metadata = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_run_metadata.csv"),
  models_rds = file.path(output_dir, "dynamic_panel_gmm_agc_intersection_models.rds")
)

run_started <- Sys.time()
log_message("INFO", "Reading E05 detector-intersection panel: %s", input_file)
intersection_panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
required_intersection <- c(
  "repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total",
  "npr_selected_file_rows", "ml_selected_file_rows",
  "intersection_selected_file_rows", "npr_threshold", "ml_threshold", "detector_intersection_rule"
)
validate_columns(intersection_panel, required_intersection, "E05 intersection panel")
strict_count_check(nrow(intersection_panel), expected_rows, "E05 intersection panel rows", strict_expected_counts)
if (data.table::uniqueN(intersection_panel[, .(repo_id, time_index)]) != nrow(intersection_panel)) abortf("E05 intersection panel has duplicate repo-month keys")
if (any(as.character(intersection_panel$detector_intersection_rule) != "NPR_primary_AND_ML_primary")) abortf("Unexpected intersection rule in E05 input")
if (any(abs(as.numeric(intersection_panel$npr_threshold) - 1.571637) > 1e-12)) abortf("Unexpected NPR threshold in E05 input")
if (any(abs(as.numeric(intersection_panel$ml_threshold) - 0.50) > 1e-12)) abortf("Unexpected ML threshold in E05 input")

log_message("INFO", "Reading B06 authoritative velocity/covariate panel: %s", b06_panel_file)
b06 <- data.table::fread(b06_panel_file, na.strings = c("", "NA", "NaN"))
b06_required <- c(
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event", "is_treatment",
  "post_event", "cursor", "log_lines_added_py_source", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues"
)
validate_columns(b06, b06_required, "B06")
strict_count_check(nrow(b06), expected_rows, "B06 rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(b06$repo_id), expected_repositories, "B06 repositories", strict_expected_counts)

intersection_panel[, `:=`(repo_id = as.integer(repo_id), time_index = as.integer(time_index))]
b06[, `:=`(repo_id = as.integer(repo_id), time_index = as.integer(time_index))]
if (anyNA(intersection_panel$repo_id) || anyNA(intersection_panel$time_index) || anyNA(b06$repo_id) || anyNA(b06$time_index)) abortf("repo_id/time_index must be integer-compatible and complete")
if (nrow(b06[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("B06 has duplicate repo-month keys")

b06_lookup <- data.table::copy(b06)
for (field in setdiff(names(b06_lookup), c("repo_id", "time_index"))) {
  data.table::setnames(b06_lookup, field, paste0("b06__", field))
}
rows_before_join <- nrow(intersection_panel)
panel <- merge(intersection_panel, b06_lookup, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
missing_velocity <- sum(is.na(panel$b06__log_lines_added_py_source))
join_audit <- data.table::data.table(
  check = c("rows_before_join", "rows_after_join", "missing_b06_velocity_rows"),
  observed = c(rows_before_join, nrow(panel), missing_velocity),
  expected = c(rows_before_join, rows_before_join, 0L),
  status = c("pass", ifelse(nrow(panel) == rows_before_join, "pass", "fail"), ifelse(missing_velocity == 0L, "pass", "fail"))
)
write_csv(join_audit, paths$b06_join_audit)
if (any(join_audit$status == "fail")) abortf("B06 join failed")

for (field in setdiff(b06_required, c("repo_id", "time_index"))) {
  panel[, (field) := get(paste0("b06__", field))]
}
panel[, (grep("^b06__", names(panel), value = TRUE)) := NULL]

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "is_treatment", "post_event", "log_lines_added_py_source", "log1p_selected_issue_total",
  "selected_issue_total", "selected_file_rows", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues"
)
numeric_audit <- coerce_numeric_with_audit(panel, numeric_columns)
write_csv(numeric_audit, paths$numeric_audit)
if (any(numeric_audit$coercion_generated_na > 0L)) abortf("Numeric coercion generated missing values")

panel[, `:=`(
  repo_id = as.integer(repo_id),
  time_index = as.integer(time_index),
  event_index = as.integer(event_index),
  treatment_group = as.integer(treatment_group)
)]
if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index) || anyNA(panel$treatment_group)) abortf("Core model indexes must be complete")
if (any(panel$ncloc_py_sonarqube < 0, na.rm = TRUE) || any(panel$selected_issue_total < 0, na.rm = TRUE) || any(panel$selected_file_rows < 0, na.rm = TRUE)) abortf("Negative count/size values found")
panel[, log_ncloc_py_sonarqube := log1p(ncloc_py_sonarqube)]

log_mismatches <- sum(abs(panel$log1p_selected_issue_total - log1p(panel$selected_issue_total)) > 1e-12, na.rm = TRUE)
if (log_mismatches > 0L) abortf("Intersection log1p outcome mismatch: %d rows", log_mismatches)

panel[, event_time_normalized := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
panel[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
panel[, legacy_cursor_flag := bool_to_int(cursor)]
panel[, legacy_is_treatment := as.integer(replace(is_treatment, is.na(is_treatment), 0))]
panel[, legacy_post_event := as.integer(replace(post_event, is.na(post_event), 0))]
panel[, `:=`(
  mismatch_cursor = legacy_cursor_flag != absorbing_treated,
  mismatch_is_treatment = legacy_is_treatment != absorbing_treated,
  mismatch_post_event = legacy_post_event != absorbing_treated
)]
panel[, legacy_mismatch_any := mismatch_cursor | mismatch_is_treatment | mismatch_post_event]

repo_count <- data.table::uniqueN(panel$repo_id)
treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])
strict_count_check(repo_count, expected_repositories, "repositories", strict_expected_counts)
strict_count_check(treatment_repos, expected_treatment_repositories, "treatment repositories", strict_expected_counts)
strict_count_check(control_repos, expected_control_repositories, "control repositories", strict_expected_counts)

duplicate_rows <- panel[, .N, by = .(repo_id, time_index)][N > 1L]
role_mismatch <- panel[(scope_role == "treatment" & treatment_group != 1L) | (scope_role == "control" & treatment_group != 0L)]
control_event_errors <- panel[treatment_group == 0L & event_index != 0L]
treatment_event_errors <- panel[treatment_group == 1L & event_index <= 0L]
timing_errors <- panel[treatment_group == 1L & (is.na(time_to_event) | as.integer(time_to_event) != event_time_normalized)]
if (nrow(duplicate_rows) > 0L || nrow(role_mismatch) > 0L || nrow(control_event_errors) > 0L || nrow(treatment_event_errors) > 0L || nrow(timing_errors) > 0L) abortf("Panel/treatment-timing invariant failed")

model_fields <- c(
  "log_lines_added_py_source", "log1p_selected_issue_total", "log_ncloc_py_sonarqube",
  "log_age", "log_contributors", "log_stars", "log_issues"
)
missing_model_rows <- panel[!stats::complete.cases(panel[, ..model_fields])]
nonfinite_model_rows <- panel[!apply(as.data.frame(panel[, ..model_fields]), 1L, function(row) all(is.finite(row)))]
if (nrow(missing_model_rows) > 0L || nrow(nonfinite_model_rows) > 0L) abortf("Missing/non-finite GMM fields")

legacy_audit <- panel[legacy_mismatch_any == TRUE, .(
  repo_id, repo_name, time, time_index, event, event_index, time_to_event,
  event_time_normalized, absorbing_treated, legacy_cursor = cursor,
  legacy_cursor_flag, legacy_is_treatment, legacy_post_event,
  mismatch_cursor, mismatch_is_treatment, mismatch_post_event,
  scope_role, treatment_group
)]
write_csv(legacy_audit, paths$legacy_audit)
legacy_mismatch_rows <- nrow(legacy_audit)
legacy_mismatch_repositories <- data.table::uniqueN(legacy_audit$repo_id)
strict_count_check(legacy_mismatch_rows, expected_legacy_mismatch_rows, "legacy mismatch rows", strict_expected_counts)
strict_count_check(legacy_mismatch_repositories, expected_legacy_mismatch_repositories, "legacy mismatch repositories", strict_expected_counts)

data.table::setorder(panel, repo_id, time_index)
panel[, previous_time_index := data.table::shift(time_index), by = repo_id]
panel[, calendar_gap := time_index - previous_time_index]
calendar_gap_audit <- panel[!is.na(previous_time_index) & calendar_gap != 1L, .(
  repo_id, repo_name, previous_time_index, time_index, calendar_gap, time
)]
write_csv(calendar_gap_audit, paths$calendar_gap_audit)

key_set <- unique(make_key(panel$repo_id, panel$time_index))
panel[, has_exact_lag1 := make_key(repo_id, time_index - 1L) %in% key_set]
panel[, has_exact_lag2 := make_key(repo_id, time_index - 2L) %in% key_set]
active_panel <- panel[has_exact_lag1 & has_exact_lag2]
active_rows <- nrow(active_panel)
active_repos <- data.table::uniqueN(active_panel$repo_id)
active_treatment_repos <- data.table::uniqueN(active_panel[treatment_group == 1L, repo_id])
active_control_repos <- data.table::uniqueN(active_panel[treatment_group == 0L, repo_id])
active_post_rows <- nrow(active_panel[absorbing_treated == 1L])
strict_count_check(active_rows, expected_active_rows, "exact-calendar active rows", strict_expected_counts)
strict_count_check(active_repos, expected_active_repositories, "active repositories", strict_expected_counts)

quality_nonzero_rows <- nrow(panel[selected_issue_total > 0])
quality_zero_share <- mean(panel$selected_issue_total == 0)
quality_variation_repos <- panel[, .(quality_unique = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][quality_unique > 1L, .N]
active_quality_zero_share <- mean(active_panel$selected_issue_total == 0)
active_quality_variation_repos <- active_panel[, .(quality_unique = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][quality_unique > 1L, .N]

formula_text <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)
model_name <- "agc_intersection_quality_to_velocity"
primary_term <- "lag(log1p_selected_issue_total, 1)"
direction <- "IntersectionQuality_{t-1} -> Velocity_t"

estimation_data <- panel[, .(
  repo_id, time_index, log_lines_added_py_source, log1p_selected_issue_total,
  absorbing_treated, log_ncloc_py_sonarqube, log_age, log_contributors, log_stars, log_issues
)]
pdata <- plm::pdata.frame(estimation_data, index = c("repo_id", "time_index"), drop.index = FALSE, row.names = FALSE)
formula <- stats::as.formula(formula_text)
log_message("INFO", "Fitting NPR-intersection-ML localized quality -> velocity GMM")
fit_capture <- capture_evaluation(plm::pgmm(
  formula, data = pdata, effect = "twoways", model = "twosteps", transformation = "d", collapse = FALSE
))
if (fit_capture$error) abortf("GMM model failed: %s", fit_capture$value$message)
summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
if (summary_capture$error) abortf("Robust GMM summary failed: %s", summary_capture$value$message)
all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings))

coefficients <- extract_coefficients(summary_capture$value, model_name, direction, primary_term, confidence_level)
write_csv(coefficients, paths$coefficients)
primary_summary <- coefficients[is_primary_interaction_term == TRUE]
if (nrow(primary_summary) != 1L) abortf("Expected exactly one intersection-quality primary coefficient")
write_csv(primary_summary, paths$primary_summary)

diagnostics <- data.table::rbindlist(list(
  extract_htest(summary_capture$value$sargan, model_name, "sargan"),
  extract_htest(summary_capture$value$m1, model_name, "ar1"),
  extract_htest(summary_capture$value$m2, model_name, "ar2")
), use.names = TRUE, fill = TRUE)
diagnostics[, `:=`(robust_summary = TRUE, warning_count = length(all_warnings), warning_messages = paste(all_warnings, collapse = " | "))]
write_csv(diagnostics, paths$diagnostics)

dimensions <- extract_model_dimensions(fit_capture$value)
instrument_ratio <- if (is.finite(dimensions$instrument_count_for_ratio) && active_repos > 0L) dimensions$instrument_count_for_ratio / active_repos else NA_real_
instrument_qc <- data.table::data.table(
  model = model_name,
  collapse = FALSE,
  instrument_specification = "lag(velocity,2)",
  minimum_calendar_support_rows = active_rows,
  minimum_calendar_support_repositories = active_repos,
  stats_nobs = dimensions$stats_nobs,
  active_gmm_repositories = active_repos,
  active_gmm_treatment_repositories = active_treatment_repos,
  active_gmm_control_repositories = active_control_repos,
  instrument_columns_min = dimensions$instrument_columns_min,
  instrument_columns_max = dimensions$instrument_columns_max,
  instrument_columns_unique = dimensions$instrument_columns_unique,
  instrument_count_for_ratio = dimensions$instrument_count_for_ratio,
  instrument_ratio_denominator = active_repos,
  instrument_to_repository_ratio = instrument_ratio,
  instrument_proliferation_flag = is.finite(instrument_ratio) && instrument_ratio >= 1,
  runtime_seconds = fit_capture$elapsed + summary_capture$elapsed,
  warning_count = length(all_warnings),
  warning_messages = paste(all_warnings, collapse = " | ")
)
write_csv(instrument_qc, paths$instrument_qc)

sample_qc <- data.table::data.table(
  metric = c(
    "source_rows", "source_repositories", "treatment_repositories", "control_repositories",
    "selected_file_rows", "selected_issue_stock", "repo_months_with_selected_files",
    "repo_months_with_positive_selected_issue_stock", "selected_issue_zero_share",
    "repositories_with_within_selected_quality_variation", "active_selected_issue_zero_share",
    "active_repositories_with_within_selected_quality_variation", "exact_t1_t2_support_rows",
    "active_gmm_repositories", "active_gmm_treatment_repositories", "active_gmm_control_repositories",
    "active_gmm_post_treatment_rows", "stats_nobs", "legacy_mismatch_rows",
    "legacy_mismatch_repositories", "calendar_gap_transitions", "log1p_recomputation_mismatches"
  ),
  value = c(
    nrow(panel), repo_count, treatment_repos, control_repos,
    sum(panel$selected_file_rows), sum(panel$selected_issue_total), nrow(panel[selected_file_rows > 0]),
    quality_nonzero_rows, quality_zero_share, quality_variation_repos, active_quality_zero_share,
    active_quality_variation_repos, active_rows, active_repos, active_treatment_repos, active_control_repos, active_post_rows,
    dimensions$stats_nobs, legacy_mismatch_rows, legacy_mismatch_repositories,
    nrow(calendar_gap_audit), log_mismatches
  )
)
write_csv(sample_qc, paths$sample_qc)

primary_rows <- nrow(primary_summary)
diagnostic_missing <- diagnostics[status != "available", .N]
ar1_p <- diagnostics[diagnostic == "ar1", p_value][1L]
ar2_p <- diagnostics[diagnostic == "ar2", p_value][1L]
sargan_p <- diagnostics[diagnostic == "sargan", p_value][1L]
qc <- data.table::data.table(
  check = c(
    "source_rows", "source_repositories", "treatment_repositories", "control_repositories",
    "duplicate_repo_time_rows", "normalized_timing_errors", "numeric_coercion_generated_na",
    "missing_model_rows", "nonfinite_model_rows", "log1p_recomputation_mismatches",
    "legacy_mismatch_rows", "legacy_mismatch_repositories", "primary_interaction_term_rows",
    "gmm_diagnostic_missing_count", "stats_nobs_matches_active_rows", "ar1_expected_pattern",
    "ar2_no_second_order_serial_correlation", "sargan_overidentification", "model_warning_count",
    "instrument_ratio", "calendar_gap_transitions"
  ),
  observed = c(
    nrow(panel), repo_count, treatment_repos, control_repos,
    nrow(duplicate_rows), nrow(timing_errors), sum(numeric_audit$coercion_generated_na),
    nrow(missing_model_rows), nrow(nonfinite_model_rows), log_mismatches,
    legacy_mismatch_rows, legacy_mismatch_repositories, primary_rows,
    diagnostic_missing, dimensions$stats_nobs, ar1_p, ar2_p, sargan_p,
    length(all_warnings), instrument_ratio, nrow(calendar_gap_audit)
  ),
  expected = c(
    expected_rows, expected_repositories, expected_treatment_repositories, expected_control_repositories,
    0, 0, 0, 0, 0, 0,
    expected_legacy_mismatch_rows, expected_legacy_mismatch_repositories, 1,
    0, active_rows, NA, NA, NA, NA, NA, NA
  ),
  status = c(
    ifelse(nrow(panel) == expected_rows, "pass", "fail"),
    ifelse(repo_count == expected_repositories, "pass", "fail"),
    ifelse(treatment_repos == expected_treatment_repositories, "pass", "fail"),
    ifelse(control_repos == expected_control_repositories, "pass", "fail"),
    ifelse(nrow(duplicate_rows) == 0L, "pass", "fail"),
    ifelse(nrow(timing_errors) == 0L, "pass", "fail"),
    ifelse(sum(numeric_audit$coercion_generated_na) == 0L, "pass", "fail"),
    ifelse(nrow(missing_model_rows) == 0L, "pass", "fail"),
    ifelse(nrow(nonfinite_model_rows) == 0L, "pass", "fail"),
    ifelse(log_mismatches == 0L, "pass", "fail"),
    ifelse(legacy_mismatch_rows == expected_legacy_mismatch_rows, "pass", "fail"),
    ifelse(legacy_mismatch_repositories == expected_legacy_mismatch_repositories, "pass", "fail"),
    ifelse(primary_rows == 1L, "pass", "fail"),
    ifelse(diagnostic_missing == 0L, "pass", "fail"),
    ifelse(is.finite(dimensions$stats_nobs) && dimensions$stats_nobs == active_rows, "pass", "fail"),
    ifelse(is.finite(ar1_p) && ar1_p < 0.05, "pass", "caution"),
    ifelse(is.finite(ar2_p) && ar2_p >= 0.05, "pass", "caution"),
    ifelse(is.finite(sargan_p) && sargan_p >= 0.05, "pass", "caution"),
    ifelse(length(all_warnings) == 0L, "pass", "caution"),
    ifelse(is.finite(instrument_ratio) && instrument_ratio < 1, "pass", "caution"),
    ifelse(nrow(calendar_gap_audit) == 0L, "pass", "informational")
  )
)
write_csv(qc, paths$qc)
failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) abortf("run-x-e05 GMM QC failed: %s", paste(failed_qc$check, collapse = ", "))

saveRDS(list(model = fit_capture$value, robust_summary = summary_capture$value), paths$models_rds)
run_finished <- Sys.time()
metadata <- data.table::data.table(
  section = c(
    "run", "run", "run", "run", "input", "input", "input", "input", "software", "software",
    "definition", "definition", "definition", "definition", "definition", "definition", "definition",
    "definition", "definition", "definition", "definition", "definition", "qc", "qc"
  ),
  metric = c(
    "run_prefix", "implementation_version", "started", "finished",
    "input_file", "input_sha256", "b06_panel_file", "b06_panel_sha256", "R", "plm",
    "analysis_scope", "detector_combination", "intersection_rule", "npr_rule", "ml_rule",
    "localized_quality", "velocity", "treatment", "size_control", "other_controls",
    "gmm_specification", "formula", "failed_checks", "caution_checks"
  ),
  value = c(
    "run-x-e05", implementation_version, format(run_started, "%Y-%m-%d %H:%M:%S %Z"), format(run_finished, "%Y-%m-%d %H:%M:%S %Z"),
    input_file, sha256_file(input_file), b06_panel_file, sha256_file(b06_panel_file), R.version.string, safe_package_version("plm"),
    "agc_detector_intersection_localized_quality_to_velocity", "AGCDetector_NPR intersection AGCDetector_ML",
    "NPR selected AND ML selected; exact detector consensus",
    "file_npr_fun_space_by_token_weighted > 1.571637",
    "file_ml_agc_share_space_by_token_weighted > 0.50",
    "log1p_selected_issue_total", "log_lines_added_py_source", "absorbing_treated",
    "log1p(ncloc_py_sonarqube)", "log_age|log_contributors|log_stars|log_issues",
    "two-step difference GMM; twoways; collapse=FALSE; instrument lag(velocity,2)",
    formula_text, nrow(failed_qc), qc[status == "caution", .N]
  )
)
write_csv(metadata, paths$metadata)

log_message(
  "INFO",
  "Completed run-x-e05 %s: beta=%.9f; se=%.9f; p=%.9f; failed_qc=%d; cautions=%d",
  implementation_version,
  primary_summary$estimate[[1L]], primary_summary$std_error[[1L]], primary_summary$p_value[[1L]],
  nrow(failed_qc), qc[status == "caution", .N]
)
