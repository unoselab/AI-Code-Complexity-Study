#!/usr/bin/env Rscript

# ============================================================
# run-x-e03 v3: ML GMM null-result robustness recheck
# ============================================================
#
# This script reuses validated helper logic from E03-v2 but is a standalone
# analysis implementation. It never calls prior experiment scripts.
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
# run-x-e03 v3 recheck: ML-localized quality -> future velocity
# ============================================================
#
# Purpose:
#   Recheck the E03-v2 null ML-quality result without changing the frozen ML
#   detector or file-selection rule. This is a post-result robustness analysis,
#   not a search for a significant specification. Every prespecified recheck is
#   reported, regardless of sign or p-value.
#
# Frozen measurement contract:
#   - file metric: file_ml_agc_share_space_by_token_weighted
#   - file rule: strict metric > 0.50
#   - localized quality: log1p_selected_issue_total
#   - velocity: log_lines_added_py_source from B06
#   - primary sample: full_sample + all_ml_files
#
# Recheck specifications:
#   R0 reference: two-step difference GMM, lag-2 instrument, uncollapsed
#   R1:           same model, collapsed instruments
#   R2:           one-step difference GMM, lag-2 instrument, uncollapsed
#   R3:           two-step, lag-2:3 instruments, collapsed
#   R4:           two-step reference instruments, no contemporaneous controls
#
# The frozen 0.50 file-composition threshold is never changed here.
# ============================================================

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
b06_panel_file <- normalizePath(require_arg(args, "b06_panel_file"), mustWork = TRUE)
reference_coefficients_file <- normalizePath(require_arg(args, "reference_coefficients_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v3" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
primary_threshold <- as_numeric_arg(args, "primary_threshold", 0.50)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
reference_tolerance <- as_numeric_arg(args, "reference_tolerance", 1e-10)
expected_input_rows <- as_integer_arg(args, "expected_input_rows", 7738L)
expected_full_rows <- as_integer_arg(args, "expected_full_rows", 1954L)
expected_full_repositories <- as_integer_arg(args, "expected_full_repositories", 167L)
expected_full_treatment_repos <- as_integer_arg(args, "expected_full_treatment_repos", 63L)
expected_full_control_repos <- as_integer_arg(args, "expected_full_control_repos", 104L)
expected_primary_selected_file_rows <- as_integer_arg(args, "expected_primary_selected_file_rows", 43325L)
expected_primary_issue_stock <- as_integer_arg(args, "expected_primary_issue_stock", 48478L)
expected_full_active_rows <- as_integer_arg(args, "expected_full_active_rows", 1631L)
expected_full_active_repositories <- as_integer_arg(args, "expected_full_active_repositories", 146L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", 11L)
expected_legacy_mismatch_repos <- as_integer_arg(args, "expected_legacy_mismatch_repos", 3L)

if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")
if (abs(primary_threshold - 0.50) > 1e-12) abortf("E03 recheck requires the frozen ML primary threshold 0.50.")
if (!is.finite(reference_tolerance) || reference_tolerance < 0) abortf("reference_tolerance must be non-negative.")
check_packages(c("data.table", "plm"))
suppressPackageStartupMessages(library(plm))
if (!exists("plm", mode = "function", inherits = TRUE)) abortf("plm() is not visible after package attachment.")

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
paths <- list(
  coefficients = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_coefficients.csv"),
  primary_summary = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_primary_summary.csv"),
  diagnostics = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_diagnostics.csv"),
  instrument_qc = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_instrument_qc.csv"),
  support = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_support_diagnostics.csv"),
  reference = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_reference_reproduction.csv"),
  model_specs = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_model_specifications.csv"),
  join_audit = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_b06_join_audit.csv"),
  qc = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_qc.csv"),
  metadata = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_run_metadata.csv"),
  models_rds = file.path(output_dir, "dynamic_panel_gmm_ml_recheck_models.rds")
)

run_started <- Sys.time()
log_message("INFO", "Reading D05 ML-localized quality panel: %s", input_file)
d05 <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
required_d05 <- c(
  "sample_spec", "mapping_spec", "primary_analysis", "ml_primary_metric",
  "ml_primary_operator", "ml_primary_threshold", "repo_id", "time_index",
  "log1p_selected_issue_total", "selected_issue_total"
)
validate_columns(d05, required_d05)
if (!"selected_file_rows" %in% names(d05)) {
  if ("selected_file_count" %in% names(d05)) d05[, selected_file_rows := selected_file_count]
  else abortf("D05 input must contain selected_file_rows or selected_file_count.")
}
strict_count_check(nrow(d05), expected_input_rows, "D05 rows", strict_expected_counts)

expected_metric <- "file_ml_agc_share_space_by_token_weighted"
metric_errors <- sum(is.na(d05$ml_primary_metric) | as.character(d05$ml_primary_metric) != expected_metric)
operator_errors <- sum(is.na(d05$ml_primary_operator) | as.character(d05$ml_primary_operator) != ">")
threshold_num <- suppressWarnings(as.numeric(d05$ml_primary_threshold))
threshold_errors <- sum(is.na(threshold_num) | abs(threshold_num - primary_threshold) > 1e-12)
if (metric_errors + operator_errors + threshold_errors > 0L) {
  abortf("Frozen D05 ML contract mismatch: metric=%d operator=%d threshold=%d", metric_errors, operator_errors, threshold_errors)
}

primary_flag <- bool_to_int(d05$primary_analysis)
primary_contract_errors <- sum(
  (d05$sample_spec == "full_sample" & d05$mapping_spec == "all_ml_files" & primary_flag != 1L) |
  (!(d05$sample_spec == "full_sample" & d05$mapping_spec == "all_ml_files") & primary_flag != 0L)
)
if (primary_contract_errors > 0L) abortf("Found %d primary_analysis contract errors.", primary_contract_errors)

primary_d05 <- data.table::copy(d05[
  d05$sample_spec == "full_sample" & d05$mapping_spec == "all_ml_files"
])
strict_count_check(nrow(primary_d05), expected_full_rows, "primary D05 rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(primary_d05$repo_id), expected_full_repositories, "primary D05 repositories", strict_expected_counts)
strict_count_check(sum(suppressWarnings(as.numeric(primary_d05$selected_file_rows)), na.rm = TRUE), expected_primary_selected_file_rows, "primary selected file rows", strict_expected_counts)
strict_count_check(sum(suppressWarnings(as.numeric(primary_d05$selected_issue_total)), na.rm = TRUE), expected_primary_issue_stock, "primary selected issue stock", strict_expected_counts)

log_message("INFO", "Reading B06 whole-Python panel: %s", b06_panel_file)
b06 <- data.table::fread(b06_panel_file, na.strings = c("", "NA", "NaN"))
b06_required <- c(
  "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event", "is_treatment",
  "post_event", "cursor", "log_lines_added_py_source", "log_issue_total_py_sonarqube",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
validate_columns(b06, b06_required)
strict_count_check(nrow(b06), expected_full_rows, "B06 rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(b06$repo_id), expected_full_repositories, "B06 repositories", strict_expected_counts)

primary_d05[, repo_id := suppressWarnings(as.integer(repo_id))]
primary_d05[, time_index := suppressWarnings(as.integer(time_index))]
b06[, repo_id := suppressWarnings(as.integer(repo_id))]
b06[, time_index := suppressWarnings(as.integer(time_index))]
if (anyNA(primary_d05$repo_id) || anyNA(primary_d05$time_index) || anyNA(b06$repo_id) || anyNA(b06$time_index)) {
  abortf("repo_id/time_index must be integer-compatible and complete.")
}
if (nrow(b06[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("B06 contains duplicate repo-time keys.")
if (nrow(primary_d05[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("Primary D05 contains duplicate repo-time keys.")

b06_lookup <- data.table::copy(b06[, ..b06_required])
for (field in setdiff(b06_required, c("repo_id", "time_index"))) {
  data.table::setnames(b06_lookup, field, paste0("b06__", field))
}
joined <- merge(primary_d05, b06_lookup, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
if (nrow(joined) != nrow(primary_d05)) abortf("B06 join changed primary D05 row count.")
missing_velocity <- sum(is.na(joined$b06__log_lines_added_py_source))
if (missing_velocity > 0L) abortf("B06 join left %d primary rows without velocity.", missing_velocity)

compare_candidates <- c(
  "repo_name", "dataset_source", "scope_role", "treatment_group", "time", "event",
  "event_index", "time_to_event", "is_treatment", "post_event", "log_age",
  "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
values_match <- function(left, right, tolerance = 1e-10) {
  left_num <- suppressWarnings(as.numeric(left)); right_num <- suppressWarnings(as.numeric(right))
  numeric_compatible <- all((is.na(left) | !is.na(left_num)) & (is.na(right) | !is.na(right_num)))
  if (numeric_compatible) {
    return((is.na(left_num) & is.na(right_num)) | (!is.na(left_num) & !is.na(right_num) & abs(left_num - right_num) <= tolerance))
  }
  left_chr <- as.character(left); right_chr <- as.character(right)
  (is.na(left_chr) & is.na(right_chr)) | (!is.na(left_chr) & !is.na(right_chr) & left_chr == right_chr)
}
join_rows <- list(data.table::data.table(field = "missing_b06_velocity_rows", mismatches = missing_velocity, status = ifelse(missing_velocity == 0L, "pass", "fail")))
for (field in intersect(compare_candidates, names(primary_d05))) {
  equal <- values_match(joined[[field]], joined[[paste0("b06__", field)]])
  mismatch_count <- sum(!equal)
  join_rows[[length(join_rows) + 1L]] <- data.table::data.table(
    field = field, mismatches = mismatch_count, status = ifelse(mismatch_count == 0L, "pass", "fail")
  )
}
join_audit <- data.table::rbindlist(join_rows, fill = TRUE)
write_csv(join_audit, paths$join_audit)
if (any(join_audit$status == "fail")) abortf("B06 join audit failed.")

for (field in setdiff(b06_required, c("repo_id", "time_index"))) joined[, (field) := get(paste0("b06__", field))]
joined[, log_lines_added_py_source := b06__log_lines_added_py_source]
joined[, log_issue_total_py_sonarqube := b06__log_issue_total_py_sonarqube]
joined[, (grep("^b06__", names(joined), value = TRUE)) := NULL]

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "is_treatment", "post_event", "log_lines_added_py_source", "log_issue_total_py_sonarqube",
  "log1p_selected_issue_total", "selected_issue_total", "selected_file_rows", "log_age",
  "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
)
coercion <- coerce_numeric_with_audit(joined, numeric_columns, "full_sample__all_ml_files")
if (any(coercion$coercion_generated_na > 0L)) abortf("Numeric coercion generated missing values.")
joined[, `:=`(
  repo_id = as.integer(repo_id), time_index = as.integer(time_index),
  event_index = as.integer(event_index), treatment_group = as.integer(treatment_group),
  log_ncloc_py_sonarqube = log1p(ncloc_py_sonarqube)
)]
if (any(joined$ncloc_py_sonarqube < 0, na.rm = TRUE) || any(joined$selected_issue_total < 0, na.rm = TRUE)) abortf("Negative size/count found.")
if (sum(abs(joined$log1p_selected_issue_total - log1p(joined$selected_issue_total)) > 1e-12, na.rm = TRUE) > 0L) abortf("Localized quality log recomputation mismatch.")

joined[, event_time_normalized := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
joined[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
joined[, legacy_cursor_flag := bool_to_int(cursor)]
joined[, legacy_is_treatment := as.integer(replace(is_treatment, is.na(is_treatment), 0))]
joined[, legacy_post_event := as.integer(replace(post_event, is.na(post_event), 0))]
joined[, legacy_mismatch_any :=
  legacy_cursor_flag != absorbing_treated |
  legacy_is_treatment != absorbing_treated |
  legacy_post_event != absorbing_treated
]

strict_count_check(data.table::uniqueN(joined[treatment_group == 1L, repo_id]), expected_full_treatment_repos, "primary treatment repositories", strict_expected_counts)
strict_count_check(data.table::uniqueN(joined[treatment_group == 0L, repo_id]), expected_full_control_repos, "primary control repositories", strict_expected_counts)
strict_count_check(nrow(joined[legacy_mismatch_any == TRUE]), expected_legacy_mismatch_rows, "legacy mismatch rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(joined[legacy_mismatch_any == TRUE, repo_id]), expected_legacy_mismatch_repos, "legacy mismatch repositories", strict_expected_counts)

model_fields <- c(
  "log_lines_added_py_source", "log_issue_total_py_sonarqube", "log1p_selected_issue_total",
  "log_ncloc_py_sonarqube", "log_age", "log_contributors", "log_stars", "log_issues"
)
if (nrow(joined[!stats::complete.cases(joined[, ..model_fields])]) > 0L) abortf("Primary model fields contain missing values.")
if (nrow(joined[!apply(as.data.frame(joined[, ..model_fields]), 1L, function(row) all(is.finite(row)))]) > 0L) abortf("Primary model fields contain non-finite values.")

data.table::setorder(joined, repo_id, time_index)
key_set <- unique(make_key(joined$repo_id, joined$time_index))
joined[, has_exact_lag1 := make_key(repo_id, time_index - 1L) %in% key_set]
joined[, has_exact_lag2 := make_key(repo_id, time_index - 2L) %in% key_set]
joined[, has_exact_lag3 := make_key(repo_id, time_index - 3L) %in% key_set]
active <- joined[has_exact_lag1 & has_exact_lag2]
strict_count_check(nrow(active), expected_full_active_rows, "exact t-1/t-2 active rows", strict_expected_counts)
strict_count_check(data.table::uniqueN(active$repo_id), expected_full_active_repositories, "active repositories", strict_expected_counts)

# Build exact-calendar lagged variables only for descriptive support diagnostics.
lag1_lookup <- joined[, .(
  repo_id,
  time_index = time_index + 1L,
  lag1_ml_quality = log1p_selected_issue_total,
  lag1_whole_quality = log_issue_total_py_sonarqube
)]
diag_panel <- merge(joined, lag1_lookup, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
diag_active <- diag_panel[has_exact_lag1 & has_exact_lag2]

safe_cor <- function(x, y) {
  ok <- is.finite(x) & is.finite(y)
  if (sum(ok) < 3L || stats::sd(x[ok]) == 0 || stats::sd(y[ok]) == 0) return(NA_real_)
  stats::cor(x[ok], y[ok])
}
within_demean <- function(data, columns) {
  result <- data.table::copy(data)
  for (column in columns) result[, (paste0(column, "_dm")) := get(column) - mean(get(column), na.rm = TRUE), by = repo_id]
  result
}
within_diag <- within_demean(diag_active, c("lag1_ml_quality", "lag1_whole_quality", "log_lines_added_py_source"))
within_quality <- within_demean(active, c("log1p_selected_issue_total", "log_issue_total_py_sonarqube"))

q <- stats::quantile(joined$log1p_selected_issue_total, probs = c(0, .25, .5, .75, .9, .95, 1), na.rm = TRUE, names = FALSE)
support <- data.table::data.table(
  metric = c(
    "source_rows", "source_repositories", "active_rows", "active_repositories",
    "selected_issue_zero_share_source", "selected_issue_zero_share_active",
    "repo_months_positive_selected_issue_source", "repo_months_positive_selected_issue_active",
    "repositories_with_within_ml_quality_variation_source", "repositories_with_within_ml_quality_variation_active",
    "ml_quality_mean_source", "ml_quality_sd_source", "ml_quality_q0", "ml_quality_q25",
    "ml_quality_q50", "ml_quality_q75", "ml_quality_q90", "ml_quality_q95", "ml_quality_q100",
    "whole_quality_mean_source", "whole_quality_sd_source",
    "cor_ml_quality_whole_quality_source", "cor_ml_quality_whole_quality_within_repo_active",
    "cor_lag1_ml_quality_current_velocity_active", "cor_lag1_ml_quality_current_velocity_within_repo_active",
    "cor_lag1_whole_quality_current_velocity_active", "cor_lag1_whole_quality_current_velocity_within_repo_active"
  ),
  value = c(
    nrow(joined), data.table::uniqueN(joined$repo_id), nrow(active), data.table::uniqueN(active$repo_id),
    mean(joined$selected_issue_total == 0), mean(active$selected_issue_total == 0),
    nrow(joined[selected_issue_total > 0]), nrow(active[selected_issue_total > 0]),
    joined[, .(u = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][u > 1L, .N],
    active[, .(u = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][u > 1L, .N],
    mean(joined$log1p_selected_issue_total), stats::sd(joined$log1p_selected_issue_total), q,
    mean(joined$log_issue_total_py_sonarqube), stats::sd(joined$log_issue_total_py_sonarqube),
    safe_cor(joined$log1p_selected_issue_total, joined$log_issue_total_py_sonarqube),
    safe_cor(within_quality$log1p_selected_issue_total_dm, within_quality$log_issue_total_py_sonarqube_dm),
    safe_cor(diag_active$lag1_ml_quality, diag_active$log_lines_added_py_source),
    safe_cor(within_diag$lag1_ml_quality_dm, within_diag$log_lines_added_py_source_dm),
    safe_cor(diag_active$lag1_whole_quality, diag_active$log_lines_added_py_source),
    safe_cor(within_diag$lag1_whole_quality_dm, within_diag$log_lines_added_py_source_dm)
  )
)
write_csv(support, paths$support)

formula_controls_lag2 <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)
formula_controls_lag23 <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
  "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2:3)"
)
formula_no_controls_lag2 <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
  "lag(log1p_selected_issue_total, 1) + absorbing_treated | ",
  "lag(log_lines_added_py_source, 2)"
)

recheck_specs <- data.table::data.table(
  recheck_id = c(
    "R0_reference_twostep_lag2_uncollapsed",
    "R1_twostep_lag2_collapsed",
    "R2_onestep_lag2_uncollapsed",
    "R3_twostep_lag2_3_collapsed",
    "R4_twostep_lag2_no_controls"
  ),
  purpose = c(
    "Exact independent reproduction of E03-v2 primary model.",
    "Instrument-compression sensitivity with otherwise identical specification.",
    "Estimator-stage sensitivity with identical regressors and instruments.",
    "Compact broader lag-depth sensitivity for the velocity instruments.",
    "Sensitivity to contemporaneous covariate adjustment; not a replacement primary model."
  ),
  estimator_model = c("twosteps", "twosteps", "onestep", "twosteps", "twosteps"),
  collapse = c(FALSE, TRUE, FALSE, TRUE, FALSE),
  instrument_specification = c("lag(velocity,2)", "lag(velocity,2)", "lag(velocity,2)", "lag(velocity,2:3)", "lag(velocity,2)"),
  formula = c(formula_controls_lag2, formula_controls_lag2, formula_controls_lag2, formula_controls_lag23, formula_no_controls_lag2),
  primary_reference = c(1L, 0L, 0L, 0L, 0L)
)
write_csv(recheck_specs, paths$model_specs)

estimation_data <- joined[, .(
  repo_id, time_index, log_lines_added_py_source, log1p_selected_issue_total,
  absorbing_treated, log_ncloc_py_sonarqube, log_age, log_contributors, log_stars, log_issues
)]
pdata <- plm::pdata.frame(estimation_data, index = c("repo_id", "time_index"), drop.index = FALSE, row.names = FALSE)

primary_term <- "lag(log1p_selected_issue_total, 1)"
direction <- "MLQuality_{t-1} -> Velocity_t"
coeff_parts <- list(); diag_parts <- list(); instrument_parts <- list(); models <- list(); summaries <- list(); qc_parts <- list()

for (idx in seq_len(nrow(recheck_specs))) {
  spec <- recheck_specs[idx]
  recheck_id <- spec$recheck_id[[1L]]
  log_message("INFO", "Fitting E03 null-result recheck %s", recheck_id)
  formula <- stats::as.formula(spec$formula[[1L]])
  fit_capture <- capture_evaluation(plm::pgmm(
    formula,
    data = pdata,
    effect = "twoways",
    model = spec$estimator_model[[1L]],
    transformation = "d",
    collapse = isTRUE(spec$collapse[[1L]])
  ))
  if (fit_capture$error) abortf("Recheck %s failed: %s", recheck_id, fit_capture$value$message)
  summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
  if (summary_capture$error) abortf("Robust summary failed for %s: %s", recheck_id, summary_capture$value$message)
  all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings))

  coef <- extract_pgmm_coefficients(summary_capture$value, "full_sample", recheck_id, direction, primary_term, confidence_level)
  coef[, `:=`(
    recheck_id = recheck_id,
    estimator_model = spec$estimator_model[[1L]],
    collapse = isTRUE(spec$collapse[[1L]]),
    instrument_specification = spec$instrument_specification[[1L]],
    primary_reference = spec$primary_reference[[1L]]
  )]
  coeff_parts[[recheck_id]] <- coef

  diagnostics <- data.table::rbindlist(list(
    extract_htest(summary_capture$value$sargan, "full_sample", recheck_id, "sargan"),
    extract_htest(summary_capture$value$m1, "full_sample", recheck_id, "ar1"),
    extract_htest(summary_capture$value$m2, "full_sample", recheck_id, "ar2")
  ), fill = TRUE)
  diagnostics[, `:=`(
    recheck_id = recheck_id,
    estimator_model = spec$estimator_model[[1L]],
    collapse = isTRUE(spec$collapse[[1L]]),
    instrument_specification = spec$instrument_specification[[1L]],
    warning_count = length(all_warnings),
    warning_messages = paste(all_warnings, collapse = " | ")
  )]
  diag_parts[[recheck_id]] <- diagnostics

  dimensions <- extract_model_dimensions(fit_capture$value)
  ratio <- dimensions$instrument_count_for_ratio / expected_full_active_repositories
  lag3_rows <- if (spec$instrument_specification[[1L]] == "lag(velocity,2:3)") nrow(joined[has_exact_lag1 & has_exact_lag2 & has_exact_lag3]) else NA_integer_
  lag3_repos <- if (spec$instrument_specification[[1L]] == "lag(velocity,2:3)") data.table::uniqueN(joined[has_exact_lag1 & has_exact_lag2 & has_exact_lag3, repo_id]) else NA_integer_
  instrument_parts[[recheck_id]] <- data.table::data.table(
    recheck_id = recheck_id,
    estimator_model = spec$estimator_model[[1L]],
    collapse = isTRUE(spec$collapse[[1L]]),
    instrument_specification = spec$instrument_specification[[1L]],
    minimum_calendar_support_rows = nrow(active),
    minimum_calendar_support_repositories = data.table::uniqueN(active$repo_id),
    lag3_moment_available_rows = lag3_rows,
    lag3_moment_available_repositories = lag3_repos,
    stats_nobs = dimensions$stats_nobs,
    instrument_count = dimensions$instrument_count_for_ratio,
    instrument_ratio_denominator = expected_full_active_repositories,
    instrument_to_repository_ratio = ratio,
    instrument_proliferation_flag = is.finite(ratio) && ratio >= 1,
    warning_count = length(all_warnings),
    warning_messages = paste(all_warnings, collapse = " | ")
  )

  ar1_p <- diagnostics[diagnostic == "ar1", p_value][1L]
  ar2_p <- diagnostics[diagnostic == "ar2", p_value][1L]
  sargan_p <- diagnostics[diagnostic == "sargan", p_value][1L]
  primary_rows <- coef[is_primary_interaction_term == TRUE, .N]
  diag_missing <- diagnostics[status != "available", .N]
  qc_parts[[recheck_id]] <- data.table::data.table(
    recheck_id = recheck_id,
    check = c("primary_term_rows", "diagnostics_available", "stats_nobs_matches_active_rows", "ar1_expected_pattern", "ar2_no_second_order_serial_correlation", "sargan_overidentification", "model_warning_count", "instrument_ratio"),
    observed = c(primary_rows, diag_missing, dimensions$stats_nobs, ar1_p, ar2_p, sargan_p, length(all_warnings), ratio),
    expected = c(1, 0, expected_full_active_rows, NA, NA, NA, 0, NA),
    status = c(
      ifelse(primary_rows == 1L, "pass", "fail"),
      ifelse(diag_missing == 0L, "pass", "fail"),
      ifelse(is.finite(dimensions$stats_nobs) && dimensions$stats_nobs == expected_full_active_rows, "pass", "fail"),
      ifelse(is.finite(ar1_p) && ar1_p < 0.05, "pass", "caution"),
      ifelse(is.finite(ar2_p) && ar2_p >= 0.05, "pass", "caution"),
      ifelse(is.finite(sargan_p) && sargan_p >= 0.05, "pass", "caution"),
      ifelse(length(all_warnings) == 0L, "pass", "caution"),
      ifelse(is.finite(ratio) && ratio < 1, "pass", "caution")
    ),
    note = c(
      "Exactly one lagged ML-quality coefficient is required.",
      "Sargan, AR(1), and AR(2) must be returned.",
      "All rechecks use the same exact-calendar t-1/t-2 structural support.",
      "Non-significant AR(1) is a caution, not a hard failure.",
      "AR(2) p < 0.05 is a caution for lag-instrument validity.",
      "Sargan p < 0.05 is a caution for overidentification review.",
      "Warnings are retained for review.",
      "Instrument count should remain below active repository count."
    )
  )
  models[[recheck_id]] <- fit_capture$value
  summaries[[recheck_id]] <- summary_capture$value
}

coefficients <- data.table::rbindlist(coeff_parts, fill = TRUE)
diagnostics <- data.table::rbindlist(diag_parts, fill = TRUE)
instrument_qc <- data.table::rbindlist(instrument_parts, fill = TRUE)
qc <- data.table::rbindlist(qc_parts, fill = TRUE)

primary_summary <- coefficients[is_primary_interaction_term == TRUE, .(
  recheck_id, estimator_model, collapse, instrument_specification,
  estimate, std_error, conf_low, conf_high, p_value, significant, primary_reference
)]
data.table::setorder(primary_summary, recheck_id)

# Independently verify that R0 reproduces the frozen E03-v2 primary coefficients.
reference <- data.table::fread(reference_coefficients_file, na.strings = c("", "NA", "NaN"))
validate_columns(reference, c("analysis_config", "term", "estimate", "std_error", "p_value"))
reference_primary <- reference[analysis_config == "full_sample__all_ml_files", .(
  term, reference_estimate = as.numeric(estimate), reference_std_error = as.numeric(std_error), reference_p_value = as.numeric(p_value)
)]
r0 <- coefficients[recheck_id == "R0_reference_twostep_lag2_uncollapsed", .(
  term, recheck_estimate = estimate, recheck_std_error = std_error, recheck_p_value = p_value
)]
reference_reproduction <- merge(reference_primary, r0, by = "term", all = TRUE, sort = FALSE)
reference_reproduction[, `:=`(
  estimate_abs_diff = abs(reference_estimate - recheck_estimate),
  std_error_abs_diff = abs(reference_std_error - recheck_std_error),
  p_value_abs_diff = abs(reference_p_value - recheck_p_value)
)]
reference_reproduction[, status := data.table::fifelse(
  is.finite(estimate_abs_diff) & is.finite(std_error_abs_diff) & is.finite(p_value_abs_diff) &
    estimate_abs_diff <= reference_tolerance & std_error_abs_diff <= reference_tolerance & p_value_abs_diff <= reference_tolerance,
  "pass", "fail"
)]
write_csv(reference_reproduction, paths$reference)
reference_failures <- reference_reproduction[status != "pass", .N]
if (reference_failures > 0L && strict_expected_counts) abortf("R0 failed to reproduce %d E03-v2 coefficient rows.", reference_failures)

write_csv(coefficients, paths$coefficients)
write_csv(primary_summary, paths$primary_summary)
write_csv(diagnostics, paths$diagnostics)
write_csv(instrument_qc, paths$instrument_qc)
write_csv(qc, paths$qc)
saveRDS(list(models = models, robust_summaries = summaries), paths$models_rds)

failed_qc <- qc[status == "fail"]
if (nrow(failed_qc) > 0L && strict_expected_counts) abortf("E03 recheck QC failed: %s", paste(paste(failed_qc$recheck_id, failed_qc$check, sep = "/"), collapse = ", "))

run_finished <- Sys.time()
metadata <- data.table::rbindlist(list(
  make_summary_row("run", "run_prefix", "run-x-e03"),
  make_summary_row("run", "analysis_variant", "null_result_recheck"),
  make_summary_row("run", "implementation_version", implementation_version),
  make_summary_row("run", "started", format(run_started, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "finished", format(run_finished, "%Y-%m-%d %H:%M:%S %Z")),
  make_summary_row("run", "input_file", input_file),
  make_summary_row("run", "input_sha256", sha256_file(input_file)),
  make_summary_row("run", "b06_panel_file", b06_panel_file),
  make_summary_row("run", "b06_panel_sha256", sha256_file(b06_panel_file)),
  make_summary_row("run", "reference_coefficients_file", reference_coefficients_file),
  make_summary_row("run", "reference_coefficients_sha256", sha256_file(reference_coefficients_file)),
  make_summary_row("run", "script_path", script_path),
  make_summary_row("run", "script_sha256", sha256_file(script_path)),
  make_summary_row("software", "R", R.version.string),
  make_summary_row("software", "data.table", safe_package_version("data.table")),
  make_summary_row("software", "plm", safe_package_version("plm")),
  make_summary_row("definition", "frozen_ml_metric", expected_metric),
  make_summary_row("definition", "frozen_file_rule", "file_ml_agc_share_space_by_token_weighted > 0.50"),
  make_summary_row("definition", "primary_sample", "full_sample__all_ml_files"),
  make_summary_row("definition", "primary_outcome", "log1p_selected_issue_total"),
  make_summary_row("definition", "velocity", "log_lines_added_py_source"),
  make_summary_row("definition", "treatment", "normalized absorbing_treated"),
  make_summary_row("definition", "recheck_policy", "Report every prespecified specification; never select a model based on significance."),
  make_summary_row("definition", "threshold_policy", "Frozen 0.50 file-composition threshold is not changed or swept."),
  make_summary_row("result", "recheck_specifications", nrow(recheck_specs)),
  make_summary_row("result", "significant_ml_quality_rechecks", primary_summary[significant == TRUE, .N]),
  make_summary_row("qc", "reference_reproduction_failures", reference_failures),
  make_summary_row("qc", "failed_checks", nrow(failed_qc)),
  make_summary_row("qc", "caution_checks", qc[status == "caution", .N])
), fill = TRUE)
write_csv(metadata, paths$metadata)

log_message(
  "INFO",
  "Completed E03 null-result recheck %s: specs=%d; significant_primary_terms=%d; reference_failures=%d; failed_qc=%d; cautions=%d",
  implementation_version, nrow(recheck_specs), primary_summary[significant == TRUE, .N], reference_failures, nrow(failed_qc), qc[status == "caution", .N]
)
