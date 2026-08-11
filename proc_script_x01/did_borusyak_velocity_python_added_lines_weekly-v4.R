#!/usr/bin/env Rscript

# Weekly Python velocity DiD with one plotted calendar and two specifications.
#
# Specifications
# --------------
# 1. Adjusted:
#      outcome ~ log_age + ncloc + log_contributors + log_stars + log_issues
#                | repo_id + time_index
# 2. FE-only:
#      outcome ~ 1 | repo_id + time_index
#
# The adjusted model reuses the exact monthly covariate columns from the
# run-x-b02 SonarQube panel that feeds the monthly run-x-b03 analysis. It does
# not reconstruct log variables from raw ts_repos_monthly.csv files.
#
# Weekly-to-month mapping
# -----------------------
# A Monday-start week is assigned to the month containing its mid-week day
# (Thursday). For partial boundary weeks, that month is clipped to the
# repository's retained run-x-b02 monthly support. This keeps boundary weeks
# aligned with the observed support while using a deterministic majority-day
# rule for ordinary cross-month weeks. If the run-x-b02 panel has an internal
# missing month, the affected weekly rows are excluded from BOTH specifications.
# This v4 common-support policy ensures that Adjusted and FE-only estimates are
# compared on exactly the same repository-week observations.

options(stringsAsFactors = FALSE)

IMPLEMENTATION_VERSION <- "v4"
PRIMARY_OUTCOME <- "log_lines_added_py_source"
PRIMARY_OUTCOME_LABEL <- "Python Source Additions"
ADJUSTED_FORMULA_TEXT <- "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
FE_ONLY_FORMULA_TEXT <- "~ 1 | repo_id + time_index"
ADJUSTED_FORMULA <- ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index
FE_ONLY_FORMULA <- ~ 1 | repo_id + time_index

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)

log_message <- function(level, fmt, ...) {
  message(sprintf("%s [%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)))
}

parse_cli <- function(args) {
  result <- list()
  i <- 1L
  while (i <= length(args)) {
    token <- args[[i]]
    if (!startsWith(token, "--")) abortf("Unexpected positional argument: %s", token)
    key <- gsub("-", "_", sub("^--", "", token), fixed = TRUE)
    if (i == length(args) || startsWith(args[[i + 1L]], "--")) {
      result[[key]] <- TRUE
      i <- i + 1L
    } else {
      result[[key]] <- args[[i + 1L]]
      i <- i + 2L
    }
  }
  result
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
  parsed <- suppressWarnings(as.integer(value))
  if (is.na(parsed)) abortf("Argument --%s must be integer: %s", gsub("_", "-", name, fixed = TRUE), value)
  parsed
}

as_numeric_arg <- function(args, name, default) {
  value <- args[[name]]
  if (is.null(value)) return(as.numeric(default))
  parsed <- suppressWarnings(as.numeric(value))
  if (is.na(parsed)) abortf("Argument --%s must be numeric: %s", gsub("_", "-", name, fixed = TRUE), value)
  parsed
}

as_logical_arg <- function(args, name, default = FALSE) {
  value <- args[[name]]
  if (is.null(value)) return(isTRUE(default))
  text <- tolower(trimws(as.character(value)))
  if (text %in% c("1", "true", "yes", "y", "on")) return(TRUE)
  if (text %in% c("0", "false", "no", "n", "off")) return(FALSE)
  abortf("Argument --%s must be boolean-like: %s", gsub("_", "-", name, fixed = TRUE), value)
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing) > 0L) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

ensure_dir <- function(path) {
  if (!dir.exists(path)) dir.create(path, recursive = TRUE, showWarnings = FALSE)
}

write_csv <- function(data, path) {
  ensure_dir(dirname(path))
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) {
    abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
  }
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
  list(
    value = value,
    warnings = unique(warnings),
    elapsed = elapsed,
    error = inherits(value, "captured_error")
  )
}

extract_effect_table <- function(result, outcome_name, confidence_level) {
  table <- data.table::as.data.table(result)
  validate_columns(table, c("term", "estimate", "std.error"), "did_imputation result")
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  table[, outcome := outcome_name]
  table[, conf.low := estimate - critical * std.error]
  table[, conf.high := estimate + critical * std.error]
  table[, p_value := ifelse(
    is.finite(std.error) & std.error > 0,
    2 * stats::pnorm(-abs(estimate / std.error)),
    NA_real_
  )]
  table[, significant := !is.na(p_value) & p_value < (1 - confidence_level)]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table
}

run_did <- function(panel, first_stage_formula, horizon = NULL, pretrends = NULL) {
  capture_evaluation(
    didimputation::did_imputation(
      data = panel,
      yname = PRIMARY_OUTCOME,
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

prepare_weekly_panel <- function(path, expected_calendar_key) {
  if (!file.exists(path)) abortf("Weekly panel does not exist: %s", path)
  panel <- data.table::fread(path, showProgress = FALSE)
  required <- c(
    "repo_id", "repo_name", "dataset_source", "treatment_group", "calendar_key",
    "analysis_timezone", "week_start", "time_index", "event_index", "time_to_event",
    "absorbing_treated", "support_start_month", "support_end_month", PRIMARY_OUTCOME
  )
  validate_columns(panel, required, "Weekly panel")

  if (data.table::uniqueN(panel$calendar_key) != 1L) {
    abortf("Weekly panel must contain exactly one calendar_key")
  }
  observed_calendar <- unique(panel$calendar_key)
  if (observed_calendar != expected_calendar_key) {
    abortf("Calendar key mismatch: expected %s, observed %s", expected_calendar_key, observed_calendar)
  }

  numeric_cols <- c(
    "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
    "absorbing_treated", PRIMARY_OUTCOME
  )
  for (column in numeric_cols) panel[, (column) := suppressWarnings(as.numeric(get(column)))]
  panel[, repo_id := as.integer(repo_id)]
  panel[, treatment_group := as.integer(treatment_group)]
  panel[, time_index := as.integer(time_index)]
  panel[, event_index := as.integer(event_index)]
  panel[, absorbing_treated := as.integer(absorbing_treated)]

  if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) {
    abortf("Weekly panel has missing repo/time/event indices")
  }
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) {
    abortf("Weekly panel has duplicate repo-week keys")
  }

  reconstructed <- as.integer(panel$treatment_group == 1L & panel$time_index >= panel$event_index)
  if (sum(reconstructed != panel$absorbing_treated) > 0L) {
    abortf("Weekly panel has absorbing-treatment mismatches")
  }

  panel[, week_start_date := as.Date(week_start)]
  if (anyNA(panel$week_start_date)) abortf("Weekly panel contains invalid week_start values")
  panel[, week_midpoint_date := week_start_date + 3L]
  panel[, covariate_month_raw := format(week_midpoint_date, "%Y-%m")]
  panel[, covariate_month := covariate_month_raw]
  panel[covariate_month < support_start_month, covariate_month := support_start_month]
  panel[covariate_month > support_end_month, covariate_month := support_end_month]
  panel[, event_time := data.table::fifelse(
    treatment_group == 1L,
    time_index - event_index,
    NA_integer_
  )]
  panel
}

prepare_monthly_panel <- function(path) {
  if (!file.exists(path)) abortf("Monthly run-x-b02 panel does not exist: %s", path)
  monthly <- data.table::fread(path, showProgress = FALSE)
  required <- c(
    "repo_id", "repo_name", "treatment_group", "time", "ncloc_backend",
    "log_age", "ncloc", "log_contributors", "log_stars", "log_issues"
  )
  validate_columns(monthly, required, "Monthly run-x-b02 SonarQube panel")

  monthly[, repo_id := suppressWarnings(as.integer(repo_id))]
  monthly[, treatment_group := suppressWarnings(as.integer(treatment_group))]
  if (anyNA(monthly$repo_id)) abortf("Monthly panel has missing/non-numeric repo_id")
  if (nrow(monthly[, .N, by = .(repo_id, time)][N > 1L]) > 0L) {
    abortf("Monthly panel has duplicate repo_id/time rows")
  }

  backend_values <- unique(tolower(trimws(as.character(monthly$ncloc_backend))))
  if (length(backend_values) != 1L || backend_values[[1L]] != "sonarqube") {
    abortf("Monthly panel must be the SonarQube backend; observed: %s", paste(backend_values, collapse = ","))
  }

  numeric_covariates <- c("log_age", "ncloc", "log_contributors", "log_stars", "log_issues")
  for (column in numeric_covariates) monthly[, (column) := suppressWarnings(as.numeric(get(column)))]

  monthly[, .(
    repo_id,
    monthly_repo_name = repo_name,
    monthly_treatment_group = treatment_group,
    covariate_month = as.character(time),
    log_age,
    ncloc,
    log_contributors,
    log_stars,
    log_issues
  )]
}

args <- parse_cli(commandArgs(trailingOnly = TRUE))
weekly_panel_path <- require_arg(args, "weekly_panel")
monthly_panel_path <- require_arg(args, "monthly_panel")
output_dir <- require_arg(args, "output_dir")
calendar_key <- require_arg(args, "calendar_key")
plot_min_event <- as_integer_arg(args, "plot_min_event", -12L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 12L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -12L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_weekly_rows <- as_integer_arg(args, "expected_weekly_rows", 8599L)
expected_monthly_rows <- as_integer_arg(args, "expected_monthly_rows", 1954L)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", 63L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", 104L)
expected_common_support_rows <- as_integer_arg(args, "expected_common_support_rows", 8595L)
expected_dropped_rows <- as_integer_arg(args, "expected_dropped_rows", 4L)
expected_event_zero_support <- as_integer_arg(args, "expected_event_zero_support", 62L)

if (plot_min_event >= -1L) abortf("plot_min_event must include pre-treatment weeks")
if (plot_max_event < 0L) abortf("plot_max_event must include post-treatment weeks")
if (pretrend_max >= -1L) abortf("pretrend_max must be at most -2 because -1 is omitted")
if (pretrend_min > pretrend_max) abortf("Invalid pretrend window")
if (!(confidence_level > 0 && confidence_level < 1)) abortf("confidence_level must be between 0 and 1")

check_packages(c("data.table", "didimputation", "fixest"))
ensure_dir(output_dir)

log_message("INFO", "Reading weekly panel: %s", weekly_panel_path)
weekly <- prepare_weekly_panel(weekly_panel_path, calendar_key)
log_message("INFO", "Reading run-x-b02 SonarQube monthly panel: %s", monthly_panel_path)
monthly <- prepare_monthly_panel(monthly_panel_path)

if (strict && nrow(weekly) != expected_weekly_rows) {
  abortf("Expected %d weekly rows, observed %d", expected_weekly_rows, nrow(weekly))
}
if (strict && nrow(monthly) != expected_monthly_rows) {
  abortf("Expected %d monthly rows, observed %d", expected_monthly_rows, nrow(monthly))
}

analysis_panel <- merge(
  weekly,
  monthly,
  by = c("repo_id", "covariate_month"),
  all.x = TRUE,
  sort = FALSE
)

if (nrow(analysis_panel) != nrow(weekly)) {
  abortf("Monthly-covariate merge changed row count: weekly=%d merged=%d", nrow(weekly), nrow(analysis_panel))
}
if (nrow(analysis_panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) {
  abortf("Merged analysis panel contains duplicate repo-week keys")
}

repo_name_mismatch <- analysis_panel[
  !is.na(monthly_repo_name) & repo_name != monthly_repo_name,
  .N
]
treatment_group_mismatch <- analysis_panel[
  !is.na(monthly_treatment_group) & treatment_group != monthly_treatment_group,
  .N
]
if (repo_name_mismatch > 0L) abortf("Found %d repo-name mismatches after monthly merge", repo_name_mismatch)
if (treatment_group_mismatch > 0L) abortf("Found %d treatment-group mismatches after monthly merge", treatment_group_mismatch)

analysis_panel[, adjusted_covariates_complete := complete.cases(
  log_age, ncloc, log_contributors, log_stars, log_issues
)]
analysis_panel[, covariate_month_was_clipped := covariate_month != covariate_month_raw]

# v4 common-support policy: both specifications use the same repository-week
# observations for which all monthly adjusted covariates are available. This
# avoids comparing an adjusted model on a smaller support with an FE-only model
# on the full weekly grid. Missing monthly covariates are never imputed.
common_panel <- analysis_panel[adjusted_covariates_complete == TRUE]
data.table::setorder(common_panel, repo_id, time_index)

dropped_common_support <- analysis_panel[adjusted_covariates_complete == FALSE, .(
  repo_id,
  repo_name,
  dataset_source,
  treatment_group,
  calendar_key,
  analysis_timezone,
  week_start,
  time_index,
  event_index,
  event_time,
  support_start_month,
  support_end_month,
  covariate_month_raw,
  covariate_month,
  log_age,
  ncloc,
  log_contributors,
  log_stars,
  log_issues
)]

if (strict && nrow(common_panel) != expected_common_support_rows) {
  abortf("Expected %d common-support weekly rows, observed %d", expected_common_support_rows, nrow(common_panel))
}
if (strict && nrow(dropped_common_support) != expected_dropped_rows) {
  abortf("Expected %d rows dropped by common-support policy, observed %d", expected_dropped_rows, nrow(dropped_common_support))
}

common_treatment_repos <- data.table::uniqueN(common_panel[treatment_group == 1L, repo_id])
common_control_repos <- data.table::uniqueN(common_panel[treatment_group == 0L, repo_id])
if (strict && common_treatment_repos != expected_treatment_repos) {
  abortf("Common support expected %d treatment repos, observed %d", expected_treatment_repos, common_treatment_repos)
}
if (strict && common_control_repos != expected_control_repos) {
  abortf("Common support expected %d control repos, observed %d", expected_control_repos, common_control_repos)
}

common_event_support <- common_panel[
  treatment_group == 1L & event_time >= plot_min_event & event_time <= plot_max_event,
  .(
    support_rows = .N,
    support_repositories = data.table::uniqueN(repo_id)
  ),
  by = event_time
]
data.table::setorder(common_event_support, event_time)
event_zero_support <- common_event_support[event_time == 0L, support_repositories]
if (length(event_zero_support) != 1L) {
  abortf("Common support does not contain exactly one event-week-0 support row")
}
if (strict && event_zero_support[[1L]] != expected_event_zero_support) {
  abortf("Expected event-week-0 support of %d repositories, observed %d", expected_event_zero_support, event_zero_support[[1L]])
}

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
expected_dynamic_terms <- length(pretrend_values) + length(post_values)

specs <- list(
  list(
    spec_key = "adjusted",
    spec_label = "Adjusted",
    formula = ADJUSTED_FORMULA,
    formula_text = ADJUSTED_FORMULA_TEXT
  ),
  list(
    spec_key = "fe_only",
    spec_label = "FE-only",
    formula = FE_ONLY_FORMULA,
    formula_text = FE_ONLY_FORMULA_TEXT
  )
)

static_tables <- list()
dynamic_tables <- list()
pretrend_tables <- list()
sample_tables <- list()
diagnostic_tables <- list()

for (entry in specs) {
  # Both specifications deliberately use the identical v4 common support.
  spec_panel <- data.table::copy(common_panel)
  data.table::setorder(spec_panel, repo_id, time_index)

  treatment_repos <- data.table::uniqueN(spec_panel[treatment_group == 1L, repo_id])
  control_repos <- data.table::uniqueN(spec_panel[treatment_group == 0L, repo_id])
  if (strict && treatment_repos != expected_treatment_repos) {
    abortf("%s expected %d treatment repos, observed %d", entry$spec_label, expected_treatment_repos, treatment_repos)
  }
  if (strict && control_repos != expected_control_repos) {
    abortf("%s expected %d control repos, observed %d", entry$spec_label, expected_control_repos, control_repos)
  }


  pre_counts <- spec_panel[treatment_group == 1L, .(
    pre_weeks = sum(event_time < 0L, na.rm = TRUE)
  ), by = repo_id]
  min_pre_weeks <- min(pre_counts$pre_weeks)
  if (min_pre_weeks < 4L) {
    abortf("%s has a treated repository with fewer than four pre-treatment weeks", entry$spec_label)
  }

  untreated_rows <- nrow(spec_panel[absorbing_treated == 0L])
  treated_rows <- nrow(spec_panel[absorbing_treated == 1L])

  sample_tables[[entry$spec_key]] <- data.table::data.table(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    calendar_key = calendar_key,
    analysis_timezone = unique(spec_panel$analysis_timezone),
    rows = nrow(spec_panel),
    repositories = data.table::uniqueN(spec_panel$repo_id),
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    untreated_first_stage_rows = untreated_rows,
    treated_rows = treated_rows,
    minimum_treatment_pre_weeks = min_pre_weeks,
    dropped_rows_due_to_common_support = nrow(analysis_panel) - nrow(common_panel),
    common_support_policy = "complete monthly adjusted covariates; identical rows for Adjusted and FE-only"
  )

  log_message("INFO", "Running static DiD: %s", entry$spec_label)
  static_capture <- run_did(spec_panel, entry$formula)
  if (static_capture$error) abortf("Static DiD failure for %s: %s", entry$spec_label, static_capture$value$message)
  static <- extract_effect_table(static_capture$value, PRIMARY_OUTCOME, confidence_level)[term == "treat"]
  if (nrow(static) != 1L) abortf("Expected one static ATT for %s, observed %d", entry$spec_label, nrow(static))
  static[, `:=`(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    calendar_key = calendar_key,
    analysis_timezone = unique(spec_panel$analysis_timezone),
    outcome_label = PRIMARY_OUTCOME_LABEL,
    outcome_role = "primary",
    first_stage_formula = entry$formula_text,
    term_type = "static_att",
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    treated_observations = treated_rows,
    first_stage_observations = untreated_rows
  )]
  static_tables[[entry$spec_key]] <- static

  log_message("INFO", "Running dynamic DiD: %s", entry$spec_label)
  dynamic_capture <- run_did(
    spec_panel,
    entry$formula,
    horizon = post_values,
    pretrends = pretrend_values
  )
  if (dynamic_capture$error) abortf("Dynamic DiD failure for %s: %s", entry$spec_label, dynamic_capture$value$message)
  dynamic <- extract_effect_table(dynamic_capture$value, PRIMARY_OUTCOME, confidence_level)
  dynamic[, event_time := suppressWarnings(as.integer(as.character(term)))]
  dynamic <- dynamic[!is.na(event_time)]
  if (nrow(dynamic) != expected_dynamic_terms) {
    abortf("Expected %d dynamic terms for %s, observed %d", expected_dynamic_terms, entry$spec_label, nrow(dynamic))
  }

  support <- data.table::copy(common_event_support)
  dynamic <- merge(dynamic, support, by = "event_time", all.x = TRUE, sort = FALSE)
  dynamic[, term_type := data.table::fcase(
    event_time %in% pretrend_values, "placebo_pretrend",
    event_time >= 0L, "post_treatment",
    default = "other"
  )]
  dynamic[, `:=`(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    calendar_key = calendar_key,
    analysis_timezone = unique(spec_panel$analysis_timezone),
    outcome_label = PRIMARY_OUTCOME_LABEL,
    outcome_role = "primary",
    first_stage_formula = entry$formula_text,
    ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0
  )]
  data.table::setorder(dynamic, event_time)
  dynamic_tables[[entry$spec_key]] <- dynamic

  pre <- data.table::copy(dynamic[term_type == "placebo_pretrend"])
  pre[, all_ci_include_zero := all(ci_includes_zero)]
  pretrend_tables[[entry$spec_key]] <- pre

  diagnostic_tables[[entry$spec_key]] <- data.table::data.table(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    static_runtime_seconds = static_capture$elapsed,
    static_warning_count = length(static_capture$warnings),
    static_warning_messages = paste(static_capture$warnings, collapse = " | "),
    dynamic_runtime_seconds = dynamic_capture$elapsed,
    dynamic_warning_count = length(dynamic_capture$warnings),
    dynamic_warning_messages = paste(dynamic_capture$warnings, collapse = " | "),
    first_stage_formula = entry$formula_text
  )
}

static_all <- data.table::rbindlist(static_tables, use.names = TRUE, fill = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, use.names = TRUE, fill = TRUE)
pretrend_all <- data.table::rbindlist(pretrend_tables, use.names = TRUE, fill = TRUE)
sample_all <- data.table::rbindlist(sample_tables, use.names = TRUE, fill = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostic_tables, use.names = TRUE, fill = TRUE)

# Validate that the two specifications report identical event-time support.
adjusted_support <- dynamic_all[spec_key == "adjusted", .(
  event_time,
  adjusted_support_rows = support_rows,
  adjusted_support_repositories = support_repositories
)]
fe_only_support <- dynamic_all[spec_key == "fe_only", .(
  event_time,
  fe_only_support_rows = support_rows,
  fe_only_support_repositories = support_repositories
)]
support_comparison <- merge(adjusted_support, fe_only_support, by = "event_time", all = TRUE)
support_comparison[, support_rows_match := adjusted_support_rows == fe_only_support_rows]
support_comparison[, support_repositories_match := adjusted_support_repositories == fe_only_support_repositories]
if (anyNA(support_comparison$support_rows_match) ||
    anyNA(support_comparison$support_repositories_match) ||
    any(!support_comparison$support_rows_match) ||
    any(!support_comparison$support_repositories_match)) {
  abortf("Adjusted and FE-only dynamic event support differs under the v4 common-support policy")
}

pretrend_summary <- pretrend_all[, .(
  all_ci_include_zero = all(ci_includes_zero),
  periods_excluding_zero = paste(event_time[!ci_includes_zero], collapse = "|"),
  minimum_p_value = ifelse(all(is.na(p_value)), NA_real_, min(p_value, na.rm = TRUE)),
  significant_placebo_terms = sum(significant, na.rm = TRUE)
), by = .(spec_key, spec_label, calendar_key, analysis_timezone, outcome, outcome_label)]

mapping_audit <- analysis_panel[, .(
  weekly_rows_before_common_support = .N,
  common_support_rows = sum(adjusted_covariates_complete),
  rows_dropped_by_common_support = sum(!adjusted_covariates_complete),
  clipped_boundary_rows = sum(covariate_month_was_clipped),
  repositories_with_dropped_rows = data.table::uniqueN(repo_id[!adjusted_covariates_complete])
)]
mapping_audit[, `:=`(
  implementation_version = IMPLEMENTATION_VERSION,
  calendar_key = calendar_key,
  monthly_covariate_source = monthly_panel_path,
  mapping_policy = "week midpoint month; clipped to run-x-b02 support boundaries",
  common_support_policy = "drop rows lacking any adjusted covariate from both specifications"
)]

qc <- data.table::data.table(
  check_name = c(
    "weekly_rows_before_covariate_merge",
    "weekly_rows_after_covariate_merge",
    "monthly_b02_rows",
    "common_support_rows",
    "rows_dropped_by_common_support",
    "common_support_treatment_repositories",
    "common_support_control_repositories",
    "event_week_zero_support_repositories",
    "static_rows",
    "dynamic_rows",
    "pretrend_rows",
    "pretrend_summary_rows",
    "sample_summary_rows",
    "diagnostic_rows",
    "cross_spec_event_support_mismatches"
  ),
  observed = c(
    nrow(weekly),
    nrow(analysis_panel),
    nrow(monthly),
    nrow(common_panel),
    nrow(dropped_common_support),
    common_treatment_repos,
    common_control_repos,
    event_zero_support[[1L]],
    nrow(static_all),
    nrow(dynamic_all),
    nrow(pretrend_all),
    nrow(pretrend_summary),
    nrow(sample_all),
    nrow(diagnostics_all),
    sum(!support_comparison$support_rows_match | !support_comparison$support_repositories_match)
  ),
  expected = c(
    expected_weekly_rows,
    expected_weekly_rows,
    expected_monthly_rows,
    expected_common_support_rows,
    expected_dropped_rows,
    expected_treatment_repos,
    expected_control_repos,
    expected_event_zero_support,
    2L,
    2L * expected_dynamic_terms,
    2L * length(pretrend_values),
    2L,
    2L,
    2L,
    0L
  )
)
qc[, status := ifelse(observed == expected, "pass", "fail")]
qc[, note := c(
  "Original Chicago weekly grid.",
  "Monthly covariate merge must preserve the weekly grid before filtering.",
  "Authoritative run-x-b02 SonarQube monthly panel.",
  "Rows used by both Adjusted and FE-only specifications.",
  "Rows lacking at least one adjusted monthly covariate.",
  "Repository roster retained after common-support filtering.",
  "Repository roster retained after common-support filtering.",
  "Event week 0 may have fewer than 63 repositories because the panel is unbalanced.",
  "Adjusted plus FE-only static ATT rows.",
  "Two specifications times package-native dynamic terms.",
  "Two specifications times placebo-pretrend terms.",
  "One pretrend summary per specification.",
  "One sample summary per specification.",
  "One diagnostic row per specification.",
  "Adjusted and FE-only must use identical event-time support."
)]
if (strict && any(qc$status == "fail")) {
  failed <- qc[status == "fail"]
  abortf(
    "Weekly v4 QC failed: %s",
    paste(sprintf("%s observed=%d expected=%d", failed$check_name, failed$observed, failed$expected), collapse = "; ")
  )
}

write_csv(static_all, file.path(output_dir, "velocity_python_added_lines_weekly_v4_static_effects.csv"))
write_csv(dynamic_all, file.path(output_dir, "velocity_python_added_lines_weekly_v4_dynamic_effects.csv"))
write_csv(pretrend_all, file.path(output_dir, "velocity_python_added_lines_weekly_v4_pretrend_checks.csv"))
write_csv(pretrend_summary, file.path(output_dir, "velocity_python_added_lines_weekly_v4_pretrend_summary.csv"))
write_csv(sample_all, file.path(output_dir, "velocity_python_added_lines_weekly_v4_sample_summary.csv"))
write_csv(diagnostics_all, file.path(output_dir, "velocity_python_added_lines_weekly_v4_diagnostics.csv"))
write_csv(mapping_audit, file.path(output_dir, "velocity_python_added_lines_weekly_v4_covariate_mapping_audit.csv"))
write_csv(dropped_common_support, file.path(output_dir, "velocity_python_added_lines_weekly_v4_common_support_dropped_rows.csv"))
write_csv(common_event_support, file.path(output_dir, "velocity_python_added_lines_weekly_v4_event_support.csv"))
write_csv(support_comparison, file.path(output_dir, "velocity_python_added_lines_weekly_v4_cross_spec_support_check.csv"))
write_csv(qc, file.path(output_dir, "velocity_python_added_lines_weekly_v4_qc.csv"))

log_message(
  "INFO",
  "Completed weekly v4 DiD: static=%d; dynamic=%d; pretrend=%d; common-support dropped rows=%d",
  nrow(static_all),
  nrow(dynamic_all),
  nrow(pretrend_all),
  nrow(dropped_common_support)
)
