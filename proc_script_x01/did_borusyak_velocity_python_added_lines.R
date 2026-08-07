#!/usr/bin/env Rscript

# ============================================================
# run-x-b03 v3: Borusyak DiD covariate sensitivity for Python added-lines velocity
# ============================================================
#
# Purpose:
#   Estimate Cursor-adoption treatment effects for the four Python velocity
#   outcomes prepared by run-x-b02-v4, using each Python-NCLOC backend.
#
# Outcome definitions:
#   - primary: log_lines_added_py_source
#   - robustness: log_lines_added_py_no_merge
#   - robustness: log_lines_added_py_source_no_tests
#   - robustness: log_lines_added_py_all
#
# First-stage sensitivity specifications:
#   - python_ncloc_adjusted:
#       outcome ~ log_age + ncloc + log_contributors + log_stars + log_issues
#                 | repo_id + time_index
#   - no_covariates:
#       outcome ~ 1 | repo_id + time_index
#
# The no-covariate specification is the immediate robustness check for
# contemporaneous post-treatment covariate conditioning. A repository-fixed
# baseline NCLOC level is not added here because repository fixed effects absorb
# time-invariant repository-level covariates; a baseline-size trend interaction
# would be a different estimand and should be evaluated separately if needed.
#
# Treatment definition:
#   Absorbing intent-to-treat timing based only on event_index and time_index.
#   Legacy month-specific columns such as cursor, is_treatment, post_event,
#   lead_*, and lag_* are audit-only and never define model treatment.
#
# Estimation design inherited from the prior b03 implementation:
#   - static ATT uses every post-adoption observation;
#   - dynamic effects use event months 0 through +6;
#   - package-native placebo coefficients use event months -6 through -2;
#   - event month -1 is the omitted reference;
#   - standard errors are clustered by repository.
#
# Backend mode fits all four outcomes for one NCLOC backend and one covariate
# specification. Backend comparison mode verifies exact same-sample alignment
# between SonarQube and cloc within a covariate specification. Covariate
# comparison mode contrasts python_ncloc_adjusted with no_covariates while
# holding backend, outcome, treatment timing, and sample fixed.
# This script does not call any prior experiment script.
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
    if (!startsWith(token, "--")) {
      abortf("Unexpected positional argument: %s", token)
    }
    key <- sub("^--", "", token)
    key <- gsub("-", "_", key, fixed = TRUE)
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
  if (length(missing) > 0L) {
    abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
  }
}

sha256_file <- function(path) {
  if (!file.exists(path)) return(NA_character_)
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

extract_effect_table <- function(result, outcome_name, confidence_level, term_type = NULL) {
  table <- data.table::as.data.table(result)
  required <- c("term", "estimate", "std.error", "conf.low", "conf.high")
  validate_columns(table, required)
  table[, outcome := outcome_name]
  alpha <- 1 - confidence_level
  critical_value <- stats::qnorm(1 - alpha / 2)
  table[, conf.low := estimate - critical_value * std.error]
  table[, conf.high := estimate + critical_value * std.error]
  table[, p_value := ifelse(is.finite(std.error) & std.error > 0,
                            2 * stats::pnorm(-abs(estimate / std.error)), NA_real_)]
  table[, exp_coefficient_change_pct := 100 * (exp(estimate) - 1)]
  table[, exp_ci_low_pct := 100 * (exp(conf.low) - 1)]
  table[, exp_ci_high_pct := 100 * (exp(conf.high) - 1)]
  table[, significant := !is.na(p_value) & p_value < alpha]
  if (!is.null(term_type)) table[, term_type := term_type]
  table
}

fit_first_stage_diagnostic <- function(data, outcome, first_stage_formula_text) {
  untreated <- data[absorbing_treated == 0L]
  formula <- stats::as.formula(sprintf("%s %s", outcome, first_stage_formula_text))
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
  predictions <- capture_evaluation(stats::predict(captured$value, newdata = data))
  if (predictions$error) return(predictions)
  captured$predictions <- predictions$value
  captured$warnings <- unique(c(captured$warnings, predictions$warnings))
  captured$elapsed <- captured$elapsed + predictions$elapsed
  captured
}

run_did_model <- function(data, outcome, first_stage_formula, horizon = NULL, pretrends = NULL) {
  capture_evaluation(
    didimputation::did_imputation(
      data = data,
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

render_html_report <- function(
  output_path, plot_png_path, static_output, dynamic_output,
  pretrend_checks, pretrend_summary, event_support, cohort_support,
  sample_summary, legacy_audit, diagnostics, metadata,
  input_rows, treatment_repos, control_repos, untreated_rows, treated_rows,
  first_stage_formula, implementation_version, backend_key, backend_label, backend_metric
) {
  if (!rmarkdown::pandoc_available()) {
    abortf("Pandoc is required to render the HTML report but was not found by rmarkdown.")
  }

  ensure_parent_dir(output_path)
  output_path <- file.path(normalizePath(dirname(output_path), mustWork = TRUE), basename(output_path))
  plot_png_path <- normalizePath(plot_png_path, mustWork = TRUE)
  template_path <- tempfile(pattern = paste0("run-x-b03-", backend_key, "-report-"), fileext = ".Rmd")
  on.exit(unlink(template_path, force = TRUE), add = TRUE)

  report_lines <- c(
    "---",
    "title: \"The Impact of Cursor Adoption on Python Velocity\"",
    "subtitle: \"Borusyak et al. (2021) Difference-in-Differences Imputation — Python Velocity Robustness\"",
    "output:",
    "  html_document:",
    "    toc: true",
    "    toc_depth: 3",
    "    number_sections: true",
    "    self_contained: true",
    "    code_folding: hide",
    "date: \"`r report_generated_at`\"",
    "---",
    "",
    "<style>",
    "body { max-width: 1200px; margin-left: auto; margin-right: auto; }",
    "table { width: 100%; }",
    "th { white-space: nowrap; }",
    ".note { padding: 0.8em 1em; background: #f5f5f5; border-left: 4px solid #777; margin: 1em 0; }",
    ".result-positive { font-weight: 600; }",
    "</style>",
    "",
    "```{r setup, include=FALSE}",
    "knitr::opts_chunk$set(echo = FALSE, message = FALSE, warning = FALSE, results = \"markup\")",
    "options(scipen = 999)",
    "fmt_num <- function(x, digits = 3) {",
    "  ifelse(is.na(x), \"\", formatC(x, format = \"f\", digits = digits))",
    "}",
    "fmt_p <- function(x) {",
    "  ifelse(is.na(x), \"\", ifelse(x < 0.001, \"<0.001\", formatC(x, format = \"f\", digits = 3)))",
    "}",
    "fmt_event <- function(x) {",
    "  ifelse(x > 0, paste0(\"+\", x), as.character(x))",
    "}",
    "sig_text <- function(x) {",
    "  ifelse(isTRUE(x), \"Yes\", \"No\")",
    "}",
    "significance_phrase <- function(p) {",
    "  ifelse(!is.na(p) && p < 0.05, \"statistically significant\", \"not statistically significant\")",
    "}",
    "primary_outcome_name <- \"log_lines_added_py_source\"",
    "primary_static <- static_report[outcome == primary_outcome_name][1]",
    "```",
    "",
    "# Overview",
    "",
    "This report was generated automatically by **run-x-b03** for the **`r backend_label_report`** Python-NCLOC backend and four Python added-lines outcome definitions. It follows the presentation logic of the original `DiffInDiffBorusyak.Rmd` and uses the run-x-b02-v4 panel while varying only the Python velocity outcome definition within a fixed matched sample and a fixed Python-NCLOC backend.",
    "",
    "All four outcome specifications use the same **`r input_rows_report` repository-month observations**, including **`r treatment_repos_report` treatment repositories** and **`r control_repos_report` matched control repositories**. The first stage uses **`r untreated_rows_report` untreated observations**, and the static ATT averages **`r treated_rows_report` post-adoption observations**.",
    "",
    "# Analysis Design",
    "",
    "## Treatment and timing",
    "",
    "- Treatment is an absorbing intent-to-treat indicator beginning at the first observed Cursor adoption month.",
    "- Calendar time and adoption time use the consecutive indices `time_index` and `event_index`.",
    "- Legacy month-specific fields such as `cursor`, `is_treatment`, `post_event`, `lead_*`, and `lag_*` are retained only for audit.",
    "- Standard errors are clustered by `repo_id`.",
    "",
    "## First stage and Python-NCLOC backend",
    "",
    "`r first_stage_formula_report`",
    "",
    "## Reported estimands",
    "",
    "- Static ATT: all post-adoption observations.",
    "- Dynamic ATT: event months 0 through +6.",
    "- Placebo pretrends: event months -6 through -2.",
    "- Event month -1 is the omitted reference period.",
    "",
    "# Sample and Quality Control",
    "",
    "```{r sample-summary}",
    "sample_display <- data.table::copy(sample_summary_report[section %in% c(\"input\", \"sample\", \"qc\")])",
    "sample_display[, section := tools::toTitleCase(gsub(\"_\", \" \", section))]",
    "sample_display[, metric := tools::toTitleCase(gsub(\"_\", \" \", metric))]",
    "data.table::setnames(sample_display, c(\"section\", \"metric\", \"value\", \"note\"), c(\"Section\", \"Metric\", \"Value\", \"Note\"))",
    "knitr::kable(sample_display, format = \"html\", row.names = FALSE, caption = \"Analysis sample and QC summary\")",
    "```",
    "",
    "<div class=\"note\">Legacy-flag mismatches are expected audit findings and are reported from the input panel. The models use normalized absorbing treatment timing. The generic `ncloc` model column is verified against the selected backend metric: `r backend_metric_report`.</div>",
    "",
    "# Aggregate Treatment Effects",
    "",
    "```{r static-effects}",
    "static_display <- static_report[, .(",
    "  Outcome = outcome_label,",
    "  Estimate = fmt_num(estimate),",
    "  `Std. Error` = fmt_num(std.error),",
    "  `95% CI` = paste0(\"[\", fmt_num(conf.low), \", \", fmt_num(conf.high), \"]\"),",
    "  `p-value` = fmt_p(p_value),",
    "  Significant = ifelse(significant, \"Yes\", \"No\"),",
    "  `Exp. coefficient change (%)` = fmt_num(exp_coefficient_change_pct, 1)",
    ")]",
    "knitr::kable(static_display, format = \"html\", row.names = FALSE, caption = \"Static Borusyak ATT estimates\")",
    "```",
    "",
    "```{r static-interpretation, results=\"asis\"}",
    "cat(sprintf(",
    "  \"The primary static ATT for **Python source added lines** is %.3f (95%% CI [%.3f, %.3f], p=%s), and is %s.  \\n\",",
    "  primary_static$estimate, primary_static$conf.low, primary_static$conf.high,",
    "  fmt_p(primary_static$p_value), significance_phrase(primary_static$p_value)",
    "))",
    "cat(\"The three additional outcomes are robustness definitions that isolate merge counting, generated/vendor code, and test-code sensitivity.  \\n\")",
    "cat(\"Exponentiated coefficient changes are descriptive transformations on the `log1p` outcome scale rather than exact percentage changes in every repository-month.\\n\")",
    "```",
    "",
    "# Dynamic Treatment Effects",
    "",
    "```{r event-study-plot, out.width=\"100%\", fig.align=\"center\"}",
    "knitr::include_graphics(plot_png_report)",
    "```",
    "",
    "The event-study figure follows the original implementation: filled points have p < 0.05, hollow points have p >= 0.05, and event month -1 is omitted.",
    "",
    "```{r dynamic-table}",
    "post_display <- dynamic_report[event_time >= 0 & event_time <= 6, .(",
    "  Outcome = outcome_label,",
    "  `Event Month` = fmt_event(event_time),",
    "  Estimate = fmt_num(estimate),",
    "  `Std. Error` = fmt_num(std.error),",
    "  `95% CI` = paste0(\"[\", fmt_num(conf.low), \", \", fmt_num(conf.high), \"]\"),",
    "  `p-value` = fmt_p(p_value),",
    "  Significant = ifelse(significant, \"Yes\", \"No\"),",
    "  `Support Repositories` = support_repositories",
    ")]",
    "knitr::kable(post_display, format = \"html\", row.names = FALSE, caption = \"Post-adoption dynamic treatment effects\")",
    "```",
    "",
    "# Pretrend Checks",
    "",
    "```{r pretrend-summary}",
    "pretrend_summary_display <- pretrend_summary_report[, .(",
    "  Outcome = outcome_label,",
    "  `Placebo Periods` = placebo_periods,",
    "  `Terms Checked` = placebo_terms,",
    "  `All 95% CIs Include Zero` = ifelse(all_ci_include_zero, \"Yes\", \"No\"),",
    "  `Periods Excluding Zero` = periods_excluding_zero,",
    "  `Minimum p-value` = fmt_p(minimum_p_value)",
    ")]",
    "knitr::kable(pretrend_summary_display, format = \"html\", row.names = FALSE, caption = \"Original-Rmd-aligned pretrend summary\")",
    "```",
    "",
    "```{r pretrend-details}",
    "pretrend_display <- pretrend_checks_report[, .(",
    "  Outcome = outcome_label,",
    "  `Event Month` = fmt_event(event_time),",
    "  Estimate = fmt_num(estimate),",
    "  `Std. Error` = fmt_num(std.error),",
    "  `95% CI` = paste0(\"[\", fmt_num(conf.low), \", \", fmt_num(conf.high), \"]\"),",
    "  `p-value` = fmt_p(p_value),",
    "  `CI Includes Zero` = ifelse(ci_includes_zero, \"Yes\", \"No\"),",
    "  `Support Repositories` = support_repositories",
    ")]",
    "knitr::kable(pretrend_display, format = \"html\", row.names = FALSE, caption = \"Package-native placebo coefficients\")",
    "```",
    "",
    "# Event-Time and Cohort Support",
    "",
    "```{r event-support}",
    "event_display <- event_support_report[event_time >= -6 & event_time <= 6, .(",
    "  `Event Month` = fmt_event(event_time),",
    "  `Treatment Rows` = treatment_rows,",
    "  `Treatment Repositories` = treatment_repositories,",
    "  `Period Type` = gsub(\"_\", \" \", period_type)",
    ")]",
    "knitr::kable(event_display, format = \"html\", row.names = FALSE, caption = \"Treatment support in the reported event window\")",
    "```",
    "",
    "```{r cohort-support}",
    "cohort_display <- cohort_support_report[, .(",
    "  `Adoption Cohort` = event,",
    "  `Treatment Repositories` = treatment_repositories,",
    "  `Pre-treatment Rows` = pre_treatment_rows,",
    "  `Post-treatment Rows` = treated_rows,",
    "  `Dynamic 0:+6 Rows` = dynamic_0_to_max_rows,",
    "  `Available Event Range` = paste0(min_event_time, \" to +\", max_event_time)",
    ")]",
    "knitr::kable(cohort_display, format = \"html\", row.names = FALSE, caption = \"Adoption-cohort support\")",
    "```",
    "",
    "# Diagnostics and Legacy-Flag Audit",
    "",
    "```{r diagnostics}",
    "diagnostics_display <- diagnostics_report[, .(",
    "  Outcome = outcome,",
    "  Model = model_type,",
    "  Status = status,",
    "  `Runtime (seconds)` = fmt_num(runtime_seconds, 3),",
    "  Warnings = warning_count,",
    "  `Result Terms` = result_terms,",
    "  Details = extra",
    ")]",
    "knitr::kable(diagnostics_display, format = \"html\", row.names = FALSE, caption = \"Model diagnostics\")",
    "```",
    "",
    "```{r legacy-audit}",
    "legacy_summary <- legacy_audit_report[, .(",
    "  `Mismatch Rows` = .N,",
    "  `First Mismatch Month` = min(time),",
    "  `Last Mismatch Month` = max(time)",
    "), by = .(`Repository` = repo_name)]",
    "knitr::kable(legacy_summary, format = \"html\", row.names = FALSE, caption = \"Legacy monthly-flag mismatches retained for audit only\")",
    "```",
    "",
    "# Reproducibility Metadata",
    "",
    "```{r metadata}",
    "metadata_display <- data.table::copy(metadata_report)",
    "metadata_display[, key := tools::toTitleCase(gsub(\"_\", \" \", key))]",
    "data.table::setnames(metadata_display, c(\"key\", \"value\"), c(\"Field\", \"Value\"))",
    "knitr::kable(metadata_display, format = \"html\", row.names = FALSE, caption = \"Run metadata\")",
    "```",
    "",
    "# Result Summary",
    "",
    "```{r result-summary, results=\"asis\"}",
    "sig_months <- function(outcome_name) {",
    "  values <- dynamic_report[outcome == outcome_name & event_time >= 0 & significant == TRUE, event_time]",
    "  if (length(values) == 0L) return(\"none\")",
    "  paste(fmt_event(values), collapse = \", \")",
    "}",
    "for (outcome_name in static_report$outcome) {",
    "  label <- static_report[outcome == outcome_name, outcome_label][1]",
    "  cat(sprintf(\"- Significant post-adoption event months for **%s**: %s.  \\n\", label, sig_months(outcome_name)))",
    "}",
    "cat(sprintf(\"- The primary static source-added-lines effect is %s.  \\n\", significance_phrase(primary_static$p_value)))",
    "cat(\"- Later event months have fewer contributing repositories and should be interpreted together with the support tables.  \\n\")",
    "cat(\"- These estimates are intent-to-treat associations under the matched staggered-DiD design and its identifying assumptions.\\n\")",
    "```",
    "",
    "---",
    "",
    "Generated by `run-x-b03` implementation `r implementation_version_report` for backend `r backend_key_report`."
  )
  writeLines(report_lines, template_path, useBytes = TRUE)

  report_env <- new.env(parent = globalenv())
  report_env$static_report <- data.table::copy(static_output)
  report_env$dynamic_report <- data.table::copy(dynamic_output)
  report_env$pretrend_checks_report <- data.table::copy(pretrend_checks)
  report_env$pretrend_summary_report <- data.table::copy(pretrend_summary)
  report_env$event_support_report <- data.table::copy(event_support)
  report_env$cohort_support_report <- data.table::copy(cohort_support)
  report_env$sample_summary_report <- data.table::copy(sample_summary)
  report_env$legacy_audit_report <- data.table::copy(legacy_audit)
  report_env$diagnostics_report <- data.table::copy(diagnostics)
  report_env$metadata_report <- data.table::copy(metadata)
  report_env$plot_png_report <- plot_png_path
  report_env$input_rows_report <- input_rows
  report_env$treatment_repos_report <- treatment_repos
  report_env$control_repos_report <- control_repos
  report_env$untreated_rows_report <- untreated_rows
  report_env$treated_rows_report <- treated_rows
  report_env$first_stage_formula_report <- first_stage_formula
  report_env$implementation_version_report <- implementation_version
  report_env$backend_key_report <- backend_key
  report_env$backend_label_report <- backend_label
  report_env$backend_metric_report <- backend_metric
  report_env$report_generated_at <- format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")

  rendered <- capture_evaluation(
    rmarkdown::render(
      input = template_path,
      output_file = basename(output_path),
      output_dir = dirname(output_path),
      envir = report_env,
      quiet = TRUE,
      clean = TRUE
    )
  )
  if (rendered$error) {
    abortf("HTML report rendering failed: %s", rendered$value$message)
  }
  if (!file.exists(output_path) || file.info(output_path)$size <= 0) {
    abortf("HTML report was not created or is empty: %s", output_path)
  }

  log_message("INFO", "Wrote self-contained HTML report to %s", output_path)
  list(path = output_path, warnings = rendered$warnings, elapsed = rendered$elapsed)
}


run_backend_comparison <- function(args) {
  outcome_names <- c(
    "log_lines_added_py_source",
    "log_lines_added_py_no_merge",
    "log_lines_added_py_source_no_tests",
    "log_lines_added_py_all"
  )
  primary_outcome <- "log_lines_added_py_source"
  robustness_outcomes <- setdiff(outcome_names, primary_outcome)
  expected_primary_metadata <- "log_lines_added_py_source"
  expected_robustness_metadata <- "log_lines_added_py_no_merge|log_lines_added_py_source_no_tests|log_lines_added_py_all"
  expected_velocity_version <- "v4"
  covariate_spec <- tolower(require_arg(args, "covariate_spec"))
  if (!covariate_spec %in% c("python_ncloc_adjusted", "no_covariates")) {
    abortf("--covariate-spec must be python_ncloc_adjusted or no_covariates: %s", covariate_spec)
  }
  sonarqube_input_file <- normalizePath(require_arg(args, "sonarqube_input_file"), mustWork = TRUE)
  cloc_input_file <- normalizePath(require_arg(args, "cloc_input_file"), mustWork = TRUE)
  sonarqube_output_dir <- normalizePath(require_arg(args, "sonarqube_output_dir"), mustWork = TRUE)
  cloc_output_dir <- normalizePath(require_arg(args, "cloc_output_dir"), mustWork = TRUE)
  comparison_output_dir <- require_arg(args, "comparison_output_dir")
  comparison_summary_output <- require_arg(args, "comparison_summary_output")
  expected_rows <- as_integer_arg(args, "expected_rows", -1L)
  strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)

  check_packages(c("data.table", "ggplot2"))
  dir.create(comparison_output_dir, recursive = TRUE, showWarnings = FALSE)
  plot_dir <- file.path(comparison_output_dir, "plots")
  dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)
  ensure_parent_dir(comparison_summary_output)

  sq_prefix <- paste0("velocity_python_added_lines_sonarqube_", covariate_spec)
  cloc_prefix <- paste0("velocity_python_added_lines_cloc_", covariate_spec)
  comparison_prefix <- paste0("velocity_python_added_lines_backend_", covariate_spec)

  input_paths <- list(
    sonarqube_static = file.path(sonarqube_output_dir, paste0(sq_prefix, "_static_effects.csv")),
    sonarqube_dynamic = file.path(sonarqube_output_dir, paste0(sq_prefix, "_dynamic_effects.csv")),
    sonarqube_pretrend_checks = file.path(sonarqube_output_dir, paste0(sq_prefix, "_pretrend_checks.csv")),
    sonarqube_pretrend_summary = file.path(sonarqube_output_dir, paste0(sq_prefix, "_pretrend_summary.csv")),
    cloc_static = file.path(cloc_output_dir, paste0(cloc_prefix, "_static_effects.csv")),
    cloc_dynamic = file.path(cloc_output_dir, paste0(cloc_prefix, "_dynamic_effects.csv")),
    cloc_pretrend_checks = file.path(cloc_output_dir, paste0(cloc_prefix, "_pretrend_checks.csv")),
    cloc_pretrend_summary = file.path(cloc_output_dir, paste0(cloc_prefix, "_pretrend_summary.csv"))
  )
  missing_inputs <- names(input_paths)[!vapply(input_paths, file.exists, logical(1))]
  if (length(missing_inputs) > 0L) {
    abortf("Comparison inputs are missing: %s", paste(missing_inputs, collapse = ", "))
  }

  sq_panel <- data.table::fread(sonarqube_input_file, na.strings = c("", "NA", "NaN"))
  cloc_panel <- data.table::fread(cloc_input_file, na.strings = c("", "NA", "NaN"))
  strict_count_check(nrow(sq_panel), expected_rows, "SonarQube comparison panel rows", strict_expected_counts)
  strict_count_check(nrow(cloc_panel), expected_rows, "cloc comparison panel rows", strict_expected_counts)

  key_columns <- c("repo_id", "time_index")
  comparison_columns <- c(
    "repo_id", "repo_name", "scope_role", "treatment_group", "time", "time_index",
    "event", "event_index", "time_to_event",
    "log_lines_added_py_source", "log_lines_added_py_no_merge",
    "log_lines_added_py_source_no_tests", "log_lines_added_py_all",
    "log_age", "log_contributors", "log_stars", "log_issues",
    "did_primary_outcome", "did_robustness_outcomes", "python_velocity_metric_version"
  )
  validate_columns(sq_panel, c(comparison_columns, "ncloc", "ncloc_backend", "ncloc_py_sonarqube"))
  validate_columns(cloc_panel, c(comparison_columns, "ncloc", "ncloc_backend", "ncloc_py_cloc"))
  data.table::setorderv(sq_panel, key_columns)
  data.table::setorderv(cloc_panel, key_columns)

  key_mismatches <- sum(
    sq_panel$repo_id != cloc_panel$repo_id |
    sq_panel$time_index != cloc_panel$time_index
  )
  non_ncloc_mismatches <- 0L
  if (key_mismatches == 0L && nrow(sq_panel) == nrow(cloc_panel)) {
    for (column in comparison_columns) {
      left <- sq_panel[[column]]
      right <- cloc_panel[[column]]
      equal <- (is.na(left) & is.na(right)) | (!is.na(left) & !is.na(right) & as.character(left) == as.character(right))
      non_ncloc_mismatches <- non_ncloc_mismatches + sum(!equal)
    }
  } else {
    non_ncloc_mismatches <- max(nrow(sq_panel), nrow(cloc_panel))
  }
  if (key_mismatches > 0L || non_ncloc_mismatches > 0L) {
    abortf(
      "Backend panels are not an exact common sample: key_mismatches=%d; non_ncloc_field_mismatches=%d",
      key_mismatches, non_ncloc_mismatches
    )
  }

  sq_alias_mismatches <- sum(
    is.na(sq_panel$ncloc) != is.na(sq_panel$ncloc_py_sonarqube) |
    (!is.na(sq_panel$ncloc) & !is.na(sq_panel$ncloc_py_sonarqube) & sq_panel$ncloc != sq_panel$ncloc_py_sonarqube)
  )
  cloc_alias_mismatches <- sum(
    is.na(cloc_panel$ncloc) != is.na(cloc_panel$ncloc_py_cloc) |
    (!is.na(cloc_panel$ncloc) & !is.na(cloc_panel$ncloc_py_cloc) & cloc_panel$ncloc != cloc_panel$ncloc_py_cloc)
  )
  if (sq_alias_mismatches > 0L || cloc_alias_mismatches > 0L) {
    abortf(
      "Backend ncloc alias mismatch: sonarqube=%d; cloc=%d",
      sq_alias_mismatches, cloc_alias_mismatches
    )
  }

  metadata_checks <- list(
    primary = expected_primary_metadata,
    robustness = expected_robustness_metadata,
    version = expected_velocity_version
  )
  sq_primary_mismatch <- sum(as.character(sq_panel$did_primary_outcome) != metadata_checks$primary, na.rm = TRUE) + sum(is.na(sq_panel$did_primary_outcome))
  cloc_primary_mismatch <- sum(as.character(cloc_panel$did_primary_outcome) != metadata_checks$primary, na.rm = TRUE) + sum(is.na(cloc_panel$did_primary_outcome))
  sq_robustness_mismatch <- sum(as.character(sq_panel$did_robustness_outcomes) != metadata_checks$robustness, na.rm = TRUE) + sum(is.na(sq_panel$did_robustness_outcomes))
  cloc_robustness_mismatch <- sum(as.character(cloc_panel$did_robustness_outcomes) != metadata_checks$robustness, na.rm = TRUE) + sum(is.na(cloc_panel$did_robustness_outcomes))
  sq_version_mismatch <- sum(as.character(sq_panel$python_velocity_metric_version) != metadata_checks$version, na.rm = TRUE) + sum(is.na(sq_panel$python_velocity_metric_version))
  cloc_version_mismatch <- sum(as.character(cloc_panel$python_velocity_metric_version) != metadata_checks$version, na.rm = TRUE) + sum(is.na(cloc_panel$python_velocity_metric_version))
  metadata_mismatch_total <- sq_primary_mismatch + cloc_primary_mismatch +
    sq_robustness_mismatch + cloc_robustness_mismatch + sq_version_mismatch + cloc_version_mismatch
  if (metadata_mismatch_total > 0L) {
    abortf(
      "Python velocity metadata mismatch: primary=%d/%d; robustness=%d/%d; version=%d/%d",
      sq_primary_mismatch, cloc_primary_mismatch, sq_robustness_mismatch,
      cloc_robustness_mismatch, sq_version_mismatch, cloc_version_mismatch
    )
  }

  sq_static <- data.table::fread(input_paths$sonarqube_static)
  cloc_static <- data.table::fread(input_paths$cloc_static)
  sq_dynamic <- data.table::fread(input_paths$sonarqube_dynamic)
  cloc_dynamic <- data.table::fread(input_paths$cloc_dynamic)
  sq_pretrend_checks <- data.table::fread(input_paths$sonarqube_pretrend_checks)
  cloc_pretrend_checks <- data.table::fread(input_paths$cloc_pretrend_checks)
  sq_pretrend_summary <- data.table::fread(input_paths$sonarqube_pretrend_summary)
  cloc_pretrend_summary <- data.table::fread(input_paths$cloc_pretrend_summary)

  for (table in list(sq_static, sq_dynamic, sq_pretrend_checks, sq_pretrend_summary,
                     cloc_static, cloc_dynamic, cloc_pretrend_checks, cloc_pretrend_summary)) {
    validate_columns(table, c("covariate_spec"))
    if (any(is.na(table$covariate_spec)) || any(table$covariate_spec != covariate_spec)) {
      abortf("Backend comparison found output rows from the wrong covariate specification; expected %s.", covariate_spec)
    }
  }

  static_all <- data.table::rbindlist(list(sq_static, cloc_static), fill = TRUE, use.names = TRUE)
  dynamic_all <- data.table::rbindlist(list(sq_dynamic, cloc_dynamic), fill = TRUE, use.names = TRUE)
  pretrend_checks_all <- data.table::rbindlist(list(sq_pretrend_checks, cloc_pretrend_checks), fill = TRUE, use.names = TRUE)
  pretrend_summary_all <- data.table::rbindlist(list(sq_pretrend_summary, cloc_pretrend_summary), fill = TRUE, use.names = TRUE)

  static_sq <- sq_static[, .(
    outcome, outcome_label,
    sonarqube_estimate = estimate,
    sonarqube_std_error = std.error,
    sonarqube_conf_low = conf.low,
    sonarqube_conf_high = conf.high,
    sonarqube_p_value = p_value,
    sonarqube_significant = significant
  )]
  static_cloc <- cloc_static[, .(
    outcome, outcome_label,
    cloc_estimate = estimate,
    cloc_std_error = std.error,
    cloc_conf_low = conf.low,
    cloc_conf_high = conf.high,
    cloc_p_value = p_value,
    cloc_significant = significant
  )]
  static_differences <- merge(static_sq, static_cloc, by = c("outcome", "outcome_label"), all = TRUE, sort = FALSE)
  static_differences[, `:=`(
    estimate_difference_sonarqube_minus_cloc = sonarqube_estimate - cloc_estimate,
    absolute_estimate_difference = abs(sonarqube_estimate - cloc_estimate),
    inference_note = "Descriptive difference only; no standard error for the difference is estimated."
  )]

  dynamic_sq <- sq_dynamic[, .(
    outcome, outcome_label, event_time, term_type, support_rows, support_repositories,
    sonarqube_estimate = estimate,
    sonarqube_std_error = std.error,
    sonarqube_conf_low = conf.low,
    sonarqube_conf_high = conf.high,
    sonarqube_p_value = p_value,
    sonarqube_significant = significant
  )]
  dynamic_cloc <- cloc_dynamic[, .(
    outcome, outcome_label, event_time, term_type, support_rows, support_repositories,
    cloc_estimate = estimate,
    cloc_std_error = std.error,
    cloc_conf_low = conf.low,
    cloc_conf_high = conf.high,
    cloc_p_value = p_value,
    cloc_significant = significant
  )]
  dynamic_differences <- merge(
    dynamic_sq, dynamic_cloc,
    by = c("outcome", "outcome_label", "event_time", "term_type", "support_rows", "support_repositories"),
    all = TRUE, sort = FALSE
  )
  dynamic_differences[, `:=`(
    estimate_difference_sonarqube_minus_cloc = sonarqube_estimate - cloc_estimate,
    absolute_estimate_difference = abs(sonarqube_estimate - cloc_estimate),
    inference_note = "Descriptive difference only; no standard error for the difference is estimated."
  )]
  data.table::setorder(dynamic_differences, outcome, event_time)

  # Compare every robustness outcome with the primary source-added-lines outcome
  # within the same NCLOC backend. These are descriptive estimate differences;
  # they are not additional hypothesis tests for the difference between models.
  primary_static <- static_all[outcome == primary_outcome, .(
    ncloc_backend, ncloc_backend_label,
    primary_outcome = outcome, primary_outcome_label = outcome_label,
    primary_estimate = estimate, primary_std_error = std.error,
    primary_conf_low = conf.low, primary_conf_high = conf.high,
    primary_p_value = p_value, primary_significant = significant
  )]
  robustness_static <- static_all[outcome %in% robustness_outcomes, .(
    ncloc_backend, ncloc_backend_label,
    robustness_outcome = outcome, robustness_outcome_label = outcome_label,
    robustness_estimate = estimate, robustness_std_error = std.error,
    robustness_conf_low = conf.low, robustness_conf_high = conf.high,
    robustness_p_value = p_value, robustness_significant = significant
  )]
  outcome_static_differences <- merge(
    robustness_static, primary_static,
    by = c("ncloc_backend", "ncloc_backend_label"), all.x = TRUE, sort = FALSE
  )
  outcome_static_differences[, `:=`(
    estimate_difference_robustness_minus_primary = robustness_estimate - primary_estimate,
    absolute_estimate_difference = abs(robustness_estimate - primary_estimate),
    inference_note = "Descriptive difference only; no standard error for the difference is estimated."
  )]
  data.table::setorder(outcome_static_differences, ncloc_backend, robustness_outcome)

  primary_dynamic <- dynamic_all[outcome == primary_outcome, .(
    ncloc_backend, ncloc_backend_label, event_time, term_type,
    primary_outcome = outcome, primary_outcome_label = outcome_label,
    primary_estimate = estimate, primary_std_error = std.error,
    primary_conf_low = conf.low, primary_conf_high = conf.high,
    primary_p_value = p_value, primary_significant = significant,
    primary_support_rows = support_rows, primary_support_repositories = support_repositories
  )]
  robustness_dynamic <- dynamic_all[outcome %in% robustness_outcomes, .(
    ncloc_backend, ncloc_backend_label, event_time, term_type,
    robustness_outcome = outcome, robustness_outcome_label = outcome_label,
    robustness_estimate = estimate, robustness_std_error = std.error,
    robustness_conf_low = conf.low, robustness_conf_high = conf.high,
    robustness_p_value = p_value, robustness_significant = significant,
    robustness_support_rows = support_rows, robustness_support_repositories = support_repositories
  )]
  outcome_dynamic_differences <- merge(
    robustness_dynamic, primary_dynamic,
    by = c("ncloc_backend", "ncloc_backend_label", "event_time", "term_type"),
    all.x = TRUE, sort = FALSE
  )
  outcome_dynamic_differences[, `:=`(
    estimate_difference_robustness_minus_primary = robustness_estimate - primary_estimate,
    absolute_estimate_difference = abs(robustness_estimate - primary_estimate),
    support_rows_match = robustness_support_rows == primary_support_rows,
    support_repositories_match = robustness_support_repositories == primary_support_repositories,
    inference_note = "Descriptive difference only; no standard error for the difference is estimated."
  )]
  data.table::setorder(outcome_dynamic_differences, ncloc_backend, robustness_outcome, event_time)

  outcome_pretrend_summary <- pretrend_summary_all[, .(
    ncloc_backend, ncloc_backend_label, outcome, outcome_label,
    all_ci_include_zero, periods_excluding_zero, minimum_p_value
  )]
  outcome_pretrend_summary[, outcome_role := ifelse(outcome == primary_outcome, "primary", "robustness")]
  data.table::setorder(outcome_pretrend_summary, ncloc_backend, outcome_role, outcome)

  output_paths <- list(
    static_all = file.path(comparison_output_dir, paste0(comparison_prefix, "_static_effects.csv")),
    dynamic_all = file.path(comparison_output_dir, paste0(comparison_prefix, "_dynamic_effects.csv")),
    pretrend_checks_all = file.path(comparison_output_dir, paste0(comparison_prefix, "_pretrend_checks.csv")),
    pretrend_summary_all = file.path(comparison_output_dir, paste0(comparison_prefix, "_pretrend_summary.csv")),
    static_differences = file.path(comparison_output_dir, paste0(comparison_prefix, "_static_differences.csv")),
    dynamic_differences = file.path(comparison_output_dir, paste0(comparison_prefix, "_dynamic_differences.csv")),
    outcome_static_differences = file.path(comparison_output_dir, paste0("velocity_python_added_lines_outcome_robustness_", covariate_spec, "_static_differences.csv")),
    outcome_dynamic_differences = file.path(comparison_output_dir, paste0("velocity_python_added_lines_outcome_robustness_", covariate_spec, "_dynamic_differences.csv")),
    outcome_pretrend_summary = file.path(comparison_output_dir, paste0("velocity_python_added_lines_outcome_robustness_", covariate_spec, "_pretrend_summary.csv")),
    panel_qc = file.path(comparison_output_dir, paste0(comparison_prefix, "_panel_alignment_qc.csv")),
    plot_pdf = file.path(plot_dir, paste0(comparison_prefix, "_dynamic_effects.pdf")),
    plot_png = file.path(plot_dir, paste0(comparison_prefix, "_dynamic_effects.png"))
  )

  expected_static_rows <- 2L * length(outcome_names)
  expected_dynamic_rows <- 2L * length(outcome_names) * data.table::uniqueN(dynamic_all$event_time)
  expected_pretrend_rows <- 2L * length(outcome_names) * data.table::uniqueN(pretrend_checks_all$event_time)
  expected_pretrend_summary_rows <- 2L * length(outcome_names)
  expected_outcome_static_diff_rows <- 2L * length(robustness_outcomes)
  expected_outcome_dynamic_diff_rows <- 2L * length(robustness_outcomes) * data.table::uniqueN(dynamic_all$event_time)
  support_mismatch_rows <- outcome_dynamic_differences[support_rows_match == FALSE | support_repositories_match == FALSE, .N]

  panel_qc <- data.table::data.table(
    check_name = c(
      "sonarqube_panel_rows", "cloc_panel_rows", "backend_panel_key_mismatches",
      "backend_panel_non_ncloc_field_mismatches", "sonarqube_ncloc_alias_mismatches",
      "cloc_ncloc_alias_mismatches", "python_velocity_metadata_mismatches",
      "static_effect_rows", "dynamic_effect_rows", "pretrend_check_rows",
      "pretrend_summary_rows", "outcome_robustness_static_difference_rows",
      "outcome_robustness_dynamic_difference_rows", "outcome_robustness_support_mismatches"
    ),
    status = c(
      ifelse(expected_rows < 0L || nrow(sq_panel) == expected_rows, "pass", "fail"),
      ifelse(expected_rows < 0L || nrow(cloc_panel) == expected_rows, "pass", "fail"),
      ifelse(key_mismatches == 0L, "pass", "fail"),
      ifelse(non_ncloc_mismatches == 0L, "pass", "fail"),
      ifelse(sq_alias_mismatches == 0L, "pass", "fail"),
      ifelse(cloc_alias_mismatches == 0L, "pass", "fail"),
      ifelse(metadata_mismatch_total == 0L, "pass", "fail"),
      ifelse(nrow(static_all) == expected_static_rows, "pass", "fail"),
      ifelse(nrow(dynamic_all) == expected_dynamic_rows, "pass", "fail"),
      ifelse(nrow(pretrend_checks_all) == expected_pretrend_rows, "pass", "fail"),
      ifelse(nrow(pretrend_summary_all) == expected_pretrend_summary_rows, "pass", "fail"),
      ifelse(nrow(outcome_static_differences) == expected_outcome_static_diff_rows, "pass", "fail"),
      ifelse(nrow(outcome_dynamic_differences) == expected_outcome_dynamic_diff_rows, "pass", "fail"),
      ifelse(support_mismatch_rows == 0L, "pass", "fail")
    ),
    observed = c(
      nrow(sq_panel), nrow(cloc_panel), key_mismatches, non_ncloc_mismatches,
      sq_alias_mismatches, cloc_alias_mismatches, metadata_mismatch_total,
      nrow(static_all), nrow(dynamic_all), nrow(pretrend_checks_all),
      nrow(pretrend_summary_all), nrow(outcome_static_differences),
      nrow(outcome_dynamic_differences), support_mismatch_rows
    ),
    expected = c(
      expected_rows, expected_rows, 0, 0, 0, 0, 0, expected_static_rows,
      expected_dynamic_rows, expected_pretrend_rows, expected_pretrend_summary_rows,
      expected_outcome_static_diff_rows, expected_outcome_dynamic_diff_rows, 0
    ),
    note = c(
      "", "", "", "Only ncloc and backend-specific provenance may differ.",
      "", "", "Requires run-x-b02-v4 primary/robustness metadata.",
      "Four outcomes times two backends.",
      "All package-native placebo and post-treatment terms for four outcomes times two backends.",
      "Placebo terms for four outcomes times two backends.",
      "Four outcome pretrend summaries times two backends.",
      "Three robustness outcomes compared with the primary within each backend.",
      "Three robustness outcomes times both backends times every dynamic/pretrend term.",
      "Outcome definitions must use identical treatment-support rows within each backend."
    )
  )
  if (any(panel_qc$status == "fail")) {
    abortf("Backend comparison QC failed: %s", paste(panel_qc[status == "fail", check_name], collapse = ", "))
  }

  write_csv(static_all, output_paths$static_all)
  write_csv(dynamic_all, output_paths$dynamic_all)
  write_csv(pretrend_checks_all, output_paths$pretrend_checks_all)
  write_csv(pretrend_summary_all, output_paths$pretrend_summary_all)
  write_csv(static_differences, output_paths$static_differences)
  write_csv(dynamic_differences, output_paths$dynamic_differences)
  write_csv(outcome_static_differences, output_paths$outcome_static_differences)
  write_csv(outcome_dynamic_differences, output_paths$outcome_dynamic_differences)
  write_csv(outcome_pretrend_summary, output_paths$outcome_pretrend_summary)
  write_csv(panel_qc, output_paths$panel_qc)

  plot_data <- dynamic_all[event_time >= -6L & event_time <= 6L]
  plot_data[, backend_display := factor(ncloc_backend_label, levels = c("SonarQube", "cloc"))]
  plot_object <- ggplot2::ggplot(
    plot_data,
    ggplot2::aes(x = event_time, y = estimate, shape = backend_display, linetype = backend_display)
  ) +
    ggplot2::geom_errorbar(
      ggplot2::aes(ymin = conf.low, ymax = conf.high),
      width = 0.25,
      position = ggplot2::position_dodge(width = 0.30)
    ) +
    ggplot2::geom_point(size = 1.8, position = ggplot2::position_dodge(width = 0.30)) +
    ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.30)) +
    ggplot2::geom_hline(yintercept = 0, linetype = "dashed") +
    ggplot2::geom_vline(xintercept = -0.5, linetype = "dashed") +
    ggplot2::scale_x_continuous(breaks = seq.int(-6L, 6L, by = 1L)) +
    ggplot2::coord_cartesian(xlim = c(-6.5, 6.5)) +
    ggplot2::labs(
      x = "Months Relative to Cursor Adoption",
      y = "Treatment Effect",
      shape = "Python NCLOC Backend",
      linetype = "Python NCLOC Backend",
      caption = "Same repository-month sample and outcome definition within each facet; only the Python-NCLOC backend changes."
    ) +
    ggplot2::theme_minimal() +
    ggplot2::theme(
      legend.position = "bottom",
      panel.grid.major.x = ggplot2::element_blank(),
      panel.grid.minor.x = ggplot2::element_blank(),
      plot.caption = ggplot2::element_text(hjust = 0.5, size = 9)
    ) +
    ggplot2::facet_wrap(~outcome_label, scales = "free_y", nrow = 2)

  ggplot2::ggsave(output_paths$plot_pdf, plot_object, width = 12, height = 7.5, units = "in", bg = "white")
  ggplot2::ggsave(output_paths$plot_png, plot_object, width = 12, height = 7.5, units = "in", dpi = 180, bg = "white")

  summary_rows <- list(
    make_summary_row("implementation", "version", "v3"),
    make_summary_row("definition", "comparison", "two_ncloc_backends_by_four_python_velocity_outcomes"),
    make_summary_row("definition", "covariate_spec", covariate_spec),
    make_summary_row("definition", "primary_outcome", primary_outcome),
    make_summary_row("definition", "robustness_outcomes", paste(robustness_outcomes, collapse = "|")),
    make_summary_row("input", "panel_rows_per_backend", nrow(sq_panel)),
    make_summary_row("qc", "backend_panel_key_mismatches", key_mismatches),
    make_summary_row("qc", "backend_panel_non_ncloc_field_mismatches", non_ncloc_mismatches),
    make_summary_row("qc", "sonarqube_ncloc_alias_mismatches", sq_alias_mismatches),
    make_summary_row("qc", "cloc_ncloc_alias_mismatches", cloc_alias_mismatches),
    make_summary_row("qc", "python_velocity_metadata_mismatches", metadata_mismatch_total),
    make_summary_row("output", "static_effect_rows", nrow(static_all)),
    make_summary_row("output", "dynamic_effect_rows", nrow(dynamic_all)),
    make_summary_row("output", "pretrend_check_rows", nrow(pretrend_checks_all)),
    make_summary_row("output", "outcome_robustness_static_difference_rows", nrow(outcome_static_differences)),
    make_summary_row("output", "outcome_robustness_dynamic_difference_rows", nrow(outcome_dynamic_differences)),
    make_summary_row("artifact", "dynamic_comparison_plot_pdf", output_paths$plot_pdf),
    make_summary_row("artifact", "dynamic_comparison_plot_png", output_paths$plot_png)
  )
  for (outcome_name in unique(static_differences$outcome)) {
    row <- static_differences[outcome == outcome_name][1]
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "static_comparison", paste0(outcome_name, "_sonarqube_estimate"), row$sonarqube_estimate
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "static_comparison", paste0(outcome_name, "_cloc_estimate"), row$cloc_estimate
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "static_comparison", paste0(outcome_name, "_estimate_difference"),
      row$estimate_difference_sonarqube_minus_cloc,
      "SonarQube minus cloc; descriptive only."
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "static_comparison", paste0(outcome_name, "_sonarqube_p_value"), row$sonarqube_p_value
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "static_comparison", paste0(outcome_name, "_cloc_p_value"), row$cloc_p_value
    )
    sq_pre <- sq_pretrend_summary[outcome == outcome_name][1]
    cloc_pre <- cloc_pretrend_summary[outcome == outcome_name][1]
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "pretrend_comparison", paste0(outcome_name, "_sonarqube_all_ci_include_zero"), sq_pre$all_ci_include_zero
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "pretrend_comparison", paste0(outcome_name, "_cloc_all_ci_include_zero"), cloc_pre$all_ci_include_zero
    )
  }
  for (idx in seq_len(nrow(outcome_static_differences))) {
    row <- outcome_static_differences[idx]
    metric_prefix <- paste(row$ncloc_backend, row$robustness_outcome, sep = "__")
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "outcome_robustness", paste0(metric_prefix, "__estimate"), row$robustness_estimate
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "outcome_robustness", paste0(metric_prefix, "__primary_estimate"), row$primary_estimate
    )
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row(
      "outcome_robustness", paste0(metric_prefix, "__difference"),
      row$estimate_difference_robustness_minus_primary,
      "Robustness estimate minus primary estimate; descriptive only."
    )
  }
  comparison_summary <- data.table::rbindlist(summary_rows, fill = TRUE, use.names = TRUE)
  write_csv(comparison_summary, comparison_summary_output)

  log_message(
    "INFO",
    "Completed run-x-b03-v3 backend comparison covariate_spec=%s: static=%d; dynamic=%d; pretrend=%d; panel_rows=%d",
    covariate_spec, nrow(static_all), nrow(dynamic_all), nrow(pretrend_checks_all), nrow(sq_panel)
  )
}


run_covariate_comparison <- function(args) {
  check_packages(c("data.table", "ggplot2"))

  adjusted_sonarqube_dir <- normalizePath(require_arg(args, "adjusted_sonarqube_output_dir"), mustWork = TRUE)
  adjusted_cloc_dir <- normalizePath(require_arg(args, "adjusted_cloc_output_dir"), mustWork = TRUE)
  no_cov_sonarqube_dir <- normalizePath(require_arg(args, "no_covariates_sonarqube_output_dir"), mustWork = TRUE)
  no_cov_cloc_dir <- normalizePath(require_arg(args, "no_covariates_cloc_output_dir"), mustWork = TRUE)
  comparison_output_dir <- require_arg(args, "comparison_output_dir")
  comparison_summary_output <- require_arg(args, "comparison_summary_output")
  strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)
  tolerance <- as_numeric_arg(args, "backend_equivalence_tolerance", 1e-8)

  dir.create(comparison_output_dir, recursive = TRUE, showWarnings = FALSE)
  plot_dir <- file.path(comparison_output_dir, "plots")
  dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)
  ensure_parent_dir(comparison_summary_output)

  specs <- data.table::data.table(
    covariate_spec = c("python_ncloc_adjusted", "no_covariates"),
    covariate_spec_label = c("Python NCLOC adjusted", "No contemporaneous covariates")
  )
  outcomes <- c(
    "log_lines_added_py_source",
    "log_lines_added_py_no_merge",
    "log_lines_added_py_source_no_tests",
    "log_lines_added_py_all"
  )
  primary_outcome <- "log_lines_added_py_source"

  entries <- list(
    list(backend = "sonarqube", spec = "python_ncloc_adjusted", dir = adjusted_sonarqube_dir),
    list(backend = "cloc", spec = "python_ncloc_adjusted", dir = adjusted_cloc_dir),
    list(backend = "sonarqube", spec = "no_covariates", dir = no_cov_sonarqube_dir),
    list(backend = "cloc", spec = "no_covariates", dir = no_cov_cloc_dir)
  )

  static_parts <- list()
  dynamic_parts <- list()
  pretrend_check_parts <- list()
  pretrend_summary_parts <- list()

  for (entry in entries) {
    prefix <- paste0("velocity_python_added_lines_", entry$backend, "_", entry$spec)
    paths <- list(
      static = file.path(entry$dir, paste0(prefix, "_static_effects.csv")),
      dynamic = file.path(entry$dir, paste0(prefix, "_dynamic_effects.csv")),
      pretrend_checks = file.path(entry$dir, paste0(prefix, "_pretrend_checks.csv")),
      pretrend_summary = file.path(entry$dir, paste0(prefix, "_pretrend_summary.csv"))
    )
    missing <- names(paths)[!vapply(paths, file.exists, logical(1))]
    if (length(missing) > 0L) {
      abortf("Covariate-comparison inputs are missing for backend=%s spec=%s: %s",
             entry$backend, entry$spec, paste(missing, collapse = ", "))
    }

    static <- data.table::fread(paths$static)
    dynamic <- data.table::fread(paths$dynamic)
    pretrend_checks <- data.table::fread(paths$pretrend_checks)
    pretrend_summary <- data.table::fread(paths$pretrend_summary)

    for (table in list(static, dynamic, pretrend_checks, pretrend_summary)) {
      validate_columns(table, c("ncloc_backend", "covariate_spec", "outcome"))
      if (any(table$ncloc_backend != entry$backend) || any(table$covariate_spec != entry$spec)) {
        abortf("Covariate-comparison provenance mismatch for backend=%s spec=%s", entry$backend, entry$spec)
      }
    }
    static_parts[[length(static_parts) + 1L]] <- static
    dynamic_parts[[length(dynamic_parts) + 1L]] <- dynamic
    pretrend_check_parts[[length(pretrend_check_parts) + 1L]] <- pretrend_checks
    pretrend_summary_parts[[length(pretrend_summary_parts) + 1L]] <- pretrend_summary
  }

  static_all <- data.table::rbindlist(static_parts, fill = TRUE, use.names = TRUE)
  dynamic_all <- data.table::rbindlist(dynamic_parts, fill = TRUE, use.names = TRUE)
  pretrend_checks_all <- data.table::rbindlist(pretrend_check_parts, fill = TRUE, use.names = TRUE)
  pretrend_summary_all <- data.table::rbindlist(pretrend_summary_parts, fill = TRUE, use.names = TRUE)

  data.table::setorder(static_all, ncloc_backend, covariate_spec, outcome)
  data.table::setorder(dynamic_all, ncloc_backend, covariate_spec, outcome, event_time)
  data.table::setorder(pretrend_checks_all, ncloc_backend, covariate_spec, outcome, event_time)
  data.table::setorder(pretrend_summary_all, ncloc_backend, covariate_spec, outcome)

  adjusted_static <- static_all[covariate_spec == "python_ncloc_adjusted", .(
    ncloc_backend, ncloc_backend_label, outcome, outcome_label,
    adjusted_estimate = estimate, adjusted_std_error = std.error,
    adjusted_conf_low = conf.low, adjusted_conf_high = conf.high,
    adjusted_p_value = p_value, adjusted_significant = significant
  )]
  no_cov_static <- static_all[covariate_spec == "no_covariates", .(
    ncloc_backend, ncloc_backend_label, outcome, outcome_label,
    no_covariates_estimate = estimate, no_covariates_std_error = std.error,
    no_covariates_conf_low = conf.low, no_covariates_conf_high = conf.high,
    no_covariates_p_value = p_value, no_covariates_significant = significant
  )]
  static_differences <- merge(
    adjusted_static, no_cov_static,
    by = c("ncloc_backend", "ncloc_backend_label", "outcome", "outcome_label"),
    all = TRUE, sort = FALSE
  )
  static_differences[, `:=`(
    estimate_difference_adjusted_minus_no_covariates = adjusted_estimate - no_covariates_estimate,
    absolute_estimate_difference = abs(adjusted_estimate - no_covariates_estimate),
    inference_note = "Descriptive paired specification difference; no standard error for the difference is estimated."
  )]
  data.table::setorder(static_differences, ncloc_backend, outcome)

  adjusted_dynamic <- dynamic_all[covariate_spec == "python_ncloc_adjusted", .(
    ncloc_backend, ncloc_backend_label, outcome, outcome_label, event_time, term_type,
    adjusted_support_rows = support_rows, adjusted_support_repositories = support_repositories,
    adjusted_estimate = estimate, adjusted_std_error = std.error,
    adjusted_conf_low = conf.low, adjusted_conf_high = conf.high,
    adjusted_p_value = p_value, adjusted_significant = significant
  )]
  no_cov_dynamic <- dynamic_all[covariate_spec == "no_covariates", .(
    ncloc_backend, ncloc_backend_label, outcome, outcome_label, event_time, term_type,
    no_covariates_support_rows = support_rows, no_covariates_support_repositories = support_repositories,
    no_covariates_estimate = estimate, no_covariates_std_error = std.error,
    no_covariates_conf_low = conf.low, no_covariates_conf_high = conf.high,
    no_covariates_p_value = p_value, no_covariates_significant = significant
  )]
  dynamic_differences <- merge(
    adjusted_dynamic, no_cov_dynamic,
    by = c("ncloc_backend", "ncloc_backend_label", "outcome", "outcome_label", "event_time", "term_type"),
    all = TRUE, sort = FALSE
  )
  dynamic_differences[, `:=`(
    support_rows_match = adjusted_support_rows == no_covariates_support_rows,
    support_repositories_match = adjusted_support_repositories == no_covariates_support_repositories,
    estimate_difference_adjusted_minus_no_covariates = adjusted_estimate - no_covariates_estimate,
    absolute_estimate_difference = abs(adjusted_estimate - no_covariates_estimate),
    inference_note = "Descriptive paired specification difference; no standard error for the difference is estimated."
  )]
  data.table::setorder(dynamic_differences, ncloc_backend, outcome, event_time)

  primary_static <- static_all[outcome == primary_outcome, .(
    ncloc_backend, ncloc_backend_label, covariate_spec, covariate_spec_label,
    outcome, outcome_label, estimate, std.error, conf.low, conf.high, p_value, significant
  )]
  primary_pretrend <- pretrend_summary_all[outcome == primary_outcome, .(
    ncloc_backend, covariate_spec, all_ci_include_zero, periods_excluding_zero, minimum_p_value
  )]
  primary_summary <- merge(
    primary_static, primary_pretrend,
    by = c("ncloc_backend", "covariate_spec"), all.x = TRUE, sort = FALSE
  )
  data.table::setorder(primary_summary, ncloc_backend, covariate_spec)

  event_minus2 <- dynamic_all[outcome == primary_outcome & event_time == -2L, .(
    ncloc_backend, ncloc_backend_label, covariate_spec, covariate_spec_label,
    outcome, outcome_label, event_time, estimate, std.error, conf.low, conf.high,
    p_value, significant, ci_includes_zero, support_rows, support_repositories
  )]
  data.table::setorder(event_minus2, ncloc_backend, covariate_spec)

  expected_static_rows <- 2L * 2L * length(outcomes)
  event_term_count <- data.table::uniqueN(dynamic_all$event_time)
  pretrend_term_count <- data.table::uniqueN(pretrend_checks_all$event_time)
  expected_dynamic_rows <- 2L * 2L * length(outcomes) * event_term_count
  expected_pretrend_check_rows <- 2L * 2L * length(outcomes) * pretrend_term_count
  expected_pretrend_summary_rows <- 2L * 2L * length(outcomes)
  expected_static_difference_rows <- 2L * length(outcomes)
  expected_dynamic_difference_rows <- 2L * length(outcomes) * event_term_count

  support_mismatches <- dynamic_differences[
    is.na(support_rows_match) | is.na(support_repositories_match) |
      support_rows_match == FALSE | support_repositories_match == FALSE,
    .N
  ]

  no_cov_static_backend <- merge(
    static_all[covariate_spec == "no_covariates" & ncloc_backend == "sonarqube", .(outcome, sq = estimate)],
    static_all[covariate_spec == "no_covariates" & ncloc_backend == "cloc", .(outcome, cloc = estimate)],
    by = "outcome", all = TRUE
  )
  no_cov_dynamic_backend <- merge(
    dynamic_all[covariate_spec == "no_covariates" & ncloc_backend == "sonarqube", .(outcome, event_time, sq = estimate)],
    dynamic_all[covariate_spec == "no_covariates" & ncloc_backend == "cloc", .(outcome, event_time, cloc = estimate)],
    by = c("outcome", "event_time"), all = TRUE
  )
  no_cov_static_max_backend_diff <- if (nrow(no_cov_static_backend) == 0L) NA_real_ else max(abs(no_cov_static_backend$sq - no_cov_static_backend$cloc), na.rm = TRUE)
  no_cov_dynamic_max_backend_diff <- if (nrow(no_cov_dynamic_backend) == 0L) NA_real_ else max(abs(no_cov_dynamic_backend$sq - no_cov_dynamic_backend$cloc), na.rm = TRUE)

  qc <- data.table::data.table(
    check_name = c(
      "static_rows", "dynamic_rows", "pretrend_check_rows", "pretrend_summary_rows",
      "static_difference_rows", "dynamic_difference_rows", "support_mismatches",
      "no_covariates_static_backend_equivalence", "no_covariates_dynamic_backend_equivalence"
    ),
    observed = c(
      nrow(static_all), nrow(dynamic_all), nrow(pretrend_checks_all), nrow(pretrend_summary_all),
      nrow(static_differences), nrow(dynamic_differences), support_mismatches,
      no_cov_static_max_backend_diff, no_cov_dynamic_max_backend_diff
    ),
    expected = c(
      expected_static_rows, expected_dynamic_rows, expected_pretrend_check_rows, expected_pretrend_summary_rows,
      expected_static_difference_rows, expected_dynamic_difference_rows, 0,
      0, 0
    ),
    status = c(
      ifelse(nrow(static_all) == expected_static_rows, "pass", "fail"),
      ifelse(nrow(dynamic_all) == expected_dynamic_rows, "pass", "fail"),
      ifelse(nrow(pretrend_checks_all) == expected_pretrend_check_rows, "pass", "fail"),
      ifelse(nrow(pretrend_summary_all) == expected_pretrend_summary_rows, "pass", "fail"),
      ifelse(nrow(static_differences) == expected_static_difference_rows, "pass", "fail"),
      ifelse(nrow(dynamic_differences) == expected_dynamic_difference_rows, "pass", "fail"),
      ifelse(support_mismatches == 0L, "pass", "fail"),
      ifelse(is.finite(no_cov_static_max_backend_diff) && no_cov_static_max_backend_diff <= tolerance, "pass", "fail"),
      ifelse(is.finite(no_cov_dynamic_max_backend_diff) && no_cov_dynamic_max_backend_diff <= tolerance, "pass", "fail")
    ),
    note = c(
      "Two backends x two covariate specifications x four outcomes.",
      "All package-native placebo and post-treatment terms.",
      "Five placebo periods for every backend/spec/outcome combination.",
      "One pretrend summary per backend/spec/outcome.",
      "Adjusted versus no-covariate static comparison within backend/outcome.",
      "Adjusted versus no-covariate dynamic comparison within backend/outcome/event time.",
      "Treatment support must be identical across covariate specifications.",
      sprintf("With no covariates, NCLOC backend is unused; estimates should match within tolerance %.3g.", tolerance),
      sprintf("With no covariates, NCLOC backend is unused; estimates should match within tolerance %.3g.", tolerance)
    )
  )
  if (strict_expected_counts && any(qc$status == "fail")) {
    abortf("Covariate sensitivity QC failed: %s", paste(qc[status == "fail", check_name], collapse = ", "))
  }

  prefix <- "velocity_python_added_lines_covariate_sensitivity"
  output_paths <- list(
    static_all = file.path(comparison_output_dir, paste0(prefix, "_static_effects.csv")),
    dynamic_all = file.path(comparison_output_dir, paste0(prefix, "_dynamic_effects.csv")),
    pretrend_checks_all = file.path(comparison_output_dir, paste0(prefix, "_pretrend_checks.csv")),
    pretrend_summary_all = file.path(comparison_output_dir, paste0(prefix, "_pretrend_summary.csv")),
    static_differences = file.path(comparison_output_dir, paste0(prefix, "_static_differences.csv")),
    dynamic_differences = file.path(comparison_output_dir, paste0(prefix, "_dynamic_differences.csv")),
    primary_summary = file.path(comparison_output_dir, paste0(prefix, "_primary_summary.csv")),
    event_minus2 = file.path(comparison_output_dir, paste0(prefix, "_primary_event_minus2.csv")),
    qc = file.path(comparison_output_dir, paste0(prefix, "_qc.csv")),
    plot_pdf = file.path(plot_dir, paste0(prefix, "_primary_dynamic_effects.pdf")),
    plot_png = file.path(plot_dir, paste0(prefix, "_primary_dynamic_effects.png"))
  )

  write_csv(static_all, output_paths$static_all)
  write_csv(dynamic_all, output_paths$dynamic_all)
  write_csv(pretrend_checks_all, output_paths$pretrend_checks_all)
  write_csv(pretrend_summary_all, output_paths$pretrend_summary_all)
  write_csv(static_differences, output_paths$static_differences)
  write_csv(dynamic_differences, output_paths$dynamic_differences)
  write_csv(primary_summary, output_paths$primary_summary)
  write_csv(event_minus2, output_paths$event_minus2)
  write_csv(qc, output_paths$qc)

  plot_data <- dynamic_all[outcome == primary_outcome & event_time >= -6L & event_time <= 6L]
  plot_data[, spec_display := factor(covariate_spec_label, levels = c("Python NCLOC adjusted", "No contemporaneous covariates"))]
  plot_object <- ggplot2::ggplot(
    plot_data,
    ggplot2::aes(x = event_time, y = estimate, shape = spec_display, linetype = spec_display)
  ) +
    ggplot2::geom_errorbar(
      ggplot2::aes(ymin = conf.low, ymax = conf.high),
      width = 0.25,
      position = ggplot2::position_dodge(width = 0.30)
    ) +
    ggplot2::geom_point(size = 1.8, position = ggplot2::position_dodge(width = 0.30)) +
    ggplot2::geom_line(position = ggplot2::position_dodge(width = 0.30)) +
    ggplot2::geom_hline(yintercept = 0, linetype = "dashed") +
    ggplot2::geom_vline(xintercept = -0.5, linetype = "dashed") +
    ggplot2::scale_x_continuous(breaks = seq.int(-6L, 6L, by = 1L)) +
    ggplot2::coord_cartesian(xlim = c(-6.5, 6.5)) +
    ggplot2::labs(
      x = "Months Relative to Cursor Adoption",
      y = "Treatment Effect",
      shape = "First-stage specification",
      linetype = "First-stage specification",
      caption = "Primary outcome only; same repository-month sample and treatment timing within each NCLOC backend."
    ) +
    ggplot2::theme_minimal() +
    ggplot2::theme(
      legend.position = "bottom",
      panel.grid.major.x = ggplot2::element_blank(),
      panel.grid.minor.x = ggplot2::element_blank(),
      plot.caption = ggplot2::element_text(hjust = 0.5, size = 9)
    ) +
    ggplot2::facet_wrap(~ncloc_backend_label, nrow = 1)

  ggplot2::ggsave(output_paths$plot_pdf, plot_object, width = 11, height = 5.5, units = "in", bg = "white")
  ggplot2::ggsave(output_paths$plot_png, plot_object, width = 11, height = 5.5, units = "in", dpi = 180, bg = "white")

  summary_rows <- list(
    make_summary_row("implementation", "version", "v3"),
    make_summary_row("definition", "comparison", "python_ncloc_adjusted_vs_no_covariates"),
    make_summary_row("definition", "primary_outcome", primary_outcome),
    make_summary_row("definition", "covariate_specs", paste(specs$covariate_spec, collapse = "|")),
    make_summary_row("definition", "backend_equivalence_tolerance", tolerance),
    make_summary_row("output", "static_rows", nrow(static_all)),
    make_summary_row("output", "dynamic_rows", nrow(dynamic_all)),
    make_summary_row("output", "pretrend_check_rows", nrow(pretrend_checks_all)),
    make_summary_row("output", "static_difference_rows", nrow(static_differences)),
    make_summary_row("output", "dynamic_difference_rows", nrow(dynamic_differences)),
    make_summary_row("qc", "support_mismatches", support_mismatches),
    make_summary_row("qc", "no_covariates_static_backend_max_abs_difference", no_cov_static_max_backend_diff),
    make_summary_row("qc", "no_covariates_dynamic_backend_max_abs_difference", no_cov_dynamic_max_backend_diff),
    make_summary_row("artifact", "primary_dynamic_plot_pdf", output_paths$plot_pdf),
    make_summary_row("artifact", "primary_dynamic_plot_png", output_paths$plot_png)
  )
  for (idx in seq_len(nrow(primary_summary))) {
    row <- primary_summary[idx]
    metric_prefix <- paste(row$ncloc_backend, row$covariate_spec, sep = "__")
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("primary_static", paste0(metric_prefix, "__estimate"), row$estimate)
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("primary_static", paste0(metric_prefix, "__p_value"), row$p_value)
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("primary_pretrend", paste0(metric_prefix, "__all_ci_include_zero"), row$all_ci_include_zero)
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("primary_pretrend", paste0(metric_prefix, "__periods_excluding_zero"), row$periods_excluding_zero)
    summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("primary_pretrend", paste0(metric_prefix, "__minimum_p_value"), row$minimum_p_value)
  }
  write_csv(data.table::rbindlist(summary_rows, fill = TRUE, use.names = TRUE), comparison_summary_output)

  log_message(
    "INFO",
    "Completed run-x-b03-v3 covariate comparison: static=%d; dynamic=%d; pretrend_checks=%d; paired_static=%d; paired_dynamic=%d",
    nrow(static_all), nrow(dynamic_all), nrow(pretrend_checks_all), nrow(static_differences), nrow(dynamic_differences)
  )
}


args <- parse_cli_args(commandArgs(trailingOnly = TRUE))
mode <- tolower(if (is.null(args$mode)) "backend" else as.character(args$mode))
if (mode == "compare") {
  run_backend_comparison(args)
  quit(save = "no", status = 0L)
}
if (mode == "covariate_compare") {
  run_covariate_comparison(args)
  quit(save = "no", status = 0L)
}
if (mode != "backend") abortf("--mode must be backend, compare, or covariate_compare: %s", mode)

backend <- tolower(require_arg(args, "backend"))
if (!backend %in% c("sonarqube", "cloc")) {
  abortf("--backend must be sonarqube or cloc: %s", backend)
}
backend_label <- if (backend == "sonarqube") "SonarQube" else "cloc"
backend_metric <- if (backend == "sonarqube") "ncloc_py_sonarqube" else "ncloc_py_cloc"
covariate_spec <- tolower(require_arg(args, "covariate_spec"))
covariate_specs <- list(
  python_ncloc_adjusted = list(
    label = "Python NCLOC adjusted",
    first_stage_formula = ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index,
    first_stage_formula_text = "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index",
    model_fields = c("log_age", "ncloc", "log_contributors", "log_stars", "log_issues")
  ),
  no_covariates = list(
    label = "No contemporaneous covariates",
    first_stage_formula = ~ 1 | repo_id + time_index,
    first_stage_formula_text = "~ 1 | repo_id + time_index",
    model_fields = character()
  )
)
if (!covariate_spec %in% names(covariate_specs)) {
  abortf("--covariate-spec must be python_ncloc_adjusted or no_covariates: %s", covariate_spec)
}
covariate_spec_label <- covariate_specs[[covariate_spec]]$label
first_stage_formula <- covariate_specs[[covariate_spec]]$first_stage_formula
first_stage_formula_text <- covariate_specs[[covariate_spec]]$first_stage_formula_text
artifact_prefix <- paste0("velocity_python_added_lines_", backend, "_", covariate_spec)

input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
output_dir <- require_arg(args, "output_dir")
summary_output <- require_arg(args, "summary_output")
html_output <- args$html_output
if (is.null(html_output) || !nzchar(as.character(html_output))) {
  html_output <- file.path(output_dir, paste0("velocity_python_added_lines_", backend, "_", covariate_spec, "_report.html"))
}
html_output <- as.character(html_output)
script_path <- args$script_path
if (is.null(script_path)) script_path <- NA_character_

plot_min_event <- as_integer_arg(args, "plot_min_event", -6L)
plot_max_event <- as_integer_arg(args, "plot_max_event", 6L)
pretrend_min <- as_integer_arg(args, "pretrend_min", -6L)
pretrend_max <- as_integer_arg(args, "pretrend_max", -2L)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)

expected_rows <- as_integer_arg(args, "expected_rows", -1L)
expected_treatment_repos <- as_integer_arg(args, "expected_treatment_repos", -1L)
expected_control_repos <- as_integer_arg(args, "expected_control_repos", -1L)
expected_untreated_rows <- as_integer_arg(args, "expected_untreated_rows", -1L)
expected_treated_rows <- as_integer_arg(args, "expected_treated_rows", -1L)
expected_dynamic_treated_rows <- as_integer_arg(args, "expected_dynamic_treated_rows", -1L)
expected_legacy_mismatch_rows <- as_integer_arg(args, "expected_legacy_mismatch_rows", -1L)
expected_legacy_mismatch_repos <- as_integer_arg(args, "expected_legacy_mismatch_repos", -1L)

if (plot_min_event > -2L) abortf("plot_min_event must include at least one pre-treatment period.")
if (plot_max_event < 0L) abortf("plot_max_event must be non-negative.")
if (pretrend_min > pretrend_max || pretrend_max >= -1L) abortf("Pretrend range must end at or before -2.")
if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1.")

required_packages <- c("data.table", "didimputation", "fixest", "ggplot2", "rmarkdown", "knitr")
check_packages(required_packages)
if (!rmarkdown::pandoc_available()) abortf("Pandoc is required for the run-x-b03 HTML report.")
i <- fixest::i

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
plot_dir <- file.path(output_dir, "plots")
dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)
ensure_parent_dir(summary_output)

paths <- list(
  static_effects = file.path(output_dir, paste0(artifact_prefix, "_static_effects.csv")),
  dynamic_effects = file.path(output_dir, paste0(artifact_prefix, "_dynamic_effects.csv")),
  pretrend_checks = file.path(output_dir, paste0(artifact_prefix, "_pretrend_checks.csv")),
  pretrend_summary = file.path(output_dir, paste0(artifact_prefix, "_pretrend_summary.csv")),
  event_support = file.path(output_dir, paste0(artifact_prefix, "_event_support.csv")),
  cohort_support = file.path(output_dir, paste0(artifact_prefix, "_cohort_support.csv")),
  sample_summary = file.path(output_dir, paste0(artifact_prefix, "_sample_summary.csv")),
  legacy_audit = file.path(output_dir, paste0(artifact_prefix, "_legacy_flag_audit.csv")),
  diagnostics = file.path(output_dir, paste0(artifact_prefix, "_diagnostics.csv")),
  metadata = file.path(output_dir, paste0(artifact_prefix, "_run_metadata.csv")),
  static_rds = file.path(output_dir, paste0(artifact_prefix, "_static_results.rds")),
  dynamic_rds = file.path(output_dir, paste0(artifact_prefix, "_dynamic_results.rds")),
  first_stage_rds = file.path(output_dir, paste0(artifact_prefix, "_first_stage_models.rds")),
  plot_pdf = file.path(plot_dir, paste0(artifact_prefix, "_dynamic_effects.pdf")),
  plot_png = file.path(plot_dir, paste0(artifact_prefix, "_dynamic_effects.png")),
  html_report = html_output
)

# Remove obsolete pretrend artifacts from earlier b03 revisions so they cannot
# be mistaken for outputs of the current package-native pretrend design.
stale_pretrend_paths <- c(
  file.path(output_dir, paste0(artifact_prefix, "_pretrend_joint_tests.csv")),
  file.path(output_dir, paste0(artifact_prefix, "_pretrend_models.rds"))
)
unlink(stale_pretrend_paths, force = TRUE)

run_started <- Sys.time()
log_message("INFO", "Reading %s Python velocity panel: %s", backend_label, input_file)
panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))

required_columns <- c(
  "repo_id", "repo_name", "scope_role", "treatment_group", "time", "time_index",
  "event", "event_index", "time_to_event",
  "log_lines_added_py_source", "log_lines_added_py_no_merge",
  "log_lines_added_py_source_no_tests", "log_lines_added_py_all",
  "log_age", "ncloc", "log_contributors", "log_stars", "log_issues",
  "is_treatment", "post_event", "cursor", "ncloc_backend", backend_metric,
  "did_primary_outcome", "did_robustness_outcomes", "python_velocity_metric_version"
)
validate_columns(panel, required_columns)

expected_primary_metadata <- "log_lines_added_py_source"
expected_robustness_metadata <- "log_lines_added_py_no_merge|log_lines_added_py_source_no_tests|log_lines_added_py_all"
expected_velocity_version <- "v4"
primary_metadata_mismatches <- sum(is.na(panel$did_primary_outcome) | as.character(panel$did_primary_outcome) != expected_primary_metadata)
robustness_metadata_mismatches <- sum(is.na(panel$did_robustness_outcomes) | as.character(panel$did_robustness_outcomes) != expected_robustness_metadata)
velocity_version_mismatches <- sum(is.na(panel$python_velocity_metric_version) | as.character(panel$python_velocity_metric_version) != expected_velocity_version)
if (primary_metadata_mismatches > 0L || robustness_metadata_mismatches > 0L || velocity_version_mismatches > 0L) {
  abortf(
    "Input Python velocity metadata mismatch: primary=%d; robustness=%d; version=%d",
    primary_metadata_mismatches, robustness_metadata_mismatches, velocity_version_mismatches
  )
}

backend_values <- unique(tolower(trimws(as.character(panel$ncloc_backend))))
if (length(backend_values) != 1L || backend_values[[1L]] != backend) {
  abortf("Input ncloc_backend must contain only %s; observed: %s", backend, paste(backend_values, collapse = ","))
}
selected_backend_values <- suppressWarnings(as.numeric(panel[[backend_metric]]))
generic_ncloc_values <- suppressWarnings(as.numeric(panel$ncloc))
alias_mismatch <- sum(
  is.na(selected_backend_values) != is.na(generic_ncloc_values) |
  (!is.na(selected_backend_values) & !is.na(generic_ncloc_values) & selected_backend_values != generic_ncloc_values)
)
if (alias_mismatch > 0L) {
  abortf("Found %d rows where generic ncloc does not match %s.", alias_mismatch, backend_metric)
}

numeric_columns <- c(
  "repo_id", "treatment_group", "time_index", "event_index", "time_to_event",
  "log_lines_added_py_source", "log_lines_added_py_no_merge",
  "log_lines_added_py_source_no_tests", "log_lines_added_py_all",
  "log_age", "ncloc", "log_contributors", "log_stars", "log_issues",
  "is_treatment", "post_event"
)
for (column in numeric_columns) panel[, (column) := suppressWarnings(as.numeric(get(column)))]

if (anyNA(panel$repo_id) || anyNA(panel$time_index) || anyNA(panel$event_index)) {
  abortf("repo_id, time_index, and event_index must be complete numeric columns.")
}
panel[, repo_id := as.integer(repo_id)]
panel[, time_index := as.integer(time_index)]
panel[, event_index := as.integer(event_index)]
panel[, treatment_group := as.integer(treatment_group)]

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
treatment_rows <- nrow(panel[treatment_group == 1L])
control_rows <- nrow(panel[treatment_group == 0L])
untreated_rows <- nrow(panel[absorbing_treated == 0L])
treated_rows <- nrow(panel[absorbing_treated == 1L])
dynamic_treated_rows <- nrow(panel[absorbing_treated == 1L & event_time_normalized >= 0L & event_time_normalized <= plot_max_event])

strict_count_check(input_rows, expected_rows, "input rows", strict_expected_counts)
strict_count_check(treatment_repos, expected_treatment_repos, "treatment repositories", strict_expected_counts)
strict_count_check(control_repos, expected_control_repos, "control repositories", strict_expected_counts)
strict_count_check(untreated_rows, expected_untreated_rows, "untreated first-stage rows", strict_expected_counts)
strict_count_check(treated_rows, expected_treated_rows, "treated rows", strict_expected_counts)
strict_count_check(dynamic_treated_rows, expected_dynamic_treated_rows, "dynamic treated rows", strict_expected_counts)

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

outcome_model_fields <- c(
  "log_lines_added_py_source", "log_lines_added_py_no_merge",
  "log_lines_added_py_source_no_tests", "log_lines_added_py_all"
)
model_fields <- c(outcome_model_fields, covariate_specs[[covariate_spec]]$model_fields)
missing_model_rows <- panel[!stats::complete.cases(panel[, ..model_fields])]
if (nrow(missing_model_rows) > 0L) abortf("Found %d rows with missing Python-NCLOC model fields.", nrow(missing_model_rows))

nonfinite_model_rows <- panel[
  !apply(as.data.frame(panel[, ..model_fields]), 1L, function(row) all(is.finite(row)))
]
if (nrow(nonfinite_model_rows) > 0L) abortf("Found %d rows with non-finite Python-NCLOC model fields.", nrow(nonfinite_model_rows))

legacy_audit <- panel[legacy_mismatch_any == TRUE, .(
  repo_id, repo_name, time, time_index, event, event_index,
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

pretrend_values <- seq.int(pretrend_min, pretrend_max)
post_values <- seq.int(0L, plot_max_event)
dynamic_horizon_values <- seq.int(plot_min_event, plot_max_event)
reported_values <- c(pretrend_values, -1L, post_values)

all_event_support <- panel[treatment_group == 1L, .(
  treatment_rows = .N,
  treatment_repositories = data.table::uniqueN(repo_id)
), by = .(event_time = as.integer(event_time_normalized))]
all_event_support[, period_type := data.table::fcase(
  event_time %in% pretrend_values, "placebo_pretrend",
  event_time == -1L, "reference",
  event_time >= 0L, "post_treatment",
  default = "other_pre_treatment"
)]
all_event_support[, in_report_window := event_time >= plot_min_event & event_time <= plot_max_event]
all_event_support[, in_pretrend_window := event_time %in% pretrend_values]
all_event_support[, in_dynamic_post_window := event_time %in% post_values]
data.table::setorder(all_event_support, event_time)
write_csv(all_event_support, paths$event_support)

cohort_support <- panel[treatment_group == 1L, .(
  treatment_repositories = data.table::uniqueN(repo_id),
  total_rows = .N,
  pre_treatment_rows = sum(event_time_normalized < 0L),
  treated_rows = sum(event_time_normalized >= 0L),
  dynamic_0_to_max_rows = sum(event_time_normalized >= 0L & event_time_normalized <= plot_max_event),
  min_event_time = min(event_time_normalized),
  max_event_time = max(event_time_normalized)
), by = .(event, event_index)]
data.table::setorder(cohort_support, event_index)
write_csv(cohort_support, paths$cohort_support)

sample_summary <- data.table::rbindlist(list(
  make_summary_row("definition", "ncloc_backend", backend),
  make_summary_row("definition", "ncloc_backend_metric", backend_metric),
  make_summary_row("definition", "covariate_spec", covariate_spec),
  make_summary_row("definition", "covariate_spec_label", covariate_spec_label),
  make_summary_row("definition", "first_stage_formula", first_stage_formula_text),
  make_summary_row("definition", "primary_outcome", expected_primary_metadata),
  make_summary_row("definition", "robustness_outcomes", expected_robustness_metadata),
  make_summary_row("definition", "python_velocity_metric_version", expected_velocity_version),
  make_summary_row("input", "rows", input_rows),
  make_summary_row("input", "repositories", repo_count),
  make_summary_row("input", "treatment_rows", treatment_rows),
  make_summary_row("input", "control_rows", control_rows),
  make_summary_row("input", "treatment_repositories", treatment_repos),
  make_summary_row("input", "control_repositories", control_repos),
  make_summary_row("sample", "untreated_first_stage_rows", untreated_rows, "Controls plus not-yet-treated treatment observations."),
  make_summary_row("sample", "treated_static_rows", treated_rows, "All event-time 0 and later observations."),
  make_summary_row("sample", "treated_dynamic_0_to_max_rows", dynamic_treated_rows, sprintf("Event times 0 through %d.", plot_max_event)),
  make_summary_row("qc", "duplicate_repo_time_rows", nrow(duplicate_rows)),
  make_summary_row("qc", "normalized_timing_errors", nrow(timing_errors)),
  make_summary_row("qc", "missing_model_rows", nrow(missing_model_rows)),
  make_summary_row("qc", "generic_ncloc_alias_mismatches", alias_mismatch),
  make_summary_row("qc", "primary_outcome_metadata_mismatches", primary_metadata_mismatches),
  make_summary_row("qc", "robustness_outcome_metadata_mismatches", robustness_metadata_mismatches),
  make_summary_row("qc", "velocity_version_mismatches", velocity_version_mismatches),
  make_summary_row("qc", "legacy_mismatch_rows", legacy_mismatch_rows, "Audit only; normalized absorbing timing is authoritative."),
  make_summary_row("qc", "legacy_mismatch_repositories", legacy_mismatch_repos)
), use.names = TRUE)
write_csv(sample_summary, paths$sample_summary)

outcomes <- c(
  "log_lines_added_py_source",
  "log_lines_added_py_no_merge",
  "log_lines_added_py_source_no_tests",
  "log_lines_added_py_all"
)
outcome_labels <- c(
  log_lines_added_py_source = "Python Added Lines: Source (Primary)",
  log_lines_added_py_no_merge = "Python Added Lines: No Merge",
  log_lines_added_py_source_no_tests = "Python Added Lines: Source, No Tests",
  log_lines_added_py_all = "Python Added Lines: Broad / Legacy-Compatible"
)
primary_outcome <- "log_lines_added_py_source"
robustness_outcomes <- setdiff(outcomes, primary_outcome)
static_tables <- list()
dynamic_tables <- list()
pretrend_check_tables <- list()
pretrend_summary_tables <- list()
first_stage_models <- list()
static_results <- list()
dynamic_results <- list()
diagnostics <- list()
model_errors <- character()

add_diagnostic <- function(outcome, model_type, status, elapsed, warnings = character(), error_message = "", result_terms = NA_integer_, extra = "") {
  diagnostics[[length(diagnostics) + 1L]] <<- data.table::data.table(
    ncloc_backend = backend,
    ncloc_backend_label = backend_label,
    ncloc_backend_metric = backend_metric,
    covariate_spec = covariate_spec,
    covariate_spec_label = covariate_spec_label,
    first_stage_formula = first_stage_formula_text,
    outcome = outcome,
    model_type = model_type,
    status = status,
    runtime_seconds = as.numeric(elapsed),
    warning_count = length(warnings),
    warning_messages = paste(warnings, collapse = " | "),
    error_message = error_message,
    input_rows = input_rows,
    untreated_rows = untreated_rows,
    treated_rows = treated_rows,
    result_terms = as.integer(result_terms),
    extra = extra
  )
}

for (outcome in outcomes) {
  # Resolve the display label before entering any data.table j expression.
  # A column named `outcome` is added to result tables, so using
  # outcome_labels[[outcome]] inside data.table would make `outcome` resolve
  # to the whole column rather than this loop scalar when the table has
  # multiple rows.
  outcome_label_value <- unname(outcome_labels[[as.character(outcome)]])
  if (length(outcome_label_value) != 1L || is.na(outcome_label_value) || !nzchar(outcome_label_value)) {
    abortf("Missing outcome label for: %s", as.character(outcome))
  }

  log_message("INFO", "Fitting first-stage diagnostic for %s under %s", outcome, covariate_spec)
  first_stage_capture <- fit_first_stage_diagnostic(panel, outcome, first_stage_formula_text)
  if (first_stage_capture$error) {
    error_text <- first_stage_capture$value$message
    add_diagnostic(outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text)
    model_errors <- c(model_errors, sprintf("%s first stage: %s", outcome, error_text))
    next
  }
  first_stage_models[[outcome]] <- first_stage_capture$value
  prediction_na_treated <- sum(is.na(first_stage_capture$predictions[panel$absorbing_treated == 1L]))
  prediction_na_all <- sum(is.na(first_stage_capture$predictions))
  if (prediction_na_treated > 0L) {
    error_text <- sprintf("First-stage predictions are missing for %d treated observations.", prediction_na_treated)
    add_diagnostic(outcome, "first_stage", "failed", first_stage_capture$elapsed, first_stage_capture$warnings, error_text,
                   extra = sprintf("prediction_na_all=%d", prediction_na_all))
    model_errors <- c(model_errors, sprintf("%s first stage: %s", outcome, error_text))
    next
  }
  add_diagnostic(
    outcome, "first_stage", "success", first_stage_capture$elapsed,
    first_stage_capture$warnings, result_terms = length(stats::coef(first_stage_capture$value)),
    extra = sprintf("nobs=%d; prediction_na_all=%d; prediction_na_treated=%d", stats::nobs(first_stage_capture$value), prediction_na_all, prediction_na_treated)
  )

  log_message("INFO", "Running static did_imputation for %s under %s", outcome, covariate_spec)
  static_capture <- run_did_model(panel, outcome, first_stage_formula, horizon = NULL, pretrends = NULL)
  if (static_capture$error) {
    error_text <- static_capture$value$message
    add_diagnostic(outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text)
    model_errors <- c(model_errors, sprintf("%s static: %s", outcome, error_text))
    next
  }
  static_results[[outcome]] <- static_capture$value
  static_table <- extract_effect_table(static_capture$value, outcome, confidence_level)
  static_table <- static_table[term == "treat"]
  if (nrow(static_table) != 1L) {
    error_text <- sprintf("Expected one static treat term, observed %d.", nrow(static_table))
    add_diagnostic(outcome, "static", "failed", static_capture$elapsed, static_capture$warnings, error_text, nrow(static_table))
    model_errors <- c(model_errors, sprintf("%s static: %s", outcome, error_text))
    next
  }
  static_table[, `:=`(
    ncloc_backend = backend,
    ncloc_backend_label = backend_label,
    ncloc_backend_metric = backend_metric,
    covariate_spec = covariate_spec,
    covariate_spec_label = covariate_spec_label,
    first_stage_formula = first_stage_formula_text,
    outcome_label = outcome_label_value,
    outcome_role = ifelse(outcome == primary_outcome, "primary", "robustness"),
    term_type = "static_att",
    treated_observations = treated_rows,
    first_stage_observations = untreated_rows,
    treatment_repositories = treatment_repos,
    control_repositories = control_repos,
    percent_interpretation = "100*(exp(beta)-1) on the log1p outcome scale"
  )]
  static_tables[[outcome]] <- static_table
  add_diagnostic(outcome, "static", "success", static_capture$elapsed, static_capture$warnings, result_terms = nrow(static_table))

  log_message("INFO", "Running dynamic did_imputation for %s under %s", outcome, covariate_spec)
  dynamic_capture <- run_did_model(panel, outcome, first_stage_formula, horizon = dynamic_horizon_values, pretrends = pretrend_values)
  if (dynamic_capture$error) {
    error_text <- dynamic_capture$value$message
    add_diagnostic(outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text)
    model_errors <- c(model_errors, sprintf("%s dynamic: %s", outcome, error_text))
    next
  }
  dynamic_results[[outcome]] <- dynamic_capture$value
  dynamic_table <- extract_effect_table(dynamic_capture$value, outcome, confidence_level)
  dynamic_table[, event_time := suppressWarnings(as.integer(as.character(term)))]
  dynamic_table <- dynamic_table[!is.na(event_time)]
  dynamic_table[, term_type := data.table::fcase(
    event_time %in% pretrend_values, "placebo_pretrend",
    event_time >= 0L, "post_treatment",
    default = "other"
  )]
  expected_dynamic_terms <- length(pretrend_values) + length(post_values)
  if (nrow(dynamic_table) != expected_dynamic_terms) {
    error_text <- sprintf("Expected %d dynamic/pretrend terms, observed %d.", expected_dynamic_terms, nrow(dynamic_table))
    add_diagnostic(outcome, "dynamic", "failed", dynamic_capture$elapsed, dynamic_capture$warnings, error_text, nrow(dynamic_table))
    model_errors <- c(model_errors, sprintf("%s dynamic: %s", outcome, error_text))
    next
  }

  support_for_merge <- all_event_support[, .(event_time, support_rows = treatment_rows, support_repositories = treatment_repositories)]
  dynamic_table <- merge(dynamic_table, support_for_merge, by = "event_time", all.x = TRUE, sort = FALSE)
  dynamic_table[, `:=`(
    ncloc_backend = backend,
    ncloc_backend_label = backend_label,
    ncloc_backend_metric = backend_metric,
    covariate_spec = covariate_spec,
    covariate_spec_label = covariate_spec_label,
    first_stage_formula = first_stage_formula_text,
    outcome_label = outcome_label_value,
    outcome_role = ifelse(outcome == primary_outcome, "primary", "robustness"),
    ci_includes_zero = !is.na(conf.low) & !is.na(conf.high) & conf.low <= 0 & conf.high >= 0,
    percent_interpretation = "100*(exp(beta)-1) on the log1p outcome scale"
  )]
  data.table::setorder(dynamic_table, event_time)
  dynamic_tables[[outcome]] <- dynamic_table
  add_diagnostic(
    outcome, "dynamic", "success", dynamic_capture$elapsed,
    dynamic_capture$warnings, result_terms = nrow(dynamic_table),
    extra = sprintf("horizon_argument=%s; pretrends=%s; reference=-1 omitted",
                    paste(dynamic_horizon_values, collapse = ","),
                    paste(pretrend_values, collapse = ","))
  )

  # Follow the original Rmd pretrend check. The package-native placebo
  # coefficients are inspected directly; no second regression is required to
  # reproduce or validate them. A CI that excludes zero is a substantive
  # finding to report, not a program error.
  pretrend_check <- data.table::copy(dynamic_table[term_type == "placebo_pretrend"])
  if (nrow(pretrend_check) != length(pretrend_values) ||
      !all(pretrend_values %in% pretrend_check$event_time)) {
    error_text <- sprintf(
      "Expected %d package-native pretrend terms, observed %d.",
      length(pretrend_values), nrow(pretrend_check)
    )
    add_diagnostic(outcome, "pretrend_original_rmd_check", "failed", 0, error_message = error_text,
                   result_terms = nrow(pretrend_check))
    model_errors <- c(model_errors, sprintf("%s pretrend check: %s", outcome, error_text))
    next
  }
  pretrend_check[, check_status := data.table::fifelse(ci_includes_zero, "includes_zero", "excludes_zero")]
  pretrend_check_tables[[outcome]] <- pretrend_check[, .(
    ncloc_backend, ncloc_backend_label, ncloc_backend_metric,
    covariate_spec, covariate_spec_label, first_stage_formula,
    outcome, outcome_label, outcome_role, event_time, term, estimate, std.error,
    conf.low, conf.high, p_value, significant, ci_includes_zero,
    check_status, support_rows, support_repositories
  )]

  excluded_periods <- pretrend_check[ci_includes_zero == FALSE, event_time]
  pretrend_summary_tables[[outcome]] <- data.table::data.table(
    ncloc_backend = backend,
    ncloc_backend_label = backend_label,
    ncloc_backend_metric = backend_metric,
    covariate_spec = covariate_spec,
    covariate_spec_label = covariate_spec_label,
    first_stage_formula = first_stage_formula_text,
    outcome = outcome,
    outcome_label = outcome_label_value,
    outcome_role = ifelse(outcome == primary_outcome, "primary", "robustness"),
    placebo_periods = paste(pretrend_values, collapse = ","),
    placebo_terms = nrow(pretrend_check),
    all_ci_include_zero = all(pretrend_check$ci_includes_zero),
    periods_excluding_zero = if (length(excluded_periods) == 0L) "" else paste(excluded_periods, collapse = ","),
    minimum_p_value = if (all(is.na(pretrend_check$p_value))) NA_real_ else min(pretrend_check$p_value, na.rm = TRUE),
    check_definition = "Original Rmd check: each package-native placebo 95% CI should include zero."
  )
  add_diagnostic(
    outcome, "pretrend_original_rmd_check", "success", 0,
    result_terms = nrow(pretrend_check),
    extra = sprintf(
      "all_ci_include_zero=%s; periods_excluding_zero=%s",
      all(pretrend_check$ci_includes_zero),
      if (length(excluded_periods) == 0L) "none" else paste(excluded_periods, collapse = ",")
    )
  )

}

diagnostics_table <- if (length(diagnostics) > 0L) data.table::rbindlist(diagnostics, fill = TRUE) else data.table::data.table()
write_csv(diagnostics_table, paths$diagnostics)

if (length(model_errors) > 0L) {
  abortf("One or more models failed: %s", paste(model_errors, collapse = " || "))
}

static_output <- data.table::rbindlist(static_tables, fill = TRUE, use.names = TRUE)
dynamic_output <- data.table::rbindlist(dynamic_tables, fill = TRUE, use.names = TRUE)
pretrend_check_output <- data.table::rbindlist(pretrend_check_tables, fill = TRUE, use.names = TRUE)
pretrend_summary_output <- data.table::rbindlist(pretrend_summary_tables, fill = TRUE, use.names = TRUE)

data.table::setcolorder(static_output, c(
  "ncloc_backend", "ncloc_backend_label", "ncloc_backend_metric",
  "covariate_spec", "covariate_spec_label", "first_stage_formula",
  "outcome", "outcome_label", "outcome_role", "term", "term_type", "estimate", "std.error",
  "conf.low", "conf.high", "p_value", "significant",
  "exp_coefficient_change_pct", "exp_ci_low_pct", "exp_ci_high_pct",
  "treated_observations", "first_stage_observations", "treatment_repositories",
  "control_repositories", "percent_interpretation"
))
data.table::setcolorder(dynamic_output, c(
  "ncloc_backend", "ncloc_backend_label", "ncloc_backend_metric",
  "covariate_spec", "covariate_spec_label", "first_stage_formula",
  "outcome", "outcome_label", "outcome_role", "event_time", "term", "term_type",
  "estimate", "std.error", "conf.low", "conf.high", "p_value", "significant",
  "exp_coefficient_change_pct", "exp_ci_low_pct", "exp_ci_high_pct",
  "support_rows", "support_repositories", "ci_includes_zero", "percent_interpretation"
))

write_csv(static_output, paths$static_effects)
write_csv(dynamic_output, paths$dynamic_effects)
write_csv(pretrend_check_output, paths$pretrend_checks)
write_csv(pretrend_summary_output, paths$pretrend_summary)

saveRDS(static_results, paths$static_rds)
saveRDS(dynamic_results, paths$dynamic_rds)
saveRDS(first_stage_models, paths$first_stage_rds)

plot_data <- dynamic_output[event_time >= plot_min_event & event_time <= plot_max_event]
plot_data[, is_significant := !is.na(conf.low) & !is.na(conf.high) & (conf.low > 0 | conf.high < 0)]

# Match the original Rmd visual design: no synthetic -1 point, a vertical
# separator at -0.5, filled significant points, hollow non-significant points,
# and solid/dotted confidence intervals.
plot_object <- ggplot2::ggplot(plot_data, ggplot2::aes(x = event_time, y = estimate)) +
  ggplot2::geom_point(data = plot_data[is_significant == TRUE], size = 1.5, shape = 19) +
  ggplot2::geom_point(data = plot_data[is_significant == FALSE], size = 1.5, shape = 21, fill = "transparent") +
  ggplot2::geom_errorbar(
    data = plot_data[is_significant == TRUE],
    ggplot2::aes(ymin = conf.low, ymax = conf.high),
    width = 0.5, linetype = "solid"
  ) +
  ggplot2::geom_errorbar(
    data = plot_data[is_significant == FALSE],
    ggplot2::aes(ymin = conf.low, ymax = conf.high),
    width = 0.5, linetype = "dotted"
  ) +
  ggplot2::geom_hline(yintercept = 0, linetype = "dashed") +
  ggplot2::geom_vline(xintercept = -0.5, linetype = "dashed") +
  ggplot2::scale_x_continuous(breaks = seq.int(plot_min_event, plot_max_event, by = 1L)) +
  ggplot2::coord_cartesian(xlim = c(plot_min_event - 0.5, plot_max_event + 0.5)) +
  ggplot2::scale_y_continuous(expand = ggplot2::expansion(mult = c(0.05, 0.05))) +
  ggplot2::labs(
    x = "Months Relative to Cursor Adoption",
    y = "Treatment Effect",
    caption = "Filled dots: p < 0.05 (significant), Hollow dots: p >= 0.05 (non-significant)"
  ) +
  ggplot2::theme_minimal() +
  ggplot2::theme(
    plot.caption = ggplot2::element_text(hjust = 0.5, size = 10, margin = ggplot2::margin(t = 3)),
    panel.grid.major.x = ggplot2::element_blank(),
    panel.grid.minor.x = ggplot2::element_blank()
  ) +
  ggplot2::facet_wrap(~outcome_label, scales = "free_y", nrow = 2)

ggplot2::ggsave(paths$plot_pdf, plot_object, width = 12, height = 7.5, units = "in", bg = "white")
ggplot2::ggsave(paths$plot_png, plot_object, width = 12, height = 7.5, units = "in", dpi = 180, bg = "white")
log_message("INFO", "Wrote plot files to %s", plot_dir)

run_finished <- Sys.time()
# `key` is a reserved formal argument of data.table(). Passing key = ...
# asks data.table to set a table key instead of creating a column named `key`.
# Build the column under a temporary name, then rename it explicitly.
metadata <- data.table::data.table(
  metadata_key = c(
    "implementation_version", "ncloc_backend", "ncloc_backend_label", "ncloc_backend_metric",
    "covariate_spec", "covariate_spec_label",
    "run_started", "run_finished", "runtime_seconds",
    "input_file", "input_sha256", "script_path", "script_sha256",
    "r_version", "platform", "hostname",
    "didimputation_version", "fixest_version", "data_table_version", "ggplot2_version",
    "rmarkdown_version", "knitr_version", "pandoc_version",
    "first_stage_formula", "cluster_variable", "primary_outcome", "robustness_outcomes",
    "python_velocity_metric_version", "dynamic_horizon_argument",
    "pretrend_horizon", "reference_event_time", "confidence_level",
    "html_report", "html_self_contained", "original_rmd_alignment"
  ),
  value = c(
    "v3", backend, backend_label, backend_metric, covariate_spec, covariate_spec_label,
    format(run_started, "%Y-%m-%d %H:%M:%S %Z"), format(run_finished, "%Y-%m-%d %H:%M:%S %Z"),
    as.character(as.numeric(difftime(run_finished, run_started, units = "secs"))),
    input_file, sha256_file(input_file), as.character(script_path), sha256_file(as.character(script_path)),
    R.version.string, R.version$platform, Sys.info()[["nodename"]],
    safe_package_version("didimputation"), safe_package_version("fixest"),
    safe_package_version("data.table"), safe_package_version("ggplot2"),
    safe_package_version("rmarkdown"), safe_package_version("knitr"),
    as.character(rmarkdown::pandoc_version()),
    first_stage_formula_text,
    "repo_id", primary_outcome, paste(robustness_outcomes, collapse = "|"), expected_velocity_version,
    paste(dynamic_horizon_values, collapse = ","), paste(pretrend_values, collapse = ","),
    "-1 omitted", as.character(confidence_level), html_output, "true",
    "Static and dynamic did_imputation calls, pretrend CI checks, and the integrated HTML report retain the prior b03 estimator while evaluating the run-x-b02-v4 Python velocity definitions."
  )
)
data.table::setnames(metadata, "metadata_key", "key")
write_csv(metadata, paths$metadata)

summary_rows <- list(
  make_summary_row("implementation", "version", "v3"),
  make_summary_row("definition", "ncloc_backend", backend),
  make_summary_row("definition", "ncloc_backend_metric", backend_metric),
  make_summary_row("definition", "covariate_spec", covariate_spec),
  make_summary_row("definition", "covariate_spec_label", covariate_spec_label),
  make_summary_row("definition", "treatment_timing", "absorbing_first_adoption", "Uses event_index and time_index; legacy monthly usage flags are audit-only."),
  make_summary_row("definition", "first_stage", first_stage_formula_text),
  make_summary_row("definition", "cluster", "repo_id"),
  make_summary_row("definition", "primary_outcome", primary_outcome),
  make_summary_row("definition", "robustness_outcomes", paste(robustness_outcomes, collapse = "|")),
  make_summary_row("definition", "python_velocity_metric_version", expected_velocity_version),
  make_summary_row("definition", "dynamic_horizon_argument", paste(dynamic_horizon_values, collapse = ","), "Matches original Rmd horizon=-6:6; package output contains placebo -6:-2 and post 0:6 terms."),
  make_summary_row("definition", "pretrend_horizon", paste(pretrend_values, collapse = ",")),
  make_summary_row("definition", "reference_event_time", -1),
  make_summary_row("definition", "pretrend_check", "package_native_ci_includes_zero", "Matches the original Rmd; no independent regression is used as a hard validation."),
  make_summary_row("input", "rows", input_rows),
  make_summary_row("input", "repositories", repo_count),
  make_summary_row("input", "treatment_repositories", treatment_repos),
  make_summary_row("input", "control_repositories", control_repos),
  make_summary_row("sample", "untreated_first_stage_rows", untreated_rows),
  make_summary_row("sample", "treated_static_rows", treated_rows),
  make_summary_row("sample", "treated_dynamic_rows", dynamic_treated_rows),
  make_summary_row("qc", "legacy_mismatch_rows", legacy_mismatch_rows),
  make_summary_row("qc", "legacy_mismatch_repositories", legacy_mismatch_repos),
  make_summary_row("qc", "normalized_timing_errors", nrow(timing_errors)),
  make_summary_row("qc", "duplicate_repo_time_rows", nrow(duplicate_rows)),
  make_summary_row("qc", "missing_model_rows", nrow(missing_model_rows)),
  make_summary_row("qc", "generic_ncloc_alias_mismatches", alias_mismatch),
  make_summary_row("model", "static_outcomes_completed", nrow(static_output)),
  make_summary_row("model", "dynamic_estimated_terms", nrow(dynamic_output)),
  make_summary_row("model", "dynamic_plot_rows", nrow(dynamic_output)),
  make_summary_row("model", "pretrend_check_rows", nrow(pretrend_check_output)),
  make_summary_row("model", "pretrend_outcomes_checked", nrow(pretrend_summary_output)),
  make_summary_row("artifact", "html_report", html_output, "Generated in the same run-x-b03 backend execution.")
)
for (outcome_name in outcomes) {
  row_static <- static_output[outcome == outcome_name]
  row_pre <- pretrend_summary_output[outcome == outcome_name]
  summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("static_effect", paste0(outcome_name, "_estimate"), row_static$estimate)
  summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("static_effect", paste0(outcome_name, "_p_value"), row_static$p_value)
  summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("pretrend", paste0(outcome_name, "_all_ci_include_zero"), row_pre$all_ci_include_zero)
  summary_rows[[length(summary_rows) + 1L]] <- make_summary_row("pretrend", paste0(outcome_name, "_periods_excluding_zero"), row_pre$periods_excluding_zero)
}
summary_table <- data.table::rbindlist(summary_rows, fill = TRUE, use.names = TRUE)
write_csv(summary_table, summary_output)

html_result <- render_html_report(
  output_path = paths$html_report,
  plot_png_path = paths$plot_png,
  static_output = static_output,
  dynamic_output = dynamic_output,
  pretrend_checks = pretrend_check_output,
  pretrend_summary = pretrend_summary_output,
  event_support = all_event_support,
  cohort_support = cohort_support,
  sample_summary = sample_summary,
  legacy_audit = legacy_audit,
  diagnostics = diagnostics_table,
  metadata = metadata,
  input_rows = input_rows,
  treatment_repos = treatment_repos,
  control_repos = control_repos,
  untreated_rows = untreated_rows,
  treated_rows = treated_rows,
  first_stage_formula = first_stage_formula_text,
  implementation_version = "v3",
  backend_key = backend,
  backend_label = backend_label,
  backend_metric = backend_metric
)

html_metadata <- data.table::data.table(
  metadata_key = c("html_render_runtime_seconds", "html_report_sha256", "html_render_warning_count", "html_render_warnings"),
  value = c(
    as.character(html_result$elapsed),
    sha256_file(paths$html_report),
    as.character(length(html_result$warnings)),
    paste(html_result$warnings, collapse = " | ")
  )
)
data.table::setnames(html_metadata, "metadata_key", "key")
metadata <- data.table::rbindlist(list(metadata, html_metadata), use.names = TRUE, fill = TRUE)
write_csv(metadata, paths$metadata)

log_message("INFO", "Completed run-x-b03-v3 backend=%s covariate_spec=%s: %d static effects, %d package-native dynamic/pretrend terms, %d pretrend checks, and 1 HTML report",
            backend, covariate_spec,
            nrow(static_output), nrow(dynamic_output), nrow(pretrend_check_output))
