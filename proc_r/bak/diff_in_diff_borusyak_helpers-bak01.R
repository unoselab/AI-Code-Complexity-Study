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

extract_dynamic_result <- function(result, outcome, outcome_label) {
  if (is.null(result)) {
    return(data.frame())
  }

  result_df <- as.data.frame(result)

  if (!("term" %in% names(result_df))) {
    return(data.frame())
  }

  time_numeric <- suppressWarnings(as.numeric(as.character(result_df$term)))
  valid <- !is.na(time_numeric) & time_numeric >= -6 & time_numeric <= 6

  if (!any(valid)) {
    return(data.frame())
  }

  get_col_or_na <- function(df, col) {
    if (col %in% names(df)) {
      return(df[[col]])
    }
    rep(NA_real_, nrow(df))
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
