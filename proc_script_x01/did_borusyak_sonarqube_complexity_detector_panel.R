#!/usr/bin/env Rscript

# ============================================================================
# run-x-j03 v1: Borusyak DiD for SonarQube cognitive-complexity detector panel
# ============================================================================
#
# Purpose:
#   Estimate Cursor-adoption effects on log1p cognitive-complexity burden for
#   three pre-specified Python scopes produced by run-x-j02:
#     1. all_python reference scope;
#     2. FUN+C_FUN NPR-selected files across 22 frozen thresholds;
#     3. FUN+C_FUN ML-selected files across 21 frozen thresholds.
#
# Primary detector specifications:
#   - NPR: file_npr_fun_cfun_space_by_token_weighted > 1.571637
#   - ML:  file_ml_fun_cfun_agc_share_space_by_token_weighted > 0.50
#
# Samples:
#   - full_sample;
#   - exclude_detector_scope_mismatch_repos, excluding every repository that
#     has at least one detector file without an exact J01 SonarQube file match.
#
# Estimation:
#   - didimputation::did_imputation;
#   - repository-clustered standard errors;
#   - adjusted and FE-only first-stage specifications;
#   - static ATT over post-adoption observations;
#   - dynamic effects 0:+6;
#   - placebo/pretrend terms -6:-2;
#   - event -1 omitted.
#
# Outcome:
#   log1p_selected_cognitive_complexity, where file-level SonarQube cognitive
#   complexity is summed within repo-month/scope before log1p transformation.
#
# This program is standalone. It reuses the validated statistical structure of
# run-x-i09/run-x-i05 but never calls those scripts or wrappers.
# ============================================================================

options(stringsAsFactors = FALSE, warn = 1)

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)
log_message <- function(level, fmt, ...) {
  message(sprintf("%s [%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)))
}

parse_cli_args <- function(args) {
  out <- list(); i <- 1L
  while (i <= length(args)) {
    token <- args[[i]]
    if (!startsWith(token, "--")) abortf("Unexpected positional argument: %s", token)
    key <- gsub("-", "_", sub("^--", "", token), fixed = TRUE)
    if (i == length(args) || startsWith(args[[i + 1L]], "--")) {
      out[[key]] <- TRUE; i <- i + 1L
    } else {
      out[[key]] <- args[[i + 1L]]; i <- i + 2L
    }
  }
  out
}

require_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(as.character(value))) abortf("Missing --%s", gsub("_", "-", name))
  as.character(value)
}

as_integer_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.integer(value))
  if (is.na(result)) abortf("--%s must be integer", gsub("_", "-", name))
  result
}

as_numeric_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.numeric(value))
  if (!is.finite(result)) abortf("--%s must be finite numeric", gsub("_", "-", name))
  result
}

as_logical_arg <- function(args, name, default = FALSE) {
  if (is.null(args[[name]])) return(isTRUE(default))
  text <- tolower(trimws(as.character(args[[name]])))
  if (text %in% c("1", "true", "yes", "y", "on")) return(TRUE)
  if (text %in% c("0", "false", "no", "n", "off")) return(FALSE)
  abortf("--%s must be boolean-like", gsub("_", "-", name))
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) abortf("Missing R packages: %s", paste(missing, collapse = ", "))
}

safe_package_version <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) return(NA_character_)
  as.character(utils::packageVersion(package))
}

sha256_file <- function(path) {
  command <- Sys.which("sha256sum")
  if (!file.exists(path) || !nzchar(command)) return(NA_character_)
  x <- suppressWarnings(system2(command, path, stdout = TRUE, stderr = TRUE))
  if (!length(x)) return(NA_character_)
  strsplit(x[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing)) abortf("%s missing columns: %s", label, paste(missing, collapse = ", "))
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows: %s", nrow(data), path)
}

capture_evaluation <- function(expr) {
  warnings <- character(); started <- proc.time()[[3L]]
  value <- tryCatch(
    withCallingHandlers(expr, warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning")
    }),
    error = function(e) structure(list(message = conditionMessage(e)), class = "captured_error")
  )
  list(value = value, warnings = unique(warnings), elapsed = proc.time()[[3L]] - started,
       error = inherits(value, "captured_error"))
}

extract_effect_table <- function(result, confidence_level) {
  x <- data.table::as.data.table(result)
  validate_columns(x, c("term", "estimate", "std.error", "conf.low", "conf.high"), "did_imputation result")
  z <- stats::qnorm(1 - (1 - confidence_level) / 2)
  x[, `:=`(
    conf.low = estimate - z * std.error,
    conf.high = estimate + z * std.error,
    p_value = ifelse(is.finite(std.error) & std.error > 0, 2 * stats::pnorm(-abs(estimate / std.error)), NA_real_),
    exp_coefficient_change_pct = 100 * (exp(estimate) - 1),
    exp_ci_low_pct = 100 * (exp(conf.low) - 1),
    exp_ci_high_pct = 100 * (exp(conf.high) - 1)
  )]
  x
}

run_did_model <- function(data, first_stage, horizon = NULL, pretrends = NULL) {
  capture_evaluation(didimputation::did_imputation(
    data = data,
    yname = "log1p_selected_cognitive_complexity",
    gname = "event_index",
    tname = "time_index",
    idname = "repo_id",
    first_stage = first_stage,
    horizon = horizon,
    pretrends = pretrends,
    cluster_var = "repo_id"
  ))
}

fit_first_stage_diagnostic <- function(data, formula_text) {
  untreated <- data[absorbing_treated == 0L]
  formula <- stats::as.formula(sprintf("log1p_selected_cognitive_complexity %s", formula_text))
  captured <- capture_evaluation(fixest::feols(
    formula, data = untreated, se = "standard", warn = FALSE, notes = FALSE, fixef.rm = "none"
  ))
  if (captured$error) return(captured)
  predicted <- capture_evaluation(stats::predict(captured$value, newdata = data))
  if (predicted$error) return(predicted)
  captured$predictions <- predicted$value
  captured$warnings <- unique(c(captured$warnings, predicted$warnings))
  captured$elapsed <- captured$elapsed + predicted$elapsed
  captured
}

model_specs <- list(
  adjusted_complexity = list(
    label = "Adjusted cognitive-complexity burden",
    first_stage = ~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index,
    first_stage_text = "~ log_age + ncloc_py_sonarqube + log_contributors + log_stars + log_issues | repo_id + time_index"
  ),
  fe_only_complexity = list(
    label = "FE-only cognitive-complexity burden",
    first_stage = ~ 1 | repo_id + time_index,
    first_stage_text = "~ 1 | repo_id + time_index"
  )
)

run_self_test <- function() {
  stopifnot(length(model_specs) == 2L)
  stopifnot(44L * 2L * 2L == 176L)
  stopifnot(176L * 12L == 2112L)
  stopifnot(176L * 5L == 880L)
  cat("did_borusyak_sonarqube_complexity_detector_panel self-test: PASS\n")
}

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
if (isTRUE(args$self_test)) {
  run_self_test(); quit(save = "no", status = 0L)
}

input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
mismatch_file <- normalizePath(require_arg(args, "detector_mismatch_file"), mustWork = TRUE)
qc_file <- normalizePath(require_arg(args, "j02_qc_file"), mustWork = TRUE)
summary_file <- normalizePath(require_arg(args, "j02_summary_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v1" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
sparse_min_dynamic_positive_repos <- as_integer_arg(args, "sparse_min_dynamic_positive_repos", 10L)
sparse_min_within_variation_repos <- as_integer_arg(args, "sparse_min_within_variation_repos", 20L)

if (plot_min_event != -6L || plot_max_event != 6L) abortf("J03 v1 requires event window -6:6")
if (pretrend_min != -6L || pretrend_max != -2L) abortf("J03 v1 requires pretrend window -6:-2")
if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1")

check_packages(c("data.table", "didimputation", "fixest"))
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

paths <- list(
  static = file.path(output_dir, "complexity_detector_static_effects.csv"),
  dynamic = file.path(output_dir, "complexity_detector_dynamic_effects.csv"),
  pretrend = file.path(output_dir, "complexity_detector_pretrend_checks.csv"),
  pretrend_summary = file.path(output_dir, "complexity_detector_pretrend_summary.csv"),
  diagnostics = file.path(output_dir, "complexity_detector_model_diagnostics.csv"),
  failures = file.path(output_dir, "complexity_detector_model_failures.csv"),
  support = file.path(output_dir, "complexity_detector_threshold_support.csv"),
  event_support = file.path(output_dir, "complexity_detector_event_support.csv"),
  sample_summary = file.path(output_dir, "complexity_detector_sample_summary.csv"),
  headline_static = file.path(output_dir, "complexity_detector_headline_static.csv"),
  headline_dynamic = file.path(output_dir, "complexity_detector_headline_dynamic.csv"),
  full_headline_static = file.path(output_dir, "complexity_detector_full_sample_headline_static.csv"),
  full_headline_dynamic = file.path(output_dir, "complexity_detector_full_sample_headline_dynamic.csv"),
  npr_threshold_static = file.path(output_dir, "complexity_npr_threshold_static.csv"),
  ml_threshold_static = file.path(output_dir, "complexity_ml_threshold_static.csv"),
  qc = file.path(output_dir, "complexity_detector_qc.csv"),
  summary = file.path(output_dir, "complexity_detector_summary.csv"),
  metadata = file.path(output_dir, "complexity_detector_run_metadata.csv")
)

run_started <- Sys.time()
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
mismatch <- data.table::fread(mismatch_file, na.strings = c("", "NA", "NaN"))
upstream_qc <- data.table::fread(qc_file, na.strings = c("", "NA", "NaN"))
upstream_summary <- data.table::fread(summary_file, na.strings = c("", "NA", "NaN"))

validate_columns(panel, c(
  "scope_id", "threshold_id", "threshold_role", "threshold", "comparison_operator",
  "repo_id", "repo_name", "dataset_source", "treatment_group", "time_index", "event_index",
  "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
  "selected_file_count", "selected_cognitive_complexity", "selected_ncloc",
  "log1p_selected_cognitive_complexity", "has_positive_complexity"
), "J02 panel")
validate_columns(mismatch, c("repo_name_casefold", "dataset_source", "scope_status"), "J02 detector mismatch file")
validate_columns(upstream_qc, c("check_name", "severity", "passed"), "J02 QC")
validate_columns(upstream_summary, c("section", "metric", "value"), "J02 summary")

# Freeze upstream provenance/QC.
if (any(upstream_qc$severity == "hard" & suppressWarnings(as.integer(upstream_qc$passed)) != 1L)) {
  abortf("J02 contains one or more failed hard QC rows")
}
summary_map <- setNames(as.character(upstream_summary$value), as.character(upstream_summary$metric))
for (required_metric in c("status", "hard_qc_failures", "j01_file_rows", "detector_file_rows", "matched_file_rows", "long_rows")) {
  if (!(required_metric %in% names(summary_map))) abortf("J02 summary missing metric: %s", required_metric)
}
if (!(summary_map[["status"]] %in% c("PASS", "PASS_WITH_SCOPE_EXCLUSIONS"))) abortf("Unexpected J02 status: %s", summary_map[["status"]])
if (as.integer(summary_map[["hard_qc_failures"]]) != 0L) abortf("J02 hard_qc_failures must be zero")

# Numeric and identity checks.
for (column in c("repo_id", "treatment_group", "time_index", "event_index", "selected_file_count",
                 "selected_cognitive_complexity", "selected_ncloc", "log1p_selected_cognitive_complexity",
                 "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues")) {
  panel[, (column) := suppressWarnings(as.numeric(get(column)))]
}
panel[, `:=`(repo_id = as.integer(repo_id), treatment_group = as.integer(treatment_group),
             time_index = as.integer(time_index), event_index = as.integer(event_index))]
if (nrow(panel) != 85976L) abortf("Expected 85976 J02 rows; observed %d", nrow(panel))
if (data.table::uniqueN(panel[, .(scope_id, threshold_id)]) != 44L) abortf("Expected 44 scope/threshold specs")
if (data.table::uniqueN(panel$scope_id) != 3L || !setequal(unique(panel$scope_id), c("all_python", "npr_fun_cfun", "ml_fun_cfun"))) abortf("Unexpected scope IDs")
if (nrow(panel[, .N, by = .(scope_id, threshold_id, repo_id, time_index)][N > 1L])) abortf("Duplicate J02 panel keys")
if (any(panel$selected_cognitive_complexity < 0, na.rm = TRUE) || any(panel$selected_ncloc < 0, na.rm = TRUE)) abortf("Negative complexity/NCLOC values")
if (max(abs(panel$log1p_selected_cognitive_complexity - log1p(panel$selected_cognitive_complexity)), na.rm = TRUE) > 1e-10) abortf("log1p complexity contract mismatch")
if (any(!stats::complete.cases(panel[, .(repo_id, time_index, event_index, log1p_selected_cognitive_complexity,
                                         log_age, ncloc_py_sonarqube, log_contributors, log_stars, log_issues)]))) abortf("Missing model fields")

# Validate frozen scope grids and primary specifications.
spec_map <- unique(panel[, .(scope_id, threshold_id, threshold_role, threshold, comparison_operator)])
if (nrow(spec_map[scope_id == "all_python"]) != 1L || spec_map[scope_id == "all_python", threshold_id] != "all_python") abortf("All-Python reference scope mismatch")
if (nrow(spec_map[scope_id == "npr_fun_cfun"]) != 22L) abortf("Expected 22 NPR specs")
if (nrow(spec_map[scope_id == "ml_fun_cfun"]) != 21L) abortf("Expected 21 ML specs")
if (nrow(spec_map[scope_id == "npr_fun_cfun" & threshold_role == "primary" & abs(threshold - 1.571637) < 1e-12]) != 1L) abortf("NPR primary >1.571637 missing")
if (nrow(spec_map[scope_id == "ml_fun_cfun" & threshold_role == "primary" & abs(threshold - 0.50) < 1e-12]) != 1L) abortf("ML primary >0.50 missing")

mismatch_repos <- sort(unique(tolower(trimws(as.character(mismatch$repo_name_casefold)))))
if (length(mismatch_repos) != 10L) abortf("Expected 10 scope-mismatch repositories; observed %d", length(mismatch_repos))

sample_names <- c("full_sample", "exclude_detector_scope_mismatch_repos")
base_all <- panel[scope_id == "all_python"]
sensitivity_base <- base_all[!(tolower(repo_name) %in% mismatch_repos)]
if (nrow(base_all) != 1954L || data.table::uniqueN(base_all$repo_id) != 167L) abortf("Full B06 support mismatch")
if (nrow(sensitivity_base) != 1796L || data.table::uniqueN(sensitivity_base$repo_id) != 157L) abortf("Scope-exclusion sensitivity support mismatch")

sample_summary <- data.table::rbindlist(lapply(sample_names, function(sample_name) {
  x <- if (sample_name == "full_sample") base_all else sensitivity_base
  data.table::data.table(
    sample_spec = sample_name,
    repo_month_rows = nrow(x),
    repositories = data.table::uniqueN(x$repo_id),
    treatment_repositories = data.table::uniqueN(x[treatment_group == 1L, repo_id]),
    control_repositories = data.table::uniqueN(x[treatment_group == 0L, repo_id]),
    excluded_repositories = ifelse(sample_name == "full_sample", 0L, length(mismatch_repos)),
    control_rows = sum(x$treatment_group == 0L),
    treatment_pre_rows = sum(x$treatment_group == 1L & x$time_index < x$event_index),
    treatment_post_rows = sum(x$treatment_group == 1L & x$time_index >= x$event_index)
  )
}))
write_csv(sample_summary, paths$sample_summary)

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- 0:plot_max_event
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)
support_event_values <- seq.int(plot_min_event, plot_max_event)

support_rows <- list(); event_support_rows <- list()
for (sample_name in sample_names) {
  excluded <- if (sample_name == "full_sample") character() else mismatch_repos
  for (i in seq_len(nrow(spec_map))) {
    sm <- spec_map[i]
    x <- panel[scope_id == sm$scope_id & threshold_id == sm$threshold_id]
    if (length(excluded)) x <- x[!(tolower(repo_name) %in% excluded)]
    x[, event_time_normalized := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]

    positive_by_event <- x[treatment_group == 1L & event_time_normalized %in% support_event_values,
      .(treatment_rows = .N,
        treatment_repositories = data.table::uniqueN(repo_id),
        positive_complexity_rows = sum(selected_cognitive_complexity > 0),
        positive_complexity_repositories = data.table::uniqueN(repo_id[selected_cognitive_complexity > 0])),
      by = .(event_time = as.integer(event_time_normalized))]
    grid <- merge(data.table::data.table(event_time = support_event_values), positive_by_event, by = "event_time", all.x = TRUE)
    for (column in c("treatment_rows", "treatment_repositories", "positive_complexity_rows", "positive_complexity_repositories")) {
      grid[is.na(get(column)), (column) := 0L]
    }
    grid[, `:=`(sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
                threshold_role = sm$threshold_role, threshold = sm$threshold,
                comparison_operator = sm$comparison_operator,
                period_type = data.table::fcase(event_time %in% pretrend_values, "placebo_pretrend",
                                                event_time == -1L, "reference",
                                                event_time >= 0L, "post_treatment", default = "other"))]
    event_support_rows[[length(event_support_rows) + 1L]] <- grid

    within_variation <- x[, .(varies = data.table::uniqueN(selected_cognitive_complexity) > 1L), by = repo_id][, sum(varies)]
    min_dynamic_positive <- min(grid[event_time %in% post_values, positive_complexity_repositories])
    sparse_reasons <- character()
    if (min_dynamic_positive < sparse_min_dynamic_positive_repos) sparse_reasons <- c(sparse_reasons, sprintf("min_dynamic_positive_repositories=%d<%d", min_dynamic_positive, sparse_min_dynamic_positive_repos))
    if (within_variation < sparse_min_within_variation_repos) sparse_reasons <- c(sparse_reasons, sprintf("repositories_within_variation=%d<%d", within_variation, sparse_min_within_variation_repos))
    support_rows[[length(support_rows) + 1L]] <- data.table::data.table(
      sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
      threshold_role = sm$threshold_role, threshold = sm$threshold, comparison_operator = sm$comparison_operator,
      repo_month_rows = nrow(x), repositories = data.table::uniqueN(x$repo_id),
      treatment_repositories = data.table::uniqueN(x[treatment_group == 1L, repo_id]),
      control_repositories = data.table::uniqueN(x[treatment_group == 0L, repo_id]),
      selected_file_count = sum(x$selected_file_count), selected_cognitive_complexity = sum(x$selected_cognitive_complexity),
      selected_ncloc = sum(x$selected_ncloc), repo_months_with_positive_complexity = sum(x$selected_cognitive_complexity > 0),
      repositories_with_within_outcome_variation = within_variation,
      min_dynamic_positive_repositories = min_dynamic_positive,
      zero_outcome_share = mean(x$selected_cognitive_complexity == 0),
      sparse_support_flag = as.integer(length(sparse_reasons) > 0L),
      sparse_support_reason = paste(sparse_reasons, collapse = " | ")
    )
  }
}
threshold_support <- data.table::rbindlist(support_rows, fill = TRUE)
event_support <- data.table::rbindlist(event_support_rows, fill = TRUE)
write_csv(threshold_support, paths$support)
write_csv(event_support, paths$event_support)

static_tables <- list(); dynamic_tables <- list(); pretrend_tables <- list(); diagnostics <- list(); failures <- list()

for (sample_name in sample_names) {
  excluded <- if (sample_name == "full_sample") character() else mismatch_repos
  for (i in seq_len(nrow(spec_map))) {
    sm <- spec_map[i]
    x <- panel[scope_id == sm$scope_id & threshold_id == sm$threshold_id]
    if (length(excluded)) x <- x[!(tolower(repo_name) %in% excluded)]
    x[, absorbing_treated := as.integer(treatment_group == 1L & time_index >= event_index)]
    treated_rows <- sum(x$absorbing_treated == 1L)
    untreated_rows <- sum(x$absorbing_treated == 0L)

    support_row <- threshold_support[sample_spec == sample_name & scope_id == sm$scope_id & threshold_id == sm$threshold_id]
    for (spec_name in names(model_specs)) {
      spec <- model_specs[[spec_name]]
      first <- fit_first_stage_diagnostic(x, spec$first_stage_text)
      diagnostics[[length(diagnostics) + 1L]] <- data.table::data.table(
        sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
        threshold = sm$threshold, model_spec = spec_name, stage = "first_stage",
        status = ifelse(first$error, "failed", "success"), runtime_seconds = first$elapsed,
        warning_count = length(first$warnings), warning_messages = paste(first$warnings, collapse = " | "),
        error_message = ifelse(first$error, first$value$message, ""), input_rows = nrow(x))
      if (first$error) {
        failures[[length(failures) + 1L]] <- diagnostics[[length(diagnostics)]]; next
      }
      if (sum(is.na(first$predictions[x$absorbing_treated == 1L])) > 0L) {
        failures[[length(failures) + 1L]] <- data.table::data.table(sample_spec = sample_name, scope_id = sm$scope_id,
          threshold_id = sm$threshold_id, threshold = sm$threshold, model_spec = spec_name, stage = "first_stage_prediction",
          error_message = "Missing first-stage predictions for treated rows")
        next
      }

      static_cap <- run_did_model(x, spec$first_stage)
      diagnostics[[length(diagnostics) + 1L]] <- data.table::data.table(
        sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
        threshold = sm$threshold, model_spec = spec_name, stage = "static",
        status = ifelse(static_cap$error, "failed", "success"), runtime_seconds = static_cap$elapsed,
        warning_count = length(static_cap$warnings), warning_messages = paste(static_cap$warnings, collapse = " | "),
        error_message = ifelse(static_cap$error, static_cap$value$message, ""), input_rows = nrow(x))
      if (static_cap$error) { failures[[length(failures) + 1L]] <- diagnostics[[length(diagnostics)]]; next }
      st <- extract_effect_table(static_cap$value, confidence_level)[term == "treat"]
      if (nrow(st) != 1L) abortf("Expected one static treat term for %s/%s/%s/%s", sample_name, sm$scope_id, sm$threshold_id, spec_name)
      st[, `:=`(
        sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
        threshold_role = sm$threshold_role, threshold = sm$threshold, comparison_operator = sm$comparison_operator,
        is_headline_scope = as.integer(sm$scope_id == "all_python" || sm$threshold_role == "primary"),
        model_spec = spec_name, model_spec_label = spec$label, first_stage_formula = spec$first_stage_text,
        outcome = "log1p_selected_cognitive_complexity", outcome_role = "primary_complexity_burden",
        treated_observations = treated_rows, first_stage_observations = untreated_rows,
        treatment_repositories = data.table::uniqueN(x[treatment_group == 1L, repo_id]),
        control_repositories = data.table::uniqueN(x[treatment_group == 0L, repo_id]),
        sparse_support_flag = support_row$sparse_support_flag, sparse_support_reason = support_row$sparse_support_reason,
        warning_count = length(static_cap$warnings), warning_messages = paste(static_cap$warnings, collapse = " | ")
      )]
      static_tables[[length(static_tables) + 1L]] <- st

      dyn_cap <- run_did_model(x, spec$first_stage, horizon = dynamic_horizon_values, pretrends = pretrend_values)
      diagnostics[[length(diagnostics) + 1L]] <- data.table::data.table(
        sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
        threshold = sm$threshold, model_spec = spec_name, stage = "dynamic",
        status = ifelse(dyn_cap$error, "failed", "success"), runtime_seconds = dyn_cap$elapsed,
        warning_count = length(dyn_cap$warnings), warning_messages = paste(dyn_cap$warnings, collapse = " | "),
        error_message = ifelse(dyn_cap$error, dyn_cap$value$message, ""), input_rows = nrow(x))
      if (dyn_cap$error) { failures[[length(failures) + 1L]] <- diagnostics[[length(diagnostics)]]; next }
      dy <- extract_effect_table(dyn_cap$value, confidence_level)
      dy[, event_time := suppressWarnings(as.integer(as.character(term)))]
      dy <- dy[!is.na(event_time)]
      if (nrow(dy) != 12L || !setequal(dy$event_time, c(pretrend_values, post_values))) abortf("Dynamic terms mismatch for %s/%s/%s/%s", sample_name, sm$scope_id, sm$threshold_id, spec_name)
      dy[, term_type := data.table::fcase(event_time %in% pretrend_values, "placebo_pretrend", event_time >= 0L, "post_treatment", default = "other")]
      dy[, `:=`(
        sample_spec = sample_name, scope_id = sm$scope_id, threshold_id = sm$threshold_id,
        threshold_role = sm$threshold_role, threshold = sm$threshold, comparison_operator = sm$comparison_operator,
        is_headline_scope = as.integer(sm$scope_id == "all_python" || sm$threshold_role == "primary"),
        model_spec = spec_name, model_spec_label = spec$label, first_stage_formula = spec$first_stage_text,
        outcome = "log1p_selected_cognitive_complexity", outcome_role = "primary_complexity_burden",
        sparse_support_flag = support_row$sparse_support_flag, sparse_support_reason = support_row$sparse_support_reason,
        ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0,
        warning_count = length(dyn_cap$warnings), warning_messages = paste(dyn_cap$warnings, collapse = " | ")
      )]
      data.table::setorder(dy, event_time)
      dynamic_tables[[length(dynamic_tables) + 1L]] <- dy
      pretrend_tables[[length(pretrend_tables) + 1L]] <- dy[term_type == "placebo_pretrend"]
    }
  }
}

failures_dt <- if (length(failures)) data.table::rbindlist(failures, fill = TRUE) else data.table::data.table()
write_csv(failures_dt, paths$failures)
if (nrow(failures_dt)) abortf("J03 model failures detected; inspect %s", paths$failures)

static_all <- data.table::rbindlist(static_tables, fill = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, fill = TRUE)
pretrend_all <- data.table::rbindlist(pretrend_tables, fill = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostics, fill = TRUE)
pretrend_summary <- pretrend_all[, .(
  pretrend_terms = .N,
  periods_excluding_zero = sum(!ci_includes_zero, na.rm = TRUE),
  significant_periods = sum(!is.na(p_value) & p_value < (1 - confidence_level)),
  all_cis_include_zero = all(ci_includes_zero),
  minimum_p_value = if (all(is.na(p_value))) NA_real_ else min(p_value, na.rm = TRUE),
  minimum_p_event = if (all(is.na(p_value))) NA_integer_ else event_time[which.min(p_value)][1L]
), by = .(sample_spec, scope_id, threshold_id, threshold_role, threshold, comparison_operator,
         is_headline_scope, model_spec, model_spec_label, first_stage_formula, outcome, outcome_role,
         sparse_support_flag, sparse_support_reason)]

write_csv(static_all, paths$static)
write_csv(dynamic_all, paths$dynamic)
write_csv(pretrend_all, paths$pretrend)
write_csv(pretrend_summary, paths$pretrend_summary)
write_csv(diagnostics_all, paths$diagnostics)

headline_static <- static_all[is_headline_scope == 1L]
headline_dynamic <- dynamic_all[is_headline_scope == 1L]
full_headline_static <- headline_static[sample_spec == "full_sample"]
full_headline_dynamic <- headline_dynamic[sample_spec == "full_sample"]
npr_threshold_static <- static_all[sample_spec == "full_sample" & scope_id == "npr_fun_cfun"]
ml_threshold_static <- static_all[sample_spec == "full_sample" & scope_id == "ml_fun_cfun"]
write_csv(headline_static, paths$headline_static)
write_csv(headline_dynamic, paths$headline_dynamic)
write_csv(full_headline_static, paths$full_headline_static)
write_csv(full_headline_dynamic, paths$full_headline_dynamic)
write_csv(npr_threshold_static, paths$npr_threshold_static)
write_csv(ml_threshold_static, paths$ml_threshold_static)

expected_counts <- list(
  static_effect_rows = 176L,
  dynamic_effect_rows = 2112L,
  pretrend_check_rows = 880L,
  pretrend_summary_rows = 176L,
  diagnostic_rows = 528L,
  threshold_support_rows = 88L,
  event_support_rows = 1144L,
  headline_static_rows = 12L,
  headline_dynamic_rows = 144L,
  full_headline_static_rows = 6L,
  full_headline_dynamic_rows = 72L,
  npr_threshold_static_rows = 44L,
  ml_threshold_static_rows = 42L
)
observed_counts <- c(
  nrow(static_all), nrow(dynamic_all), nrow(pretrend_all), nrow(pretrend_summary), nrow(diagnostics_all),
  nrow(threshold_support), nrow(event_support), nrow(headline_static), nrow(headline_dynamic),
  nrow(full_headline_static), nrow(full_headline_dynamic), nrow(npr_threshold_static), nrow(ml_threshold_static)
)
qc <- data.table::data.table(
  check_name = names(expected_counts),
  observed = as.integer(observed_counts),
  expected = as.integer(unlist(expected_counts)),
  severity = "hard"
)
qc[, status := ifelse(observed == expected, "pass", "fail")]
qc <- data.table::rbindlist(list(
  qc,
  data.table::data.table(check_name = c("model_failures", "j02_hard_qc_failures", "scope_mismatch_repositories"),
                         observed = c(nrow(failures_dt), as.integer(summary_map[["hard_qc_failures"]]), length(mismatch_repos)),
                         expected = c(0L, 0L, 10L), severity = "hard", status = "pass")
), fill = TRUE)
write_csv(qc, paths$qc)
failed_qc <- qc[severity == "hard" & status != "pass"]
if (nrow(failed_qc) && strict_expected_counts) abortf("J03 hard QC failed: %s", paste(failed_qc$check_name, collapse = ", "))

summary <- data.table::data.table(
  section = c("run", "run", "run", "input", "input", "analysis", "analysis", "analysis", "analysis", "analysis", "analysis", "output", "output", "qc"),
  metric = c("implementation_version", "status", "hard_qc_failures", "j02_panel_rows", "scope_mismatch_repositories",
             "scope_threshold_specs", "sample_specs", "model_specs", "model_jobs", "dynamic_window", "pretrend_window",
             "static_effect_rows", "dynamic_effect_rows", "model_failures"),
  value = as.character(c(implementation_version, ifelse(nrow(failed_qc) == 0L, "PASS", "FAIL"), nrow(failed_qc), nrow(panel),
                         length(mismatch_repos), 44L, 2L, 2L, 176L, "-6:6", "-6:-2", nrow(static_all), nrow(dynamic_all), nrow(failures_dt))),
  note = c("", "", "", "Frozen J02 long panel.", "Excluded only in sensitivity sample.",
           "1 All-Python + 22 NPR + 21 ML.", "full + detector-scope-mismatch exclusion.",
           "adjusted + FE-only.", "44 x 2 x 2 x 1 outcome.", "Event -1 omitted.", "Placebo terms only.",
           "", "", "")
)
write_csv(summary, paths$summary)

metadata <- data.table::data.table(
  section = c(rep("run", 7), rep("software", 4), rep("definition", 10), rep("input_sha256", 4)),
  metric = c("implementation_version", "started", "finished", "input_file", "detector_mismatch_file", "script_path", "script_sha256",
             "R", "data.table", "didimputation", "fixest",
             "primary_outcome", "npr_primary", "ml_primary", "samples", "cluster_variable", "dynamic_window", "pretrend_window", "reference_event", "first_stage_specs", "scope_mismatch_policy",
             "j02_panel", "j02_detector_mismatch", "j02_qc", "j02_summary"),
  value = c(implementation_version, format(run_started, "%Y-%m-%d %H:%M:%S %Z"), format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
            input_file, mismatch_file, script_path, ifelse(is.na(script_path), NA_character_, sha256_file(script_path)),
            R.version.string, safe_package_version("data.table"), safe_package_version("didimputation"), safe_package_version("fixest"),
            "log1p_selected_cognitive_complexity", "NPR > 1.571637", "ML > 0.50", paste(sample_names, collapse = "|"), "repo_id",
            "-6:6", "-6:-2", "-1", "adjusted_complexity|fe_only_complexity",
            "No remapping; sensitivity excludes all repositories with detector-only J01 scope mismatch.",
            sha256_file(input_file), sha256_file(mismatch_file), sha256_file(qc_file), sha256_file(summary_file))
)
write_csv(metadata, paths$metadata)

log_message("INFO", "Completed run-x-j03 %s: status=%s; static=%d; dynamic=%d; failures=%d; hard_qc_failures=%d",
            implementation_version, ifelse(nrow(failed_qc) == 0L, "PASS", "FAIL"), nrow(static_all), nrow(dynamic_all), nrow(failures_dt), nrow(failed_qc))
