# Helper functions for Borusyak DiD v2 activity smoke tests.
#
# Reused/refactored from:
#   notebooks/DiffInDiffBorusyak.Rmd
#
# Reused logic:
#   1. Static Borusyak did_imputation call:
#      original get_static_effects()
#      -> run_borusyak_static()
#
#   2. Dynamic Borusyak event-study did_imputation call:
#      original run_dynamic_analysis()
#      -> run_borusyak_dynamic()
#
#      Reason:
#      The original paper reports not only average ATT, but also
#      horizon-average treatment effects (ATT_h) from 0 to +6 months
#      after Cursor adoption and placebo pre-adoption effects from
#      -6 to -2 months for the pre-trend check. This function preserves
#      that event-study logic by parameterizing the original
#      did_imputation(..., horizon = -6:6, pretrends = -6:-2) call.
# 
#  
#   3. Static "treat" term extraction:
#      original static_df construction
#      -> extract_static_result()
#
#   4. Dynamic event-study plot-data construction:
#      original event_study_data loop
#      -> extract_dynamic_result()
#
# Deliberately not reused:
#   - original baseline panel loading
#   - repo_metrics / matching / language-group logic
#   - SonarQube quality outcomes
#   - full-paper covariates: age, ncloc, stars, issues
#   - robustness settings and publication plot sections
#
# Main v2 difference:
#   first_stage is parameterized so activity-only panels can use:
#     ~ contributors | repo_name + time
#   instead of the full-paper formula:
#     ~ age + ncloc + contributors + stars + issues | repo_name + time

#' Run the static Borusyak imputation estimator for one outcome.
#'
#' This function refactors the original `get_static_effects()` logic from
#' `notebooks/DiffInDiffBorusyak.Rmd`. The estimator structure is unchanged:
#' `event` is the treatment cohort, `time` is the monthly period, and
#' `repo_name` is the unit identifier. The only v2 change is that the
#' first-stage formula is passed as an argument so that the same helper can be
#' used with both the full paper panel and the smaller activity-only panel.
#'
#' @param data A data frame/data.table in the format required by
#'   `didimputation::did_imputation()`. It must contain the outcome column,
#'   `event`, `time`, and `repo_name`.
#' @param outcome_var Character scalar. Name of the outcome column to model,
#'   for example `"commits"` or `"lines_added"`.
#' @param first_stage_formula R formula passed to `first_stage`. For the v2
#'   activity panel, use `~ contributors | repo_name + time`.
#' @return The raw object returned by `didimputation::did_imputation()`.
run_borusyak_static <- function(data, outcome_var, first_stage_formula) {
  didimputation::did_imputation(
    data = data,
    yname = outcome_var,
    gname = "event",
    tname = "time",
    idname = "repo_name",
    first_stage = first_stage_formula
  )
}

#' Run the dynamic Borusyak event-study estimator for one outcome.
#'
#' This function refactors the original `run_dynamic_analysis()` logic from
#' `notebooks/DiffInDiffBorusyak.Rmd`. It keeps the paper-style event-study
#' window (`horizon = -6:6`) and pre-trend test window (`pretrends = -6:-2`) by
#' default. The first-stage formula is parameterized for reuse with v2 panels.
#'
#' @param data A data frame/data.table in the format required by
#'   `didimputation::did_imputation()`.
#' @param outcome_var Character scalar. Name of the outcome column to model.
#' @param first_stage_formula R formula passed to `first_stage`.
#' @param horizon Integer vector of relative event times to estimate. Defaults
#'   to `-6:6`, matching the original Borusyak notebook.
#' @param pretrends Integer vector of pre-treatment horizons used for the
#'   pre-trend/placebo test. Defaults to `-6:-2`, matching the paper notebook.
#' @return The raw object returned by `didimputation::did_imputation()`.
run_borusyak_dynamic <- function(data, outcome_var, first_stage_formula,
                                 horizon = -6:6, pretrends = -6:-2) {
  didimputation::did_imputation(
    data = data,
    yname = outcome_var,
    gname = "event",
    tname = "time",
    idname = "repo_name",
    first_stage = first_stage_formula,
    horizon = horizon,
    pretrends = pretrends
  )
}

#' Extract the static treatment effect from a Borusyak result.
#'
#' The original notebook builds a static-effect table by selecting the
#' `term == "treat"` row from each `did_imputation()` result. This helper keeps
#' that same extraction logic but wraps it in a defensive function so the smoke
#' test can continue and record useful diagnostics when a model fails or returns
#' an unexpected shape.
#'
#' @param result Raw result returned by `run_borusyak_static()`, or `NULL` if the
#'   model failed inside `tryCatch()`.
#' @param outcome Character scalar. Outcome name to attach to the extracted row.
#' @return A one-row data frame with outcome, term, estimate, standard error,
#'   confidence interval, and a note field.
extract_static_result <- function(result, outcome) {
  if (is.null(result)) {
    return(data.frame(
      outcome = outcome,
      term = "treat",
      estimate = NA_real_,
      std_error = NA_real_,
      conf_low = NA_real_,
      conf_high = NA_real_,
      note = "model failed"
    ))
  }

  result_df <- as.data.frame(result)

  if (!("term" %in% names(result_df))) {
    return(data.frame(
      outcome = outcome,
      term = "treat",
      estimate = NA_real_,
      std_error = NA_real_,
      conf_low = NA_real_,
      conf_high = NA_real_,
      note = "term column not found"
    ))
  }

  row <- result_df[result_df$term == "treat", , drop = FALSE]

  if (nrow(row) == 0) {
    return(data.frame(
      outcome = outcome,
      term = "treat",
      estimate = NA_real_,
      std_error = NA_real_,
      conf_low = NA_real_,
      conf_high = NA_real_,
      note = "treat term not found"
    ))
  }

  data.frame(
    outcome = outcome,
    term = row$term,
    estimate = row$estimate,
    std_error = if ("std.error" %in% names(row)) row$std.error else NA_real_,
    conf_low = if ("conf.low" %in% names(row)) row$conf.low else NA_real_,
    conf_high = if ("conf.high" %in% names(row)) row$conf.high else NA_real_,
    note = "smoke test only; do not interpret as final estimate"
  )
}

#' Safely read a result column or return an NA vector.
#'
#' `did_imputation()` outputs usually contain `conf.low`, `conf.high`, and
#' `std.error`, but defensive extraction is useful for smoke tests. This helper
#' avoids repeated `%in% names(df)` checks inside result-processing functions.
#'
#' @param df Data frame containing model output.
#' @param col Character scalar. Column name to extract.
#' @return The requested column if present; otherwise an `NA_real_` vector with
#'   the same length as `nrow(df)`.
get_col_or_na <- function(df, col) {
  if (col %in% names(df)) {
    return(df[[col]])
  }
  rep(NA_real_, nrow(df))
}

#' Extract dynamic event-study estimates from a Borusyak result.
#'
#' The original notebook constructs event-study plot data by removing the static
#' `treat` row, converting the remaining `term` values into relative-time
#' integers, and carrying over estimates and confidence intervals. This helper
#' preserves that logic and adds small robustness improvements for smoke testing:
#' it returns an empty data frame when results are missing, filters to the
#' `[-6, 6]` horizon, and treats CIs excluding zero as significant for plotting.
#'
#' @param result Raw result returned by `run_borusyak_dynamic()`, or `NULL` if
#'   the model failed inside `tryCatch()`.
#' @param outcome Character scalar. Outcome name, for example `"commits"`.
#' @param outcome_label Human-readable outcome label for plots/tables.
#' @return A data frame with columns: outcome, outcome_label, time, estimate,
#'   conf_low, conf_high, std_error, and significant. Returns an empty data
#'   frame if no valid dynamic terms are available.
extract_dynamic_result <- function(result, outcome, outcome_label) {
  if (is.null(result)) {
    return(data.frame())
  }

  result_df <- as.data.frame(result)

  if (!("term" %in% names(result_df))) {
    return(data.frame())
  }

  # Normalize common Unicode dash/minus variants before numeric parsing. This
  # protects against copy/paste or rendering differences in model output terms.
  term_chr <- gsub("[\u2212\u2013\u2014]", "-", as.character(result_df$term))
  time_numeric <- suppressWarnings(as.numeric(term_chr))
  valid <- !is.na(time_numeric) & time_numeric >= -6 & time_numeric <= 6

  if (!any(valid)) {
    return(data.frame())
  }

  out <- data.frame(
    outcome = outcome,
    outcome_label = outcome_label,
    time = time_numeric[valid],
    estimate = result_df$estimate[valid],
    conf_low = get_col_or_na(result_df, "conf.low")[valid],
    conf_high = get_col_or_na(result_df, "conf.high")[valid],
    std_error = get_col_or_na(result_df, "std.error")[valid]
  )

  out$significant <- !is.na(out$conf_low) &
    !is.na(out$conf_high) &
    ((out$conf_low > 0) | (out$conf_high < 0))

  out
}
