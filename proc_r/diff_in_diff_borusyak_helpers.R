# Helper functions for Borusyak DiD analyses.
#
# These helpers are shared by run9 quality DiD analyses.
#
# Reused logic:
#   1. Static Borusyak did_imputation call.
#   2. Dynamic Borusyak event-study did_imputation call.
#   3. Static treatment-effect extraction.
#   4. Dynamic event-study result extraction.
#
# Expected panel columns:
#   - repo_name: numeric repository/unit id
#   - time: numeric monthly time id, e.g., 202501
#   - event: numeric treatment cohort month, e.g., 202501, or 0 for never-treated controls
#
# Main dependency:
#   didimputation::did_imputation()


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


get_col_or_na <- function(df, col) {
  if (col %in% names(df)) {
    return(df[[col]])
  }
  rep(NA_real_, nrow(df))
}


get_first_available_col_or_na <- function(df, cols) {
  for (col in cols) {
    if (col %in% names(df)) {
      return(df[[col]])
    }
  }
  rep(NA_real_, nrow(df))
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
      p_value = NA_real_,
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
      p_value = NA_real_,
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
      p_value = NA_real_,
      note = "treat term not found"
    ))
  }

  data.frame(
    outcome = outcome,
    term = row$term,
    estimate = row$estimate,
    std_error = get_first_available_col_or_na(row, c("std.error", "std_error")),
    conf_low = get_first_available_col_or_na(row, c("conf.low", "conf_low")),
    conf_high = get_first_available_col_or_na(row, c("conf.high", "conf_high")),
    p_value = get_first_available_col_or_na(row, c("p.value", "p_value", "p")),
    note = "Borusyak static treatment effect"
  )
}


extract_dynamic_result <- function(result, outcome, outcome_label,
                                   min_horizon = -6, max_horizon = 6) {
  if (is.null(result)) {
    return(data.frame())
  }

  result_df <- as.data.frame(result)

  if (!("term" %in% names(result_df))) {
    return(data.frame())
  }

  term_chr <- gsub("[\u2212\u2013\u2014]", "-", as.character(result_df$term))
  time_numeric <- suppressWarnings(as.numeric(term_chr))

  valid <- !is.na(time_numeric) &
    time_numeric >= min_horizon &
    time_numeric <= max_horizon

  if (!any(valid)) {
    return(data.frame())
  }

  out <- data.frame(
    outcome = outcome,
    outcome_label = outcome_label,
    time = time_numeric[valid],
    estimate = result_df$estimate[valid],
    conf_low = get_first_available_col_or_na(result_df, c("conf.low", "conf_low"))[valid],
    conf_high = get_first_available_col_or_na(result_df, c("conf.high", "conf_high"))[valid],
    std_error = get_first_available_col_or_na(result_df, c("std.error", "std_error"))[valid],
    p_value = get_first_available_col_or_na(result_df, c("p.value", "p_value", "p"))[valid]
  )

  out$significant <- !is.na(out$conf_low) &
    !is.na(out$conf_high) &
    ((out$conf_low > 0) | (out$conf_high < 0))

  out <- out[order(out$outcome, out$time), ]

  out
}
