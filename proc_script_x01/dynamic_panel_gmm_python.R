#!/usr/bin/env Rscript

# ============================================================
# run-x-e01 v3: Dynamic panel GMM for Python velocity-quality interactions
# ============================================================
#
# Purpose:
#   Estimate the whole-Python dynamic interaction between development velocity
#   and Python-only SonarQube issue stock. The statistical specification adapts
#   the original MSR DynamicPanel.Rmd models while preserving the normalized
#   treatment timing and measurement contracts established by run-x-b02/b06/b07.
#
# Primary variables:
#   - Velocity: log_lines_added_py_source
#   - Quality:  log_issue_total_py_sonarqube
#   - Size:     log1p(ncloc_py_sonarqube), created in this script to match the
#               original DynamicPanel.Rmd GMM functional form.
#
# Primary models:
#   1. velocity_to_quality
#      Quality_t ~ Quality_{t-1} + Velocity_t + treatment_t + controls_t
#      GMM instruments: Quality_{t-2:t-3}, Velocity_{t-2:t-3}
#      collapse = TRUE
#
#   2. quality_to_velocity
#      Velocity_t ~ Velocity_{t-1} + Quality_{t-1} + treatment_t + controls_t
#      GMM instruments: Velocity_{t-2}
#      collapse = FALSE
#
# Estimator settings inherited from the original DynamicPanel.Rmd:
#   - plm::pgmm
#   - effect = "twoways"
#   - model = "twosteps"
#   - transformation = "d" (difference GMM)
#   - robust two-step summary
#
# Treatment definition:
#   absorbing_treated = 1 only for treatment repositories at/after event_index.
#   Legacy cursor/is_treatment/post_event fields are audit-only.
#
# Important lag rule:
#   Calendar lags are defined by repo_id and the explicit monthly time_index.
#   The script audits time gaps before estimation and records exact lag support.
#   plm's indexed lag operator is used for model estimation; simple row shifts
#   are never used to construct statistical lags.
#
# Input:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# This script is self-contained. It reuses validated QC/provenance conventions
# from prior project R scripts but does not call any prior experiment script.
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
  if (is.na(path) || !nzchar(path) || !file.exists(path)) return(NA_character_)
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
      model = model_name, diagnostic = diagnostic_name, statistic = NA_real_,
      parameter = NA_real_, p_value = NA_real_, method = NA_character_, status = "missing"
    ))
  }
  statistic <- if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_
  parameter <- if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_
  p_value <- if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_
  method <- if (!is.null(test$method)) as.character(test$method) else NA_character_
  data.table::data.table(
    model = model_name,
    diagnostic = diagnostic_name,
    statistic = statistic,
    parameter = parameter,
    p_value = p_value,
    method = method,
    status = ifelse(is.finite(statistic) && is.finite(p_value), "available", "missing")
  )
}

extract_pgmm_coefficients <- function(summary_object, model_name, direction, primary_term, confidence_level) {
  matrix <- summary_object$coefficients
  if (is.null(matrix) || nrow(matrix) == 0L) abortf("No coefficient matrix returned for model %s.", model_name)
  matrix <- as.matrix(matrix)
  cn <- colnames(matrix)
  estimate_col <- which(tolower(cn) == "estimate")[1L]
  se_col <- grep("std\\.?[[:space:]]*error", cn, ignore.case = TRUE)[1L]
  p_col <- grep("pr\\(", cn, ignore.case = TRUE)[1L]
  if (is.na(estimate_col) || is.na(se_col)) abortf("Could not identify estimate/SE columns for model %s.", model_name)

  estimate <- as.numeric(matrix[, estimate_col])
  std_error <- as.numeric(matrix[, se_col])
  p_value <- if (!is.na(p_col)) as.numeric(matrix[, p_col]) else 2 * stats::pnorm(-abs(estimate / std_error))
  alpha <- 1 - confidence_level
  critical <- stats::qnorm(1 - alpha / 2)
  terms <- rownames(matrix)
  if (is.null(terms)) terms <- paste0("term_", seq_len(nrow(matrix)))

  data.table::data.table(
    model = model_name,
    direction = direction,
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

extract_model_dimensions <- function(model) {
  stats_nobs <- tryCatch(as.integer(stats::nobs(model)), error = function(e) NA_integer_)
  pgmm_internal_matrix_rows <- NA_integer_
  pgmm_internal_repository_slots <- NA_integer_
  if (is.list(model$model)) {
    # pgmm keeps an internally balanced/transformed model list. These counts
    # are implementation bookkeeping, not the effective estimation sample.
    pgmm_internal_repository_slots <- length(model$model)
    row_counts <- vapply(model$model, function(x) if (is.null(dim(x))) 0L else nrow(x), integer(1))
    pgmm_internal_matrix_rows <- sum(row_counts)
  }

  instrument_columns <- integer()
  if (is.list(model$W) && length(model$W) > 0L) {
    instrument_columns <- vapply(model$W, function(x) if (is.null(dim(x))) 0L else ncol(x), integer(1))
  }
  instrument_columns <- instrument_columns[instrument_columns > 0L]

  list(
    stats_nobs = stats_nobs,
    pgmm_internal_matrix_rows = pgmm_internal_matrix_rows,
    pgmm_internal_repository_slots = pgmm_internal_repository_slots,
    instrument_columns_min = if (length(instrument_columns)) min(instrument_columns) else NA_integer_,
    instrument_columns_max = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_unique = if (length(instrument_columns)) paste(sort(unique(instrument_columns)), collapse = "|") else "",
    instrument_columns_constant = length(unique(instrument_columns)) <= 1L,
    instrument_count_for_ratio = if (length(instrument_columns)) max(instrument_columns) else NA_integer_
  )
}

make_key <- function(repo_id, time_index) paste(repo_id, time_index, sep = "::")

# ----------------------------
# Arguments and dependencies
# ----------------------------

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v3" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)

expected_rows <- as_integer_arg(args, "expected_rows", -1L)
expected_repositories <- as_integer_arg(args, "expected_repositories", -1L)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", -1L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", -1L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", -1L)
expected_legacy_mismatch_repos <- as_integer_arg(args, "expected_legacy_mismatch_repos", -1L)

if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")
check_packages(c("data.table", "plm"))

# plm::pgmm() internally constructs a call whose function name is the bare
# symbol `plm` and evaluates that call in the caller environment. Calling only
# plm::pgmm() does not attach the package, so plm 2.6-7 can fail with
# "could not find function \"plm\"" even though requireNamespace("plm")
# succeeds. Attach plm explicitly for the duration of this analysis process.
suppressPackageStartupMessages(library(plm))
if (!exists("plm", mode = "function", inherits = TRUE)) {
  abortf("plm package was found but the plm() function is not visible after attachment.")
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  coefficients = file.path(output_dir, "dynamic_panel_gmm_coefficients.csv"),
  diagnostics = file.path(output_dir, "dynamic_panel_gmm_diagnostics.csv"),
  sample_qc = file.path(output_dir, "dynamic_panel_gmm_sample_qc.csv"),
  instrument_qc = file.path(output_dir, "dynamic_panel_gmm_instrument_qc.csv"),
  model_specs = file.path(output_dir, "dynamic_panel_gmm_model_specifications.csv"),
  legacy_audit = file.path(output_dir, "dynamic_panel_gmm_legacy_flag_audit.csv"),
  coercion_audit = file.path(output_dir, "dynamic_panel_gmm_numeric_coercion_audit.csv"),
  calendar_gap_audit = file.path(output_dir, "dynamic_panel_gmm_calendar_gap_audit.csv"),
  run_metadata = file.path(output_dir, "dynamic_panel_gmm_run_metadata.csv"),
  qc = file.path(output_dir, "dynamic_panel_gmm_qc.csv"),
  models_rds = file.path(output_dir, "dynamic_panel_gmm_models.rds")
)

run_started <- Sys.time()
log_message("INFO", "Reading run-x-b06 Python quality panel: %s", input_file)
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))

# ----------------------------
# Source measurement contracts
# ----------------------------

required_columns <- c(
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor",
  "log_lines_added_py_source", "log_issue_total_py_sonarqube",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  "did_primary_outcome", "python_velocity_metric_version",
  "quality_did_complete", "quality_scope", "quality_count_semantics",
  "quality_primary_outcome", "quality_density_outcome", "quality_metric_version"
)
validate_columns(panel, required_columns)

metadata_mismatches <- c(
  velocity_primary_outcome = sum(is.na(panel$did_primary_outcome) | panel$did_primary_outcome != "log_lines_added_py_source"),
  velocity_metric_version = sum(is.na(panel$python_velocity_metric_version) | panel$python_velocity_metric_version != "v4"),
  quality_did_complete = sum(bool_to_int(panel$quality_did_complete) != 1L),
  quality_scope = sum(is.na(panel$quality_scope) | panel$quality_scope != "python_only_sonar_inclusions"),
  quality_count_semantics = sum(is.na(panel$quality_count_semantics) | panel$quality_count_semantics != "unresolved_issue_stock_at_historical_snapshot"),
  quality_primary_outcome = sum(is.na(panel$quality_primary_outcome) | panel$quality_primary_outcome != "log_issue_total_py_sonarqube"),
  quality_density_outcome = sum(is.na(panel$quality_density_outcome) | panel$quality_density_outcome != "log_issues_per_kloc_py_sonarqube"),
  quality_metric_version = sum(is.na(panel$quality_metric_version) | panel$quality_metric_version != "v1")
)
if (any(metadata_mismatches > 0L)) {
  abortf("Input measurement metadata mismatch: %s", paste(names(metadata_mismatches), metadata_mismatches, sep = "=", collapse = "; "))
}

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "is_treatment", "post_event", "log_lines_added_py_source",
  "log_issue_total_py_sonarqube", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues"
)
coercion_audit <- coerce_numeric_with_audit(panel, numeric_columns)
write_csv(coercion_audit, paths$coercion_audit)
if (any(coercion_audit$coercion_generated_na > 0L)) {
  bad <- coercion_audit[coercion_generated_na > 0L]
  abortf("Numeric coercion generated NA values: %s", paste(bad$column, bad$coercion_generated_na, sep = "=", collapse = "; "))
}

if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) {
  abortf("repo_id, time_index, and event_index must be complete numeric columns.")
}
panel[, repo_id := as.integer(repo_id)]
panel[, time_index := as.integer(time_index)]
panel[, event_index := as.integer(event_index)]
panel[, treatment_group := as.integer(treatment_group)]

if (any(panel$ncloc_py_sonarqube < 0, na.rm = TRUE)) abortf("ncloc_py_sonarqube must be non-negative.")
panel[, log_ncloc_py_sonarqube := log1p(ncloc_py_sonarqube)]

model_fields <- c(
  "log_lines_added_py_source", "log_issue_total_py_sonarqube",
  "log_ncloc_py_sonarqube", "log_age", "log_contributors", "log_stars", "log_issues"
)
missing_model_rows <- panel[!stats::complete.cases(panel[, ..model_fields])]
if (nrow(missing_model_rows) > 0L) abortf("Found %d rows with missing primary GMM model fields.", nrow(missing_model_rows))
nonfinite_model_rows <- panel[
  !apply(as.data.frame(panel[, ..model_fields]), 1L, function(row) all(is.finite(row)))
]
if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d rows with non-finite primary GMM model fields.", nrow(nonfinite_model_rows))

# ----------------------------
# Normalized treatment and timing QC
# ----------------------------

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

strict_count_check(input_rows, expected_rows, "input rows", strict_expected_counts)
strict_count_check(repo_count, expected_repositories, "repositories", strict_expected_counts)
strict_count_check(treatment_repos, expected_treatment_repos, "treatment repositories", strict_expected_counts)
strict_count_check(control_repos, expected_control_repos, "control repositories", strict_expected_counts)

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

legacy_audit <- panel[legacy_mismatch_any == TRUE, .(
  repo_id, repo_name, dataset_source, time, time_index, event, event_index,
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

# ----------------------------
# Calendar continuity and raw lag support
# ----------------------------

data.table::setorder(panel, repo_id, time_index)
panel[, previous_time_index := data.table::shift(time_index), by = repo_id]
panel[, time_gap_from_previous := time_index - previous_time_index]
transition_rows <- panel[!is.na(previous_time_index)]
calendar_gap_rows <- transition_rows[time_gap_from_previous != 1L]
calendar_gap_audit <- calendar_gap_rows[, .(
  repo_id, repo_name, dataset_source, scope_role, treatment_group, time, time_index,
  previous_time_index, time_gap_from_previous
)]
write_csv(calendar_gap_audit, paths$calendar_gap_audit)

all_keys <- make_key(panel$repo_id, panel$time_index)
panel[, has_lag1_calendar := make_key(repo_id, time_index - 1L) %in% all_keys]
panel[, has_lag2_calendar := make_key(repo_id, time_index - 2L) %in% all_keys]
panel[, has_lag3_calendar := make_key(repo_id, time_index - 3L) %in% all_keys]
panel[, support_lag1 := has_lag1_calendar]
panel[, support_lag1_lag2 := has_lag1_calendar & has_lag2_calendar]
panel[, support_lag1_lag2_lag3 := has_lag1_calendar & has_lag2_calendar & has_lag3_calendar]

lag1_rows <- panel[support_lag1 == TRUE, .N]
lag12_rows <- panel[support_lag1_lag2 == TRUE, .N]
lag123_rows <- panel[support_lag1_lag2_lag3 == TRUE, .N]
lag1_repos <- panel[support_lag1 == TRUE, data.table::uniqueN(repo_id)]
lag12_repos <- panel[support_lag1_lag2 == TRUE, data.table::uniqueN(repo_id)]
lag123_repos <- panel[support_lag1_lag2_lag3 == TRUE, data.table::uniqueN(repo_id)]

# Both primary difference-GMM equations require exact calendar t-1 and t-2
# support. The forward 2:3 instrument range uses lag-3 moments only where an
# exact t-3 observation exists; lack of t-3 does not remove an otherwise valid
# t-2 equation row from pgmm. Because all primary model fields are complete,
# this minimum calendar-support set is the effective GMM estimation sample.
active_gmm <- panel[support_lag1_lag2 == TRUE]
active_gmm_rows <- nrow(active_gmm)
active_gmm_repos <- data.table::uniqueN(active_gmm$repo_id)
active_gmm_treatment_rows <- active_gmm[treatment_group == 1L, .N]
active_gmm_control_rows <- active_gmm[treatment_group == 0L, .N]
active_gmm_treatment_repos <- active_gmm[treatment_group == 1L, data.table::uniqueN(repo_id)]
active_gmm_control_repos <- active_gmm[treatment_group == 0L, data.table::uniqueN(repo_id)]
active_gmm_post_treated_rows <- active_gmm[absorbing_treated == 1L, .N]

# ----------------------------
# Original-aligned GMM specifications
# ----------------------------

quality_variable <- "log_issue_total_py_sonarqube"
velocity_variable <- "log_lines_added_py_source"
control_variables <- c(
  "absorbing_treated", "log_ncloc_py_sonarqube", "log_age",
  "log_contributors", "log_stars", "log_issues"
)

forward_formula_text <- paste0(
  "log_issue_total_py_sonarqube ~ lag(log_issue_total_py_sonarqube, 1) + ",
  "log_lines_added_py_source + absorbing_treated + log_ncloc_py_sonarqube + ",
  "log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_issue_total_py_sonarqube, 2:3) + lag(log_lines_added_py_source, 2:3)"
)
reverse_formula_text <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log_issue_total_py_sonarqube, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)

forward_formula <- stats::as.formula(forward_formula_text)
reverse_formula <- stats::as.formula(reverse_formula_text)

model_specs <- data.table::data.table(
  model = c("velocity_to_quality", "quality_to_velocity"),
  direction = c("Velocity_t -> Quality_t", "Quality_{t-1} -> Velocity_t (conceptually Quality_t -> Velocity_{t+1})"),
  dependent_variable = c(quality_variable, velocity_variable),
  primary_interaction_term = c(velocity_variable, "lag(log_issue_total_py_sonarqube, 1)"),
  formula = c(forward_formula_text, reverse_formula_text),
  gmm_instruments = c(
    "lag(quality,2:3) + lag(velocity,2:3)",
    "lag(velocity,2)"
  ),
  effect = "twoways",
  estimator = "twosteps",
  transformation = "d",
  collapse = c(TRUE, FALSE),
  raw_calendar_support_definition = c("minimum exact t-1,t-2 calendar support; lag-3 moments used where exact t-3 exists", "requires exact t-1,t-2 calendar months"),
  source_alignment = c(
    "Original DynamicPanel.Rmd static_analysis_warnings model adapted to Python-only SonarQube issue stock.",
    "Original DynamicPanel.Rmd lines_added/static_analysis_warnings reverse model; no explicit lead outcome is created."
  )
)
write_csv(model_specs, paths$model_specs)

# pgmm documentation requires the estimation data to contain no factor or
# character vectors. Keep only numeric index/model fields in the pdata.frame.
gmm_data <- panel[, .(
  repo_id, time_index,
  log_lines_added_py_source, log_issue_total_py_sonarqube,
  absorbing_treated, log_ncloc_py_sonarqube, log_age,
  log_contributors, log_stars, log_issues
)]
pdata <- plm::pdata.frame(
  gmm_data,
  index = c("repo_id", "time_index"),
  drop.index = FALSE,
  row.names = FALSE
)

fit_pgmm <- function(model_name, formula, collapse, primary_term, direction) {
  log_message("INFO", "Fitting %s", model_name)
  fit_capture <- capture_evaluation(
    plm::pgmm(
      formula = formula,
      data = pdata,
      effect = "twoways",
      model = "twosteps",
      transformation = "d",
      collapse = collapse
    )
  )
  if (fit_capture$error) abortf("GMM model %s failed: %s", model_name, fit_capture$value$message)

  summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
  if (summary_capture$error) abortf("Robust GMM summary %s failed: %s", model_name, summary_capture$value$message)

  all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings))
  coefficients <- extract_pgmm_coefficients(summary_capture$value, model_name, direction, primary_term, confidence_level)
  dimensions <- extract_model_dimensions(fit_capture$value)

  diagnostics <- data.table::rbindlist(list(
    extract_htest(summary_capture$value$sargan, model_name, "sargan"),
    extract_htest(summary_capture$value$m1, model_name, "ar1"),
    extract_htest(summary_capture$value$m2, model_name, "ar2")
  ), use.names = TRUE, fill = TRUE)
  diagnostics[, `:=`(
    robust_summary = TRUE,
    warning_count = length(all_warnings),
    warning_messages = paste(all_warnings, collapse = " | ")
  )]

  list(
    model = fit_capture$value,
    summary = summary_capture$value,
    coefficients = coefficients,
    diagnostics = diagnostics,
    dimensions = dimensions,
    warnings = all_warnings,
    runtime_seconds = fit_capture$elapsed + summary_capture$elapsed
  )
}

forward <- fit_pgmm(
  model_name = "velocity_to_quality",
  formula = forward_formula,
  collapse = TRUE,
  primary_term = velocity_variable,
  direction = "Velocity_t -> Quality_t"
)
reverse <- fit_pgmm(
  model_name = "quality_to_velocity",
  formula = reverse_formula,
  collapse = FALSE,
  primary_term = "lag(log_issue_total_py_sonarqube, 1)",
  direction = "Quality_{t-1} -> Velocity_t"
)

coefficients <- data.table::rbindlist(list(forward$coefficients, reverse$coefficients), use.names = TRUE, fill = TRUE)
write_csv(coefficients, paths$coefficients)

diagnostics <- data.table::rbindlist(list(forward$diagnostics, reverse$diagnostics), use.names = TRUE, fill = TRUE)
write_csv(diagnostics, paths$diagnostics)

make_instrument_row <- function(
  model_name, result, collapse, instrument_spec,
  minimum_support_rows, minimum_support_repos,
  lag3_available_rows = NA_integer_, lag3_available_repos = NA_integer_
) {
  d <- result$dimensions
  ratio <- if (is.finite(d$instrument_count_for_ratio) && active_gmm_repos > 0L) {
    d$instrument_count_for_ratio / active_gmm_repos
  } else {
    NA_real_
  }
  data.table::data.table(
    model = model_name,
    collapse = collapse,
    instrument_specification = instrument_spec,
    minimum_calendar_support_rows = minimum_support_rows,
    minimum_calendar_support_repositories = minimum_support_repos,
    lag3_moment_available_rows = lag3_available_rows,
    lag3_moment_available_repositories = lag3_available_repos,
    stats_nobs = d$stats_nobs,
    active_gmm_repositories = active_gmm_repos,
    active_gmm_treatment_repositories = active_gmm_treatment_repos,
    active_gmm_control_repositories = active_gmm_control_repos,
    pgmm_internal_matrix_rows = d$pgmm_internal_matrix_rows,
    pgmm_internal_repository_slots = d$pgmm_internal_repository_slots,
    instrument_columns_min = d$instrument_columns_min,
    instrument_columns_max = d$instrument_columns_max,
    instrument_columns_unique = d$instrument_columns_unique,
    instrument_columns_constant = d$instrument_columns_constant,
    instrument_count_for_ratio = d$instrument_count_for_ratio,
    instrument_ratio_denominator = active_gmm_repos,
    instrument_to_repository_ratio = ratio,
    instrument_proliferation_flag = is.finite(ratio) && ratio >= 1,
    runtime_seconds = result$runtime_seconds,
    warning_count = length(result$warnings),
    warning_messages = paste(result$warnings, collapse = " | ")
  )
}

instrument_qc <- data.table::rbindlist(list(
  make_instrument_row(
    "velocity_to_quality", forward, TRUE,
    "lag(quality,2:3)+lag(velocity,2:3)",
    lag12_rows, lag12_repos, lag123_rows, lag123_repos
  ),
  make_instrument_row(
    "quality_to_velocity", reverse, FALSE,
    "lag(velocity,2)",
    lag12_rows, lag12_repos
  )
), use.names = TRUE, fill = TRUE)
write_csv(instrument_qc, paths$instrument_qc)

# ----------------------------
# Sample accounting and QC
# ----------------------------

sample_qc <- data.table::rbindlist(list(
  make_summary_row("input", "rows", input_rows),
  make_summary_row("input", "repositories", repo_count),
  make_summary_row("input", "treatment_repositories", treatment_repos),
  make_summary_row("input", "control_repositories", control_repos),
  make_summary_row("definition", "velocity", velocity_variable),
  make_summary_row("definition", "quality", quality_variable),
  make_summary_row("definition", "size_control", "log1p(ncloc_py_sonarqube)", "Original DynamicPanel.Rmd GMM functional form."),
  make_summary_row("definition", "treatment", "absorbing_treated", "Normalized first-adoption treatment; legacy flags are audit-only."),
  make_summary_row("qc", "duplicate_repo_time_rows", nrow(duplicate_rows)),
  make_summary_row("qc", "normalized_timing_errors", nrow(timing_errors)),
  make_summary_row("qc", "metadata_mismatch_total", sum(metadata_mismatches)),
  make_summary_row("qc", "missing_model_rows", nrow(missing_model_rows)),
  make_summary_row("qc", "nonfinite_model_rows", nrow(nonfinite_model_rows)),
  make_summary_row("qc", "numeric_coercion_generated_na", sum(coercion_audit$coercion_generated_na)),
  make_summary_row("qc", "legacy_mismatch_rows", legacy_mismatch_rows, "Audit only."),
  make_summary_row("qc", "legacy_mismatch_repositories", legacy_mismatch_repos, "Audit only."),
  make_summary_row("calendar", "within_repo_transitions", nrow(transition_rows)),
  make_summary_row("calendar", "consecutive_transitions", sum(transition_rows$time_gap_from_previous == 1L)),
  make_summary_row("calendar", "gap_transitions", nrow(calendar_gap_rows), "Recorded, not repaired by row shifting."),
  make_summary_row("lag_support", "lag1_rows", lag1_rows),
  make_summary_row("lag_support", "lag1_repositories", lag1_repos),
  make_summary_row("lag_support", "lag1_lag2_rows", lag12_rows),
  make_summary_row("lag_support", "lag1_lag2_repositories", lag12_repos),
  make_summary_row("lag_support", "lag1_lag2_lag3_rows", lag123_rows),
  make_summary_row("lag_support", "lag1_lag2_lag3_repositories", lag123_repos),
  make_summary_row("active_gmm", "rows", active_gmm_rows, "Exact calendar t-1 and t-2 support; all primary model fields complete."),
  make_summary_row("active_gmm", "repositories", active_gmm_repos),
  make_summary_row("active_gmm", "treatment_rows", active_gmm_treatment_rows),
  make_summary_row("active_gmm", "control_rows", active_gmm_control_rows),
  make_summary_row("active_gmm", "treatment_repositories", active_gmm_treatment_repos),
  make_summary_row("active_gmm", "control_repositories", active_gmm_control_repos),
  make_summary_row("active_gmm", "post_treated_rows", active_gmm_post_treated_rows),
  make_summary_row("model", "velocity_to_quality_stats_nobs", forward$dimensions$stats_nobs),
  make_summary_row("model", "velocity_to_quality_pgmm_internal_matrix_rows", forward$dimensions$pgmm_internal_matrix_rows, "Internal balanced/transformed pgmm rows; not estimation N."),
  make_summary_row("model", "velocity_to_quality_pgmm_internal_repository_slots", forward$dimensions$pgmm_internal_repository_slots, "Internal pgmm list slots; not active GMM repositories."),
  make_summary_row("model", "quality_to_velocity_stats_nobs", reverse$dimensions$stats_nobs),
  make_summary_row("model", "quality_to_velocity_pgmm_internal_matrix_rows", reverse$dimensions$pgmm_internal_matrix_rows, "Internal balanced/transformed pgmm rows; not estimation N."),
  make_summary_row("model", "quality_to_velocity_pgmm_internal_repository_slots", reverse$dimensions$pgmm_internal_repository_slots, "Internal pgmm list slots; not active GMM repositories.")
), use.names = TRUE, fill = TRUE)
write_csv(sample_qc, paths$sample_qc)

primary_forward_rows <- coefficients[model == "velocity_to_quality" & is_primary_interaction_term == TRUE, .N]
primary_reverse_rows <- coefficients[model == "quality_to_velocity" & is_primary_interaction_term == TRUE, .N]
diagnostic_missing <- diagnostics[status != "available", .N]
forward_ar1_p <- diagnostics[model == "velocity_to_quality" & diagnostic == "ar1", p_value][1L]
reverse_ar1_p <- diagnostics[model == "quality_to_velocity" & diagnostic == "ar1", p_value][1L]

qc <- data.table::data.table(
  check = c(
    "input_rows", "repositories", "treatment_repositories", "control_repositories",
    "duplicate_repo_time_rows", "normalized_timing_errors", "metadata_mismatch_total",
    "missing_model_rows", "nonfinite_model_rows", "numeric_coercion_generated_na",
    "legacy_mismatch_rows", "legacy_mismatch_repositories",
    "primary_velocity_to_quality_term_rows", "primary_quality_to_velocity_term_rows",
    "gmm_diagnostic_missing_count", "calendar_gap_transitions",
    "velocity_to_quality_stats_nobs_matches_active_rows", "quality_to_velocity_stats_nobs_matches_active_rows",
    "velocity_to_quality_ar1_expected_pattern", "quality_to_velocity_ar1_expected_pattern",
    "velocity_to_quality_warning_count", "quality_to_velocity_warning_count",
    "velocity_to_quality_instrument_ratio", "quality_to_velocity_instrument_ratio"
  ),
  observed = c(
    input_rows, repo_count, treatment_repos, control_repos,
    nrow(duplicate_rows), nrow(timing_errors), sum(metadata_mismatches),
    nrow(missing_model_rows), nrow(nonfinite_model_rows), sum(coercion_audit$coercion_generated_na),
    legacy_mismatch_rows, legacy_mismatch_repos,
    primary_forward_rows, primary_reverse_rows,
    diagnostic_missing, nrow(calendar_gap_rows),
    forward$dimensions$stats_nobs, reverse$dimensions$stats_nobs,
    forward_ar1_p, reverse_ar1_p,
    length(forward$warnings), length(reverse$warnings),
    instrument_qc[model == "velocity_to_quality", instrument_to_repository_ratio],
    instrument_qc[model == "quality_to_velocity", instrument_to_repository_ratio]
  ),
  expected = c(
    expected_rows, expected_repositories, expected_treatment_repos, expected_control_repos,
    0, 0, 0, 0, 0, 0,
    expected_legacy_mismatch_rows, expected_legacy_mismatch_repos,
    1, 1, 0, NA,
    active_gmm_rows, active_gmm_rows,
    NA, NA,
    NA, NA, NA, NA
  ),
  status = c(
    ifelse(expected_rows < 0L || input_rows == expected_rows, "pass", "fail"),
    ifelse(expected_repositories < 0L || repo_count == expected_repositories, "pass", "fail"),
    ifelse(expected_treatment_repos < 0L || treatment_repos == expected_treatment_repos, "pass", "fail"),
    ifelse(expected_control_repos < 0L || control_repos == expected_control_repos, "pass", "fail"),
    ifelse(nrow(duplicate_rows) == 0L, "pass", "fail"),
    ifelse(nrow(timing_errors) == 0L, "pass", "fail"),
    ifelse(sum(metadata_mismatches) == 0L, "pass", "fail"),
    ifelse(nrow(missing_model_rows) == 0L, "pass", "fail"),
    ifelse(nrow(nonfinite_model_rows) == 0L, "pass", "fail"),
    ifelse(sum(coercion_audit$coercion_generated_na) == 0L, "pass", "fail"),
    ifelse(expected_legacy_mismatch_rows < 0L || legacy_mismatch_rows == expected_legacy_mismatch_rows, "pass", "fail"),
    ifelse(expected_legacy_mismatch_repos < 0L || legacy_mismatch_repos == expected_legacy_mismatch_repos, "pass", "fail"),
    ifelse(primary_forward_rows == 1L, "pass", "fail"),
    ifelse(primary_reverse_rows == 1L, "pass", "fail"),
    ifelse(diagnostic_missing == 0L, "pass", "fail"),
    ifelse(nrow(calendar_gap_rows) == 0L, "pass", "informational"),
    ifelse(is.finite(forward$dimensions$stats_nobs) && forward$dimensions$stats_nobs == active_gmm_rows, "pass", "fail"),
    ifelse(is.finite(reverse$dimensions$stats_nobs) && reverse$dimensions$stats_nobs == active_gmm_rows, "pass", "fail"),
    ifelse(is.finite(forward_ar1_p) && forward_ar1_p < 0.05, "pass", "caution"),
    ifelse(is.finite(reverse_ar1_p) && reverse_ar1_p < 0.05, "pass", "caution"),
    ifelse(length(forward$warnings) == 0L, "pass", "caution"),
    ifelse(length(reverse$warnings) == 0L, "pass", "caution"),
    ifelse(isTRUE(instrument_qc[model == "velocity_to_quality", instrument_proliferation_flag]), "caution", "pass"),
    ifelse(isTRUE(instrument_qc[model == "quality_to_velocity", instrument_proliferation_flag]), "caution", "pass")
  ),
  note = c(
    "Source-panel invariant.", "Source-panel invariant.", "Source-panel invariant.", "Source-panel invariant.",
    "Must be zero.", "Must be zero.", "B02/B06 measurement contracts must match.",
    "Primary GMM fields must be complete.", "Primary GMM fields must be finite.", "Numeric parsing must not introduce missingness.",
    "Expected legacy mismatch is audit-only.", "Expected legacy mismatch is audit-only.",
    "Exactly one contemporaneous velocity coefficient is required.", "Exactly one lagged-quality coefficient is required.",
    "Sargan, AR(1), and AR(2) must be returned for both models.",
    "Calendar gaps are recorded explicitly; indexed lags must not be row shifted.",
    "stats::nobs(pgmm) should equal the exact-calendar t-1/t-2 active GMM rows for this complete primary panel.",
    "stats::nobs(pgmm) should equal the exact-calendar t-1/t-2 active GMM rows for this complete primary panel.",
    "Difference-GMM commonly yields first-order serial correlation after differencing; non-significant AR(1) is a caution, not a hard failure.",
    "Difference-GMM commonly yields first-order serial correlation after differencing; non-significant AR(1) is a caution, not a hard failure.",
    "Warnings are retained for review rather than automatically treated as fatal.",
    "Warnings are retained for review rather than automatically treated as fatal.",
    "Caution if reported instrument dimension is at least the number of active GMM repositories.",
    "Caution if reported instrument dimension is at least the number of active GMM repositories."
  )
)
write_csv(qc, paths$qc)

failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("run-x-e01 GMM QC failed: %s", paste(failed_qc$check, collapse = ", "))
}

saveRDS(
  list(
    velocity_to_quality = forward$model,
    quality_to_velocity = reverse$model,
    robust_summaries = list(
      velocity_to_quality = forward$summary,
      quality_to_velocity = reverse$summary
    )
  ),
  paths$models_rds
)

run_finished <- Sys.time()
metadata <- data.table::rbindlist(list(
  make_summary_row("run", "run_prefix", "run-x-e01"),
  make_summary_row("run", "implementation_version", implementation_version),
  make_summary_row("run", "started", format(run_started, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "finished", format(run_finished, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "runtime_seconds", as.numeric(difftime(run_finished, run_started, units = "secs"))),
  make_summary_row("run", "input_file", input_file),
  make_summary_row("run", "input_sha256", sha256_file(input_file)),
  make_summary_row("run", "script_path", script_path),
  make_summary_row("run", "script_sha256", sha256_file(script_path)),
  make_summary_row("software", "R", R.version.string),
  make_summary_row("software", "platform", R.version$platform),
  make_summary_row("software", "hostname", Sys.info()[["nodename"]]),
  make_summary_row("software", "data.table", safe_package_version("data.table")),
  make_summary_row("software", "plm", safe_package_version("plm")),
  make_summary_row("definition", "analysis_scope", "whole_python"),
  make_summary_row("definition", "velocity", velocity_variable),
  make_summary_row("definition", "quality", quality_variable),
  make_summary_row("definition", "treatment", "absorbing_treated"),
  make_summary_row("definition", "size_control", "log1p(ncloc_py_sonarqube)"),
  make_summary_row("definition", "other_controls", "log_age|log_contributors|log_stars|log_issues"),
  make_summary_row("definition", "effect", "twoways"),
  make_summary_row("definition", "model", "twosteps"),
  make_summary_row("definition", "transformation", "d"),
  make_summary_row("definition", "robust_summary", "true"),
  make_summary_row("definition", "forward_collapse", "true"),
  make_summary_row("definition", "reverse_collapse", "false"),
  make_summary_row("definition", "forward_formula", forward_formula_text),
  make_summary_row("definition", "reverse_formula", reverse_formula_text),
  make_summary_row("definition", "source_alignment", "Original DynamicPanel.Rmd model/instrument asymmetry retained; current normalized absorbing treatment and Python-specific measures substituted."),
  make_summary_row("definition", "log_transform_rule", "Velocity and quality are already log1p outcomes and are not transformed again; Python NCLOC is transformed with log1p inside this script."),
  make_summary_row("definition", "active_gmm_sample_rule", "Exact calendar t-1 and t-2 support; forward lag-3 moments are used where available without requiring t-3 for every estimation row."),
  make_summary_row("definition", "instrument_ratio_denominator", "active_gmm_repositories"),
  make_summary_row("definition", "pgmm_internal_count_note", "Internal balanced/transformed pgmm matrix rows and repository slots are reported separately from effective estimation N and active repositories."),
  make_summary_row("definition", "ar1_qc_rule", "AR(1) p >= 0.05 is recorded as caution, not failure; AR(2) and overidentification diagnostics remain reported separately."),
  make_summary_row("qc", "failed_checks", nrow(failed_qc)),
  make_summary_row("qc", "caution_checks", qc[status == "caution", .N])
), use.names = TRUE, fill = TRUE)
write_csv(metadata, paths$run_metadata)

log_message(
  "INFO",
  "Completed run-x-e01 %s: coefficients=%d; diagnostics=%d; source_rows=%d; source_repos=%d; failed_qc=%d; cautions=%d",
  implementation_version, nrow(coefficients), nrow(diagnostics), input_rows, repo_count,
  nrow(failed_qc), qc[status == "caution", .N]
)
