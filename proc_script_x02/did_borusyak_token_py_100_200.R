#!/usr/bin/env Rscript

# Borusyak et al. DiD for the D02 Python function-body token panel.
#
# Input:
#   A repo-month panel containing log_token_py_100_200 and Model A controls.
#
# Outputs:
#   Static ATT, dynamic event-study effects, individual and joint pretrend
#   checks, support tables, diagnostics, QC, plots, and serialized models.
#
# Treatment timing uses event_index and time_index. Legacy monthly Cursor
# flags are retained only for audit and never define treatment in the model.

suppressPackageStartupMessages({
  library(data.table)
  library(didimputation)
  library(fixest)
  library(ggplot2)
})

options(stringsAsFactors = FALSE)

parse_args <- function(args) {
  out <- list()
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop("Unexpected argument: ", key)
    if (i == length(args)) stop("Missing value for argument: ", key)
    out[[substring(key, 3L)]] <- args[[i + 1L]]
    i <- i + 2L
  }
  out
}

required_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || identical(value, "")) stop("Missing required argument --", name)
  value
}

as_int_arg <- function(args, name) as.integer(required_arg(args, name))
as_num_arg <- function(args, name) as.numeric(required_arg(args, name))
as_bool_arg <- function(args, name) {
  value <- required_arg(args, name)
  if (!value %in% c("0", "1")) stop("--", name, " must be 0 or 1")
  identical(value, "1")
}

log_info <- function(...) {
  cat(format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "[INFO]", ..., "\n")
}

ensure_parent <- function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
write_csv <- function(x, path) {
  ensure_parent(path)
  fwrite(x, path, na = "")
  log_info("Wrote", nrow(x), "rows to", path)
}

safe_num <- function(x) suppressWarnings(as.numeric(x))
percent <- function(x) 100 * (exp(x) - 1)

add_qc <- function(qc, check_name, observed, expected, pass, note = "") {
  rbind(
    qc,
    data.table(
      check_name = check_name,
      status = if (isTRUE(pass)) "pass" else "fail",
      observed = paste(observed, collapse = ","),
      expected = paste(expected, collapse = ","),
      note = note
    ),
    fill = TRUE
  )
}

extract_result <- function(model, outcome, model_type, confidence_level) {
  result <- as.data.table(model)
  if (!"term" %in% names(result)) stop("did_imputation output has no term column")
  required <- c("estimate", "std.error", "conf.low", "conf.high")
  missing <- setdiff(required, names(result))
  if (length(missing)) stop("did_imputation output missing columns: ", paste(missing, collapse = ", "))
  if (!"p.value" %in% names(result)) {
    result[, p.value := 2 * pnorm(abs(estimate / std.error), lower.tail = FALSE)]
  }
  result[, `:=`(
    outcome = outcome,
    model_type = model_type,
    confidence_level = confidence_level,
    percent_change = percent(estimate),
    percent_ci_low = percent(conf.low),
    percent_ci_high = percent(conf.high),
    significant_05 = !is.na(p.value) & p.value < 0.05
  )]
  setnames(result,
    old = c("std.error", "conf.low", "conf.high", "p.value"),
    new = c("std_error", "conf_low", "conf_high", "p_value")
  )
  result
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
input_file <- required_arg(args, "input-file")
static_output <- required_arg(args, "static-output")
dynamic_output <- required_arg(args, "dynamic-output")
pretrend_output <- required_arg(args, "pretrend-output")
pretrend_joint_output <- required_arg(args, "pretrend-joint-output")
event_support_output <- required_arg(args, "event-support-output")
cohort_support_output <- required_arg(args, "cohort-support-output")
sample_summary_output <- required_arg(args, "sample-summary-output")
legacy_audit_output <- required_arg(args, "legacy-audit-output")
model_diagnostics_output <- required_arg(args, "model-diagnostics-output")
qc_output <- required_arg(args, "qc-output")
static_model_rds <- required_arg(args, "static-model-rds")
dynamic_model_rds <- required_arg(args, "dynamic-model-rds")
pretrend_model_rds <- required_arg(args, "pretrend-model-rds")
session_info_output <- required_arg(args, "session-info-output")
dynamic_pdf <- required_arg(args, "dynamic-pdf")
dynamic_png <- required_arg(args, "dynamic-png")
summary_output <- required_arg(args, "summary-output")

horizon_min <- as_int_arg(args, "horizon-min")
horizon_max <- as_int_arg(args, "horizon-max")
pretrend_min <- as_int_arg(args, "pretrend-min")
pretrend_max <- as_int_arg(args, "pretrend-max")
reference_event_time <- as_int_arg(args, "reference-event-time")
confidence_level <- as_num_arg(args, "confidence-level")
strict_expected <- as_bool_arg(args, "strict-expected-counts")
random_seed <- as_int_arg(args, "random-seed")

expected <- list(
  rows = as_int_arg(args, "expected-rows"),
  repositories = as_int_arg(args, "expected-repositories"),
  treatment_repositories = as_int_arg(args, "expected-treatment-repositories"),
  control_repositories = as_int_arg(args, "expected-control-repositories"),
  treatment_rows = as_int_arg(args, "expected-treatment-rows"),
  control_rows = as_int_arg(args, "expected-control-rows"),
  untreated_rows = as_int_arg(args, "expected-untreated-rows"),
  treated_rows = as_int_arg(args, "expected-treated-rows"),
  dynamic_treated_rows = as_int_arg(args, "expected-dynamic-treated-rows"),
  static_rows = as_int_arg(args, "expected-static-rows"),
  dynamic_rows = as_int_arg(args, "expected-dynamic-rows"),
  pretrend_rows = as_int_arg(args, "expected-pretrend-rows"),
  explicit_exclusions = as_int_arg(args, "expected-explicit-exclusions")
)

if (horizon_min > horizon_max) stop("Invalid horizon range")
if (pretrend_min > pretrend_max || pretrend_max >= 0) stop("Invalid pretrend range")
if (reference_event_time >= pretrend_min && reference_event_time <= pretrend_max) {
  stop("Reference event time must not be inside the requested pretrend range")
}
if (!file.exists(input_file)) stop("Input file not found: ", input_file)

set.seed(random_seed)
log_info("Reading D02 panel:", normalizePath(input_file))
dt <- fread(input_file)

required_columns <- c(
  "repo_id", "repo_name", "dataset_source", "treatment_group",
  "time", "time_index", "event", "event_index", "time_to_event",
  "log_token_py_100_200", "token_py_100_200",
  "log_age", "ncloc", "log_contributors", "log_stars", "log_issues",
  "model_d_token_complete", "token_py_100_200_explicitly_excluded"
)
missing_columns <- setdiff(required_columns, names(dt))
if (length(missing_columns)) stop("Input is missing required columns: ", paste(missing_columns, collapse = ", "))

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "log_token_py_100_200", "token_py_100_200", "log_age", "ncloc",
  "log_contributors", "log_stars", "log_issues", "model_d_token_complete"
)
for (column in numeric_columns) set(dt, j = column, value = safe_num(dt[[column]]))

# Normalize treatment timing independently from legacy monthly usage flags.
dt[, normalized_event_time := fifelse(treatment_group == 1, time_index - event_index, NA_real_)]
dt[, absorbing_treated := as.integer(treatment_group == 1 & event_index > 0 & time_index >= event_index)]
dt[, untreated_first_stage := absorbing_treated == 0]

model_columns <- c(
  "repo_id", "time_index", "event_index", "log_token_py_100_200",
  "log_age", "ncloc", "log_contributors", "log_stars", "log_issues"
)
missing_model_rows <- dt[, sum(!complete.cases(.SD)), .SDcols = model_columns]
duplicate_rows <- dt[, .N, by = .(repo_id, time_index)][N > 1, sum(N - 1L)]
if (length(duplicate_rows) == 0L || is.na(duplicate_rows)) duplicate_rows <- 0L
normalized_timing_errors <- dt[treatment_group == 1, sum(normalized_event_time != time_to_event, na.rm = TRUE)]
control_event_errors <- dt[treatment_group == 0, sum(event_index != 0, na.rm = TRUE)]
treatment_event_errors <- dt[treatment_group == 1, sum(event_index <= 0 | is.na(event_index))]
negative_metric_rows <- dt[token_py_100_200 < 0, .N]
incomplete_token_rows <- dt[model_d_token_complete != 1, .N]

# Legacy monthly flags are audit evidence only.
legacy_cols <- intersect(c("is_treatment", "post_event", "cursor_flag", "cursor"), names(dt))
legacy_audit <- copy(dt[0])
if (length(legacy_cols)) {
  legacy_mismatch <- rep(FALSE, nrow(dt))
  for (column in legacy_cols) {
    values <- dt[[column]]
    if (is.logical(values)) values <- as.integer(values)
    values <- suppressWarnings(as.integer(as.character(values)))
    legacy_mismatch <- legacy_mismatch | (!is.na(values) & values != dt$absorbing_treated)
  }
  legacy_audit <- dt[legacy_mismatch, c(
    "repo_id", "repo_name", "dataset_source", "time", "time_index",
    "event", "event_index", "time_to_event", "normalized_event_time",
    "absorbing_treated", legacy_cols
  ), with = FALSE]
}
write_csv(legacy_audit, legacy_audit_output)

# Event and cohort support are descriptive and do not truncate the model panel.
event_support <- dt[treatment_group == 1, .(
  support_rows = .N,
  support_repositories = uniqueN(repo_id)
), by = .(event_time = as.integer(normalized_event_time))][order(event_time)]
write_csv(event_support, event_support_output)

cohort_support <- dt[treatment_group == 1, .(
  treatment_repositories = uniqueN(repo_id),
  total_rows = .N,
  pre_treatment_rows = sum(normalized_event_time < 0),
  post_treatment_rows = sum(normalized_event_time >= 0),
  dynamic_post_rows = sum(normalized_event_time >= 0 & normalized_event_time <= horizon_max),
  maximum_post_horizon = max(normalized_event_time, na.rm = TRUE)
), by = .(event, event_index)][order(event_index)]
write_csv(cohort_support, cohort_support_output)

sample_counts <- list(
  rows = nrow(dt),
  repositories = uniqueN(dt$repo_id),
  treatment_repositories = dt[treatment_group == 1, uniqueN(repo_id)],
  control_repositories = dt[treatment_group == 0, uniqueN(repo_id)],
  treatment_rows = dt[treatment_group == 1, .N],
  control_rows = dt[treatment_group == 0, .N],
  untreated_rows = dt[untreated_first_stage == TRUE, .N],
  treated_rows = dt[absorbing_treated == 1, .N],
  dynamic_treated_rows = dt[absorbing_treated == 1 & normalized_event_time >= 0 & normalized_event_time <= horizon_max, .N]
)

sample_summary <- rbindlist(list(
  data.table(section = "input", metric = names(sample_counts), value = unlist(sample_counts), note = ""),
  data.table(section = "definition", metric = c(
    "outcome", "first_stage", "dynamic_horizon", "pretrend_window", "reference_event_time"
  ), value = c(
    "log_token_py_100_200",
    "log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index",
    paste0(horizon_min, ":", horizon_max),
    paste0(pretrend_min, ":", pretrend_max),
    reference_event_time
  ), note = "")
), fill = TRUE)
write_csv(sample_summary, sample_summary_output)

qc <- data.table(check_name = character(), status = character(), observed = character(), expected = character(), note = character())
qc <- add_qc(qc, "input_rows", nrow(dt), expected$rows, nrow(dt) == expected$rows)
qc <- add_qc(qc, "repositories", uniqueN(dt$repo_id), expected$repositories, uniqueN(dt$repo_id) == expected$repositories)
qc <- add_qc(qc, "treatment_repositories", sample_counts$treatment_repositories, expected$treatment_repositories, sample_counts$treatment_repositories == expected$treatment_repositories)
qc <- add_qc(qc, "control_repositories", sample_counts$control_repositories, expected$control_repositories, sample_counts$control_repositories == expected$control_repositories)
qc <- add_qc(qc, "treatment_rows", sample_counts$treatment_rows, expected$treatment_rows, sample_counts$treatment_rows == expected$treatment_rows)
qc <- add_qc(qc, "control_rows", sample_counts$control_rows, expected$control_rows, sample_counts$control_rows == expected$control_rows)
qc <- add_qc(qc, "untreated_first_stage_rows", sample_counts$untreated_rows, expected$untreated_rows, sample_counts$untreated_rows == expected$untreated_rows)
qc <- add_qc(qc, "treated_static_rows", sample_counts$treated_rows, expected$treated_rows, sample_counts$treated_rows == expected$treated_rows)
qc <- add_qc(qc, "treated_dynamic_rows", sample_counts$dynamic_treated_rows, expected$dynamic_treated_rows, sample_counts$dynamic_treated_rows == expected$dynamic_treated_rows)
qc <- add_qc(qc, "duplicate_repo_time_rows", duplicate_rows, 0, duplicate_rows == 0)
qc <- add_qc(qc, "missing_model_rows", missing_model_rows, 0, missing_model_rows == 0)
qc <- add_qc(qc, "normalized_timing_errors", normalized_timing_errors, 0, normalized_timing_errors == 0)
qc <- add_qc(qc, "control_event_errors", control_event_errors, 0, control_event_errors == 0)
qc <- add_qc(qc, "treatment_event_errors", treatment_event_errors, 0, treatment_event_errors == 0)
qc <- add_qc(qc, "negative_token_metric_rows", negative_metric_rows, 0, negative_metric_rows == 0)
qc <- add_qc(qc, "incomplete_token_rows_in_usable_panel", incomplete_token_rows, 0, incomplete_token_rows == 0)
qc <- add_qc(qc, "explicit_exclusion_provenance", expected$explicit_exclusions, expected$explicit_exclusions, TRUE,
  "The one D01b explicit exclusion was removed by D02; this expected count is provenance, not an input-row count.")

if (strict_expected && any(qc$status == "fail")) {
  write_csv(qc, qc_output)
  stop("Input validation failed under strict expected-count mode")
}

first_stage_formula <- ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index
outcome <- "log_token_py_100_200"
model_diagnostics <- data.table()

fit_with_diagnostics <- function(label, expression) {
  warnings <- character()
  started <- proc.time()[[3L]]
  value <- withCallingHandlers(
    tryCatch(expression, error = function(e) e),
    warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }
  )
  elapsed <- proc.time()[[3L]] - started
  if (inherits(value, "error")) {
    model_diagnostics <<- rbind(model_diagnostics, data.table(
      model = label, status = "failed", runtime_seconds = elapsed,
      warning_count = length(warnings), warnings = paste(unique(warnings), collapse = " | "),
      error_message = conditionMessage(value)
    ), fill = TRUE)
    stop(label, " failed: ", conditionMessage(value))
  }
  model_diagnostics <<- rbind(model_diagnostics, data.table(
    model = label, status = "success", runtime_seconds = elapsed,
    warning_count = length(warnings), warnings = paste(unique(warnings), collapse = " | "),
    error_message = ""
  ), fill = TRUE)
  value
}

log_info("Fitting first-stage diagnostic")
first_stage_model <- fit_with_diagnostics("first_stage_diagnostic", feols(
  log_token_py_100_200 ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index,
  data = dt[untreated_first_stage == TRUE],
  cluster = ~repo_id,
  warn = TRUE,
  notes = FALSE
))

log_info("Running static did_imputation")
static_model <- fit_with_diagnostics("static_did_imputation", did_imputation(
  data = as.data.frame(dt),
  yname = outcome,
  gname = "event_index",
  tname = "time_index",
  idname = "repo_id",
  first_stage = first_stage_formula,
  cluster_var = "repo_id"
))

log_info("Running dynamic did_imputation")
dynamic_model <- fit_with_diagnostics("dynamic_did_imputation", did_imputation(
  data = as.data.frame(dt),
  yname = outcome,
  gname = "event_index",
  tname = "time_index",
  idname = "repo_id",
  first_stage = first_stage_formula,
  cluster_var = "repo_id",
  horizon = horizon_min:horizon_max,
  pretrends = pretrend_min:pretrend_max
))

static_result <- extract_result(static_model, outcome, "static", confidence_level)
static_result <- static_result[term == "treat"]
static_result[, `:=`(
  treated_observations = sample_counts$treated_rows,
  first_stage_observations = sample_counts$untreated_rows,
  treatment_repositories = sample_counts$treatment_repositories,
  control_repositories = sample_counts$control_repositories
)]
write_csv(static_result, static_output)

dynamic_result <- extract_result(dynamic_model, outcome, "dynamic", confidence_level)
dynamic_result <- dynamic_result[term != "treat"]
dynamic_result[, event_time := as.integer(as.character(term))]
dynamic_result <- dynamic_result[event_time >= horizon_min & event_time <= horizon_max & event_time != reference_event_time]
dynamic_result[, term_type := fifelse(event_time < reference_event_time, "placebo", "post_treatment")]
dynamic_result[, estimated := 1L]
dynamic_result <- merge(dynamic_result, event_support, by = "event_time", all.x = TRUE, sort = TRUE)
setcolorder(dynamic_result, c(
  "outcome", "event_time", "term_type", "estimated", "estimate", "std_error",
  "conf_low", "conf_high", "p_value", "percent_change", "percent_ci_low",
  "percent_ci_high", "support_rows", "support_repositories", "significant_05"
))
write_csv(dynamic_result, dynamic_output)

pretrend_result <- dynamic_result[event_time >= pretrend_min & event_time <= pretrend_max]
pretrend_result[, ci_includes_zero := conf_low <= 0 & conf_high >= 0]
write_csv(pretrend_result, pretrend_output)

# Independent pretrend regression and joint Wald test on untreated observations.
pretrend_periods <- pretrend_min:pretrend_max
pretrend_terms <- paste0("pre_m", abs(pretrend_periods))
for (j in seq_along(pretrend_periods)) {
  h <- pretrend_periods[[j]]
  dt[, (pretrend_terms[[j]]) := as.integer(treatment_group == 1 & normalized_event_time == h)]
}
pretrend_formula <- as.formula(paste0(
  outcome, " ~ ", paste(c(pretrend_terms, "log_age", "ncloc", "log_contributors", "log_stars", "log_issues"), collapse = " + "),
  " | repo_id + time_index"
))
log_info("Running independent pretrend regression")
pretrend_model <- fit_with_diagnostics("pretrend_joint_fixest", feols(
  pretrend_formula,
  data = dt[untreated_first_stage == TRUE],
  cluster = ~repo_id,
  warn = TRUE,
  notes = FALSE
))
wald_result <- wald(pretrend_model, keep = paste(pretrend_terms, collapse = "|"), print = FALSE)
wald_stat <- if (!is.null(wald_result$stat)) wald_result$stat else NA_real_
wald_p <- if (!is.null(wald_result$p)) wald_result$p else NA_real_
wald_df1 <- if (!is.null(wald_result$df1)) wald_result$df1 else length(pretrend_terms)
wald_df2 <- if (!is.null(wald_result$df2)) wald_result$df2 else NA_real_
pretrend_joint <- data.table(
  outcome = outcome,
  placebo_periods = paste(pretrend_periods, collapse = ","),
  statistic = as.numeric(wald_stat),
  df_num = as.numeric(wald_df1),
  df_denom = as.numeric(wald_df2),
  p_value = as.numeric(wald_p),
  passes_05 = !is.na(wald_p) & wald_p >= 0.05
)
write_csv(pretrend_joint, pretrend_joint_output)

write_csv(model_diagnostics, model_diagnostics_output)
ensure_parent(static_model_rds); saveRDS(static_model, static_model_rds)
ensure_parent(dynamic_model_rds); saveRDS(dynamic_model, dynamic_model_rds)
ensure_parent(pretrend_model_rds); saveRDS(pretrend_model, pretrend_model_rds)
ensure_parent(session_info_output); capture.output(sessionInfo(), file = session_info_output)

# Plot includes an explicit, non-estimated reference row at event time -1.
reference_row <- data.table(
  outcome = outcome, event_time = reference_event_time, term_type = "reference",
  estimated = 0L, estimate = 0, std_error = NA_real_, conf_low = NA_real_,
  conf_high = NA_real_, p_value = NA_real_, percent_change = 0,
  percent_ci_low = NA_real_, percent_ci_high = NA_real_, support_rows = event_support[event_time == reference_event_time, support_rows],
  support_repositories = event_support[event_time == reference_event_time, support_repositories], significant_05 = FALSE
)
plot_dt <- rbind(dynamic_result, reference_row, fill = TRUE)[order(event_time)]
plot_object <- ggplot(plot_dt, aes(x = event_time, y = estimate)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.4) +
  geom_vline(xintercept = -0.5, linetype = "dotted", linewidth = 0.4) +
  geom_errorbar(data = plot_dt[estimated == 1], aes(ymin = conf_low, ymax = conf_high), width = 0.16) +
  geom_point(aes(shape = term_type, fill = significant_05), size = 2.6) +
  scale_x_continuous(breaks = horizon_min:horizon_max) +
  labs(
    title = "Cursor adoption and Python 100-200-token function-body stock",
    subtitle = paste0("Borusyak DiD; event -1 is the omitted reference; joint pretrend p = ", signif(wald_p, 3)),
    x = "Months relative to adoption",
    y = "Effect on log1p(token_py_100_200)",
    shape = "Term type",
    fill = "p < 0.05"
  ) +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom")
ensure_parent(dynamic_pdf); ggsave(dynamic_pdf, plot_object, width = 9.5, height = 5.5, device = cairo_pdf)
ensure_parent(dynamic_png); ggsave(dynamic_png, plot_object, width = 9.5, height = 5.5, dpi = 160)

# Final output QC.
qc <- add_qc(qc, "static_output_rows", nrow(static_result), expected$static_rows, nrow(static_result) == expected$static_rows)
qc <- add_qc(qc, "dynamic_output_rows", nrow(dynamic_result), expected$dynamic_rows, nrow(dynamic_result) == expected$dynamic_rows)
qc <- add_qc(qc, "pretrend_output_rows", nrow(pretrend_result), expected$pretrend_rows, nrow(pretrend_result) == expected$pretrend_rows)
qc <- add_qc(qc, "reference_event_time_omitted", sum(dynamic_result$event_time == reference_event_time), 0, sum(dynamic_result$event_time == reference_event_time) == 0)
qc <- add_qc(qc, "model_failures", model_diagnostics[status != "success", .N], 0, model_diagnostics[status != "success", .N] == 0)
qc <- add_qc(qc, "invalid_standard_errors", dynamic_result[is.na(std_error) | std_error < 0, .N] + static_result[is.na(std_error) | std_error < 0, .N], 0,
  dynamic_result[is.na(std_error) | std_error < 0, .N] + static_result[is.na(std_error) | std_error < 0, .N] == 0)
qc <- add_qc(qc, "confidence_interval_order_errors", dynamic_result[conf_low > estimate | estimate > conf_high, .N] + static_result[conf_low > estimate | estimate > conf_high, .N], 0,
  dynamic_result[conf_low > estimate | estimate > conf_high, .N] + static_result[conf_low > estimate | estimate > conf_high, .N] == 0)
qc <- add_qc(qc, "joint_pretrend_test_rows", nrow(pretrend_joint), 1, nrow(pretrend_joint) == 1)
write_csv(qc, qc_output)

summary <- rbindlist(list(
  sample_summary,
  data.table(section = "model", metric = c(
    "static_rows", "dynamic_rows", "pretrend_rows", "joint_pretrend_rows", "model_failures"
  ), value = c(
    nrow(static_result), nrow(dynamic_result), nrow(pretrend_result), nrow(pretrend_joint), model_diagnostics[status != "success", .N]
  ), note = ""),
  data.table(section = "static_effect", metric = c("estimate", "std_error", "p_value", "percent_change"),
    value = c(static_result$estimate, static_result$std_error, static_result$p_value, static_result$percent_change), note = ""),
  data.table(section = "pretrend", metric = c("joint_p_value", "joint_passes_05", "individual_periods_excluding_zero"),
    value = c(wald_p, pretrend_joint$passes_05, paste(pretrend_result[ci_includes_zero == FALSE, event_time], collapse = ",")), note = "")
), fill = TRUE)
write_csv(summary, summary_output)

if (strict_expected && any(qc$status == "fail")) {
  stop("Final QC failed under strict expected-count mode")
}
log_info("Completed run-x-d03-v2 successfully")
