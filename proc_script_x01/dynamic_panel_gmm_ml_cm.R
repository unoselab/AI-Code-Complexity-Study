#!/usr/bin/env Rscript

# ============================================================
# run-x-k06 v1: Dynamic panel GMM for ML-localized CM issue burden
# ============================================================
#
# Purpose:
#   Estimate whether unresolved Python static-analysis issue burden localized
#   to files selected by the primary ML threshold within the CM localization scope predicts lower
#   subsequent whole-Python development velocity.
#
# Primary detector/localization contract:
#   - detector: AGCDetector_ML; localization scope: CM
#   - file ML metric: file_ml_cfun_agc_share_space_by_token_weighted
#   - primary threshold: 0.5
#   - comparison operator: strict >
#   - localized quality outcome: log1p_selected_issue_total
#   - velocity outcome: log_lines_added_py_source
#
# Primary GMM model:
#   Velocity_t ~ Velocity_{t-1} + MLCMQuality_{t-1} + treatment_t + controls_t
#   GMM instruments: Velocity_{t-2}
#   collapse = FALSE
#
# Estimator settings are intentionally aligned with run-x-e01 and the original
# MSR DynamicPanel.Rmd reverse-direction model:
#   - plm::pgmm
#   - effect = "twoways"
#   - model = "twosteps"
#   - transformation = "d"
#   - robust two-step summary
#
# Samples:
#   1. full_sample (primary)
#   2. exclude_scope_mismatch_repos (pre-specified ML scope robustness)
#
# Important scope decision:
#   This run does not estimate Velocity_t -> ML-localized Quality_t because a
#   detector-localized velocity-flow outcome has not yet been constructed.
#   K06 therefore addresses the pre-specified secondary interaction question:
#   ML-localized CM issue burden_t -> whole-Python velocity_{t+1}.
#
# Treatment definition:
#   absorbing_treated = 1 only for treatment repositories at/after event_index.
#   Legacy cursor/is_treatment/post_event fields are audit-only.
#
# Inputs:
#   - ML-localized CM quality panel:
#       repo_x01/run-x-h07/quality_ml_cfun_threshold_input_panel.csv.gz
#   - Authoritative whole-Python velocity/covariate panel:
#       repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Join rule:
#   H07 intentionally contains localized quality outcomes but not the B02/B06
#   whole-Python velocity outcome. K06 therefore joins log_lines_added_py_source
#   from the B06 panel by exact (repo_id, time_index), while auditing
#   all overlapping timing/covariate fields before estimation.
#
# This script is self-contained. Its estimator/QC structure is copied from
# the validated K04/E03 reverse-direction GMM logic and adapted to H07 ML-CM
# inputs. It does not call any prior experiment script or shell wrapper.
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

coerce_numeric_with_audit <- function(data, columns, sample_spec) {
  rows <- vector("list", length(columns))
  for (idx in seq_along(columns)) {
    column <- columns[[idx]]
    before <- data[[column]]
    before_missing <- is.na(before) | trimws(as.character(before)) == ""
    converted <- suppressWarnings(as.numeric(before))
    generated_na <- sum(!before_missing & is.na(converted))
    data[, (column) := converted]
    rows[[idx]] <- data.table::data.table(
      sample_spec = sample_spec,
      column = column,
      missing_before = sum(before_missing),
      missing_after = sum(is.na(converted)),
      coercion_generated_na = generated_na
    )
  }
  data.table::rbindlist(rows)
}

extract_htest <- function(test, sample_spec, model_name, diagnostic_name) {
  if (is.null(test)) {
    return(data.table::data.table(
      sample_spec = sample_spec, model = model_name, diagnostic = diagnostic_name,
      statistic = NA_real_, parameter = NA_real_, p_value = NA_real_,
      method = NA_character_, status = "missing"
    ))
  }
  statistic <- if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_
  parameter <- if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_
  p_value <- if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_
  method <- if (!is.null(test$method)) as.character(test$method) else NA_character_
  data.table::data.table(
    sample_spec = sample_spec,
    model = model_name,
    diagnostic = diagnostic_name,
    statistic = statistic,
    parameter = parameter,
    p_value = p_value,
    method = method,
    status = ifelse(is.finite(statistic) && is.finite(p_value), "available", "missing")
  )
}

extract_pgmm_coefficients <- function(summary_object, sample_spec, model_name, direction, primary_term, confidence_level) {
  matrix <- summary_object$coefficients
  if (is.null(matrix) || nrow(matrix) == 0L) abortf("No coefficient matrix returned for sample %s model %s.", sample_spec, model_name)
  matrix <- as.matrix(matrix)
  cn <- colnames(matrix)
  estimate_col <- which(tolower(cn) == "estimate")[1L]
  se_col <- grep("std\\.?[[:space:]]*error", cn, ignore.case = TRUE)[1L]
  p_col <- grep("pr\\(", cn, ignore.case = TRUE)[1L]
  if (is.na(estimate_col) || is.na(se_col)) abortf("Could not identify estimate/SE columns for sample %s model %s.", sample_spec, model_name)

  estimate <- as.numeric(matrix[, estimate_col])
  std_error <- as.numeric(matrix[, se_col])
  p_value <- if (!is.na(p_col)) as.numeric(matrix[, p_col]) else 2 * stats::pnorm(-abs(estimate / std_error))
  alpha <- 1 - confidence_level
  critical <- stats::qnorm(1 - alpha / 2)
  terms <- rownames(matrix)
  if (is.null(terms)) terms <- paste0("term_", seq_len(nrow(matrix)))

  data.table::data.table(
    sample_spec = sample_spec,
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

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
b06_panel_file <- normalizePath(require_arg(args, "b06_panel_file"), mustWork = TRUE)
h07_summary_file <- normalizePath(require_arg(args, "h07_summary_file"), mustWork = TRUE)
h07_sample_summary_file <- normalizePath(require_arg(args, "h07_sample_summary_file"), mustWork = TRUE)
h07_global_audit_file <- normalizePath(require_arg(args, "h07_global_audit_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
primary_threshold <- as_numeric_arg(args, "primary_threshold", 0.5)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_long_rows <- as_integer_arg(args, "expected_long_rows", 81249L)
expected_thresholds <- as_integer_arg(args, "expected_thresholds", 21L)
expected_sample_specs <- as_integer_arg(args, "expected_sample_specs", 2L)
expected_full_rows <- as_integer_arg(args, "expected_full_rows", 1954L)
expected_full_repositories <- as_integer_arg(args, "expected_full_repositories", 167L)
expected_full_treatment_repos <- as_integer_arg(args, "expected_full_treatment_repos", 63L)
expected_full_control_repos <- as_integer_arg(args, "expected_full_control_repos", 104L)
expected_sensitivity_rows <- as_integer_arg(args, "expected_sensitivity_rows", 1915L)
expected_sensitivity_repositories <- as_integer_arg(args, "expected_sensitivity_repositories", 165L)
expected_sensitivity_treatment_repos <- as_integer_arg(args, "expected_sensitivity_treatment_repos", 62L)
expected_sensitivity_control_repos <- as_integer_arg(args, "expected_sensitivity_control_repos", 103L)
expected_primary_full_selected_files <- as_integer_arg(args, "expected_primary_full_selected_files", 37757L)
expected_primary_full_issue_stock <- as_integer_arg(args, "expected_primary_full_issue_stock", 36432L)
expected_primary_sensitivity_selected_files <- as_integer_arg(args, "expected_primary_sensitivity_selected_files", 37271L)
expected_primary_sensitivity_issue_stock <- as_integer_arg(args, "expected_primary_sensitivity_issue_stock", 36252L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", 11L)
expected_legacy_mismatch_repos <- as_integer_arg(args, "expected_legacy_mismatch_repos", 3L)

if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")
check_packages(c("data.table", "plm"))
suppressPackageStartupMessages(library(plm))
if (!exists("plm", mode = "function", inherits = TRUE)) {
  abortf("plm package was found but the plm() function is not visible after attachment.")
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  coefficients = file.path(output_dir, "dynamic_panel_gmm_ml_cm_coefficients.csv"),
  diagnostics = file.path(output_dir, "dynamic_panel_gmm_ml_cm_diagnostics.csv"),
  sample_qc = file.path(output_dir, "dynamic_panel_gmm_ml_cm_sample_qc.csv"),
  instrument_qc = file.path(output_dir, "dynamic_panel_gmm_ml_cm_instrument_qc.csv"),
  model_specs = file.path(output_dir, "dynamic_panel_gmm_ml_cm_model_specifications.csv"),
  threshold_input_audit = file.path(output_dir, "dynamic_panel_gmm_ml_cm_threshold_input_audit.csv"),
  b06_join_audit = file.path(output_dir, "dynamic_panel_gmm_ml_cm_b06_join_audit.csv"),
  legacy_audit = file.path(output_dir, "dynamic_panel_gmm_ml_cm_legacy_flag_audit.csv"),
  coercion_audit = file.path(output_dir, "dynamic_panel_gmm_ml_cm_numeric_coercion_audit.csv"),
  calendar_gap_audit = file.path(output_dir, "dynamic_panel_gmm_ml_cm_calendar_gap_audit.csv"),
  run_metadata = file.path(output_dir, "dynamic_panel_gmm_ml_cm_run_metadata.csv"),
  qc = file.path(output_dir, "dynamic_panel_gmm_ml_cm_qc.csv"),
  models_rds = file.path(output_dir, "dynamic_panel_gmm_ml_cm_models.rds")
)

run_started <- Sys.time()
log_message("INFO", "Reading H07 CM-ML threshold quality panel: %s", input_file)
long_panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))

required_columns <- c(
  "sample_spec", "threshold_spec_id", "threshold_role", "threshold", "ml_operator",
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor",
  "log1p_selected_issue_total",
  "selected_issue_total", "selected_file_count", "eligible_ml_file_count",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
validate_columns(long_panel, required_columns)

strict_count_check(nrow(long_panel), expected_long_rows, "H07 long-panel rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(long_panel$threshold_spec_id), expected_thresholds, "H07 threshold specifications", strict_expected_counts)
strict_count_check(data.table::uniqueN(long_panel$sample_spec), expected_sample_specs, "H07 sample specifications", strict_expected_counts)

# H07 was built from B06 for quality/timing support, but the H07 long panel does
# not intentionally carry the whole-Python velocity outcome. Read B06 directly
# and use it as the authoritative velocity source for K06.
log_message("INFO", "Reading B06 whole-Python velocity/covariate panel: %s", b06_panel_file)
b06_panel <- data.table::fread(b06_panel_file, na.strings = c("", "NA", "NaN"))
b06_required_columns <- c(
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "is_treatment", "post_event", "cursor",
  "log_lines_added_py_source", "log_age", "ncloc_py_sonarqube",
  "log_contributors", "log_stars", "log_issues"
)
validate_columns(b06_panel, b06_required_columns)
strict_count_check(nrow(b06_panel), expected_full_rows, "B06 panel rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(b06_panel$repo_id), expected_full_repositories, "B06 repositories", strict_expected_counts)

b06_panel[, repo_id := suppressWarnings(as.integer(repo_id))]
b06_panel[, time_index := suppressWarnings(as.integer(time_index))]
if (anyNA(b06_panel$repo_id) || anyNA(b06_panel$time_index)) {
  abortf("B06 repo_id/time_index must be complete integer-compatible keys.")
}
b06_duplicate_keys <- b06_panel[, .N, by = .(repo_id, time_index)][N > 1L]
if (nrow(b06_duplicate_keys) > 0L) {
  abortf("B06 panel contains %d duplicate repo_id-time_index keys.", nrow(b06_duplicate_keys))
}

primary_panel <- long_panel[
  threshold_role == "primary" &
  abs(as.numeric(threshold) - primary_threshold) <= 1e-12 &
  ml_operator == ">"
]
if (nrow(primary_panel) == 0L) abortf("No H07 primary-threshold rows found for strict ML > %.6f.", primary_threshold)
if (any(primary_panel$threshold_role != "primary")) abortf("Primary threshold rows must have threshold_role=primary.")

sample_specs <- c("full_sample", "exclude_scope_mismatch_repos")
if (!all(sample_specs %in% unique(primary_panel$sample_spec))) {
  abortf("Primary H07 panel is missing required sample specifications: %s", paste(setdiff(sample_specs, unique(primary_panel$sample_spec)), collapse = ", "))
}
primary_panel <- primary_panel[sample_spec %in% sample_specs]

# Join only after freezing the H07 primary threshold and the two pre-specified
# sample memberships. This prevents the B06 join from changing detector sample
# membership or threshold selection.
primary_panel[, repo_id := suppressWarnings(as.integer(repo_id))]
primary_panel[, time_index := suppressWarnings(as.integer(time_index))]
if (anyNA(primary_panel$repo_id) || anyNA(primary_panel$time_index)) {
  abortf("H07 primary repo_id/time_index must be complete integer-compatible keys before the B06 join.")
}

join_compare_fields <- c(
  "repo_name", "dataset_source", "scope_role", "treatment_group", "time",
  "event", "event_index", "time_to_event", "is_treatment", "post_event",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
b06_lookup_fields <- c("repo_id", "time_index", "log_lines_added_py_source", join_compare_fields)
b06_lookup <- data.table::copy(b06_panel[, ..b06_lookup_fields])
for (field in setdiff(b06_lookup_fields, c("repo_id", "time_index"))) {
  data.table::setnames(b06_lookup, field, paste0("b06__", field))
}
primary_rows_before_b06_join <- nrow(primary_panel)
primary_panel <- merge(primary_panel, b06_lookup, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
if (nrow(primary_panel) != primary_rows_before_b06_join) {
  abortf("B06 join changed H07 primary row count: before=%d after=%d.", primary_rows_before_b06_join, nrow(primary_panel))
}

# Missing B06 velocity means the H07 repo-month key did not resolve to the
# authoritative B06 panel (B06 velocity itself is complete on this panel).
b06_join_missing_velocity <- sum(is.na(primary_panel$b06__log_lines_added_py_source))
if (b06_join_missing_velocity > 0L) {
  abortf("B06 join left %d H07 primary rows without log_lines_added_py_source.", b06_join_missing_velocity)
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

join_audit_parts <- list(
  data.table::data.table(
    audit_type = "join", field = "primary_rows_before_join", mismatches = 0L,
    observed = primary_rows_before_b06_join, expected = primary_rows_before_b06_join, status = "pass",
    note = "H07 primary rows before the B06 velocity join."
  ),
  data.table::data.table(
    audit_type = "join", field = "primary_rows_after_join", mismatches = 0L,
    observed = nrow(primary_panel), expected = primary_rows_before_b06_join, status = ifelse(nrow(primary_panel) == primary_rows_before_b06_join, "pass", "fail"),
    note = "B06 join must not change H07 primary sample membership."
  ),
  data.table::data.table(
    audit_type = "join", field = "missing_b06_velocity_rows", mismatches = b06_join_missing_velocity,
    observed = b06_join_missing_velocity, expected = 0L, status = ifelse(b06_join_missing_velocity == 0L, "pass", "fail"),
    note = "Every H07 primary repo-month must resolve to authoritative B06 log_lines_added_py_source."
  )
)
for (field in join_compare_fields) {
  b06_field <- paste0("b06__", field)
  equal <- values_match(primary_panel[[field]], primary_panel[[b06_field]])
  mismatch_count <- sum(!equal)
  join_audit_parts[[length(join_audit_parts) + 1L]] <- data.table::data.table(
    audit_type = "overlap_field", field = field, mismatches = mismatch_count,
    observed = mismatch_count, expected = 0L, status = ifelse(mismatch_count == 0L, "pass", "fail"),
    note = "H07 field must agree with the authoritative B06 source on matched repo-month keys."
  )
}
b06_join_audit <- data.table::rbindlist(join_audit_parts, use.names = TRUE, fill = TRUE)
b06_join_mismatch_total <- b06_join_audit[status == "fail", sum(mismatches, na.rm = TRUE)]
write_csv(b06_join_audit, paths$b06_join_audit)
if (any(b06_join_audit$status == "fail")) {
  abortf("B06 join/provenance audit failed: %s", paste(b06_join_audit[status == "fail", field], collapse = ", "))
}

primary_panel[, log_lines_added_py_source := b06__log_lines_added_py_source]
drop_b06_columns <- grep("^b06__", names(primary_panel), value = TRUE)
primary_panel[, (drop_b06_columns) := NULL]

# Validate H07 summary and sample-support artifacts before estimation.
h07_summary <- data.table::fread(h07_summary_file, na.strings = c("", "NA", "NaN"))
validate_columns(h07_summary, c("metric", "value"))
summary_lookup <- setNames(as.character(h07_summary$value), as.character(h07_summary$metric))
if (!identical(summary_lookup[["status"]], "PASS")) abortf("H07 summary status is not PASS.")
if (abs(as.numeric(summary_lookup[["primary_threshold"]]) - primary_threshold) > 1e-12) abortf("H07 summary primary threshold mismatch.")

sample_summary_input <- data.table::fread(h07_sample_summary_file, na.strings = c("", "NA", "NaN"))
validate_columns(sample_summary_input, c("sample_spec", "repo_month_rows", "repositories", "control_repositories", "treatment_repositories"))
if (nrow(sample_summary_input[sample_spec == "full_sample"]) != 1L ||
    nrow(sample_summary_input[sample_spec == "exclude_scope_mismatch_repos"]) != 1L) {
  abortf("H07 sample summary must contain exactly one row for each K06 sample specification.")
}
strict_count_check(sample_summary_input[sample_spec == "full_sample", repo_month_rows], expected_full_rows, "H07 sample-summary full rows", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "full_sample", repositories], expected_full_repositories, "H07 sample-summary full repositories", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "full_sample", treatment_repositories], expected_full_treatment_repos, "H07 sample-summary full treatment repositories", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "full_sample", control_repositories], expected_full_control_repos, "H07 sample-summary full control repositories", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "exclude_scope_mismatch_repos", repo_month_rows], expected_sensitivity_rows, "H07 sample-summary sensitivity rows", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "exclude_scope_mismatch_repos", repositories], expected_sensitivity_repositories, "H07 sample-summary sensitivity repositories", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "exclude_scope_mismatch_repos", treatment_repositories], expected_sensitivity_treatment_repos, "H07 sample-summary sensitivity treatment repositories", strict_expected_counts)
strict_count_check(sample_summary_input[sample_spec == "exclude_scope_mismatch_repos", control_repositories], expected_sensitivity_control_repos, "H07 sample-summary sensitivity control repositories", strict_expected_counts)

global_audit <- data.table::fread(h07_global_audit_file, na.strings = c("", "NA", "NaN"))
validate_columns(global_audit, c(
  "sample_spec", "mapping_spec", "threshold_spec_id", "threshold", "threshold_role", "repo_month_rows",
  "repositories", "selected_file_rows", "selected_issue_total"
))
primary_global <- global_audit[
  sample_spec %in% sample_specs & mapping_spec == "all_ml_files" & threshold_role == "primary" &
  abs(as.numeric(threshold) - primary_threshold) <= 1e-12
]
if (nrow(primary_global) != 2L) abortf("Expected two primary rows in H07 global audit; observed %d.", nrow(primary_global))
write_csv(primary_global, paths$threshold_input_audit)

strict_count_check(primary_global[sample_spec == "full_sample", selected_file_rows], expected_primary_full_selected_files, "primary full selected files", strict_expected_counts)
strict_count_check(primary_global[sample_spec == "full_sample", selected_issue_total], expected_primary_full_issue_stock, "primary full issue stock", strict_expected_counts)
strict_count_check(primary_global[sample_spec == "exclude_scope_mismatch_repos", selected_file_rows], expected_primary_sensitivity_selected_files, "primary sensitivity selected files", strict_expected_counts)
strict_count_check(primary_global[sample_spec == "exclude_scope_mismatch_repos", selected_issue_total], expected_primary_sensitivity_issue_stock, "primary sensitivity issue stock", strict_expected_counts)

expected_by_sample <- list(
  full_sample = list(rows = expected_full_rows, repos = expected_full_repositories, treat = expected_full_treatment_repos, control = expected_full_control_repos),
  exclude_scope_mismatch_repos = list(rows = expected_sensitivity_rows, repos = expected_sensitivity_repositories, treat = expected_sensitivity_treatment_repos, control = expected_sensitivity_control_repos)
)

formula_text <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)
model_specs <- data.table::data.table(
  model = "ml_cm_quality_to_velocity",
  direction = "MLCMQuality_{t-1} -> Velocity_t",
  conceptual_direction = "ML-localized Quality_t -> Velocity_{t+1}",
  dependent_variable = "log_lines_added_py_source",
  primary_interaction_term = "lag(log1p_selected_issue_total, 1)",
  localized_quality = "log1p_selected_issue_total",
  threshold_spec_id = "ml_t50",
  threshold = primary_threshold,
  ml_operator = ">",
  instrument_specification = "lag(velocity,2)",
  collapse = FALSE,
  effect = "twoways",
  estimator_model = "twosteps",
  transformation = "d",
  formula = formula_text
)
write_csv(model_specs, paths$model_specs)

coefficients_parts <- list()
diagnostics_parts <- list()
instrument_parts <- list()
sample_qc_parts <- list()
coercion_parts <- list()
legacy_parts <- list()
gap_parts <- list()
qc_parts <- list()
models <- list()
robust_summaries <- list()

for (sample_spec_value in sample_specs) {
  # Use a loop variable whose name cannot be resolved as the data.table column
  # `sample_spec`. In v2, the expression `primary_panel$sample_spec == sample_spec`
  # was evaluated inside data.table scope, so the bare right-hand `sample_spec`
  # resolved to the column itself and selected both sample specifications.
  # The explicit scalar below guarantees exact per-sample filtering.
  panel <- data.table::copy(primary_panel[primary_panel$sample_spec == sample_spec_value])
  sample_spec <- sample_spec_value
  expected <- expected_by_sample[[sample_spec]]
  if (is.null(expected)) abortf("Missing expected-count specification for sample %s.", sample_spec)

  strict_count_check(nrow(panel), expected$rows, sprintf("%s primary rows", sample_spec), strict_expected_counts)
  strict_count_check(data.table::uniqueN(panel$repo_id), expected$repos, sprintf("%s repositories", sample_spec), strict_expected_counts)

  numeric_columns <- c(
    "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
    "is_treatment", "post_event", "log_lines_added_py_source", "log1p_selected_issue_total",
    "selected_issue_total", "selected_file_count", "eligible_ml_file_count",
    "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
  )
  coercion <- coerce_numeric_with_audit(panel, numeric_columns, sample_spec)
  coercion_parts[[sample_spec]] <- coercion
  if (any(coercion$coercion_generated_na > 0L)) {
    bad <- coercion[coercion_generated_na > 0L]
    abortf("Numeric coercion generated NA values in %s: %s", sample_spec, paste(bad$column, bad$coercion_generated_na, sep = "=", collapse = "; "))
  }

  if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) {
    abortf("repo_id, time_index, and event_index must be complete in sample %s.", sample_spec)
  }
  panel[, repo_id := as.integer(repo_id)]
  panel[, time_index := as.integer(time_index)]
  panel[, event_index := as.integer(event_index)]
  panel[, treatment_group := as.integer(treatment_group)]

  if (any(panel$ncloc_py_sonarqube < 0, na.rm = TRUE)) abortf("ncloc_py_sonarqube must be non-negative in sample %s.", sample_spec)
  if (any(panel$selected_issue_total < 0, na.rm = TRUE)) abortf("selected_issue_total must be non-negative in sample %s.", sample_spec)
  if (any(panel$selected_file_count < 0, na.rm = TRUE)) abortf("selected_file_count must be non-negative in sample %s.", sample_spec)
  panel[, log_ncloc_py_sonarqube := log1p(ncloc_py_sonarqube)]

  log_recompute_mismatch <- sum(abs(panel$log1p_selected_issue_total - log1p(panel$selected_issue_total)) > 1e-12, na.rm = TRUE)
  if (log_recompute_mismatch > 0L) abortf("Found %d log1p selected-issue recomputation mismatches in sample %s.", log_recompute_mismatch, sample_spec)

  expected_selected_files <- if (sample_spec == "full_sample") expected_primary_full_selected_files else expected_primary_sensitivity_selected_files
  expected_issue_stock <- if (sample_spec == "full_sample") expected_primary_full_issue_stock else expected_primary_sensitivity_issue_stock
  strict_count_check(sum(panel$selected_file_count), expected_selected_files, sprintf("%s long-panel selected-file total", sample_spec), strict_expected_counts)
  strict_count_check(sum(panel$selected_issue_total), expected_issue_stock, sprintf("%s long-panel selected-issue total", sample_spec), strict_expected_counts)

  panel[, event_time_normalized := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
  panel[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
  panel[, legacy_cursor_flag := bool_to_int(cursor)]
  panel[, legacy_is_treatment := as.integer(replace(is_treatment, is.na(is_treatment), 0))]
  panel[, legacy_post_event := as.integer(replace(post_event, is.na(post_event), 0))]
  panel[, mismatch_cursor := legacy_cursor_flag != absorbing_treated]
  panel[, mismatch_is_treatment := legacy_is_treatment != absorbing_treated]
  panel[, mismatch_post_event := legacy_post_event != absorbing_treated]
  panel[, legacy_mismatch_any := mismatch_cursor | mismatch_is_treatment | mismatch_post_event]

  repo_count <- data.table::uniqueN(panel$repo_id)
  treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
  control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])
  strict_count_check(treatment_repos, expected$treat, sprintf("%s treatment repositories", sample_spec), strict_expected_counts)
  strict_count_check(control_repos, expected$control, sprintf("%s control repositories", sample_spec), strict_expected_counts)

  duplicate_rows <- panel[, .N, by = .(repo_id, time_index)][N > 1L]
  if (nrow(duplicate_rows) > 0L) abortf("Found %d duplicate repo_id-time_index keys in sample %s.", nrow(duplicate_rows), sample_spec)

  role_mismatch <- panel[
    (scope_role == "treatment" & treatment_group != 1L) |
    (scope_role == "control" & treatment_group != 0L)
  ]
  if (nrow(role_mismatch) > 0L) abortf("Found %d scope_role/treatment_group inconsistencies in sample %s.", nrow(role_mismatch), sample_spec)

  control_event_errors <- panel[treatment_group == 0L & event_index != 0L]
  treatment_event_errors <- panel[treatment_group == 1L & event_index <= 0L]
  if (nrow(control_event_errors) > 0L) abortf("Found %d control rows with nonzero event_index in sample %s.", nrow(control_event_errors), sample_spec)
  if (nrow(treatment_event_errors) > 0L) abortf("Found %d treatment rows with nonpositive event_index in sample %s.", nrow(treatment_event_errors), sample_spec)

  timing_errors <- panel[
    treatment_group == 1L & (is.na(time_to_event) | as.integer(time_to_event) != event_time_normalized)
  ]
  if (nrow(timing_errors) > 0L) abortf("Found %d normalized timing errors in sample %s.", nrow(timing_errors), sample_spec)

  model_fields <- c(
    "log_lines_added_py_source", "log1p_selected_issue_total", "log_ncloc_py_sonarqube",
    "log_age", "log_contributors", "log_stars", "log_issues"
  )
  missing_model_rows <- panel[!stats::complete.cases(panel[, ..model_fields])]
  if (nrow(missing_model_rows) > 0L) abortf("Found %d missing GMM model rows in sample %s.", nrow(missing_model_rows), sample_spec)
  nonfinite_model_rows <- panel[
    !apply(as.data.frame(panel[, ..model_fields]), 1L, function(row) all(is.finite(row)))
  ]
  if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d non-finite GMM model rows in sample %s.", nrow(nonfinite_model_rows), sample_spec)

  legacy_audit <- panel[legacy_mismatch_any == TRUE, .(
    sample_spec = sample_spec, repo_id, repo_name, time, time_index, event, event_index,
    time_to_event, event_time_normalized, absorbing_treated,
    legacy_cursor = cursor, legacy_cursor_flag, legacy_is_treatment, legacy_post_event,
    mismatch_cursor, mismatch_is_treatment, mismatch_post_event, scope_role, treatment_group
  )]
  legacy_parts[[sample_spec]] <- legacy_audit
  legacy_mismatch_rows <- nrow(legacy_audit)
  legacy_mismatch_repos <- data.table::uniqueN(legacy_audit$repo_id)
  strict_count_check(legacy_mismatch_rows, expected_legacy_mismatch_rows, sprintf("%s legacy mismatch rows", sample_spec), strict_expected_counts)
  strict_count_check(legacy_mismatch_repos, expected_legacy_mismatch_repos, sprintf("%s legacy mismatch repositories", sample_spec), strict_expected_counts)

  data.table::setorder(panel, repo_id, time_index)
  panel[, previous_time_index := data.table::shift(time_index), by = repo_id]
  panel[, calendar_gap := time_index - previous_time_index]
  calendar_gap_rows <- panel[!is.na(previous_time_index) & calendar_gap != 1L, .(
    sample_spec = sample_spec, repo_id, repo_name, previous_time_index,
    time_index, calendar_gap, time
  )]
  gap_parts[[sample_spec]] <- calendar_gap_rows

  key_set <- unique(make_key(panel$repo_id, panel$time_index))
  panel[, has_exact_lag1 := make_key(repo_id, time_index - 1L) %in% key_set]
  panel[, has_exact_lag2 := make_key(repo_id, time_index - 2L) %in% key_set]
  active_panel <- panel[has_exact_lag1 & has_exact_lag2]
  active_rows <- nrow(active_panel)
  active_repos <- data.table::uniqueN(active_panel$repo_id)
  active_treatment_repos <- data.table::uniqueN(active_panel[treatment_group == 1L, repo_id])
  active_control_repos <- data.table::uniqueN(active_panel[treatment_group == 0L, repo_id])
  active_treatment_rows <- nrow(active_panel[treatment_group == 1L])
  active_control_rows <- nrow(active_panel[treatment_group == 0L])
  active_post_rows <- nrow(active_panel[absorbing_treated == 1L])

  quality_nonzero_rows <- nrow(panel[selected_issue_total > 0])
  quality_zero_share <- mean(panel$selected_issue_total == 0)
  quality_variation_repos <- panel[, .(quality_unique = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][quality_unique > 1L, .N]

  estimation_data <- panel[, .(
    repo_id,
    time_index,
    log_lines_added_py_source,
    log1p_selected_issue_total,
    absorbing_treated,
    log_ncloc_py_sonarqube,
    log_age,
    log_contributors,
    log_stars,
    log_issues
  )]
  pdata <- plm::pdata.frame(estimation_data, index = c("repo_id", "time_index"), drop.index = FALSE, row.names = FALSE)

  formula <- stats::as.formula(formula_text)
  log_message("INFO", "Fitting ML-localized quality -> velocity GMM for sample=%s", sample_spec)
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
  if (fit_capture$error) abortf("GMM model failed for sample %s: %s", sample_spec, fit_capture$value$message)

  summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
  if (summary_capture$error) abortf("Robust GMM summary failed for sample %s: %s", sample_spec, summary_capture$value$message)

  model_name <- "ml_cm_quality_to_velocity"
  primary_term <- "lag(log1p_selected_issue_total, 1)"
  direction <- "MLCMQuality_{t-1} -> Velocity_t"
  coefficients_parts[[sample_spec]] <- extract_pgmm_coefficients(summary_capture$value, sample_spec, model_name, direction, primary_term, confidence_level)

  all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings))
  diagnostics <- data.table::rbindlist(list(
    extract_htest(summary_capture$value$sargan, sample_spec, model_name, "sargan"),
    extract_htest(summary_capture$value$m1, sample_spec, model_name, "ar1"),
    extract_htest(summary_capture$value$m2, sample_spec, model_name, "ar2")
  ), use.names = TRUE, fill = TRUE)
  diagnostics[, `:=`(
    robust_summary = TRUE,
    warning_count = length(all_warnings),
    warning_messages = paste(all_warnings, collapse = " | ")
  )]
  diagnostics_parts[[sample_spec]] <- diagnostics

  dimensions <- extract_model_dimensions(fit_capture$value)
  instrument_ratio <- if (is.finite(dimensions$instrument_count_for_ratio) && active_repos > 0L) dimensions$instrument_count_for_ratio / active_repos else NA_real_
  instrument_parts[[sample_spec]] <- data.table::data.table(
    sample_spec = sample_spec,
    model = model_name,
    collapse = FALSE,
    instrument_specification = "lag(velocity,2)",
    minimum_calendar_support_rows = active_rows,
    minimum_calendar_support_repositories = active_repos,
    stats_nobs = dimensions$stats_nobs,
    active_gmm_repositories = active_repos,
    active_gmm_treatment_repositories = active_treatment_repos,
    active_gmm_control_repositories = active_control_repos,
    pgmm_internal_matrix_rows = dimensions$pgmm_internal_matrix_rows,
    pgmm_internal_repository_slots = dimensions$pgmm_internal_repository_slots,
    instrument_columns_min = dimensions$instrument_columns_min,
    instrument_columns_max = dimensions$instrument_columns_max,
    instrument_columns_unique = dimensions$instrument_columns_unique,
    instrument_columns_constant = dimensions$instrument_columns_constant,
    instrument_count_for_ratio = dimensions$instrument_count_for_ratio,
    instrument_ratio_denominator = active_repos,
    instrument_to_repository_ratio = instrument_ratio,
    instrument_proliferation_flag = is.finite(instrument_ratio) && instrument_ratio >= 1,
    runtime_seconds = fit_capture$elapsed + summary_capture$elapsed,
    warning_count = length(unique(c(fit_capture$warnings, summary_capture$warnings))),
    warning_messages = paste(unique(c(fit_capture$warnings, summary_capture$warnings)), collapse = " | ")
  )

  sample_qc_parts[[sample_spec]] <- data.table::rbindlist(list(
    make_summary_row(sample_spec, "source_rows", nrow(panel)),
    make_summary_row(sample_spec, "source_repositories", repo_count),
    make_summary_row(sample_spec, "treatment_repositories", treatment_repos),
    make_summary_row(sample_spec, "control_repositories", control_repos),
    make_summary_row(sample_spec, "selected_file_rows", sum(panel$selected_file_count)),
    make_summary_row(sample_spec, "selected_issue_stock", sum(panel$selected_issue_total)),
    make_summary_row(sample_spec, "repo_months_with_selected_files", nrow(panel[selected_file_count > 0])),
    make_summary_row(sample_spec, "repo_months_with_positive_selected_issue_stock", quality_nonzero_rows),
    make_summary_row(sample_spec, "selected_issue_zero_share", quality_zero_share),
    make_summary_row(sample_spec, "repositories_with_within_selected_quality_variation", quality_variation_repos),
    make_summary_row(sample_spec, "calendar_gap_transitions", nrow(calendar_gap_rows)),
    make_summary_row(sample_spec, "exact_t1_t2_support_rows", active_rows),
    make_summary_row(sample_spec, "active_gmm_repositories", active_repos),
    make_summary_row(sample_spec, "active_gmm_treatment_repositories", active_treatment_repos),
    make_summary_row(sample_spec, "active_gmm_control_repositories", active_control_repos),
    make_summary_row(sample_spec, "active_gmm_treatment_rows", active_treatment_rows),
    make_summary_row(sample_spec, "active_gmm_control_rows", active_control_rows),
    make_summary_row(sample_spec, "active_gmm_post_treatment_rows", active_post_rows),
    make_summary_row(sample_spec, "stats_nobs", dimensions$stats_nobs),
    make_summary_row(sample_spec, "pgmm_internal_matrix_rows", dimensions$pgmm_internal_matrix_rows, "Internal balanced/transformed pgmm rows; not estimation N."),
    make_summary_row(sample_spec, "pgmm_internal_repository_slots", dimensions$pgmm_internal_repository_slots, "Internal pgmm list slots; not active GMM repositories."),
    make_summary_row(sample_spec, "legacy_mismatch_rows", legacy_mismatch_rows),
    make_summary_row(sample_spec, "legacy_mismatch_repositories", legacy_mismatch_repos),
    make_summary_row(sample_spec, "log1p_selected_issue_recomputation_mismatches", log_recompute_mismatch),
    make_summary_row(sample_spec, "missing_model_rows", nrow(missing_model_rows)),
    make_summary_row(sample_spec, "nonfinite_model_rows", nrow(nonfinite_model_rows))
  ), use.names = TRUE, fill = TRUE)

  primary_rows <- coefficients_parts[[sample_spec]][is_primary_interaction_term == TRUE, .N]
  diagnostic_missing <- diagnostics[status != "available", .N]
  ar1_p <- diagnostics[diagnostic == "ar1", p_value][1L]
  ar2_p <- diagnostics[diagnostic == "ar2", p_value][1L]
  sargan_p <- diagnostics[diagnostic == "sargan", p_value][1L]
  model_warning_count <- length(unique(c(fit_capture$warnings, summary_capture$warnings)))

  qc_parts[[sample_spec]] <- data.table::data.table(
    sample_spec = sample_spec,
    check = c(
      "source_rows", "source_repositories", "treatment_repositories", "control_repositories",
      "duplicate_repo_time_rows", "normalized_timing_errors", "numeric_coercion_generated_na",
      "missing_model_rows", "nonfinite_model_rows", "log1p_selected_issue_recomputation_mismatches",
      "legacy_mismatch_rows", "legacy_mismatch_repositories", "primary_interaction_term_rows",
      "gmm_diagnostic_missing_count", "stats_nobs_matches_active_rows", "ar1_expected_pattern",
      "ar2_no_second_order_serial_correlation", "sargan_overidentification", "model_warning_count",
      "instrument_ratio", "calendar_gap_transitions"
    ),
    observed = c(
      nrow(panel), repo_count, treatment_repos, control_repos,
      nrow(duplicate_rows), nrow(timing_errors), sum(coercion$coercion_generated_na),
      nrow(missing_model_rows), nrow(nonfinite_model_rows), log_recompute_mismatch,
      legacy_mismatch_rows, legacy_mismatch_repos, primary_rows,
      diagnostic_missing, dimensions$stats_nobs, ar1_p,
      ar2_p, sargan_p, model_warning_count,
      instrument_ratio, nrow(calendar_gap_rows)
    ),
    expected = c(
      expected$rows, expected$repos, expected$treat, expected$control,
      0, 0, 0, 0, 0, 0,
      expected_legacy_mismatch_rows, expected_legacy_mismatch_repos, 1,
      0, active_rows, NA, NA, NA, NA, NA, NA
    ),
    status = c(
      ifelse(nrow(panel) == expected$rows, "pass", "fail"),
      ifelse(repo_count == expected$repos, "pass", "fail"),
      ifelse(treatment_repos == expected$treat, "pass", "fail"),
      ifelse(control_repos == expected$control, "pass", "fail"),
      ifelse(nrow(duplicate_rows) == 0L, "pass", "fail"),
      ifelse(nrow(timing_errors) == 0L, "pass", "fail"),
      ifelse(sum(coercion$coercion_generated_na) == 0L, "pass", "fail"),
      ifelse(nrow(missing_model_rows) == 0L, "pass", "fail"),
      ifelse(nrow(nonfinite_model_rows) == 0L, "pass", "fail"),
      ifelse(log_recompute_mismatch == 0L, "pass", "fail"),
      ifelse(legacy_mismatch_rows == expected_legacy_mismatch_rows, "pass", "fail"),
      ifelse(legacy_mismatch_repos == expected_legacy_mismatch_repos, "pass", "fail"),
      ifelse(primary_rows == 1L, "pass", "fail"),
      ifelse(diagnostic_missing == 0L, "pass", "fail"),
      ifelse(is.finite(dimensions$stats_nobs) && dimensions$stats_nobs == active_rows, "pass", "fail"),
      ifelse(is.finite(ar1_p) && ar1_p < 0.05, "pass", "caution"),
      ifelse(is.finite(ar2_p) && ar2_p >= 0.05, "pass", "caution"),
      ifelse(is.finite(sargan_p) && sargan_p >= 0.05, "pass", "caution"),
      ifelse(model_warning_count == 0L, "pass", "caution"),
      ifelse(is.finite(instrument_ratio) && instrument_ratio < 1, "pass", "caution"),
      ifelse(nrow(calendar_gap_rows) == 0L, "pass", "informational")
    ),
    note = c(
      "Primary H07 sample invariant.", "Primary H07 sample invariant.", "Primary H07 sample invariant.", "Primary H07 sample invariant.",
      "Must be zero.", "Normalized timing must be exact.", "Numeric parsing must not introduce missingness.",
      "GMM fields must be complete.", "GMM fields must be finite.", "H07 localized quality log outcome must equal log1p(selected_issue_total).",
      "Legacy mismatch is audit-only.", "Legacy mismatch is audit-only.", "Exactly one lagged ML-quality coefficient is required.",
      "Sargan, AR(1), and AR(2) must be returned.", "stats::nobs(pgmm) should equal exact-calendar t-1/t-2 active rows.",
      "Difference-GMM commonly yields AR(1) after differencing; non-significance is caution, not failure.",
      "AR(2) p < 0.05 would invalidate the usual lag-instrument interpretation.",
      "Sargan p < 0.05 is recorded as caution for instrument-validity review rather than silently accepted.",
      "Model warnings are retained for review.", "Caution if instrument dimension is at least active repository count.",
      "Calendar gaps are audited; indexed lags must not be row shifted."
    )
  )

  models[[sample_spec]] <- fit_capture$value
  robust_summaries[[sample_spec]] <- summary_capture$value
}

coefficients <- data.table::rbindlist(coefficients_parts, use.names = TRUE, fill = TRUE)
diagnostics <- data.table::rbindlist(diagnostics_parts, use.names = TRUE, fill = TRUE)
instrument_qc <- data.table::rbindlist(instrument_parts, use.names = TRUE, fill = TRUE)
sample_qc <- data.table::rbindlist(sample_qc_parts, use.names = TRUE, fill = TRUE)
coercion_audit <- data.table::rbindlist(coercion_parts, use.names = TRUE, fill = TRUE)
legacy_audit <- data.table::rbindlist(legacy_parts, use.names = TRUE, fill = TRUE)
calendar_gap_audit <- data.table::rbindlist(gap_parts, use.names = TRUE, fill = TRUE)
qc <- data.table::rbindlist(qc_parts, use.names = TRUE, fill = TRUE)

write_csv(coefficients, paths$coefficients)
write_csv(diagnostics, paths$diagnostics)
write_csv(instrument_qc, paths$instrument_qc)
write_csv(sample_qc, paths$sample_qc)
write_csv(coercion_audit, paths$coercion_audit)
write_csv(legacy_audit, paths$legacy_audit)
write_csv(calendar_gap_audit, paths$calendar_gap_audit)
write_csv(qc, paths$qc)

failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) {
  abortf("run-x-k06 ML GMM QC failed: %s", paste(paste(failed_qc$sample_spec, failed_qc$check, sep = "/"), collapse = ", "))
}

saveRDS(list(models = models, robust_summaries = robust_summaries), paths$models_rds)

run_finished <- Sys.time()
metadata <- data.table::rbindlist(list(
  make_summary_row("run", "run_prefix", "run-x-k06"),
  make_summary_row("run", "implementation_version", implementation_version),
  make_summary_row("run", "started", format(run_started, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "finished", format(run_finished, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "runtime_seconds", as.numeric(difftime(run_finished, run_started, units = "secs"))),
  make_summary_row("run", "input_file", input_file),
  make_summary_row("run", "input_sha256", sha256_file(input_file)),
  make_summary_row("run", "b06_panel_file", b06_panel_file),
  make_summary_row("run", "b06_panel_sha256", sha256_file(b06_panel_file)),
  make_summary_row("run", "h07_summary_file", h07_summary_file),
  make_summary_row("run", "h07_summary_sha256", sha256_file(h07_summary_file)),
  make_summary_row("run", "h07_sample_summary_file", h07_sample_summary_file),
  make_summary_row("run", "h07_sample_summary_sha256", sha256_file(h07_sample_summary_file)),
  make_summary_row("run", "h07_global_audit_file", h07_global_audit_file),
  make_summary_row("run", "h07_global_audit_sha256", sha256_file(h07_global_audit_file)),
  make_summary_row("run", "script_path", script_path),
  make_summary_row("run", "script_sha256", sha256_file(script_path)),
  make_summary_row("software", "R", R.version.string),
  make_summary_row("software", "platform", R.version$platform),
  make_summary_row("software", "hostname", Sys.info()[["nodename"]]),
  make_summary_row("software", "data.table", safe_package_version("data.table")),
  make_summary_row("software", "plm", safe_package_version("plm")),
  make_summary_row("definition", "analysis_scope", "agc_ml_cm_localized_quality_to_velocity"),
  make_summary_row("definition", "localization_scope", "CM"),
  make_summary_row("definition", "detector_scope_pair", "ML|CM"),
  make_summary_row("definition", "detector", "AGCDetector_ML"),
  make_summary_row("definition", "ml_metric", "file_ml_cfun_agc_share_space_by_token_weighted"),
  make_summary_row("definition", "threshold_spec_id", "ml_t50"),
  make_summary_row("definition", "primary_threshold", primary_threshold),
  make_summary_row("definition", "ml_operator", ">"),
  make_summary_row("definition", "localized_quality", "log1p_selected_issue_total"),
  make_summary_row("definition", "velocity", "log_lines_added_py_source"),
  make_summary_row("definition", "velocity_source", "run-x-b06 authoritative panel joined by exact repo_id + time_index"),
  make_summary_row("definition", "b06_join_overlap_fields", paste(join_compare_fields, collapse = "|")),
  make_summary_row("qc", "b06_join_failed_fields", b06_join_audit[status == "fail", .N]),
  make_summary_row("qc", "b06_join_missing_velocity_rows", b06_join_missing_velocity),
  make_summary_row("definition", "samples", paste(sample_specs, collapse = "|")),
  make_summary_row("definition", "treatment", "absorbing_treated"),
  make_summary_row("definition", "size_control", "log1p(ncloc_py_sonarqube)"),
  make_summary_row("definition", "other_controls", "log_age|log_contributors|log_stars|log_issues"),
  make_summary_row("definition", "effect", "twoways"),
  make_summary_row("definition", "model", "twosteps"),
  make_summary_row("definition", "transformation", "d"),
  make_summary_row("definition", "collapse", "false"),
  make_summary_row("definition", "instrument_specification", "lag(velocity,2)"),
  make_summary_row("definition", "formula", formula_text),
  make_summary_row("definition", "scope_note", "Secondary detector-localized GMM: lagged ML-selected issue burden predicts subsequent whole-Python velocity; detector-localized velocity flow is not yet constructed."),
  make_summary_row("definition", "quality_semantics", "unresolved SonarQube issue stock among Python files with ML-CM share > 0.50 at the corresponding historical snapshot"),
  make_summary_row("definition", "log_transform_rule", "Velocity and localized quality are already log1p outcomes and are not transformed again; whole-Python SonarQube NCLOC is transformed with log1p inside this script."),
  make_summary_row("definition", "active_gmm_sample_rule", "Exact calendar t-1 and t-2 support."),
  make_summary_row("definition", "instrument_ratio_denominator", "active_gmm_repositories"),
  make_summary_row("definition", "ar1_qc_rule", "AR(1) p >= 0.05 is caution, not failure."),
  make_summary_row("definition", "ar2_qc_rule", "AR(2) p < 0.05 is recorded as caution for model-validity review."),
  make_summary_row("qc", "failed_checks", nrow(failed_qc)),
  make_summary_row("qc", "caution_checks", qc[status == "caution", .N])
), use.names = TRUE, fill = TRUE)
write_csv(metadata, paths$run_metadata)

log_message(
  "INFO",
  "Completed run-x-k06 %s: samples=%d; coefficients=%d; diagnostics=%d; failed_qc=%d; cautions=%d",
  implementation_version, length(sample_specs), nrow(coefficients), nrow(diagnostics),
  nrow(failed_qc), qc[status == "caution", .N]
)
