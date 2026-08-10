#!/usr/bin/env Rscript

# Weekly Python velocity DiD with one calendar and two specifications:
# (1) FE-only: ~ 1 | repo_id + time_index
# (2) Adjusted: ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index
#
# The adjusted weekly specification uses lagged monthly covariates. For a weekly
# row whose Monday week-start falls in month M, the model attaches covariates
# from month M-1 for the same repository. This avoids using contemporaneous or
# future information from the same month while still permitting a weekly
# sensitivity analysis.

options(stringsAsFactors = FALSE)

IMPLEMENTATION_VERSION <- "v2"
PRIMARY_OUTCOME <- "log_lines_added_py_source"
PRIMARY_OUTCOME_LABEL <- "Python Added Lines: Source (Primary)"

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
  if (is.null(value) || !nzchar(as.character(value))) abortf("Missing required argument: --%s", gsub("_", "-", name, fixed = TRUE))
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
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
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

increment_month_string <- function(month_vec, delta = 1L) {
  pieces <- strsplit(month_vec, "-", fixed = TRUE)
  result <- character(length(month_vec))
  for (i in seq_along(pieces)) {
    part <- pieces[[i]]
    if (length(part) != 2L) abortf("Invalid YYYY-MM value: %s", month_vec[[i]])
    year <- suppressWarnings(as.integer(part[[1L]]))
    month <- suppressWarnings(as.integer(part[[2L]]))
    if (is.na(year) || is.na(month) || month < 1L || month > 12L) abortf("Invalid YYYY-MM value: %s", month_vec[[i]])
    total <- year * 12L + (month - 1L) + delta
    new_year <- total %/% 12L
    new_month <- total %% 12L + 1L
    result[[i]] <- sprintf("%04d-%02d", new_year, new_month)
  }
  result
}

extract_effect_table <- function(result, outcome_name, confidence_level) {
  table <- data.table::as.data.table(result)
  validate_columns(table, c("term", "estimate", "std.error"), "did_imputation result")
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  table[, outcome := outcome_name]
  table[, conf.low := estimate - critical * std.error]
  table[, conf.high := estimate + critical * std.error]
  table[, p_value := ifelse(is.finite(std.error) & std.error > 0, 2 * stats::pnorm(-abs(estimate / std.error)), NA_real_)]
  table[, significant := !is.na(p_value) & p_value < (1 - confidence_level)]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table
}

run_did <- function(panel, outcome, first_stage_formula, horizon = NULL, pretrends = NULL) {
  capture_evaluation(
    didimputation::did_imputation(
      data = panel,
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

prepare_weekly_panel <- function(path, expected_calendar_key) {
  panel <- data.table::fread(path, showProgress = FALSE)
  required <- c(
    "repo_id", "repo_name", "dataset_source", "treatment_group", "calendar_key",
    "analysis_timezone", "week_start", "time_index", "event_index", "time_to_event",
    "absorbing_treated", PRIMARY_OUTCOME
  )
  validate_columns(panel, required, "Weekly panel")
  if (data.table::uniqueN(panel$calendar_key) != 1L) abortf("Weekly panel must contain exactly one calendar_key")
  if (unique(panel$calendar_key) != expected_calendar_key) {
    abortf("Calendar key mismatch: expected %s, observed %s", expected_calendar_key, unique(panel$calendar_key))
  }
  numeric_cols <- c("repo_id", "treatment_group", "time_index", "event_index", "time_to_event", "absorbing_treated", PRIMARY_OUTCOME)
  for (column in numeric_cols) panel[, (column) := suppressWarnings(as.numeric(get(column)))]
  panel[, repo_id := as.integer(repo_id)]
  panel[, treatment_group := as.integer(treatment_group)]
  panel[, time_index := as.integer(time_index)]
  panel[, event_index := as.integer(event_index)]
  panel[, absorbing_treated := as.integer(absorbing_treated)]
  if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) abortf("Weekly panel has missing repo/time/event indices")
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("Weekly panel has duplicate repo-week keys")
  panel[, week_month := substr(week_start, 1L, 7L)]
  panel[, event_time := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
  panel
}

prepare_monthly_covariates <- function(treatment_path, control_path) {
  treat <- data.table::fread(treatment_path, showProgress = FALSE)
  control <- data.table::fread(control_path, showProgress = FALSE)
  treat[, dataset_source := "treatment"]
  control[, dataset_source := "control"]
  monthly <- data.table::rbindlist(list(treat, control), use.names = TRUE, fill = TRUE)
  required <- c("repo_name", "month", "dataset_source", "age", "ncloc", "contributors", "stars", "issues")
  validate_columns(monthly, required, "Combined monthly covariates")
  numeric_cols <- c("age", "ncloc", "contributors", "stars", "issues")
  for (column in numeric_cols) monthly[, (column) := suppressWarnings(as.numeric(get(column)))]
  monthly[, source_month := as.character(month)]
  monthly[, target_month := increment_month_string(source_month, delta = 1L)]
  monthly[, log_age := log1p(pmax(age, 0))]
  monthly[, log_contributors := log1p(pmax(contributors, 0))]
  monthly[, log_stars := log1p(pmax(stars, 0))]
  monthly[, log_issues := log1p(pmax(issues, 0))]
  covars <- monthly[, .(
    repo_name,
    dataset_source,
    target_month,
    lag_source_month = source_month,
    log_age,
    ncloc,
    log_contributors,
    log_stars,
    log_issues
  )]
  if (nrow(covars[, .N, by = .(repo_name, dataset_source, target_month)][N > 1L]) > 0L) {
    abortf("Lagged monthly covariates contain duplicate repo/month keys")
  }
  covars
}

args <- parse_cli(commandArgs(trailingOnly = TRUE))
weekly_panel_path <- require_arg(args, "weekly_panel")
monthly_treatment_path <- require_arg(args, "monthly_treatment")
monthly_control_path <- require_arg(args, "monthly_control")
output_dir <- require_arg(args, "output_dir")
calendar_key <- require_arg(args, "calendar_key")
plot_min_event <- as_integer_arg(args, "plot_min_event", -12L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 12L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -12L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", 63L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", 104L)

if (plot_min_event >= -1L) abortf("plot_min_event must include pre-treatment weeks")
if (plot_max_event < 0L) abortf("plot_max_event must include post-treatment weeks")
if (pretrend_max >= -1L) abortf("pretrend_max must be at most -2 because -1 is the omitted reference")
if (pretrend_min > pretrend_max) abortf("Invalid pretrend window")
if (!(confidence_level > 0 && confidence_level < 1)) abortf("confidence_level must be between 0 and 1")

check_packages(c("data.table", "didimputation", "fixest"))
ensure_dir(output_dir)

log_message("INFO", "Reading weekly panel: %s", weekly_panel_path)
weekly_panel <- prepare_weekly_panel(weekly_panel_path, calendar_key)
log_message("INFO", "Reading monthly treatment/control covariates")
covars <- prepare_monthly_covariates(monthly_treatment_path, monthly_control_path)

panel <- merge(
  weekly_panel,
  covars,
  by.x = c("repo_name", "dataset_source", "week_month"),
  by.y = c("repo_name", "dataset_source", "target_month"),
  all.x = TRUE,
  sort = FALSE
)

if (nrow(panel) != nrow(weekly_panel)) abortf("Weekly merge changed row count: before=%d after=%d", nrow(weekly_panel), nrow(panel))
if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("Merged weekly panel has duplicate repo-week keys")

panel[, adjusted_covariates_complete := complete.cases(log_age, ncloc, log_contributors, log_stars, log_issues)]
pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
expected_dynamic_terms <- length(pretrend_values) + length(post_values)

specs <- list(
  list(
    spec_key = "adjusted",
    spec_label = "Adjusted",
    formula = ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index,
    formula_text = "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index",
    use_complete_covariates = TRUE
  ),
  list(
    spec_key = "fe_only",
    spec_label = "FE-only",
    formula = ~ 1 | repo_id + time_index,
    formula_text = "~ 1 | repo_id + time_index",
    use_complete_covariates = FALSE
  )
)

static_tables <- list()
dynamic_tables <- list()
sample_tables <- list()
qc_rows <- list()

for (entry in specs) {
  spec_panel <- if (isTRUE(entry$use_complete_covariates)) panel[adjusted_covariates_complete == TRUE] else data.table::copy(panel)
  spec_panel <- spec_panel[order(repo_id, time_index)]

  treatment_repos <- data.table::uniqueN(spec_panel[treatment_group == 1L, repo_id])
  control_repos <- data.table::uniqueN(spec_panel[treatment_group == 0L, repo_id])
  if (strict && treatment_repos != expected_treatment_repos) {
    abortf("Spec %s expected %d treatment repositories, observed %d", entry$spec_key, expected_treatment_repos, treatment_repos)
  }
  if (strict && control_repos != expected_control_repos) {
    abortf("Spec %s expected %d control repositories, observed %d", entry$spec_key, expected_control_repos, control_repos)
  }

  missing_event_zero <- spec_panel[treatment_group == 1L, .(has_event_zero = any(event_time == 0L)), by = repo_id][has_event_zero == FALSE]
  if (nrow(missing_event_zero) > 0L) {
    abortf("Spec %s lost event-week observations for %d treated repositories", entry$spec_key, nrow(missing_event_zero))
  }
  pre_counts <- spec_panel[treatment_group == 1L, .(pre_weeks = sum(event_time < 0L, na.rm = TRUE)), by = repo_id]
  min_pre_weeks <- min(pre_counts$pre_weeks)
  if (min_pre_weeks < 4L) abortf("Spec %s has a treated repository with fewer than four pre-treatment weeks", entry$spec_key)

  sample_tables[[entry$spec_key]] <- data.table::data.table(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    calendar_key = calendar_key,
    analysis_timezone = unique(spec_panel$analysis_timezone),
    rows = nrow(spec_panel),
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    treated_rows = nrow(spec_panel[absorbing_treated == 1L]),
    untreated_rows = nrow(spec_panel[absorbing_treated == 0L]),
    rows_with_complete_adjusted_covariates = sum(spec_panel$adjusted_covariates_complete),
    minimum_treatment_pre_weeks = min_pre_weeks,
    lagged_covariate_policy = ifelse(entry$use_complete_covariates, "previous_month_for_week_start_month", "not_applicable")
  )

  log_message("INFO", "Running weekly static DiD: %s", entry$spec_label)
  static_capture <- run_did(spec_panel, PRIMARY_OUTCOME, entry$formula)
  if (static_capture$error) abortf("Static DiD failure for %s: %s", entry$spec_key, static_capture$value$message)
  static <- extract_effect_table(static_capture$value, PRIMARY_OUTCOME, confidence_level)[term == "treat"]
  if (nrow(static) != 1L) abortf("Expected one static term for %s, observed %d", entry$spec_key, nrow(static))
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
    treated_observations = nrow(spec_panel[absorbing_treated == 1L]),
    first_stage_observations = nrow(spec_panel[absorbing_treated == 0L]),
    lagged_covariate_policy = ifelse(entry$use_complete_covariates, "previous_month_for_week_start_month", "not_applicable")
  )]
  static_tables[[entry$spec_key]] <- static

  log_message("INFO", "Running weekly dynamic DiD: %s", entry$spec_label)
  dynamic_capture <- run_did(spec_panel, PRIMARY_OUTCOME, entry$formula, horizon = post_values, pretrends = pretrend_values)
  if (dynamic_capture$error) abortf("Dynamic DiD failure for %s: %s", entry$spec_key, dynamic_capture$value$message)
  dynamic <- extract_effect_table(dynamic_capture$value, PRIMARY_OUTCOME, confidence_level)
  dynamic[, event_time := suppressWarnings(as.integer(as.character(term)))]
  dynamic <- dynamic[!is.na(event_time)]
  if (nrow(dynamic) != expected_dynamic_terms) {
    abortf("Expected %d dynamic terms for %s, observed %d", expected_dynamic_terms, entry$spec_key, nrow(dynamic))
  }
  support <- spec_panel[treatment_group == 1L & event_time >= plot_min_event & event_time <= plot_max_event, .(
    support_rows = .N,
    support_repositories = data.table::uniqueN(repo_id)
  ), by = event_time]
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
    ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0,
    lagged_covariate_policy = ifelse(entry$use_complete_covariates, "previous_month_for_week_start_month", "not_applicable")
  )]
  data.table::setorder(dynamic, event_time)
  dynamic_tables[[entry$spec_key]] <- dynamic

  qc_rows[[entry$spec_key]] <- data.table::data.table(
    spec_key = entry$spec_key,
    spec_label = entry$spec_label,
    calendar_key = calendar_key,
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    rows = nrow(spec_panel),
    missing_adjusted_covariate_rows = sum(!spec_panel$adjusted_covariates_complete),
    minimum_treatment_pre_weeks = min_pre_weeks,
    dynamic_terms = nrow(dynamic),
    status = "pass"
  )
}

static_all <- data.table::rbindlist(static_tables, use.names = TRUE, fill = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, use.names = TRUE, fill = TRUE)
sample_all <- data.table::rbindlist(sample_tables, use.names = TRUE, fill = TRUE)
qc_all <- data.table::rbindlist(qc_rows, use.names = TRUE, fill = TRUE)
summary_all <- data.table::data.table(
  section = c("definition", "definition", "definition", "definition", "definition", "definition"),
  metric = c("implementation_version", "calendar_key", "primary_outcome", "plot_window", "pretrend_window", "adjusted_weekly_policy"),
  value = c(
    IMPLEMENTATION_VERSION,
    calendar_key,
    PRIMARY_OUTCOME,
    sprintf("%d:%d", plot_min_event, plot_max_event),
    sprintf("%d:%d", pretrend_min, pretrend_max),
    "For week-start month M, use covariates from month M-1"
  )
)

write_csv(static_all, file.path(output_dir, "velocity_python_added_lines_weekly_v2_static_effects.csv"))
write_csv(dynamic_all, file.path(output_dir, "velocity_python_added_lines_weekly_v2_dynamic_effects.csv"))
write_csv(sample_all, file.path(output_dir, "velocity_python_added_lines_weekly_v2_sample_summary.csv"))
write_csv(qc_all, file.path(output_dir, "velocity_python_added_lines_weekly_v2_qc.csv"))
write_csv(summary_all, file.path(output_dir, "velocity_python_added_lines_weekly_v2_summary.csv"))

log_message("INFO", "Completed weekly velocity v2: static=%d dynamic=%d", nrow(static_all), nrow(dynamic_all))
