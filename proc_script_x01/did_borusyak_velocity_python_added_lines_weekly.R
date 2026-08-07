#!/usr/bin/env Rscript

# Weekly Python velocity timing-resolution robustness analysis.
#
# This script intentionally uses a fixed-effects-only first stage:
#   outcome ~ 1 | repo_id + time_index
#
# The weekly experiment is designed to localize the pre-adoption activity
# pattern at week resolution. It is not a replacement for the monthly primary
# adjusted specification. Two calendar variants are analyzed independently:
# America/New_York (the reconstructed legacy calendar behavior) and
# America/Chicago (the run-x-b02-v4 outcome calendar).

options(stringsAsFactors = FALSE)

IMPLEMENTATION_VERSION <- "v1"
PRIMARY_OUTCOME <- "log_lines_added_py_source"
OUTCOMES <- c(
  "log_lines_added_py_source",
  "log_lines_added_py_no_merge",
  "log_lines_added_py_source_no_tests",
  "log_lines_added_py_all"
)
OUTCOME_LABELS <- c(
  log_lines_added_py_source = "Python Added Lines: Source (Primary)",
  log_lines_added_py_no_merge = "Python Added Lines: No Merge",
  log_lines_added_py_source_no_tests = "Python Added Lines: Source, No Tests",
  log_lines_added_py_all = "Python Added Lines: Broad / All"
)
FIRST_STAGE_FORMULA <- ~ 1 | repo_id + time_index
FIRST_STAGE_TEXT <- "~ 1 | repo_id + time_index"

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

fit_first_stage <- function(panel, outcome) {
  untreated <- panel[absorbing_treated == 0L]
  formula <- stats::as.formula(sprintf("%s %s", outcome, FIRST_STAGE_TEXT))
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
  pred <- capture_evaluation(stats::predict(captured$value, newdata = panel))
  if (pred$error) return(pred)
  captured$predictions <- pred$value
  captured$warnings <- unique(c(captured$warnings, pred$warnings))
  captured$elapsed <- captured$elapsed + pred$elapsed
  captured
}

run_did <- function(panel, outcome, horizon = NULL, pretrends = NULL) {
  capture_evaluation(
    didimputation::did_imputation(
      data = panel,
      yname = outcome,
      gname = "event_index",
      tname = "time_index",
      idname = "repo_id",
      first_stage = FIRST_STAGE_FORMULA,
      horizon = horizon,
      pretrends = pretrends,
      cluster_var = "repo_id"
    )
  )
}

prepare_panel <- function(path, calendar_key, expected_rows, expected_treatment_repos, expected_control_repos, strict) {
  if (!file.exists(path)) abortf("Panel file does not exist: %s", path)
  panel <- data.table::fread(path, showProgress = FALSE)
  required <- c(
    "repo_id", "repo_name", "dataset_source", "treatment_group", "calendar_key",
    "analysis_timezone", "week_start", "time_index", "event_index", "time_to_event",
    "absorbing_treated", OUTCOMES
  )
  validate_columns(panel, required, sprintf("%s weekly panel", calendar_key))
  if (data.table::uniqueN(panel$calendar_key) != 1L || unique(panel$calendar_key) != calendar_key) {
    abortf("Calendar key mismatch for %s panel", calendar_key)
  }
  numeric_cols <- c("repo_id", "treatment_group", "time_index", "event_index", "time_to_event", "absorbing_treated", OUTCOMES)
  for (column in numeric_cols) panel[, (column) := suppressWarnings(as.numeric(get(column)))]
  if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) abortf("%s panel has missing repo/time/event indices", calendar_key)
  panel[, repo_id := as.integer(repo_id)]
  panel[, treatment_group := as.integer(treatment_group)]
  panel[, time_index := as.integer(time_index)]
  panel[, event_index := as.integer(event_index)]
  panel[, absorbing_treated := as.integer(absorbing_treated)]
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L]) > 0L) abortf("%s panel has duplicate repo-week keys", calendar_key)
  if (nrow(panel[treatment_group == 0L & event_index != 0L]) > 0L) abortf("%s controls have nonzero event_index", calendar_key)
  if (nrow(panel[treatment_group == 1L & event_index <= 0L]) > 0L) abortf("%s treatment rows have nonpositive event_index", calendar_key)
  reconstructed <- as.integer(panel$treatment_group == 1L & panel$time_index >= panel$event_index)
  if (sum(reconstructed != panel$absorbing_treated) > 0L) abortf("%s absorbing treatment mismatch", calendar_key)
  treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
  control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])
  if (strict && nrow(panel) != expected_rows) abortf("%s expected %d rows, observed %d", calendar_key, expected_rows, nrow(panel))
  if (strict && treatment_repos != expected_treatment_repos) abortf("%s expected %d treatment repos, observed %d", calendar_key, expected_treatment_repos, treatment_repos)
  if (strict && control_repos != expected_control_repos) abortf("%s expected %d control repos, observed %d", calendar_key, expected_control_repos, control_repos)
  pre_counts <- panel[treatment_group == 1L, .(pre_weeks = sum(time_index < event_index)), by = repo_id]
  if (any(pre_counts$pre_weeks < 4L)) abortf("%s at least one treatment repository has fewer than four untreated weeks", calendar_key)
  panel
}

args <- parse_cli(commandArgs(trailingOnly = TRUE))
new_york_panel_path <- require_arg(args, "new_york_panel")
chicago_panel_path <- require_arg(args, "chicago_panel")
output_dir <- require_arg(args, "output_dir")
plot_min_event <- as_integer_arg(args, "plot_min_event", -12L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 12L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -12L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict <- as_logical_arg(args, "strict_expected_counts", TRUE)
expected_rows <- as_integer_arg(args, "expected_rows", 8599L)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", 63L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", 104L)

if (plot_min_event >= -1L) abortf("plot_min_event must include pre-treatment weeks")
if (plot_max_event < 0L) abortf("plot_max_event must include post-treatment weeks")
if (pretrend_max >= -1L) abortf("pretrend_max must be at most -2 because -1 is the omitted reference")
if (pretrend_min > pretrend_max) abortf("Invalid pretrend window")
if (!(confidence_level > 0 && confidence_level < 1)) abortf("confidence_level must be between 0 and 1")

check_packages(c("data.table", "didimputation", "fixest", "ggplot2"))
ensure_dir(output_dir)
plot_dir <- file.path(output_dir, "plots")
ensure_dir(plot_dir)

calendar_inputs <- list(
  new_york = list(path = new_york_panel_path, label = "America/New_York"),
  chicago = list(path = chicago_panel_path, label = "America/Chicago")
)
pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
key_window_values <- c(-4L, -3L, -2L, 0L, 1L, 2L, 3L, 4L)

static_tables <- list()
dynamic_tables <- list()
pretrend_tables <- list()
diagnostic_tables <- list()
support_tables <- list()
sample_tables <- list()

for (calendar_key in names(calendar_inputs)) {
  calendar_info <- calendar_inputs[[calendar_key]]
  log_message("INFO", "Reading %s weekly panel: %s", calendar_key, calendar_info$path)
  panel <- prepare_panel(
    calendar_info$path,
    calendar_key,
    expected_rows,
    expected_treatment_repos,
    expected_control_repos,
    strict
  )
  panel[, event_time := data.table::fifelse(treatment_group == 1L, time_index - event_index, NA_integer_)]
  treatment_repos <- data.table::uniqueN(panel[treatment_group == 1L, repo_id])
  control_repos <- data.table::uniqueN(panel[treatment_group == 0L, repo_id])
  untreated_rows <- nrow(panel[absorbing_treated == 0L])
  treated_rows <- nrow(panel[absorbing_treated == 1L])
  support <- panel[treatment_group == 1L & event_time >= plot_min_event & event_time <= plot_max_event, .(
    support_rows = .N,
    support_repositories = data.table::uniqueN(repo_id)
  ), by = event_time]
  support[, `:=`(calendar_key = calendar_key, analysis_timezone = calendar_info$label)]
  data.table::setorder(support, event_time)
  support_tables[[calendar_key]] <- support
  sample_tables[[calendar_key]] <- data.table::data.table(
    calendar_key = calendar_key,
    analysis_timezone = calendar_info$label,
    rows = nrow(panel),
    repositories = data.table::uniqueN(panel$repo_id),
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    untreated_first_stage_rows = untreated_rows,
    treated_rows = treated_rows,
    minimum_treatment_pre_weeks = min(panel[treatment_group == 1L, .(pre_weeks = sum(time_index < event_index)), by = repo_id]$pre_weeks)
  )

  for (outcome in OUTCOMES) {
    outcome_label <- unname(OUTCOME_LABELS[[outcome]])
    log_message("INFO", "Fitting first stage calendar=%s outcome=%s", calendar_key, outcome)
    first_stage <- fit_first_stage(panel, outcome)
    if (first_stage$error) abortf("First-stage failure calendar=%s outcome=%s: %s", calendar_key, outcome, first_stage$value$message)
    prediction_na_treated <- sum(is.na(first_stage$predictions[panel$absorbing_treated == 1L]))
    if (prediction_na_treated > 0L) abortf("First-stage predictions missing for %d treated rows calendar=%s outcome=%s", prediction_na_treated, calendar_key, outcome)
    diagnostic_tables[[paste(calendar_key, outcome, "first_stage", sep = "|")]] <- data.table::data.table(
      calendar_key = calendar_key,
      analysis_timezone = calendar_info$label,
      outcome = outcome,
      model_type = "first_stage",
      status = "success",
      runtime_seconds = first_stage$elapsed,
      warning_count = length(first_stage$warnings),
      warning_messages = paste(first_stage$warnings, collapse = " | "),
      prediction_na_treated = prediction_na_treated,
      first_stage_formula = FIRST_STAGE_TEXT
    )

    log_message("INFO", "Running static did_imputation calendar=%s outcome=%s", calendar_key, outcome)
    static_capture <- run_did(panel, outcome)
    if (static_capture$error) abortf("Static DiD failure calendar=%s outcome=%s: %s", calendar_key, outcome, static_capture$value$message)
    static <- extract_effect_table(static_capture$value, outcome, confidence_level)[term == "treat"]
    if (nrow(static) != 1L) abortf("Expected one static treatment term calendar=%s outcome=%s, observed=%d", calendar_key, outcome, nrow(static))
    static[, `:=`(
      calendar_key = calendar_key,
      analysis_timezone = calendar_info$label,
      outcome_label = outcome_label,
      outcome_role = ifelse(outcome == PRIMARY_OUTCOME, "primary", "robustness"),
      first_stage_formula = FIRST_STAGE_TEXT,
      treatment_repositories = treatment_repos,
      control_repositories = control_repos,
      treated_observations = treated_rows,
      untreated_first_stage_observations = untreated_rows
    )]
    static_tables[[paste(calendar_key, outcome, sep = "|")]] <- static

    log_message("INFO", "Running weekly dynamic did_imputation calendar=%s outcome=%s", calendar_key, outcome)
    dynamic_capture <- run_did(panel, outcome, horizon = post_values, pretrends = pretrend_values)
    if (dynamic_capture$error) abortf("Dynamic DiD failure calendar=%s outcome=%s: %s", calendar_key, outcome, dynamic_capture$value$message)
    dynamic <- extract_effect_table(dynamic_capture$value, outcome, confidence_level)
    dynamic[, event_time := suppressWarnings(as.integer(as.character(term)))]
    dynamic <- dynamic[!is.na(event_time)]
    expected_terms <- length(pretrend_values) + length(post_values)
    if (nrow(dynamic) != expected_terms) abortf("Expected %d dynamic terms calendar=%s outcome=%s, observed=%d", expected_terms, calendar_key, outcome, nrow(dynamic))
    dynamic[, term_type := data.table::fcase(
      event_time %in% pretrend_values, "placebo_pretrend",
      event_time >= 0L, "post_treatment",
      default = "other"
    )]
    dynamic <- merge(dynamic, support, by = "event_time", all.x = TRUE, sort = FALSE)
    dynamic[, `:=`(
      calendar_key = calendar_key,
      analysis_timezone = calendar_info$label,
      outcome_label = outcome_label,
      outcome_role = ifelse(outcome == PRIMARY_OUTCOME, "primary", "robustness"),
      first_stage_formula = FIRST_STAGE_TEXT,
      ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0
    )]
    data.table::setorder(dynamic, event_time)
    dynamic_tables[[paste(calendar_key, outcome, sep = "|")]] <- dynamic

    pre <- data.table::copy(dynamic[term_type == "placebo_pretrend"])
    if (nrow(pre) != length(pretrend_values)) abortf("Pretrend term count mismatch calendar=%s outcome=%s", calendar_key, outcome)
    pre[, all_ci_include_zero := all(ci_includes_zero), by = .(calendar_key, outcome)]
    pretrend_tables[[paste(calendar_key, outcome, sep = "|")]] <- pre

    diagnostic_tables[[paste(calendar_key, outcome, "static", sep = "|")]] <- data.table::data.table(
      calendar_key = calendar_key,
      analysis_timezone = calendar_info$label,
      outcome = outcome,
      model_type = "static",
      status = "success",
      runtime_seconds = static_capture$elapsed,
      warning_count = length(static_capture$warnings),
      warning_messages = paste(static_capture$warnings, collapse = " | "),
      prediction_na_treated = NA_integer_,
      first_stage_formula = FIRST_STAGE_TEXT
    )
    diagnostic_tables[[paste(calendar_key, outcome, "dynamic", sep = "|")]] <- data.table::data.table(
      calendar_key = calendar_key,
      analysis_timezone = calendar_info$label,
      outcome = outcome,
      model_type = "dynamic",
      status = "success",
      runtime_seconds = dynamic_capture$elapsed,
      warning_count = length(dynamic_capture$warnings),
      warning_messages = paste(dynamic_capture$warnings, collapse = " | "),
      prediction_na_treated = NA_integer_,
      first_stage_formula = FIRST_STAGE_TEXT
    )
  }
}

static_all <- data.table::rbindlist(static_tables, use.names = TRUE, fill = TRUE)
dynamic_all <- data.table::rbindlist(dynamic_tables, use.names = TRUE, fill = TRUE)
pretrend_all <- data.table::rbindlist(pretrend_tables, use.names = TRUE, fill = TRUE)
diagnostics_all <- data.table::rbindlist(diagnostic_tables, use.names = TRUE, fill = TRUE)
support_all <- data.table::rbindlist(support_tables, use.names = TRUE, fill = TRUE)
sample_all <- data.table::rbindlist(sample_tables, use.names = TRUE, fill = TRUE)

pretrend_summary <- pretrend_all[, .(
  all_ci_include_zero = all(ci_includes_zero),
  periods_excluding_zero = paste(event_time[!ci_includes_zero], collapse = "|"),
  minimum_p_value = ifelse(all(is.na(p_value)), NA_real_, min(p_value, na.rm = TRUE)),
  significant_placebo_terms = sum(significant, na.rm = TRUE)
), by = .(calendar_key, analysis_timezone, outcome, outcome_label, outcome_role)]

primary_key <- dynamic_all[
  outcome == PRIMARY_OUTCOME & event_time %in% key_window_values,
  .(calendar_key, analysis_timezone, outcome, outcome_label, event_time, term_type,
    estimate, std.error, conf.low, conf.high, p_value, significant,
    exp_coefficient_change_pct, support_rows, support_repositories)
]
data.table::setorder(primary_key, calendar_key, event_time)

static_compare <- merge(
  static_all[calendar_key == "new_york", .(outcome, estimate_new_york = estimate, se_new_york = std.error, p_new_york = p_value)],
  static_all[calendar_key == "chicago", .(outcome, estimate_chicago = estimate, se_chicago = std.error, p_chicago = p_value)],
  by = "outcome",
  all = TRUE
)
static_compare[, estimate_difference_new_york_minus_chicago := estimate_new_york - estimate_chicago]

dynamic_compare <- merge(
  dynamic_all[calendar_key == "new_york", .(outcome, event_time, estimate_new_york = estimate, se_new_york = std.error, p_new_york = p_value)],
  dynamic_all[calendar_key == "chicago", .(outcome, event_time, estimate_chicago = estimate, se_chicago = std.error, p_chicago = p_value)],
  by = c("outcome", "event_time"),
  all = TRUE
)
dynamic_compare[, estimate_difference_new_york_minus_chicago := estimate_new_york - estimate_chicago]

qc <- data.table::data.table(
  check_name = c(
    "static_rows",
    "dynamic_rows",
    "pretrend_rows",
    "pretrend_summary_rows",
    "primary_key_rows",
    "diagnostic_rows",
    "calendar_static_comparison_rows",
    "calendar_dynamic_comparison_rows"
  ),
  observed = c(
    nrow(static_all),
    nrow(dynamic_all),
    nrow(pretrend_all),
    nrow(pretrend_summary),
    nrow(primary_key),
    nrow(diagnostics_all),
    nrow(static_compare),
    nrow(dynamic_compare)
  ),
  expected = c(
    8L,
    2L * length(OUTCOMES) * (length(pretrend_values) + length(post_values)),
    2L * length(OUTCOMES) * length(pretrend_values),
    8L,
    2L * length(key_window_values),
    2L * length(OUTCOMES) * 3L,
    4L,
    length(OUTCOMES) * (length(pretrend_values) + length(post_values))
  )
)
qc[, status := ifelse(observed == expected, "pass", "fail")]
qc[, note := c(
  "Two calendars x four outcomes.",
  "Package-native placebo and post-treatment weekly terms.",
  "Weekly placebo terms only; event -1 is the omitted reference.",
  "One pretrend summary per calendar/outcome.",
  "Primary outcome at weeks -4,-3,-2,0,+1,+2,+3,+4 for both calendars.",
  "First-stage, static, and dynamic diagnostics for each calendar/outcome.",
  "One static New York minus Chicago comparison per outcome.",
  "One dynamic New York minus Chicago comparison per outcome/event term."
)]
if (strict && any(qc$status == "fail")) {
  failed <- qc[status == "fail"]
  abortf("Weekly result QC failed: %s", paste(sprintf("%s observed=%d expected=%d", failed$check_name, failed$observed, failed$expected), collapse = "; "))
}

write_csv(static_all, file.path(output_dir, "velocity_python_added_lines_weekly_static_effects.csv"))
write_csv(dynamic_all, file.path(output_dir, "velocity_python_added_lines_weekly_dynamic_effects.csv"))
write_csv(pretrend_all, file.path(output_dir, "velocity_python_added_lines_weekly_pretrend_checks.csv"))
write_csv(pretrend_summary, file.path(output_dir, "velocity_python_added_lines_weekly_pretrend_summary.csv"))
write_csv(primary_key, file.path(output_dir, "velocity_python_added_lines_weekly_primary_key_window.csv"))
write_csv(static_compare, file.path(output_dir, "velocity_python_added_lines_weekly_calendar_static_differences.csv"))
write_csv(dynamic_compare, file.path(output_dir, "velocity_python_added_lines_weekly_calendar_dynamic_differences.csv"))
write_csv(support_all, file.path(output_dir, "velocity_python_added_lines_weekly_event_support.csv"))
write_csv(sample_all, file.path(output_dir, "velocity_python_added_lines_weekly_sample_summary.csv"))
write_csv(diagnostics_all, file.path(output_dir, "velocity_python_added_lines_weekly_diagnostics.csv"))
write_csv(qc, file.path(output_dir, "velocity_python_added_lines_weekly_qc.csv"))

primary_plot <- dynamic_all[outcome == PRIMARY_OUTCOME & event_time >= plot_min_event & event_time <= plot_max_event]
plot <- ggplot2::ggplot(
  primary_plot,
  ggplot2::aes(x = event_time, y = estimate, group = calendar_key, linetype = calendar_key)
) +
  ggplot2::geom_hline(yintercept = 0, linewidth = 0.4) +
  ggplot2::geom_vline(xintercept = -0.5, linetype = "dashed", linewidth = 0.4) +
  ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.15, position = ggplot2::position_dodge(width = 0.22)) +
  ggplot2::geom_point(position = ggplot2::position_dodge(width = 0.22), size = 1.8) +
  ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.22), linewidth = 0.5) +
  ggplot2::scale_x_continuous(breaks = seq.int(plot_min_event, plot_max_event, by = 2L)) +
  ggplot2::labs(
    title = "Weekly Python Added Lines Around First Observable Cursor Evidence",
    subtitle = "FE-only Borusyak DiD; event -1 is the omitted reference",
    x = "Weeks relative to first observable Cursor-related commit",
    y = "Effect on log(1 + Python source lines added)",
    linetype = "Calendar"
  ) +
  ggplot2::theme_minimal(base_size = 10)
plot_path <- file.path(plot_dir, "velocity_python_added_lines_weekly_primary_dynamic_effects.pdf")
ggplot2::ggsave(plot_path, plot = plot, width = 8.5, height = 5.2, units = "in")
log_message("INFO", "Wrote plot to %s", plot_path)

summary <- data.table::data.table(
  section = c(
    "definition", "definition", "definition", "definition", "definition",
    "sample", "sample", "sample", "window", "window", "output"
  ),
  metric = c(
    "implementation_version", "primary_outcome", "first_stage", "week_definition", "calendar_variants",
    "weekly_rows_per_calendar", "treatment_repositories", "control_repositories",
    "dynamic_window", "pretrend_window", "static_models"
  ),
  value = c(
    IMPLEMENTATION_VERSION, PRIMARY_OUTCOME, FIRST_STAGE_TEXT, "Monday-start weeks", "America/New_York | America/Chicago",
    as.character(expected_rows), as.character(expected_treatment_repos), as.character(expected_control_repos),
    sprintf("%d:%d", plot_min_event, plot_max_event), sprintf("%d:%d", pretrend_min, pretrend_max), as.character(nrow(static_all))
  ),
  note = c(
    "", "", "FE-only timing diagnostic; no weekly NCLOC or other contemporaneous covariates.",
    "", "Both outcome and treatment week are defined within each calendar variant.",
    "", "", "", "", "Event -1 omitted.", "Two calendars x four outcome definitions."
  )
)
write_csv(summary, file.path(output_dir, "velocity_python_added_lines_weekly_summary.csv"))

log_message(
  "INFO",
  "Completed run-x-b03-d weekly DiD: static=%d; dynamic=%d; pretrend=%d; primary_key=%d",
  nrow(static_all), nrow(dynamic_all), nrow(pretrend_all), nrow(primary_key)
)
