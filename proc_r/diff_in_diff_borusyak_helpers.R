# Helper functions for Borusyak DiD analyses.
#
# Expected default panel columns:
#   - repo_id: numeric repository/unit id
#   - time_id: numeric monthly time id, e.g., year * 12 + month
#   - event_id: numeric treatment cohort month id, or 0 for never-treated controls
#
# Main dependency:
#   didimputation::did_imputation()


run_borusyak_static <- function(data,
                                outcome_var,
                                first_stage_formula,
                                idname = "repo_id",
                                tname = "time_id",
                                gname = "event_id") {
  didimputation::did_imputation(
    data = data,
    yname = outcome_var,
    gname = gname,
    tname = tname,
    idname = idname,
    first_stage = first_stage_formula
  )
}


run_borusyak_dynamic <- function(data,
                                 outcome_var,
                                 first_stage_formula,
                                 horizon = -6:6,
                                 pretrends = -6:-2,
                                 idname = "repo_id",
                                 tname = "time_id",
                                 gname = "event_id") {
  didimputation::did_imputation(
    data = data,
    yname = outcome_var,
    gname = gname,
    tname = tname,
    idname = idname,
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


extract_event_time_from_term <- function(term_vec) {
  term_chr <- gsub("[\u2212\u2013\u2014]", "-", as.character(term_vec))
  term_chr <- gsub("\\s+", "", term_chr)

  out <- suppressWarnings(as.numeric(term_chr))

  missing_idx <- is.na(out)
  if (any(missing_idx)) {
    extracted <- regmatches(
      term_chr[missing_idx],
      regexpr("-?[0-9]+$", term_chr[missing_idx])
    )
    out[missing_idx] <- suppressWarnings(as.numeric(extracted))
  }

  out
}


extract_dynamic_result <- function(result,
                                   outcome,
                                   outcome_label,
                                   min_horizon = -6,
                                   max_horizon = 6) {
  if (is.null(result)) {
    return(data.frame())
  }

  result_df <- as.data.frame(result)

  if (!("term" %in% names(result_df))) {
    return(data.frame())
  }

  time_numeric <- extract_event_time_from_term(result_df$term)

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
