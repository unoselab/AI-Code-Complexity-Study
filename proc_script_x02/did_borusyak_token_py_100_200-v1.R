#!/usr/bin/env Rscript

# run-x-d03 v1
# Estimate Borusyak et al. imputation DiD effects for the log-transformed
# stock of Python function-body literal-space tokens in the inclusive
# 100-200 token range.

suppressPackageStartupMessages({
  library(data.table)
  library(didimputation)
  library(fixest)
  library(ggplot2)
})

parse_args <- function(args) {
  out <- list()
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop("Unexpected positional argument: ", key)
    if (i == length(args)) stop("Missing value for argument: ", key)
    out[[sub("^--", "", key)]] <- args[[i + 1L]]
    i <- i + 2L
  }
  out
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required_args <- c(
  "input", "static-output", "dynamic-output", "pretrend-output",
  "pretrend-summary-output", "event-support-output", "cohort-support-output",
  "sample-summary-output", "legacy-audit-output", "model-diagnostics-output",
  "run-metadata-output", "qc-output", "session-info-output",
  "static-model-output", "dynamic-model-output", "pretrend-model-output",
  "summary-output", "dynamic-pdf-output", "dynamic-png-output",
  "static-pdf-output", "strict-expected-counts", "expected-rows",
  "expected-repositories", "expected-treatment-rows", "expected-control-rows",
  "expected-treatment-repositories", "expected-control-repositories",
  "expected-untreated-rows", "expected-static-treated-rows",
  "expected-dynamic-post-rows", "expected-legacy-mismatch-rows",
  "horizon-min", "horizon-max", "pretrend-min", "pretrend-max",
  "reference-event-time", "random-seed"
)
missing_args <- setdiff(required_args, names(args))
if (length(missing_args)) stop("Missing arguments: ", paste(missing_args, collapse = ", "))

as_int <- function(name) as.integer(args[[name]])
strict_counts <- identical(args[["strict-expected-counts"]], "1")
horizon_min <- as_int("horizon-min")
horizon_max <- as_int("horizon-max")
pretrend_min <- as_int("pretrend-min")
pretrend_max <- as_int("pretrend-max")
reference_event_time <- as_int("reference-event-time")
set.seed(as_int("random-seed"))

output_paths <- unlist(args[grepl("-output$", names(args))], use.names = FALSE)
for (path in output_paths) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)

qc_rows <- list()
add_qc <- function(check_name, status, observed, expected = "", note = "") {
  qc_rows[[length(qc_rows) + 1L]] <<- data.table(
    check_name = as.character(check_name),
    status = as.character(status),
    observed = as.character(observed),
    expected = as.character(expected),
    note = as.character(note)
  )
}
check_equal <- function(name, observed, expected, note = "") {
  status <- if (identical(as.character(observed), as.character(expected))) "pass" else "fail"
  add_qc(name, status, observed, expected, note)
}
check_zero <- function(name, observed, note = "") check_equal(name, observed, 0, note)

input_path <- args[["input"]]
input_sha256 <- unname(tools::md5sum(input_path))
dt <- fread(input_path, na.strings = c("", "NA", "NaN"))

required_columns <- c(
  "repo_id", "repo_name", "scope_role", "treatment_group", "time_index",
  "event_index", "time_to_event", "log_token_py_100_200", "log_age", "ncloc",
  "log_contributors", "log_stars", "log_issues", "token_py_100_200"
)
missing_columns <- setdiff(required_columns, names(dt))
if (length(missing_columns)) stop("Input is missing required columns: ", paste(missing_columns, collapse = ", "))

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "log_token_py_100_200", "log_age", "ncloc", "log_contributors",
  "log_stars", "log_issues", "token_py_100_200"
)
for (column in numeric_columns) set(dt, j = column, value = as.numeric(dt[[column]]))

# Normalize role and treatment timing. Legacy monthly flags are audit-only.
dt[, scope_role := tolower(trimws(as.character(scope_role)))]
dt[, event_time_normalized := fifelse(event_index > 0, time_index - event_index, NA_real_)]
dt[, absorbing_treated := as.integer(event_index > 0 & time_index >= event_index)]
dt[scope_role == "control", absorbing_treated := 0L]
dt[, unit_month_key := paste(repo_id, time_index, sep = "::")]

# Input and timing QC.
check_equal("input_rows", nrow(dt), as_int("expected-rows"))
check_equal("input_repositories", uniqueN(dt$repo_id), as_int("expected-repositories"))
check_equal("treatment_rows", nrow(dt[scope_role == "treatment"]), as_int("expected-treatment-rows"))
check_equal("control_rows", nrow(dt[scope_role == "control"]), as_int("expected-control-rows"))
check_equal("treatment_repositories", uniqueN(dt[scope_role == "treatment", repo_id]), as_int("expected-treatment-repositories"))
check_equal("control_repositories", uniqueN(dt[scope_role == "control", repo_id]), as_int("expected-control-repositories"))
check_zero("duplicate_unit_month_rows", nrow(dt[duplicated(unit_month_key)]))
check_zero("control_rows_with_event_index", nrow(dt[scope_role == "control" & event_index != 0]))
check_zero("treatment_rows_without_positive_event_index", nrow(dt[scope_role == "treatment" & event_index <= 0]))
check_zero("normalized_event_time_mismatch", nrow(dt[scope_role == "treatment" & event_time_normalized != time_to_event]))
check_zero("pre_event_rows_marked_treated", nrow(dt[scope_role == "treatment" & time_to_event < 0 & absorbing_treated == 1]))
check_zero("post_event_rows_marked_untreated", nrow(dt[scope_role == "treatment" & time_to_event >= 0 & absorbing_treated == 0]))
check_zero("control_rows_marked_treated", nrow(dt[scope_role == "control" & absorbing_treated == 1]))
check_zero("negative_primary_metric", nrow(dt[token_py_100_200 < 0]))

model_fields <- c(
  "repo_id", "time_index", "event_index", "log_token_py_100_200",
  "log_age", "ncloc", "log_contributors", "log_stars", "log_issues"
)
missing_model_values <- sum(!complete.cases(dt[, ..model_fields]))
check_zero("missing_model_values", missing_model_values)
if (missing_model_values > 0) stop("Model input contains missing required values.")

expected_log <- log1p(dt$token_py_100_200)
log_mismatch <- sum(abs(expected_log - dt$log_token_py_100_200) > 1e-10)
check_zero("primary_log_transform_mismatch", log_mismatch)

untreated_rows <- nrow(dt[absorbing_treated == 0])
static_treated_rows <- nrow(dt[absorbing_treated == 1])
dynamic_post_rows <- nrow(dt[scope_role == "treatment" & time_to_event >= 0 & time_to_event <= horizon_max])
check_equal("untreated_first_stage_rows", untreated_rows, as_int("expected-untreated-rows"))
check_equal("static_treated_rows", static_treated_rows, as_int("expected-static-treated-rows"))
check_equal("dynamic_post_rows", dynamic_post_rows, as_int("expected-dynamic-post-rows"))

# Legacy flag audit. Only columns present in the input are compared.
legacy_flags <- intersect(c("is_treatment", "post_event", "cursor", "cursor_flag"), names(dt))
legacy_audit <- data.table()
if (length(legacy_flags)) {
  normalize_flag <- function(x) {
    values <- tolower(trimws(as.character(x)))
    as.integer(values %in% c("1", "true", "t", "yes"))
  }
  for (column in legacy_flags) {
    legacy_value <- normalize_flag(dt[[column]])
    mismatch_index <- which(!is.na(legacy_value) & legacy_value != dt$absorbing_treated)
    if (length(mismatch_index)) {
      part <- copy(dt[mismatch_index, .(
        repo_id, repo_name, scope_role, time_index, event_index,
        time_to_event, absorbing_treated
      )])
      part[, `:=`(
        legacy_column = column,
        legacy_value = legacy_value[mismatch_index]
      )]
      legacy_audit <- rbindlist(list(legacy_audit, part), use.names = TRUE, fill = TRUE)
    }
  }
}
# The expected count is based on unique rows rather than the number of flag-column mismatches.
legacy_unique_rows <- if (nrow(legacy_audit)) uniqueN(legacy_audit[, paste(repo_id, time_index, sep = "::")]) else 0L
check_equal("legacy_mismatch_rows", legacy_unique_rows, as_int("expected-legacy-mismatch-rows"), "Legacy flags are audit-only and do not affect treatment timing.")
fwrite(legacy_audit, args[["legacy-audit-output"]])

# Support tables.
event_support <- dt[scope_role == "treatment", .(
  support_rows = .N,
  support_repositories = uniqueN(repo_id),
  mean_token_py_100_200 = mean(token_py_100_200),
  median_token_py_100_200 = median(token_py_100_200)
), by = .(event_time = as.integer(time_to_event))][order(event_time)]
fwrite(event_support, args[["event-support-output"]])

cohort_support <- dt[scope_role == "treatment", .(
  treatment_repositories = uniqueN(repo_id),
  total_rows = .N,
  pre_treatment_rows = sum(time_to_event < 0),
  post_treatment_rows = sum(time_to_event >= 0),
  dynamic_post_rows = sum(time_to_event >= 0 & time_to_event <= horizon_max),
  minimum_event_time = min(time_to_event),
  maximum_event_time = max(time_to_event)
), by = .(event_index)][order(event_index)]
fwrite(cohort_support, args[["cohort-support-output"]])

sample_summary <- data.table(
  metric = c(
    "rows", "repositories", "treatment_rows", "control_rows",
    "treatment_repositories", "control_repositories", "untreated_first_stage_rows",
    "static_treated_rows", "dynamic_post_rows", "legacy_mismatch_rows",
    "zero_primary_metric_rows", "primary_metric_mean", "primary_metric_median"
  ),
  value = c(
    nrow(dt), uniqueN(dt$repo_id), nrow(dt[scope_role == "treatment"]),
    nrow(dt[scope_role == "control"]), uniqueN(dt[scope_role == "treatment", repo_id]),
    uniqueN(dt[scope_role == "control", repo_id]), untreated_rows,
    static_treated_rows, dynamic_post_rows, legacy_unique_rows,
    nrow(dt[token_py_100_200 == 0]), mean(dt$token_py_100_200), median(dt$token_py_100_200)
  )
)
fwrite(sample_summary, args[["sample-summary-output"]])

first_stage_formula <- ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index
model_diagnostics <- list()
record_diagnostic <- function(model_type, status, runtime_seconds, warning_text = "", error_text = "") {
  model_diagnostics[[length(model_diagnostics) + 1L]] <<- data.table(
    outcome = "log_token_py_100_200",
    model_type = model_type,
    status = status,
    runtime_seconds = runtime_seconds,
    input_rows = nrow(dt),
    untreated_rows = untreated_rows,
    treated_rows = static_treated_rows,
    repositories = uniqueN(dt$repo_id),
    warning_text = warning_text,
    error_text = error_text
  )
}

run_with_warnings <- function(expression) {
  warnings <- character()
  start <- proc.time()[[3L]]
  result <- tryCatch(
    withCallingHandlers(
      expression,
      warning = function(w) {
        warnings <<- c(warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  elapsed <- proc.time()[[3L]] - start
  list(result = result, elapsed = elapsed, warnings = unique(warnings))
}

# Static Borusyak ATT: all post-adoption observations.
static_run <- run_with_warnings(
  didimputation::did_imputation(
    data = dt,
    yname = "log_token_py_100_200",
    gname = "event_index",
    tname = "time_index",
    idname = "repo_id",
    first_stage = first_stage_formula,
    cluster_var = "repo_id"
  )
)
if (inherits(static_run$result, "error")) {
  record_diagnostic("static", "fail", static_run$elapsed, paste(static_run$warnings, collapse = " | "), conditionMessage(static_run$result))
  fwrite(rbindlist(model_diagnostics), args[["model-diagnostics-output"]])
  stop("Static did_imputation failed: ", conditionMessage(static_run$result))
}
record_diagnostic("static", "success", static_run$elapsed, paste(static_run$warnings, collapse = " | "))
static_model <- static_run$result
saveRDS(static_model, args[["static-model-output"]])

static_row <- as.data.table(static_model)[term == "treat"]
if (nrow(static_row) != 1L) stop("Expected exactly one static treatment row.")
static_effect <- static_row[, .(
  outcome = "log_token_py_100_200",
  term = as.character(term),
  estimate = as.numeric(estimate),
  std_error = as.numeric(std.error),
  conf_low = as.numeric(conf.low),
  conf_high = as.numeric(conf.high),
  p_value = as.numeric(p.value)
)]
static_effect[, `:=`(
  percent_change = 100 * (exp(estimate) - 1),
  percent_ci_low = 100 * (exp(conf_low) - 1),
  percent_ci_high = 100 * (exp(conf_high) - 1),
  treated_observations = static_treated_rows,
  first_stage_observations = untreated_rows,
  treatment_repositories = uniqueN(dt[scope_role == "treatment", repo_id]),
  control_repositories = uniqueN(dt[scope_role == "control", repo_id])
)]
fwrite(static_effect, args[["static-output"]])

# Dynamic post-treatment effects and placebo pretrends.
dynamic_run <- run_with_warnings(
  didimputation::did_imputation(
    data = dt,
    yname = "log_token_py_100_200",
    gname = "event_index",
    tname = "time_index",
    idname = "repo_id",
    first_stage = first_stage_formula,
    cluster_var = "repo_id",
    horizon = horizon_min:horizon_max,
    pretrends = pretrend_min:pretrend_max
  )
)
if (inherits(dynamic_run$result, "error")) {
  record_diagnostic("dynamic", "fail", dynamic_run$elapsed, paste(dynamic_run$warnings, collapse = " | "), conditionMessage(dynamic_run$result))
  fwrite(rbindlist(model_diagnostics), args[["model-diagnostics-output"]])
  stop("Dynamic did_imputation failed: ", conditionMessage(dynamic_run$result))
}
record_diagnostic("dynamic", "success", dynamic_run$elapsed, paste(dynamic_run$warnings, collapse = " | "))
dynamic_model <- dynamic_run$result
saveRDS(dynamic_model, args[["dynamic-model-output"]])

dynamic_effects <- as.data.table(dynamic_model)
dynamic_effects[, event_time := suppressWarnings(as.integer(as.character(term)))]
dynamic_effects <- dynamic_effects[!is.na(event_time)]
dynamic_effects[, `:=`(
  outcome = "log_token_py_100_200",
  term_type = fifelse(event_time < 0, "placebo", "post_treatment"),
  estimated = 1L,
  std_error = as.numeric(std.error),
  conf_low = as.numeric(conf.low),
  conf_high = as.numeric(conf.high),
  p_value = as.numeric(p.value),
  estimate = as.numeric(estimate)
)]
dynamic_effects[, `:=`(
  percent_change = 100 * (exp(estimate) - 1),
  percent_ci_low = 100 * (exp(conf_low) - 1),
  percent_ci_high = 100 * (exp(conf_high) - 1),
  significant_05 = p_value < 0.05
)]
dynamic_effects <- merge(
  dynamic_effects,
  event_support[, .(event_time, support_rows, support_repositories)],
  by = "event_time",
  all.x = TRUE,
  sort = FALSE
)
dynamic_effects <- dynamic_effects[, .(
  outcome, event_time, term_type, estimated, estimate, std_error,
  conf_low, conf_high, p_value, percent_change, percent_ci_low,
  percent_ci_high, support_rows, support_repositories, significant_05
)][order(event_time)]

expected_estimated_times <- c(pretrend_min:pretrend_max, 0:horizon_max)
missing_dynamic_times <- setdiff(expected_estimated_times, dynamic_effects$event_time)
unexpected_dynamic_times <- setdiff(dynamic_effects$event_time, expected_estimated_times)
check_zero("missing_dynamic_event_times", length(missing_dynamic_times), paste(missing_dynamic_times, collapse = ","))
check_zero("unexpected_dynamic_event_times", length(unexpected_dynamic_times), paste(unexpected_dynamic_times, collapse = ","))
check_equal("dynamic_estimated_rows", nrow(dynamic_effects), length(expected_estimated_times))

reference_support <- event_support[event_time == reference_event_time]
reference_row <- data.table(
  outcome = "log_token_py_100_200",
  event_time = reference_event_time,
  term_type = "reference",
  estimated = 0L,
  estimate = 0,
  std_error = NA_real_,
  conf_low = NA_real_,
  conf_high = NA_real_,
  p_value = NA_real_,
  percent_change = 0,
  percent_ci_low = NA_real_,
  percent_ci_high = NA_real_,
  support_rows = if (nrow(reference_support)) reference_support$support_rows else NA_integer_,
  support_repositories = if (nrow(reference_support)) reference_support$support_repositories else NA_integer_,
  significant_05 = FALSE
)
dynamic_with_reference <- rbindlist(list(dynamic_effects, reference_row), use.names = TRUE, fill = TRUE)[order(event_time)]
fwrite(dynamic_with_reference, args[["dynamic-output"]])

# Explicit untreated-sample placebo model and joint Wald test.
pretrend_dt <- copy(dt[absorbing_treated == 0])
pretrend_terms <- paste0("pre_m", abs(pretrend_min:pretrend_max))
for (h in pretrend_min:pretrend_max) {
  column <- paste0("pre_m", abs(h))
  pretrend_dt[, (column) := as.integer(scope_role == "treatment" & time_to_event == h)]
}
pretrend_formula <- as.formula(paste(
  "log_token_py_100_200 ~",
  paste(c(pretrend_terms, "log_age", "ncloc", "log_contributors", "log_stars", "log_issues"), collapse = " + "),
  "| repo_id + time_index"
))
pretrend_run <- run_with_warnings(
  fixest::feols(pretrend_formula, data = pretrend_dt, cluster = ~repo_id, warn = FALSE, notes = FALSE)
)
if (inherits(pretrend_run$result, "error")) {
  record_diagnostic("pretrend_joint", "fail", pretrend_run$elapsed, paste(pretrend_run$warnings, collapse = " | "), conditionMessage(pretrend_run$result))
  fwrite(rbindlist(model_diagnostics), args[["model-diagnostics-output"]])
  stop("Pretrend regression failed: ", conditionMessage(pretrend_run$result))
}
record_diagnostic("pretrend_joint", "success", pretrend_run$elapsed, paste(pretrend_run$warnings, collapse = " | "))
pretrend_model <- pretrend_run$result
saveRDS(pretrend_model, args[["pretrend-model-output"]])

coef_table <- as.data.table(fixest::coeftable(pretrend_model), keep.rownames = "term")
setnames(coef_table, c("Estimate", "Std. Error", "t value", "Pr(>|t|)"), c("estimate", "std_error", "statistic", "p_value"), skip_absent = TRUE)
pretrend_checks <- coef_table[term %in% pretrend_terms]
pretrend_checks[, event_time := -as.integer(sub("pre_m", "", term))]
pretrend_checks[, `:=`(
  outcome = "log_token_py_100_200",
  conf_low = estimate - qnorm(0.975) * std_error,
  conf_high = estimate + qnorm(0.975) * std_error,
  significant_05 = p_value < 0.05
)]
pretrend_checks <- merge(
  pretrend_checks,
  event_support[, .(event_time, support_rows, support_repositories)],
  by = "event_time", all.x = TRUE, sort = FALSE
)[, .(outcome, event_time, term, estimate, std_error, conf_low, conf_high,
      statistic, p_value, support_rows, support_repositories, significant_05)][order(event_time)]
fwrite(pretrend_checks, args[["pretrend-output"]])

wald_result <- fixest::wald(pretrend_model, keep = paste(pretrend_terms, collapse = "|"), print = FALSE)
wald_names <- names(wald_result)
extract_wald_value <- function(candidates, default = NA_real_) {
  hit <- intersect(candidates, wald_names)
  if (length(hit)) as.numeric(wald_result[[hit[[1L]]]]) else default
}
pretrend_summary <- data.table(
  outcome = "log_token_py_100_200",
  placebo_periods = paste(pretrend_min:pretrend_max, collapse = ","),
  wald_statistic = extract_wald_value(c("stat", "F", "Chisq")),
  df_num = extract_wald_value(c("df1", "df")),
  df_denom = extract_wald_value(c("df2")),
  p_value = extract_wald_value(c("p", "p.value", "Pr(>F)", "Pr(>Chisq)"))
)
pretrend_summary[, passes_05 := p_value >= 0.05]
fwrite(pretrend_summary, args[["pretrend-summary-output"]])

# Model diagnostics and basic effect QC.
diagnostics_dt <- rbindlist(model_diagnostics, use.names = TRUE, fill = TRUE)
fwrite(diagnostics_dt, args[["model-diagnostics-output"]])
check_equal("successful_model_components", nrow(diagnostics_dt[status == "success"]), 3)
check_zero("failed_model_components", nrow(diagnostics_dt[status != "success"]))
check_zero("invalid_static_standard_errors", sum(!is.finite(static_effect$std_error) | static_effect$std_error < 0))
check_zero("invalid_dynamic_standard_errors", sum(!is.finite(dynamic_effects$std_error) | dynamic_effects$std_error < 0))
check_zero("invalid_dynamic_confidence_intervals", sum(dynamic_effects$conf_low > dynamic_effects$conf_high))
check_equal("pretrend_coefficient_rows", nrow(pretrend_checks), length(pretrend_terms))
check_equal("pretrend_joint_test_rows", nrow(pretrend_summary), 1)

# Plots.
plot_dt <- copy(dynamic_with_reference)
plot_dt[, significance_label := fifelse(term_type == "reference", "Reference", fifelse(significant_05, "p < 0.05", "p >= 0.05"))]
plot_dt[, significance_label := factor(significance_label, levels = c("p < 0.05", "p >= 0.05", "Reference"))]
pretrend_p_label <- if (is.finite(pretrend_summary$p_value)) sprintf("Joint pretrend p = %.3f", pretrend_summary$p_value) else "Joint pretrend p unavailable"

dynamic_plot <- ggplot(plot_dt, aes(x = event_time, y = estimate)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.35) +
  geom_vline(xintercept = -0.5, linetype = "dotted", linewidth = 0.35) +
  geom_errorbar(data = plot_dt[estimated == 1], aes(ymin = conf_low, ymax = conf_high), width = 0.15) +
  geom_point(aes(shape = significance_label), size = 2.5) +
  scale_shape_manual(values = c("p < 0.05" = 16, "p >= 0.05" = 1, "Reference" = 4), drop = FALSE) +
  scale_x_continuous(breaks = horizon_min:horizon_max) +
  labs(
    title = "Borusyak DiD: Python Function-Body Tokens (100-200)",
    subtitle = pretrend_p_label,
    x = "Months relative to Cursor adoption",
    y = "Treatment effect on log1p token stock",
    shape = NULL
  ) +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom")

ggsave(args[["dynamic-pdf-output"]], dynamic_plot, width = 8, height = 5.5)
ggsave(args[["dynamic-png-output"]], dynamic_plot, width = 8, height = 5.5, dpi = 180)

static_plot <- ggplot(static_effect, aes(x = outcome, y = estimate)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.35) +
  geom_errorbar(aes(ymin = conf_low, ymax = conf_high), width = 0.08) +
  geom_point(size = 2.8) +
  coord_flip() +
  labs(
    title = "Static ATT: Python Function-Body Tokens (100-200)",
    x = NULL,
    y = "Treatment effect on log1p token stock"
  ) +
  theme_minimal(base_size = 11)
ggsave(args[["static-pdf-output"]], static_plot, width = 7, height = 3.5)

# Metadata and summary.
package_versions <- c(
  R = paste(R.version$major, R.version$minor, sep = "."),
  didimputation = as.character(packageVersion("didimputation")),
  data.table = as.character(packageVersion("data.table")),
  fixest = as.character(packageVersion("fixest")),
  ggplot2 = as.character(packageVersion("ggplot2"))
)
metadata <- data.table(
  field = c(
    "implementation_version", "experiment", "input_file", "input_md5",
    "outcome", "first_stage", "cluster_variable", "horizon",
    "pretrend_window", "reference_event_time", names(package_versions)
  ),
  value = c(
    "v1", "run-x-d03-did-borusyak-token-py-100-200", input_path, input_sha256,
    "log_token_py_100_200",
    "log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index",
    "repo_id", paste(horizon_min, horizon_max, sep = ":"),
    paste(pretrend_min, pretrend_max, sep = ":"), reference_event_time,
    unname(package_versions)
  )
)
fwrite(metadata, args[["run-metadata-output"]])
writeLines(capture.output(sessionInfo()), args[["session-info-output"]])

summary_dt <- rbindlist(list(
  data.table(section = "sample", metric = sample_summary$metric, value = as.character(sample_summary$value), note = ""),
  data.table(section = "static", metric = c("estimate", "std_error", "p_value", "percent_change"), value = as.character(unlist(static_effect[, .(estimate, std_error, p_value, percent_change)])), note = ""),
  data.table(section = "pretrend", metric = c("joint_statistic", "joint_p_value", "passes_05"), value = as.character(unlist(pretrend_summary[, .(wald_statistic, p_value, passes_05)])), note = ""),
  data.table(section = "model", metric = "dynamic_estimated_terms", value = as.character(nrow(dynamic_effects)), note = paste("Reference event time", reference_event_time, "is stored separately."))
), use.names = TRUE, fill = TRUE)
fwrite(summary_dt, args[["summary-output"]])

qc_dt <- rbindlist(qc_rows, use.names = TRUE, fill = TRUE)
if (!strict_counts) {
  count_checks <- c(
    "input_rows", "input_repositories", "treatment_rows", "control_rows",
    "treatment_repositories", "control_repositories", "untreated_first_stage_rows",
    "static_treated_rows", "dynamic_post_rows", "legacy_mismatch_rows"
  )
  qc_dt[check_name %in% count_checks & status == "fail", `:=`(
    status = "warn",
    note = paste(trimws(note), "Strict expected counts are disabled.")
  )]
}
fwrite(qc_dt, args[["qc-output"]])

cat("\nStatic effect preview:\n")
print(static_effect)
cat("\nPretrend joint test preview:\n")
print(pretrend_summary)
cat("\nQC preview:\n")
print(qc_dt)

if (any(qc_dt$status == "fail")) {
  failed <- qc_dt[status == "fail", check_name]
  stop("D03 QC failed: ", paste(failed, collapse = ", "))
}

cat(sprintf(
  "\nCompleted run-x-d03-v1: rows=%d; repositories=%d; treated_rows=%d; untreated_rows=%d; static_att=%.6f; pretrend_p=%.6f\n",
  nrow(dt), uniqueN(dt$repo_id), static_treated_rows, untreated_rows,
  static_effect$estimate, pretrend_summary$p_value
))
