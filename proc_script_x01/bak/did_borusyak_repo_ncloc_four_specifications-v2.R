#!/usr/bin/env Rscript

# ============================================================
# run-x-c06 v1: Borusyak DiD for four repository-NCLOC specs
# ============================================================
#
# This script runs the same static and dynamic DiD model on four panels.
# The exact-common specifications share identical repository-month keys, so
# their differences isolate the NCLOC measurement backend or taxonomy scope.

parse_cli <- function(args) {
  result <- list()
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) {
      stop(sprintf("Unexpected argument: %s", key))
    }
    if (i == length(args)) {
      stop(sprintf("Missing value for argument: %s", key))
    }
    name <- gsub("-", "_", substring(key, 3L), fixed = TRUE)
    result[[name]] <- args[[i + 1L]]
    i <- i + 2L
  }
  result
}

args <- parse_cli(commandArgs(trailingOnly = TRUE))

required_args <- c(
  "paper_full_input",
  "paper_common_input",
  "local_taxonomy_common_input",
  "local_all_common_input",
  "static_output",
  "dynamic_output",
  "pretrend_output",
  "pretrend_summary_output",
  "static_comparison_output",
  "dynamic_comparison_output",
  "specification_summary_output",
  "model_audit_output",
  "qc_output",
  "session_info_output",
  "summary_output",
  "dynamic_plot_output",
  "primary_comparison_plot_output",
  "static_plot_output"
)
missing_args <- required_args[!vapply(required_args, function(x) !is.null(args[[x]]), logical(1))]
if (length(missing_args) > 0L) {
  stop(sprintf("Missing required arguments: %s", paste(missing_args, collapse = ", ")))
}

as_int <- function(name, default = NA_integer_) {
  value <- args[[name]]
  if (is.null(value)) return(default)
  parsed <- suppressWarnings(as.integer(value))
  if (is.na(parsed)) stop(sprintf("Argument --%s must be an integer.", gsub("_", "-", name)))
  parsed
}

strict_expected_counts <- as_int("strict_expected_counts", 1L)
expected_paper_full_rows <- as_int("expected_paper_full_rows", 2127L)
expected_paper_full_repositories <- as_int("expected_paper_full_repositories", 198L)
expected_paper_full_treatment_repositories <- as_int("expected_paper_full_treatment_repositories", 72L)
expected_paper_full_control_repositories <- as_int("expected_paper_full_control_repositories", 126L)
expected_common_rows <- as_int("expected_common_rows", 2090L)
expected_common_repositories <- as_int("expected_common_repositories", 194L)
expected_common_treatment_repositories <- as_int("expected_common_treatment_repositories", 69L)
expected_common_control_repositories <- as_int("expected_common_control_repositories", 125L)
expected_static_rows <- as_int("expected_static_rows", 8L)
# Dynamic-row expectations default to NA and are derived from the estimable
# event-time grid below, because event time -1 is the normalized reference
# period and is never estimated by didimputation.
expected_dynamic_rows <- as_int("expected_dynamic_rows", NA_integer_)
expected_pretrend_rows <- as_int("expected_pretrend_rows", NA_integer_)
expected_model_audit_rows <- as_int("expected_model_audit_rows", 16L)
expected_static_comparison_rows <- as_int("expected_static_comparison_rows", 6L)
expected_dynamic_comparison_rows <- as_int("expected_dynamic_comparison_rows", NA_integer_)
horizon_min <- as_int("horizon_min", -6L)
horizon_max <- as_int("horizon_max", 6L)
pretrend_min <- as_int("pretrend_min", -6L)
pretrend_max <- as_int("pretrend_max", -2L)
random_seed <- as_int("random_seed", 20260804L)

if (!strict_expected_counts %in% c(0L, 1L)) {
  stop("strict_expected_counts must be 0 or 1.")
}
if (horizon_min > horizon_max) stop("horizon_min must not exceed horizon_max.")
if (pretrend_min > pretrend_max) stop("pretrend_min must not exceed pretrend_max.")

required_packages <- c("didimputation", "data.table", "ggplot2")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0L) {
  stop(sprintf("Missing R packages: %s", paste(missing_packages, collapse = ", ")))
}

suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
})

set.seed(random_seed)

all_output_files <- unlist(args[required_args[grepl("output$", required_args)]], use.names = FALSE)
for (path in all_output_files) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
}

log_message <- function(...) {
  cat(format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "[INFO]", sprintf(...), "\n")
}

write_csv <- function(dt, path) {
  data.table::fwrite(dt, path, na = "")
}

pct_effect <- function(value) {
  (exp(value) - 1) * 100
}

safe_equal_numeric <- function(x, y, tolerance = 1e-9) {
  if (length(x) != length(y)) return(FALSE)
  same_na <- is.na(x) == is.na(y)
  if (!all(same_na)) return(FALSE)
  idx <- !is.na(x)
  if (!any(idx)) return(TRUE)
  all(abs(as.numeric(x[idx]) - as.numeric(y[idx])) <= tolerance)
}

qc_rows <- list()
add_qc <- function(check_name, observed, expected, passed, severity = "hard", details = "") {
  qc_rows[[length(qc_rows) + 1L]] <<- data.table(
    check_name = check_name,
    observed = as.character(observed),
    expected = as.character(expected),
    passed = as.logical(passed),
    severity = severity,
    details = details
  )
}

strict_count_check <- function(check_name, observed, expected, details = "") {
  passed <- identical(as.integer(observed), as.integer(expected))
  severity <- if (strict_expected_counts == 1L) "hard" else "warning"
  add_qc(check_name, observed, expected, passed, severity, details)
}

specifications <- data.table(
  specification_id = c(
    "paper_full",
    "paper_common",
    "local_taxonomy_common",
    "local_all_common"
  ),
  specification_order = 1:4,
  specification_label = c(
    "Paper NCLOC, full sample",
    "Paper NCLOC, common sample",
    "Local taxonomy NCLOC, common sample",
    "Local all-recognized NCLOC, common sample"
  ),
  specification_role = c(
    "baseline_replication",
    "sample_attrition_reference",
    "primary_backend_comparison",
    "taxonomy_robustness"
  ),
  input_file = c(
    args$paper_full_input,
    args$paper_common_input,
    args$local_taxonomy_common_input,
    args$local_all_common_input
  ),
  expected_ncloc_metric = c(
    "paper_ncloc",
    "paper_ncloc",
    "ncloc_local_cloc_paper_taxonomy",
    "ncloc_local_cloc_all_recognized"
  ),
  expected_rows = c(
    expected_paper_full_rows,
    expected_common_rows,
    expected_common_rows,
    expected_common_rows
  ),
  expected_repositories = c(
    expected_paper_full_repositories,
    expected_common_repositories,
    expected_common_repositories,
    expected_common_repositories
  ),
  expected_treatment_repositories = c(
    expected_paper_full_treatment_repositories,
    expected_common_treatment_repositories,
    expected_common_treatment_repositories,
    expected_common_treatment_repositories
  ),
  expected_control_repositories = c(
    expected_paper_full_control_repositories,
    expected_common_control_repositories,
    expected_common_control_repositories,
    expected_common_control_repositories
  )
)

outcomes <- data.table(
  outcome = c("log_commits", "log_lines_added"),
  outcome_order = 1:2,
  outcome_label = c("Commits", "Lines Added")
)

required_columns <- c(
  "repo_id", "repo_name", "treatment_group", "time_index", "event_index",
  "event_time_normalized", "absorbing_treated", "log_commits",
  "log_lines_added", "log_age", "ncloc", "log_contributors", "log_stars",
  "log_issues", "paper_ncloc", "ncloc_local_cloc_paper_taxonomy",
  "ncloc_local_cloc_all_recognized"
)

panel_list <- list()
spec_summary_rows <- list()

log_message("Reading and validating four C05 input panels")
for (i in seq_len(nrow(specifications))) {
  spec <- specifications[i]
  dt <- data.table::fread(spec$input_file)
  missing_columns <- setdiff(required_columns, names(dt))
  if (length(missing_columns) > 0L) {
    stop(sprintf(
      "%s is missing required columns: %s",
      spec$specification_id,
      paste(missing_columns, collapse = ", ")
    ))
  }

  numeric_columns <- c(
    "repo_id", "treatment_group", "time_index", "event_index",
    "event_time_normalized", "absorbing_treated", "log_commits",
    "log_lines_added", "log_age", "ncloc", "log_contributors", "log_stars",
    "log_issues", "paper_ncloc", "ncloc_local_cloc_paper_taxonomy",
    "ncloc_local_cloc_all_recognized"
  )
  for (column in numeric_columns) {
    dt[, (column) := as.numeric(get(column))]
  }

  rows <- nrow(dt)
  repositories <- uniqueN(dt$repo_id)
  treatment_repositories <- uniqueN(dt[treatment_group == 1, repo_id])
  control_repositories <- uniqueN(dt[treatment_group == 0, repo_id])
  duplicate_keys <- dt[, .N, by = .(repo_id, time_index)][N > 1, .N]
  missing_model_values <- dt[, sum(!complete.cases(
    repo_id, time_index, event_index, log_commits, log_lines_added,
    log_age, ncloc, log_contributors, log_stars, log_issues
  ))]

  strict_count_check(
    sprintf("%s_rows", spec$specification_id),
    rows,
    spec$expected_rows
  )
  strict_count_check(
    sprintf("%s_repositories", spec$specification_id),
    repositories,
    spec$expected_repositories
  )
  strict_count_check(
    sprintf("%s_treatment_repositories", spec$specification_id),
    treatment_repositories,
    spec$expected_treatment_repositories
  )
  strict_count_check(
    sprintf("%s_control_repositories", spec$specification_id),
    control_repositories,
    spec$expected_control_repositories
  )
  add_qc(
    sprintf("%s_duplicate_repo_month_keys", spec$specification_id),
    duplicate_keys,
    0,
    duplicate_keys == 0,
    "hard"
  )
  add_qc(
    sprintf("%s_missing_model_values", spec$specification_id),
    missing_model_values,
    0,
    missing_model_values == 0,
    "hard"
  )

  expected_metric <- spec$expected_ncloc_metric
  alias_matches <- safe_equal_numeric(dt$ncloc, dt[[expected_metric]])
  add_qc(
    sprintf("%s_ncloc_alias_matches_%s", spec$specification_id, expected_metric),
    alias_matches,
    TRUE,
    alias_matches,
    "hard"
  )

  treated_support <- dt[treatment_group == 1, .(
    has_pre = any(time_index < event_index),
    has_treated = any(time_index >= event_index)
  ), by = repo_id]
  unsupported_treatments <- treated_support[!(has_pre & has_treated), .N]
  add_qc(
    sprintf("%s_treated_repositories_without_pre_and_post", spec$specification_id),
    unsupported_treatments,
    0,
    unsupported_treatments == 0,
    "hard"
  )

  panel_list[[spec$specification_id]] <- dt
  spec_summary_rows[[length(spec_summary_rows) + 1L]] <- data.table(
    specification_id = spec$specification_id,
    specification_order = spec$specification_order,
    specification_label = spec$specification_label,
    specification_role = spec$specification_role,
    input_file = spec$input_file,
    ncloc_metric = spec$expected_ncloc_metric,
    observations = rows,
    repositories = repositories,
    treatment_repositories = treatment_repositories,
    control_repositories = control_repositories,
    treatment_pre_observations = dt[treatment_group == 1 & time_index < event_index, .N],
    treatment_post_observations = dt[treatment_group == 1 & time_index >= event_index, .N],
    control_observations = dt[treatment_group == 0, .N],
    ncloc_min = min(dt$ncloc),
    ncloc_median = median(dt$ncloc),
    ncloc_mean = mean(dt$ncloc),
    ncloc_max = max(dt$ncloc)
  )
}

specification_summary <- rbindlist(spec_summary_rows)
setorder(specification_summary, specification_order)

common_ids <- c("paper_common", "local_taxonomy_common", "local_all_common")
common_key_tables <- lapply(common_ids, function(id) {
  panel_list[[id]][order(repo_id, time_index), .(repo_id, time_index)]
})
common_keys_identical <- all(vapply(
  common_key_tables[-1L],
  function(x) identical(x, common_key_tables[[1L]]),
  logical(1)
))
add_qc(
  "common_specification_repo_month_keys_identical",
  common_keys_identical,
  TRUE,
  common_keys_identical,
  "hard"
)

common_shared_columns <- c(
  "repo_id", "time_index", "event_index", "event_time_normalized",
  "treatment_group", "absorbing_treated", "log_commits", "log_lines_added",
  "log_age", "log_contributors", "log_stars", "log_issues"
)
common_reference <- panel_list[["paper_common"]][order(repo_id, time_index), ..common_shared_columns]
common_shared_values_identical <- all(vapply(
  c("local_taxonomy_common", "local_all_common"),
  function(id) {
    candidate <- panel_list[[id]][order(repo_id, time_index), ..common_shared_columns]
    identical(candidate, common_reference)
  },
  logical(1)
))
add_qc(
  "common_specification_shared_model_values_identical",
  common_shared_values_identical,
  TRUE,
  common_shared_values_identical,
  "hard",
  "All common-sample values except the selected NCLOC metric must match."
)

first_stage_formula <- stats::as.formula(
  "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
)
horizon_values <- seq.int(horizon_min, horizon_max)
pretrend_values <- seq.int(pretrend_min, pretrend_max)

# didimputation::did_imputation estimates post-treatment effects from the
# `horizon` argument (relative time >= 0 only) and pre-treatment placebo terms
# from `pretrends`. Relative time -1 is the normalized reference period and is
# never estimated, and negative values passed through `horizon` match no
# treated observation. The estimable grid is therefore the union of the
# requested pretrends (excluding -1) and the non-negative horizons; it has one
# fewer term than seq(horizon_min, horizon_max) whenever -1 falls inside the
# requested window.
post_horizon_values <- if (horizon_max < 0L) integer(0) else seq.int(max(0L, horizon_min), horizon_max)
estimable_pretrend_values <- pretrend_values[pretrend_values < 0L & pretrend_values != -1L]
estimable_event_times <- sort(unique(c(estimable_pretrend_values, post_horizon_values)))
expected_dynamic_terms_per_model <- length(estimable_event_times)
if (expected_dynamic_terms_per_model == 0L) {
  stop("The requested horizon and pretrend windows contain no estimable event times.")
}

resolve_expected <- function(value, computed) {
  if (is.na(value)) as.integer(computed) else as.integer(value)
}

n_models <- nrow(specifications) * nrow(outcomes)
expected_dynamic_rows <- resolve_expected(
  expected_dynamic_rows,
  n_models * expected_dynamic_terms_per_model
)
expected_pretrend_rows <- resolve_expected(
  expected_pretrend_rows,
  n_models * length(estimable_pretrend_values)
)

log_message(
  "Estimable event times: %s (%d terms per dynamic model; -1 is the reference period)",
  paste(estimable_event_times, collapse = ","),
  expected_dynamic_terms_per_model
)

pick_column <- function(df, candidates, required = TRUE) {
  found <- candidates[candidates %in% names(df)]
  if (length(found) == 0L) {
    if (required) {
      stop(sprintf("None of the expected result columns were found: %s", paste(candidates, collapse = ", ")))
    }
    return(rep(NA_real_, nrow(df)))
  }
  df[[found[[1L]]]]
}

standardize_result <- function(result) {
  df <- as.data.frame(result)
  data.table(
    term = as.character(pick_column(df, c("term"))),
    estimate = as.numeric(pick_column(df, c("estimate"))),
    std_error = as.numeric(pick_column(df, c("std.error", "std_error"))),
    conf_low = as.numeric(pick_column(df, c("conf.low", "conf_low"))),
    conf_high = as.numeric(pick_column(df, c("conf.high", "conf_high"))),
    p_value = as.numeric(pick_column(df, c("p.value", "p_value"), required = FALSE))
  )[, p_value := fifelse(
    is.na(p_value) & !is.na(std_error) & std_error > 0,
    2 * stats::pnorm(-abs(estimate / std_error)),
    p_value
  )]
}

run_with_audit <- function(model_type, spec, outcome_row, dt) {
  warning_messages <- character()
  started_at <- Sys.time()
  error_message <- ""
  result <- tryCatch(
    withCallingHandlers(
      {
        if (model_type == "static") {
          didimputation::did_imputation(
            data = dt,
            yname = outcome_row$outcome,
            gname = "event_index",
            tname = "time_index",
            idname = "repo_id",
            first_stage = first_stage_formula
          )
        } else {
          didimputation::did_imputation(
            data = dt,
            yname = outcome_row$outcome,
            gname = "event_index",
            tname = "time_index",
            idname = "repo_id",
            first_stage = first_stage_formula,
            horizon = post_horizon_values,
            pretrends = estimable_pretrend_values
          )
        }
      },
      warning = function(w) {
        warning_messages <<- c(warning_messages, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) {
      error_message <<- conditionMessage(e)
      NULL
    }
  )
  elapsed <- as.numeric(difftime(Sys.time(), started_at, units = "secs"))
  audit <- data.table(
    specification_id = spec$specification_id,
    specification_order = spec$specification_order,
    specification_label = spec$specification_label,
    outcome = outcome_row$outcome,
    outcome_order = outcome_row$outcome_order,
    outcome_label = outcome_row$outcome_label,
    model_type = model_type,
    model_status = if (is.null(result)) "failed" else "success",
    elapsed_seconds = elapsed,
    warning_count = length(warning_messages),
    warning_messages = paste(unique(warning_messages), collapse = " | "),
    error_message = error_message,
    observations = nrow(dt),
    repositories = uniqueN(dt$repo_id),
    treatment_repositories = uniqueN(dt[treatment_group == 1, repo_id]),
    control_repositories = uniqueN(dt[treatment_group == 0, repo_id])
  )
  list(result = result, audit = audit)
}

static_rows <- list()
dynamic_rows <- list()
model_audit_rows <- list()

log_message("Running 16 models: four specifications x two outcomes x static/dynamic")
for (i in seq_len(nrow(specifications))) {
  spec <- specifications[i]
  dt <- panel_list[[spec$specification_id]]
  for (j in seq_len(nrow(outcomes))) {
    outcome_row <- outcomes[j]
    log_message(
      "Running %s / %s",
      spec$specification_id,
      outcome_row$outcome
    )

    static_run <- run_with_audit("static", spec, outcome_row, dt)
    model_audit_rows[[length(model_audit_rows) + 1L]] <- static_run$audit
    if (!is.null(static_run$result)) {
      standardized <- standardize_result(static_run$result)
      static_term <- standardized[term == "treat"]
      if (nrow(static_term) == 0L) {
        stop(sprintf("Static treat term missing for %s / %s", spec$specification_id, outcome_row$outcome))
      }
      static_rows[[length(static_rows) + 1L]] <- static_term[1L, .(
        specification_id = spec$specification_id,
        specification_order = spec$specification_order,
        specification_label = spec$specification_label,
        specification_role = spec$specification_role,
        ncloc_metric = spec$expected_ncloc_metric,
        outcome = outcome_row$outcome,
        outcome_order = outcome_row$outcome_order,
        outcome_label = outcome_row$outcome_label,
        term,
        estimate,
        std_error,
        conf_low,
        conf_high,
        p_value,
        percent_effect = pct_effect(estimate),
        percent_conf_low = pct_effect(conf_low),
        percent_conf_high = pct_effect(conf_high),
        significant_at_0_05 = !is.na(p_value) & p_value < 0.05,
        observations = nrow(dt),
        repositories = uniqueN(dt$repo_id),
        treatment_repositories = uniqueN(dt[treatment_group == 1, repo_id]),
        control_repositories = uniqueN(dt[treatment_group == 0, repo_id])
      )]
    }

    dynamic_run <- run_with_audit("dynamic", spec, outcome_row, dt)
    model_audit_rows[[length(model_audit_rows) + 1L]] <- dynamic_run$audit
    if (!is.null(dynamic_run$result)) {
      standardized <- standardize_result(dynamic_run$result)
      standardized[, event_time := suppressWarnings(as.integer(term))]
      dynamic_terms <- standardized[
        !is.na(event_time) & event_time >= horizon_min & event_time <= horizon_max
      ]
      if (nrow(dynamic_terms) > 0L) {
        support <- dt[treatment_group == 1, .(
          treated_observations_at_event_time = .N,
          treated_repositories_at_event_time = uniqueN(repo_id)
        ), by = .(event_time = as.integer(event_time_normalized))]
        dynamic_terms <- merge(dynamic_terms, support, by = "event_time", all.x = TRUE)
        dynamic_terms[, `:=`(
          treated_observations_at_event_time = fifelse(
            is.na(treated_observations_at_event_time), 0L, treated_observations_at_event_time
          ),
          treated_repositories_at_event_time = fifelse(
            is.na(treated_repositories_at_event_time), 0L, treated_repositories_at_event_time
          )
        )]
        dynamic_rows[[length(dynamic_rows) + 1L]] <- dynamic_terms[, .(
          specification_id = spec$specification_id,
          specification_order = spec$specification_order,
          specification_label = spec$specification_label,
          specification_role = spec$specification_role,
          ncloc_metric = spec$expected_ncloc_metric,
          outcome = outcome_row$outcome,
          outcome_order = outcome_row$outcome_order,
          outcome_label = outcome_row$outcome_label,
          event_time,
          term,
          estimate,
          std_error,
          conf_low,
          conf_high,
          p_value,
          percent_effect = pct_effect(estimate),
          percent_conf_low = pct_effect(conf_low),
          percent_conf_high = pct_effect(conf_high),
          significant_at_0_05 = !is.na(p_value) & p_value < 0.05,
          ci_includes_zero = conf_low <= 0 & conf_high >= 0,
          treated_observations_at_event_time,
          treated_repositories_at_event_time,
          observations = nrow(dt),
          repositories = uniqueN(dt$repo_id),
          treatment_repositories = uniqueN(dt[treatment_group == 1, repo_id]),
          control_repositories = uniqueN(dt[treatment_group == 0, repo_id])
        )]
      }
    }
  }
}

static_effects <- if (length(static_rows)) rbindlist(static_rows, fill = TRUE) else data.table()
dynamic_effects <- if (length(dynamic_rows)) rbindlist(dynamic_rows, fill = TRUE) else data.table()
model_audit <- rbindlist(model_audit_rows, fill = TRUE)

if (nrow(static_effects) > 0L) setorder(static_effects, outcome_order, specification_order)
if (nrow(dynamic_effects) > 0L) setorder(dynamic_effects, outcome_order, event_time, specification_order)
setorder(model_audit, specification_order, outcome_order, model_type)

model_failures <- model_audit[model_status != "success", .N]
add_qc("model_failures", model_failures, 0, model_failures == 0, "hard")
strict_count_check("model_audit_rows", nrow(model_audit), expected_model_audit_rows)
strict_count_check("static_effect_rows", nrow(static_effects), expected_static_rows)
strict_count_check("dynamic_effect_rows", nrow(dynamic_effects), expected_dynamic_rows)

static_missing_numeric <- if (nrow(static_effects)) {
  static_effects[, sum(!complete.cases(estimate, std_error, conf_low, conf_high))]
} else {
  expected_static_rows
}
dynamic_missing_numeric <- if (nrow(dynamic_effects)) {
  dynamic_effects[, sum(!complete.cases(estimate, std_error, conf_low, conf_high))]
} else {
  expected_dynamic_rows
}
add_qc("static_effect_rows_missing_numeric_results", static_missing_numeric, 0, static_missing_numeric == 0, "hard")
add_qc("dynamic_effect_rows_missing_numeric_results", dynamic_missing_numeric, 0, dynamic_missing_numeric == 0, "hard")

pretrend_checks <- dynamic_effects[
  event_time >= pretrend_min & event_time <= pretrend_max,
  .(
    specification_id,
    specification_order,
    specification_label,
    outcome,
    outcome_order,
    outcome_label,
    event_time,
    estimate,
    std_error,
    conf_low,
    conf_high,
    p_value,
    ci_includes_zero,
    significant_at_0_05,
    treated_repositories_at_event_time
  )
]
if (nrow(pretrend_checks) > 0L) setorder(pretrend_checks, outcome_order, specification_order, event_time)
strict_count_check("pretrend_check_rows", nrow(pretrend_checks), expected_pretrend_rows)

pretrend_summary <- pretrend_checks[, .(
  pretrend_terms = .N,
  ci_includes_zero_terms = sum(ci_includes_zero, na.rm = TRUE),
  ci_excludes_zero_terms = sum(!ci_includes_zero, na.rm = TRUE),
  significant_terms_0_05 = sum(significant_at_0_05, na.rm = TRUE),
  all_pretrend_cis_include_zero = all(ci_includes_zero),
  minimum_pretrend_p_value = min(p_value, na.rm = TRUE)
), by = .(
  specification_id,
  specification_order,
  specification_label,
  outcome,
  outcome_order,
  outcome_label
)]
setorder(pretrend_summary, outcome_order, specification_order)

comparison_definitions <- data.table(
  comparison_id = c("sample_attrition", "measurement_backend", "taxonomy_breadth"),
  comparison_order = 1:3,
  comparison_label = c(
    "Paper common minus paper full",
    "Local taxonomy minus paper common",
    "Local all-recognized minus local taxonomy"
  ),
  reference_specification_id = c(
    "paper_full",
    "paper_common",
    "local_taxonomy_common"
  ),
  comparison_specification_id = c(
    "paper_common",
    "local_taxonomy_common",
    "local_all_common"
  ),
  interpretation = c(
    "Descriptive effect of restricting the paper analysis to the exact common sample.",
    "Primary descriptive difference caused by replacing paper NCLOC with local taxonomy-aligned cloc NCLOC on identical rows.",
    "Robustness difference caused by including every cloc-recognized language type on identical rows."
  )
)

build_static_comparisons <- function() {
  rows <- list()
  for (i in seq_len(nrow(comparison_definitions))) {
    definition <- comparison_definitions[i]
    reference <- static_effects[specification_id == definition$reference_specification_id]
    comparison <- static_effects[specification_id == definition$comparison_specification_id]
    merged <- merge(
      reference[, .(
        outcome,
        outcome_order,
        outcome_label,
        reference_estimate = estimate,
        reference_percent_effect = percent_effect
      )],
      comparison[, .(
        outcome,
        comparison_estimate = estimate,
        comparison_percent_effect = percent_effect
      )],
      by = "outcome"
    )
    rows[[length(rows) + 1L]] <- merged[, .(
      comparison_id = definition$comparison_id,
      comparison_order = definition$comparison_order,
      comparison_label = definition$comparison_label,
      interpretation = definition$interpretation,
      reference_specification_id = definition$reference_specification_id,
      comparison_specification_id = definition$comparison_specification_id,
      outcome,
      outcome_order,
      outcome_label,
      reference_estimate,
      comparison_estimate,
      estimate_difference = comparison_estimate - reference_estimate,
      reference_percent_effect,
      comparison_percent_effect,
      percentage_point_difference = comparison_percent_effect - reference_percent_effect,
      difference_is_descriptive = TRUE
    )]
  }
  result <- rbindlist(rows)
  setorder(result, outcome_order, comparison_order)
  result
}

build_dynamic_comparisons <- function() {
  rows <- list()
  for (i in seq_len(nrow(comparison_definitions))) {
    definition <- comparison_definitions[i]
    reference <- dynamic_effects[specification_id == definition$reference_specification_id]
    comparison <- dynamic_effects[specification_id == definition$comparison_specification_id]
    merged <- merge(
      reference[, .(
        outcome,
        outcome_order,
        outcome_label,
        event_time,
        reference_estimate = estimate,
        reference_percent_effect = percent_effect
      )],
      comparison[, .(
        outcome,
        event_time,
        comparison_estimate = estimate,
        comparison_percent_effect = percent_effect
      )],
      by = c("outcome", "event_time")
    )
    rows[[length(rows) + 1L]] <- merged[, .(
      comparison_id = definition$comparison_id,
      comparison_order = definition$comparison_order,
      comparison_label = definition$comparison_label,
      interpretation = definition$interpretation,
      reference_specification_id = definition$reference_specification_id,
      comparison_specification_id = definition$comparison_specification_id,
      outcome,
      outcome_order,
      outcome_label,
      event_time,
      reference_estimate,
      comparison_estimate,
      estimate_difference = comparison_estimate - reference_estimate,
      reference_percent_effect,
      comparison_percent_effect,
      percentage_point_difference = comparison_percent_effect - reference_percent_effect,
      difference_is_descriptive = TRUE
    )]
  }
  result <- rbindlist(rows)
  setorder(result, outcome_order, event_time, comparison_order)
  result
}

static_comparisons <- build_static_comparisons()
dynamic_comparisons <- build_dynamic_comparisons()
expected_dynamic_comparison_rows <- resolve_expected(
  expected_dynamic_comparison_rows,
  nrow(comparison_definitions) * nrow(outcomes) * expected_dynamic_terms_per_model
)
strict_count_check("static_comparison_rows", nrow(static_comparisons), expected_static_comparison_rows)
strict_count_check("dynamic_comparison_rows", nrow(dynamic_comparisons), expected_dynamic_comparison_rows)

static_spec_outcome_unique <- static_effects[, uniqueN(paste(specification_id, outcome, sep = "::"))]
dynamic_spec_outcome_horizon_unique <- dynamic_effects[, uniqueN(paste(specification_id, outcome, event_time, sep = "::"))]
add_qc(
  "static_specification_outcome_keys_unique",
  static_spec_outcome_unique,
  nrow(static_effects),
  static_spec_outcome_unique == nrow(static_effects),
  "hard"
)
add_qc(
  "dynamic_specification_outcome_horizon_keys_unique",
  dynamic_spec_outcome_horizon_unique,
  nrow(dynamic_effects),
  dynamic_spec_outcome_horizon_unique == nrow(dynamic_effects),
  "hard"
)

expected_horizon_terms <- expected_dynamic_terms_per_model
dynamic_term_counts <- dynamic_effects[, .N, by = .(specification_id, outcome)]
dynamic_incomplete_models <- dynamic_term_counts[N != expected_horizon_terms, .N]
add_qc(
  "dynamic_models_without_complete_horizon",
  dynamic_incomplete_models,
  0,
  dynamic_incomplete_models == 0,
  "hard",
  sprintf(
    "Every model must contain %d event-time coefficients (%s); -1 is the omitted reference period.",
    expected_horizon_terms,
    paste(estimable_event_times, collapse = ",")
  )
)

observed_event_times <- sort(unique(dynamic_effects$event_time))
event_grid_matches <- identical(as.integer(observed_event_times), as.integer(estimable_event_times))
add_qc(
  "dynamic_event_time_grid_matches_estimable_grid",
  paste(observed_event_times, collapse = ","),
  paste(estimable_event_times, collapse = ","),
  event_grid_matches,
  "hard"
)

qc <- rbindlist(qc_rows, fill = TRUE)
hard_qc_failures <- qc[severity == "hard" & !passed, .N]
warning_qc_failures <- qc[severity == "warning" & !passed, .N]

write_csv(specification_summary, args$specification_summary_output)
write_csv(model_audit, args$model_audit_output)
write_csv(static_effects, args$static_output)
write_csv(dynamic_effects, args$dynamic_output)
write_csv(pretrend_checks, args$pretrend_output)
write_csv(pretrend_summary, args$pretrend_summary_output)
write_csv(static_comparisons, args$static_comparison_output)
write_csv(dynamic_comparisons, args$dynamic_comparison_output)
write_csv(qc, args$qc_output)

plot_spec_levels <- specifications[order(specification_order), specification_label]

if (nrow(dynamic_effects) > 0L) {
  dynamic_plot_data <- copy(dynamic_effects)
  dynamic_plot_data[, specification_label := factor(specification_label, levels = plot_spec_levels)]
  dynamic_plot_data[, outcome_label := factor(outcome_label, levels = outcomes$outcome_label)]
  position <- position_dodge(width = 0.55)
  dynamic_plot <- ggplot(
    dynamic_plot_data,
    aes(x = event_time, y = estimate, color = specification_label, group = specification_label)
  ) +
    geom_hline(yintercept = 0, linetype = "dashed") +
    geom_vline(xintercept = -0.5, linetype = "dashed") +
    geom_errorbar(
      aes(ymin = conf_low, ymax = conf_high),
      position = position,
      width = 0.35,
      linewidth = 0.35
    ) +
    geom_line(position = position, linewidth = 0.45) +
    geom_point(position = position, size = 1.5) +
    scale_x_continuous(breaks = horizon_values) +
    facet_wrap(~ outcome_label, scales = "free_y", nrow = 1) +
    labs(
      x = "Months Relative to Cursor Adoption",
      y = "Treatment Effect on log(x + 1)",
      color = "NCLOC Specification"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      legend.position = "bottom",
      panel.grid.minor.x = element_blank(),
      panel.grid.major.x = element_blank()
    )
  ggsave(args$dynamic_plot_output, dynamic_plot, width = 13, height = 4.2, device = grDevices::pdf)

  primary_plot_data <- dynamic_plot_data[
    specification_id %in% c("paper_common", "local_taxonomy_common")
  ]
  primary_plot_data[, specification_label := droplevels(specification_label)]
  primary_plot <- ggplot(
    primary_plot_data,
    aes(x = event_time, y = estimate, color = specification_label, group = specification_label)
  ) +
    geom_hline(yintercept = 0, linetype = "dashed") +
    geom_vline(xintercept = -0.5, linetype = "dashed") +
    geom_errorbar(
      aes(ymin = conf_low, ymax = conf_high),
      position = position_dodge(width = 0.35),
      width = 0.25,
      linewidth = 0.4
    ) +
    geom_line(position = position_dodge(width = 0.35), linewidth = 0.55) +
    geom_point(position = position_dodge(width = 0.35), size = 1.7) +
    scale_x_continuous(breaks = horizon_values) +
    facet_wrap(~ outcome_label, scales = "free_y", nrow = 1) +
    labs(
      x = "Months Relative to Cursor Adoption",
      y = "Treatment Effect on log(x + 1)",
      color = "Common-Sample Backend"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      legend.position = "bottom",
      panel.grid.minor.x = element_blank(),
      panel.grid.major.x = element_blank()
    )
  ggsave(
    args$primary_comparison_plot_output,
    primary_plot,
    width = 10.5,
    height = 4.2,
    device = grDevices::pdf
  )
}

if (nrow(static_effects) > 0L) {
  static_plot_data <- copy(static_effects)
  static_plot_data[, specification_label := factor(specification_label, levels = rev(plot_spec_levels))]
  static_plot_data[, outcome_label := factor(outcome_label, levels = outcomes$outcome_label)]
  static_plot <- ggplot(
    static_plot_data,
    aes(x = specification_label, y = estimate)
  ) +
    geom_hline(yintercept = 0, linetype = "dashed") +
    geom_errorbar(aes(ymin = conf_low, ymax = conf_high), width = 0.2) +
    geom_point(size = 1.8) +
    facet_wrap(~ outcome_label, scales = "free_y", nrow = 1) +
    coord_flip() +
    labs(
      x = NULL,
      y = "Static Treatment Effect on log(x + 1)"
    ) +
    theme_minimal(base_size = 11) +
    theme(panel.grid.minor = element_blank())
  ggsave(args$static_plot_output, static_plot, width = 11, height = 4.5, device = grDevices::pdf)
}

session_lines <- capture.output(sessionInfo())
writeLines(session_lines, args$session_info_output)

summary_output <- data.table(
  implementation_version = "v1",
  specifications = nrow(specifications),
  outcomes = nrow(outcomes),
  static_models = model_audit[model_type == "static", .N],
  dynamic_models = model_audit[model_type == "dynamic", .N],
  successful_models = model_audit[model_status == "success", .N],
  failed_models = model_failures,
  static_effect_rows = nrow(static_effects),
  dynamic_effect_rows = nrow(dynamic_effects),
  pretrend_check_rows = nrow(pretrend_checks),
  static_comparison_rows = nrow(static_comparisons),
  dynamic_comparison_rows = nrow(dynamic_comparisons),
  hard_qc_failures = hard_qc_failures,
  warning_qc_failures = warning_qc_failures,
  horizon_min = horizon_min,
  horizon_max = horizon_max,
  pretrend_min = pretrend_min,
  pretrend_max = pretrend_max,
  first_stage_formula = paste(deparse(first_stage_formula), collapse = " "),
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")
)
write_csv(summary_output, args$summary_output)

if (nrow(static_effects) > 0L) {
  for (i in seq_len(nrow(static_effects))) {
    row <- static_effects[i]
    log_message(
      "Static: spec=%s; outcome=%s; estimate=%.6f; se=%.6f; p=%.6g; percent=%.2f",
      row$specification_id,
      row$outcome,
      row$estimate,
      row$std_error,
      row$p_value,
      row$percent_effect
    )
  }
}
log_message(
  paste0(
    "Completed run-x-c06-v1: specifications=%d; outcomes=%d; ",
    "static_rows=%d; dynamic_rows=%d; model_failures=%d; ",
    "hard_qc_failures=%d; warnings=%d"
  ),
  nrow(specifications),
  nrow(outcomes),
  nrow(static_effects),
  nrow(dynamic_effects),
  model_failures,
  hard_qc_failures,
  warning_qc_failures
)

if (hard_qc_failures > 0L || model_failures > 0L) {
  stop(sprintf(
    "C06 produced %d hard QC failure(s) and %d model failure(s).",
    hard_qc_failures,
    model_failures
  ))
}