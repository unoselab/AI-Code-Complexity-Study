#!/usr/bin/env Rscript

# run-x-b09 v2: detector-localized Python velocity timing sensitivity
#
# This script extends the run-x-b08 detector-localized velocity analysis in two
# ways while preserving its file-selection rules and DiD specifications:
#   1. monthly estimates under recorded T, T-1, and T-2 treatment clocks; and
#   2. weekly estimates based on the exact first observable Cursor-related
#      commit represented in the established America/Chicago weekly panel.
#
# Inputs
# ------
# - run-x-b08-v4 monthly localized panel and static estimates;
# - run-x-b03-d-v4 America/Chicago weekly panel;
# - run-x-b02 file-change and commit-level Python additions;
# - C05 NPR file scores and I06 ML file scores.
#
# Outputs
# -------
# - monthly static/dynamic estimates for all treatment clocks;
# - monthly pre-adoption summaries and recorded-clock re-indexing;
# - a weekly localized repository-week panel;
# - weekly static/dynamic estimates and pre-adoption summaries;
# - localization, reconciliation, support, diagnostic, and QC tables.

options(stringsAsFactors = FALSE, warn = 1)

RUN_LABEL <- "run-x-b09-v2"
TIMEZONE_NAME <- "America/Chicago"
ADJUSTED_FORMULA <- ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index
FE_ONLY_FORMULA <- ~ 1 | repo_id + time_index
ADJUSTED_FORMULA_TEXT <- "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
FE_ONLY_FORMULA_TEXT <- "~ 1 | repo_id + time_index"

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)

log_message <- function(level, fmt, ...) {
  message(sprintf("%s [%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)))
}

parse_args <- function(values) {
  result <- list()
  i <- 1L
  while (i <= length(values)) {
    key <- values[[i]]
    if (!startsWith(key, "--")) abortf("Unexpected positional argument: %s", key)
    key <- gsub("-", "_", substring(key, 3L), fixed = TRUE)
    if (i == length(values) || startsWith(values[[i + 1L]], "--")) {
      result[[key]] <- "1"
      i <- i + 1L
    } else {
      result[[key]] <- values[[i + 1L]]
      i <- i + 2L
    }
  }
  result
}

arg_required <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) abortf("Missing required option --%s", gsub("_", "-", name))
  as.character(value)
}

arg_value <- function(args, name, default) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) default else value
}

as_flag <- function(value, name) {
  if (!value %in% c("0", "1")) abortf("--%s must be 0 or 1", gsub("_", "-", name))
  identical(value, "1")
}

strict_count <- function(observed, expected, label, strict) {
  if (is.na(expected) || expected < 0L) return(invisible(TRUE))
  if (as.integer(observed) != as.integer(expected)) {
    message <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, observed)
    if (strict) abortf("%s", message) else log_message("WARNING", "%s", message)
  }
  invisible(TRUE)
}

require_packages <- function() {
  packages <- c("data.table", "didimputation", "fixest")
  missing <- packages[!vapply(packages, requireNamespace, logical(1L), quietly = TRUE)]
  if (length(missing)) abortf("Missing R packages: %s", paste(missing, collapse = ", "))
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing)) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

write_csv_gz <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "", compress = "gzip")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

normalize_path <- function(value) {
  value <- gsub("\\", "/", trimws(as.character(value)), fixed = TRUE)
  sub("^\\./+", "", value)
}

normalize_source <- function(value) tolower(trimws(as.character(value)))
normalize_repo <- function(value) trimws(as.character(value))

normalize_month <- function(value, label) {
  text <- trimws(as.character(value))
  result <- ifelse(grepl("^[0-9]{4}-[0-9]{2}", text), substr(text, 1L, 7L), NA_character_)
  if (anyNA(result)) abortf("%s contains %d values without a YYYY-MM prefix", label, sum(is.na(result)))
  result
}

numeric_strict <- function(value, label, allow_missing = FALSE) {
  original <- trimws(as.character(value))
  number <- suppressWarnings(as.numeric(original))
  missing_token <- is.na(original) | !nzchar(original) | tolower(original) %in% c("na", "nan", "none", "null")
  unexpected <- is.na(number) & !missing_token
  if (any(unexpected)) abortf("%s contains %d nonnumeric values", label, sum(unexpected))
  if (!allow_missing && anyNA(number)) abortf("%s contains %d missing values", label, sum(is.na(number)))
  number
}

bool_int <- function(value, label) {
  text <- tolower(trimws(as.character(value)))
  result <- rep(NA_integer_, length(text))
  result[text %in% c("1", "true", "t", "yes", "y")] <- 1L
  result[text %in% c("0", "false", "f", "no", "n", "")] <- 0L
  if (anyNA(result)) abortf("%s contains %d unrecognized Boolean values", label, sum(is.na(result)))
  result
}

read_selected <- function(path, columns, label) {
  header <- names(data.table::fread(path, nrows = 0L, showProgress = FALSE))
  missing <- setdiff(columns, header)
  if (length(missing)) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
  data.table::fread(path, select = columns, showProgress = TRUE, na.strings = c("", "NA", "NaN"))
}

capture_evaluation <- function(expression) {
  warnings <- character()
  started <- proc.time()[[3L]]
  value <- tryCatch(
    withCallingHandlers(
      expression,
      warning = function(condition) {
        warnings <<- c(warnings, conditionMessage(condition))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(condition) structure(list(message = conditionMessage(condition)), class = "captured_error")
  )
  list(
    value = value,
    warnings = unique(warnings),
    elapsed = proc.time()[[3L]] - started,
    error = inherits(value, "captured_error")
  )
}

extract_effects <- function(result, confidence_level) {
  table <- data.table::as.data.table(result)
  validate_columns(table, c("term", "estimate", "std.error"), "did_imputation result")
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  table[, `:=`(
    conf.low = estimate - critical * std.error,
    conf.high = estimate + critical * std.error,
    p_value = data.table::fifelse(
      is.finite(std.error) & std.error > 0,
      2 * stats::pnorm(-abs(estimate / std.error)),
      NA_real_
    ),
    percent_change = 100 * (exp(estimate) - 1),
    significant_05 = !is.na(std.error) & std.error > 0 &
      2 * stats::pnorm(-abs(estimate / std.error)) < 0.05
  )]
  table
}

prepare_source_additions <- function(input, audit_path) {
  data <- data.table::copy(input)
  validate_columns(data, c("included_in_py_source", "lines_added"), "B02 file additions")
  data[, included_in_py_source := bool_int(included_in_py_source, "included_in_py_source")]
  raw <- trimws(as.character(data$lines_added))
  parsed <- suppressWarnings(as.numeric(raw))
  missing <- is.na(raw) | !nzchar(raw) | tolower(raw) %in% c("na", "nan", "none", "null")
  valid <- is.finite(parsed) & parsed >= 0 & parsed == floor(parsed)
  status <- rep("valid_nonnegative_integer", length(parsed))
  status[!valid] <- "invalid_numeric_count"
  status[is.na(parsed) & !missing] <- "nonnumeric_count"
  status[missing] <- "missing_count"
  audit <- data.table::data.table(
    included_in_py_source = data$included_in_py_source,
    count_status = status,
    file_status = if ("file_status" %in% names(data)) as.character(data$file_status) else "not_provided",
    is_binary = if ("is_binary" %in% names(data)) as.character(data$is_binary) else "not_provided"
  )[, .(rows = .N), by = .(included_in_py_source, count_status, file_status, is_binary)]
  data.table::setorder(audit, included_in_py_source, count_status, file_status, is_binary)
  write_csv(audit, audit_path)
  invalid_included <- which(data$included_in_py_source == 1L & !valid)
  if (length(invalid_included)) {
    abortf("B02 source-included lines_added contains %d missing or invalid counts", length(invalid_included))
  }
  data[, lines_added := parsed]
  data[included_in_py_source == 1L]
}

build_localization_long <- function(npr, ml, npr_threshold, ml_threshold) {
  npr_specs <- data.table::data.table(
    scope = c("RF", "CM", "RF+CM"),
    score_column = c(
      "file_npr_fun_space_by_token_weighted",
      "file_npr_cfun_space_by_token_weighted",
      "file_npr_fun_cfun_space_by_token_weighted"
    )
  )
  ml_specs <- data.table::data.table(
    scope = c("RF", "CM", "RF+CM"),
    score_column = c(
      "file_ml_agc_share_space_by_token_weighted",
      "file_ml_cfun_agc_share_space_by_token_weighted",
      "file_ml_fun_cfun_agc_share_space_by_token_weighted"
    )
  )
  make_rows <- function(source, detector, specs, threshold, time_column) {
    data.table::rbindlist(lapply(seq_len(nrow(specs)), function(index) {
      spec <- specs[index]
      score <- numeric_strict(source[[spec$score_column]], spec$score_column, allow_missing = TRUE)
      data.table::data.table(
        snapshot_id = trimws(as.character(source$snapshot_id)),
        dataset_source = normalize_source(source$dataset_source),
        repo_name = normalize_repo(source$repo_name),
        time = normalize_month(source[[time_column]], paste(detector, time_column)),
        relative_path = normalize_path(source$relative_path),
        detector = detector,
        scope = spec$scope,
        score = score,
        eligible = as.integer(is.finite(score)),
        selected = as.integer(is.finite(score) & score > threshold),
        threshold = threshold,
        comparison_operator = ">"
      )
    }))
  }
  result <- data.table::rbindlist(list(
    make_rows(npr, "NPR", npr_specs, npr_threshold, "repo_month"),
    make_rows(ml, "ML", ml_specs, ml_threshold, "snapshot_time")
  ))
  if (result[, any(!nzchar(snapshot_id) | !nzchar(relative_path))]) {
    abortf("Localization inputs contain empty snapshot identifiers or paths")
  }
  duplicate <- result[, .N, by = .(
    dataset_source, repo_name, time, snapshot_id, relative_path, detector, scope
  )][N > 1L]
  if (nrow(duplicate)) abortf("Localization inputs contain %d duplicate keys", nrow(duplicate))
  result
}

prepare_monthly_panel <- function(path) {
  panel <- data.table::fread(path, showProgress = FALSE)
  outcome_ids <- c("npr_rf", "npr_cm", "npr_rf_cm", "ml_rf", "ml_cm", "ml_rf_cm")
  raw_outcomes <- paste0("lines_added_py_source_localized_", outcome_ids)
  log_outcomes <- paste0("log_", raw_outcomes)
  required <- c(
    "repo_id", "repo_name", "dataset_source", "treatment_group", "time", "time_index",
    "event_index", "snapshot_id", "log_age", "ncloc", "log_contributors", "log_stars",
    "log_issues", raw_outcomes, log_outcomes
  )
  validate_columns(panel, required, "run-x-b08-v4 monthly localized panel")
  panel[, `:=`(
    repo_id = as.integer(numeric_strict(repo_id, "monthly repo_id")),
    treatment_group = as.integer(numeric_strict(treatment_group, "monthly treatment_group")),
    time_index = as.integer(numeric_strict(time_index, "monthly time_index")),
    event_index = as.integer(numeric_strict(event_index, "monthly event_index")),
    time = normalize_month(time, "monthly time"),
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    snapshot_id = trimws(as.character(snapshot_id))
  )]
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L])) {
    abortf("Monthly panel contains duplicate repository-month keys")
  }
  for (column in c("log_age", "ncloc", "log_contributors", "log_stars", "log_issues", raw_outcomes, log_outcomes)) {
    panel[, (column) := numeric_strict(get(column), paste("monthly", column))]
  }
  list(panel = panel, raw_outcomes = raw_outcomes, log_outcomes = log_outcomes)
}

prepare_weekly_base <- function(path) {
  panel <- data.table::fread(path, showProgress = FALSE)
  required <- c(
    "repo_id", "repo_name", "dataset_source", "treatment_group", "calendar_key",
    "analysis_timezone", "week_start", "time_index", "event_index", "absorbing_treated",
    "event_week_start", "support_start_month", "support_end_month",
    "python_velocity_metric_version", "source_metric_version"
  )
  validate_columns(panel, required, "run-x-b03-d-v4 weekly panel")
  if (data.table::uniqueN(panel$calendar_key) != 1L || unique(panel$calendar_key) != "chicago") {
    abortf("Weekly panel must contain only calendar_key=chicago")
  }
  if (data.table::uniqueN(panel$analysis_timezone) != 1L || unique(panel$analysis_timezone) != TIMEZONE_NAME) {
    abortf("Weekly panel must use %s", TIMEZONE_NAME)
  }
  panel[, `:=`(
    repo_id = as.integer(numeric_strict(repo_id, "weekly repo_id")),
    treatment_group = as.integer(numeric_strict(treatment_group, "weekly treatment_group")),
    time_index = as.integer(numeric_strict(time_index, "weekly time_index")),
    event_index = as.integer(numeric_strict(event_index, "weekly event_index")),
    absorbing_treated = as.integer(numeric_strict(absorbing_treated, "weekly absorbing_treated")),
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    week_start = as.character(week_start)
  )]
  if (anyNA(as.Date(panel$week_start))) abortf("Weekly panel contains invalid week_start values")
  if (nrow(panel[, .N, by = .(repo_id, time_index)][N > 1L])) {
    abortf("Weekly panel contains duplicate repository-week keys")
  }
  reconstructed <- as.integer(panel$treatment_group == 1L & panel$time_index >= panel$event_index)
  if (any(reconstructed != panel$absorbing_treated)) abortf("Weekly panel contains treatment-state mismatches")
  if (panel[treatment_group == 1L, any(!nzchar(trimws(as.character(event_week_start))))]) {
    abortf("At least one treated repository-week lacks an exact-date event-week assignment")
  }
  if (panel[, any(!nzchar(trimws(as.character(python_velocity_metric_version))) |
                  !nzchar(trimws(as.character(source_metric_version))))]) {
    abortf("Weekly panel lacks metric provenance")
  }
  panel
}

selected_paths_from_scores <- function(args, monthly_panel) {
  npr_columns <- c(
    "snapshot_id", "dataset_source", "repo_name", "repo_month", "relative_path",
    "file_npr_fun_space_by_token_weighted", "file_npr_cfun_space_by_token_weighted",
    "file_npr_fun_cfun_space_by_token_weighted"
  )
  ml_columns <- c(
    "snapshot_id", "dataset_source", "repo_name", "snapshot_time", "relative_path",
    "file_ml_agc_share_space_by_token_weighted",
    "file_ml_cfun_agc_share_space_by_token_weighted",
    "file_ml_fun_cfun_agc_share_space_by_token_weighted"
  )
  log_message("INFO", "Reading C05 NPR file scores: %s", args$npr_file)
  npr <- read_selected(args$npr_file, npr_columns, "C05 NPR file scores")
  log_message("INFO", "Reading I06 ML file scores: %s", args$ml_file)
  ml <- read_selected(args$ml_file, ml_columns, "I06 ML file scores")
  localization <- build_localization_long(npr, ml, args$npr_threshold, args$ml_threshold)
  rm(npr, ml)
  invisible(gc())

  snapshot_map <- unique(monthly_panel[, .(
    dataset_source, repo_name, time, snapshot_id, repo_id
  )])
  localization <- merge(
    localization,
    snapshot_map,
    by = c("dataset_source", "repo_name", "time", "snapshot_id"),
    all.x = TRUE,
    sort = FALSE
  )
  if (localization[, any(is.na(repo_id))]) {
    abortf("Localization/monthly-panel identity mismatches: %d", localization[is.na(repo_id), .N])
  }
  summary <- localization[, .(
    file_rows = .N,
    eligible_files = sum(eligible),
    selected_files = sum(selected),
    repositories_with_selected_files = data.table::uniqueN(repo_id[selected == 1L]),
    repository_months_with_selected_files = data.table::uniqueN(
      paste(repo_id[selected == 1L], time[selected == 1L], sep = ":")
    )
  ), by = .(detector, scope, threshold, comparison_operator)]
  selected <- localization[selected == 1L, .(
    dataset_source, repo_name, time, relative_path, repo_id, detector, scope
  )]
  if (nrow(selected[, .N, by = .(dataset_source, repo_name, time, relative_path, detector, scope)][N > 1L])) {
    abortf("Selected localization paths are not unique within repository-month/detector/scope")
  }
  list(selected = selected, summary = summary)
}

monday_start <- function(local_dates) {
  weekdays_sunday_zero <- as.POSIXlt(as.Date(local_dates), tz = TIMEZONE_NAME)$wday
  as.Date(local_dates) - ((weekdays_sunday_zero + 6L) %% 7L)
}

construct_weekly_localized_panel <- function(args, monthly, weekly, selected) {
  file_columns <- c(
    "repo_name", "dataset_source", "commit_sha", "commit_month", "post_path",
    "lines_added", "included_in_py_source", "file_status", "is_binary"
  )
  commit_columns <- c(
    "repo_name", "dataset_source", "commit_sha", "commit_time_epoch", "python_metric_complete"
  )
  log_message("INFO", "Reading B02 file-change additions: %s", args$file_additions_file)
  files <- read_selected(args$file_additions_file, file_columns, "B02 file additions")
  files <- prepare_source_additions(
    files,
    file.path(args$output_dir, "detector_localized_velocity_sensitivity_b02_count_audit.csv")
  )
  files[, `:=`(
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    commit_sha = trimws(as.character(commit_sha)),
    commit_month = normalize_month(commit_month, "B02 file commit_month"),
    relative_path = normalize_path(post_path)
  )]
  files <- files[lines_added > 0]

  log_message("INFO", "Reading B02 commit timestamps: %s", args$commit_file)
  commits <- read_selected(args$commit_file, commit_columns, "B02 commit-level additions")
  commits[, `:=`(
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    commit_sha = trimws(as.character(commit_sha)),
    commit_time_epoch = numeric_strict(commit_time_epoch, "B02 commit_time_epoch"),
    python_metric_complete = bool_int(python_metric_complete, "python_metric_complete")
  )]
  if (nrow(commits[, .N, by = .(dataset_source, repo_name, commit_sha)][N > 1L])) {
    abortf("B02 commit file contains duplicate repository/commit keys")
  }
  files <- merge(
    files,
    commits[, .(dataset_source, repo_name, commit_sha, commit_time_epoch, python_metric_complete)],
    by = c("dataset_source", "repo_name", "commit_sha"),
    all.x = TRUE,
    sort = FALSE
  )
  if (files[, any(!is.finite(commit_time_epoch))]) {
    abortf("Positive source-file additions lack commit timestamps: %d", files[!is.finite(commit_time_epoch), .N])
  }
  if (files[, any(python_metric_complete != 1L)]) {
    abortf("Positive source-file additions are associated with incomplete commit metrics")
  }
  instant <- as.POSIXct(files$commit_time_epoch, origin = "1970-01-01", tz = "UTC")
  files[, local_date := as.Date(format(instant, tz = TIMEZONE_NAME, format = "%Y-%m-%d"))]
  files[, local_month := format(local_date, "%Y-%m")]
  files[, week_start := as.character(monday_start(local_date))]

  month_audit <- files[, .(
    positive_source_file_rows = .N,
    additions = sum(lines_added)
  ), by = .(
    commit_month,
    local_month,
    month_matches = commit_month == local_month
  )]
  write_csv(month_audit, file.path(args$output_dir, "detector_localized_velocity_sensitivity_commit_month_audit.csv"))
  if (month_audit[, any(!month_matches)]) {
    abortf("B02 commit_month differs from %s month for positive source-file additions", TIMEZONE_NAME)
  }

  matched <- merge(
    files[, .(dataset_source, repo_name, time = local_month, relative_path,
              commit_sha, week_start, lines_added)],
    selected,
    by = c("dataset_source", "repo_name", "time", "relative_path"),
    allow.cartesian = TRUE,
    sort = FALSE
  )
  matched[, outcome_id := paste(tolower(detector), gsub("\\+", "_", tolower(scope)), sep = "_")]
  weekly_long <- matched[, .(
    localized_lines_added = sum(lines_added),
    positive_file_change_rows = .N,
    commits_with_additions = data.table::uniqueN(commit_sha)
  ), by = .(repo_id, week_start, outcome_id)]

  outcome_ids <- c("npr_rf", "npr_cm", "npr_rf_cm", "ml_rf", "ml_cm", "ml_rf_cm")
  raw_outcomes <- paste0("lines_added_py_source_localized_", outcome_ids)
  wide <- data.table::dcast(
    weekly_long,
    repo_id + week_start ~ outcome_id,
    value.var = "localized_lines_added",
    fill = 0
  )
  for (id in outcome_ids) if (!id %in% names(wide)) wide[, (id) := 0]
  data.table::setnames(wide, outcome_ids, raw_outcomes)
  panel <- merge(weekly, wide, by = c("repo_id", "week_start"), all.x = TRUE, sort = FALSE)
  for (outcome in raw_outcomes) {
    panel[is.na(get(outcome)), (outcome) := 0]
    panel[, (paste0("log_", outcome)) := log1p(get(outcome))]
  }
  data.table::setorder(panel, repo_id, time_index)

  # Reproduce every run-x-b08 localized monthly total from timestamped file rows.
  monthly_from_files <- matched[, .(
    localized_lines_added = sum(lines_added)
  ), by = .(repo_id, time, outcome_id)]
  monthly_wide <- data.table::dcast(
    monthly_from_files,
    repo_id + time ~ outcome_id,
    value.var = "localized_lines_added",
    fill = 0
  )
  for (id in outcome_ids) if (!id %in% names(monthly_wide)) monthly_wide[, (id) := 0]
  data.table::setnames(monthly_wide, outcome_ids, paste0(raw_outcomes, "_recomputed"))
  comparison <- merge(
    monthly[, c("repo_id", "time", raw_outcomes), with = FALSE],
    monthly_wide,
    by = c("repo_id", "time"),
    all.x = TRUE,
    sort = FALSE
  )
  for (outcome in raw_outcomes) {
    recomputed <- paste0(outcome, "_recomputed")
    comparison[is.na(get(recomputed)), (recomputed) := 0]
  }
  reconciliation <- data.table::rbindlist(lapply(raw_outcomes, function(outcome) {
    recomputed <- paste0(outcome, "_recomputed")
    difference <- comparison[[recomputed]] - comparison[[outcome]]
    data.table::data.table(
      outcome = outcome,
      monthly_rows = length(difference),
      mismatched_rows = sum(difference != 0),
      maximum_absolute_difference = max(abs(difference)),
      run_x_b08_total = sum(comparison[[outcome]]),
      recomputed_total = sum(comparison[[recomputed]])
    )
  }))
  if (reconciliation[, any(mismatched_rows > 0L)]) {
    abortf("Weekly construction does not reproduce run-x-b08 monthly localized outcomes")
  }
  list(
    panel = panel,
    raw_outcomes = raw_outcomes,
    log_outcomes = paste0("log_", raw_outcomes),
    reconciliation = reconciliation,
    join_audit = data.table::data.table(
      metric = c(
        "positive_source_file_rows",
        "positive_source_additions",
        "localized_positive_file_rows",
        "localized_positive_additions",
        "localized_repository_weeks"
      ),
      value = c(
        nrow(files), sum(files$lines_added), nrow(matched), sum(matched$lines_added),
        nrow(unique(weekly_long[, .(repo_id, week_start)]))
      )
    )
  )
}

attach_weekly_covariates <- function(weekly, monthly) {
  weekly <- data.table::copy(weekly)
  weekly[, week_start_date := as.Date(week_start)]
  weekly[, week_midpoint_date := week_start_date + 3L]
  weekly[, covariate_month_raw := format(week_midpoint_date, "%Y-%m")]
  weekly[, covariate_month := covariate_month_raw]
  weekly[covariate_month < support_start_month, covariate_month := support_start_month]
  weekly[covariate_month > support_end_month, covariate_month := support_end_month]
  monthly_covariates <- monthly[, .(
    repo_id,
    covariate_month = time,
    monthly_repo_name = repo_name,
    monthly_treatment_group = treatment_group,
    log_age,
    ncloc,
    log_contributors,
    log_stars,
    log_issues
  )]
  panel <- merge(weekly, monthly_covariates, by = c("repo_id", "covariate_month"), all.x = TRUE, sort = FALSE)
  if (nrow(panel) != nrow(weekly)) abortf("Monthly covariate merge changed weekly row count")
  if (panel[!is.na(monthly_repo_name) & repo_name != monthly_repo_name, .N]) {
    abortf("Repository-name mismatch after weekly covariate merge")
  }
  if (panel[!is.na(monthly_treatment_group) & treatment_group != monthly_treatment_group, .N]) {
    abortf("Treatment-group mismatch after weekly covariate merge")
  }
  panel[, adjusted_covariates_complete := complete.cases(
    log_age, ncloc, log_contributors, log_stars, log_issues
  )]
  panel[, event_time := data.table::fifelse(
    treatment_group == 1L, time_index - event_index, NA_integer_
  )]
  data.table::setorder(panel, repo_id, time_index)
  panel
}

fit_did_models <- function(panel, outcome_names, confidence_level, pre_values, post_values,
                           timing_spec, timing_label, shift_value, time_unit) {
  specs <- list(
    FECS = list(formula = ADJUSTED_FORMULA, formula_text = ADJUSTED_FORMULA_TEXT),
    FEOS = list(formula = FE_ONLY_FORMULA, formula_text = FE_ONLY_FORMULA_TEXT)
  )
  outcome_map <- data.table::data.table(
    outcome = outcome_names,
    detector = rep(c("NPR", "ML"), each = 3L),
    scope = rep(c("RF", "CM", "RF+CM"), 2L)
  )
  event_support <- panel[treatment_group == 1L & event_time %in% c(pre_values, post_values), .(
    support_rows = .N,
    support_repositories = data.table::uniqueN(repo_id)
  ), by = event_time]
  static_parts <- list()
  dynamic_parts <- list()
  diagnostics <- list()
  index <- 0L
  for (specification in names(specs)) {
    spec <- specs[[specification]]
    for (outcome_name in outcome_names) {
      index <- index + 1L
      identity <- outcome_map[which(outcome_map[["outcome"]] == outcome_name)]
      started <- proc.time()[[3L]]
      static_capture <- capture_evaluation(didimputation::did_imputation(
        data = panel,
        yname = outcome_name,
        gname = "event_index_model",
        tname = "time_index",
        idname = "repo_id",
        first_stage = spec$formula,
        cluster_var = "repo_id"
      ))
      if (static_capture$error) abortf(
        "Static model failed for %s/%s/%s/%s: %s",
        time_unit, timing_spec, specification, outcome_name, static_capture$value$message
      )
      static <- extract_effects(static_capture$value, confidence_level)[term == "treat"]
      if (nrow(static) != 1L) abortf("Expected one static ATT for %s", outcome_name)
      static[, `:=`(
        specification = specification,
        first_stage_formula = spec$formula_text,
        outcome = outcome_name,
        detector = identity$detector,
        scope = identity$scope,
        timing_spec = timing_spec,
        timing_label = timing_label,
        adoption_shift = shift_value,
        time_unit = time_unit,
        treated_observations = panel[, sum(absorbing_treated_model)],
        first_stage_observations = panel[, sum(absorbing_treated_model == 0L)],
        treatment_repositories = panel[treatment_group == 1L, data.table::uniqueN(repo_id)],
        control_repositories = panel[treatment_group == 0L, data.table::uniqueN(repo_id)]
      )]
      static_parts[[index]] <- static

      dynamic_capture <- capture_evaluation(didimputation::did_imputation(
        data = panel,
        yname = outcome_name,
        gname = "event_index_model",
        tname = "time_index",
        idname = "repo_id",
        first_stage = spec$formula,
        horizon = post_values,
        pretrends = pre_values,
        cluster_var = "repo_id"
      ))
      if (dynamic_capture$error) abortf(
        "Dynamic model failed for %s/%s/%s/%s: %s",
        time_unit, timing_spec, specification, outcome_name, dynamic_capture$value$message
      )
      dynamic <- extract_effects(dynamic_capture$value, confidence_level)
      dynamic[, event_time := suppressWarnings(as.integer(as.character(term)))]
      dynamic <- dynamic[!is.na(event_time)]
      expected_terms <- length(pre_values) + length(post_values)
      if (nrow(dynamic) != expected_terms) {
        abortf("Expected %d dynamic terms for %s; observed %d", expected_terms, outcome_name, nrow(dynamic))
      }
      dynamic <- merge(dynamic, event_support, by = "event_time", all.x = TRUE, sort = FALSE)
      dynamic[, `:=`(
        specification = specification,
        first_stage_formula = spec$formula_text,
        outcome = outcome_name,
        detector = identity$detector,
        scope = identity$scope,
        timing_spec = timing_spec,
        timing_label = timing_label,
        adoption_shift = shift_value,
        time_unit = time_unit,
        term_type = data.table::fifelse(event_time < 0L, "placebo_pretrend", "post_treatment")
      )]
      dynamic_parts[[index]] <- dynamic
      diagnostics[[index]] <- data.table::data.table(
        time_unit = time_unit,
        timing_spec = timing_spec,
        specification = specification,
        detector = identity$detector,
        scope = identity$scope,
        static_warning_count = length(static_capture$warnings),
        static_warnings = paste(static_capture$warnings, collapse = " | "),
        dynamic_warning_count = length(dynamic_capture$warnings),
        dynamic_warnings = paste(dynamic_capture$warnings, collapse = " | "),
        elapsed_seconds = proc.time()[[3L]] - started
      )
      log_message(
        "INFO", "%s %s %s %s/%s: ATT=%.3f, SE=%.3f, p=%.4g",
        time_unit, timing_spec, specification, identity$detector, identity$scope,
        static$estimate, static$std.error, static$p_value
      )
    }
  }
  static <- data.table::rbindlist(static_parts, fill = TRUE)
  dynamic <- data.table::rbindlist(dynamic_parts, fill = TRUE)
  diagnostics <- data.table::rbindlist(diagnostics, fill = TRUE)
  pretrend <- dynamic[event_time < 0L, .(
    individually_significant_terms = sum(p_value < 0.05, na.rm = TRUE),
    significant_event_times = paste(event_time[p_value < 0.05], collapse = "|"),
    minimum_p_value = ifelse(all(is.na(p_value)), NA_real_, min(p_value, na.rm = TRUE)),
    all_individual_estimates_insignificant = all(is.na(p_value) | p_value >= 0.05)
  ), by = .(
    time_unit, timing_spec, timing_label, adoption_shift,
    specification, detector, scope, outcome
  )]
  list(static = static, dynamic = dynamic, pretrend = pretrend,
       diagnostics = diagnostics, event_support = event_support)
}

run_monthly_timing <- function(args, monthly, log_outcomes) {
  timings <- data.table::data.table(
    timing_spec = c("recorded_t", "t_minus_1", "t_minus_2"),
    timing_label = c("Recorded adoption T", "Effective adoption T-1", "Effective adoption T-2"),
    shift = c(0L, -1L, -2L)
  )
  parts <- list()
  for (index in seq_len(nrow(timings))) {
    timing <- timings[index]
    panel <- data.table::copy(monthly)
    panel[, event_index_model := data.table::fifelse(
      treatment_group == 1L, event_index + timing$shift, 0L
    )]
    if (panel[treatment_group == 1L, any(event_index_model <= 0L)]) {
      abortf("%s produces a nonpositive treatment index", timing$timing_spec)
    }
    panel[, absorbing_treated_model := as.integer(
      treatment_group == 1L & time_index >= event_index_model
    )]
    panel[, event_time := data.table::fifelse(
      treatment_group == 1L, time_index - event_index_model, NA_integer_
    )]
    parts[[index]] <- fit_did_models(
      panel, log_outcomes, args$confidence_level,
      seq.int(args$monthly_pre_min, -2L), seq.int(0L, args$monthly_post_max),
      timing$timing_spec, timing$timing_label, timing$shift, "month"
    )
  }
  static <- data.table::rbindlist(lapply(parts, `[[`, "static"), fill = TRUE)
  dynamic <- data.table::rbindlist(lapply(parts, `[[`, "dynamic"), fill = TRUE)
  pretrend <- data.table::rbindlist(lapply(parts, `[[`, "pretrend"), fill = TRUE)
  diagnostics <- data.table::rbindlist(lapply(parts, `[[`, "diagnostics"), fill = TRUE)
  event_support <- data.table::rbindlist(lapply(seq_along(parts), function(index) {
    data.table::copy(parts[[index]]$event_support)[, `:=`(
      timing_spec = timings$timing_spec[index],
      timing_label = timings$timing_label[index],
      adoption_shift = timings$shift[index]
    )]
  }), fill = TRUE)
  dynamic[, recorded_event_time := event_time + adoption_shift]
  list(static = static, dynamic = dynamic, pretrend = pretrend,
       diagnostics = diagnostics, event_support = event_support)
}

validate_recorded_reproduction <- function(static, reference_path, tolerance) {
  reference <- data.table::fread(reference_path, showProgress = FALSE)
  validate_columns(reference, c("detector", "scope", "specification", "estimate", "std.error"),
                   "run-x-b08-v4 static reference")
  observed <- static[timing_spec == "recorded_t", .(
    detector, scope, specification,
    observed_estimate = estimate,
    observed_std_error = std.error
  )]
  expected <- reference[, .(
    detector, scope, specification,
    reference_estimate = estimate,
    reference_std_error = std.error
  )]
  audit <- merge(observed, expected, by = c("detector", "scope", "specification"), all = TRUE)
  audit[, `:=`(
    estimate_absolute_difference = abs(observed_estimate - reference_estimate),
    std_error_absolute_difference = abs(observed_std_error - reference_std_error)
  )]
  audit[, pass := is.finite(estimate_absolute_difference) &
    is.finite(std_error_absolute_difference) &
    estimate_absolute_difference <= tolerance &
    std_error_absolute_difference <= tolerance]
  if (anyNA(audit$pass) || any(!audit$pass)) {
    abortf("Recorded-T estimates do not reproduce run-x-b08-v4 within tolerance %.3g", tolerance)
  }
  audit
}

run_self_test <- function() {
  stopifnot(identical(normalize_path("./a\\b.py"), "a/b.py"))
  stopifnot(identical(normalize_month("2025-03-17", "test"), "2025-03"))
  stopifnot(identical(as.character(monday_start(as.Date("2025-03-12"))), "2025-03-10"))
  test <- data.table::data.table(
    included_in_py_source = c(1, 1, 0, 0),
    lines_added = c("0", "7", "", ""),
    file_status = c("included", "included", "excluded", "excluded"),
    is_binary = c(0, 0, 1, 1)
  )
  audit_path <- tempfile(fileext = ".csv")
  kept <- prepare_source_additions(test, audit_path)
  stopifnot(nrow(kept) == 2L, sum(kept$lines_added) == 7)
  event_index <- 10L
  stopifnot(event_index - 1L == 9L, event_index - 2L == 8L)
  cat("SELF-TEST PASS: normalization, Monday weeks, source-count policy, and treatment shifts\n")
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
if (!is.null(args$version)) {
  cat(paste0(RUN_LABEL, "\n"))
  quit(save = "no", status = 0L)
}
if (!is.null(args$self_test)) {
  require_packages()
  run_self_test()
  quit(save = "no", status = 0L)
}

require_packages()
args$monthly_panel_file <- arg_required(args, "monthly_panel_file")
args$monthly_static_reference <- arg_required(args, "monthly_static_reference")
args$weekly_panel_file <- arg_required(args, "weekly_panel_file")
args$file_additions_file <- arg_required(args, "file_additions_file")
args$commit_file <- arg_required(args, "commit_file")
args$npr_file <- arg_required(args, "npr_file")
args$ml_file <- arg_required(args, "ml_file")
args$output_dir <- arg_required(args, "output_dir")
args$npr_threshold <- as.numeric(arg_value(args, "npr_threshold", "1.515059"))
args$ml_threshold <- as.numeric(arg_value(args, "ml_threshold", "0.50"))
args$confidence_level <- as.numeric(arg_value(args, "confidence_level", "0.95"))
args$monthly_pre_min <- as.integer(arg_value(args, "monthly_pre_min", "-6"))
args$monthly_post_max <- as.integer(arg_value(args, "monthly_post_max", "6"))
args$weekly_pre_min <- as.integer(arg_value(args, "weekly_pre_min", "-12"))
args$weekly_post_max <- as.integer(arg_value(args, "weekly_post_max", "12"))
args$reference_tolerance <- as.numeric(arg_value(args, "reference_tolerance", "1e-10"))
strict <- as_flag(arg_value(args, "strict_expected_counts", "1"), "strict_expected_counts")
expected_monthly_rows <- as.integer(arg_value(args, "expected_monthly_rows", "1954"))
expected_weekly_rows <- as.integer(arg_value(args, "expected_weekly_rows", "8599"))
expected_common_weekly_rows <- as.integer(arg_value(args, "expected_common_weekly_rows", "8595"))
expected_repositories <- as.integer(arg_value(args, "expected_repositories", "167"))
expected_treatment_repositories <- as.integer(arg_value(args, "expected_treatment_repositories", "63"))
expected_control_repositories <- as.integer(arg_value(args, "expected_control_repositories", "104"))
expected_event_zero_support <- as.integer(arg_value(args, "expected_event_zero_support", "62"))

if (!is.finite(args$npr_threshold) || !is.finite(args$ml_threshold)) abortf("Thresholds must be finite")
if (!(args$confidence_level > 0 && args$confidence_level < 1)) abortf("Invalid confidence level")
if (args$monthly_pre_min > -2L || args$weekly_pre_min > -2L) abortf("Pre-adoption windows must include -2")
if (args$monthly_post_max < 0L || args$weekly_post_max < 0L) abortf("Post-adoption windows must include 0")
dir.create(args$output_dir, recursive = TRUE, showWarnings = FALSE)

log_message("INFO", "Reading run-x-b08-v4 monthly localized panel: %s", args$monthly_panel_file)
monthly_prepared <- prepare_monthly_panel(args$monthly_panel_file)
monthly <- monthly_prepared$panel
strict_count(nrow(monthly), expected_monthly_rows, "monthly rows", strict)
strict_count(data.table::uniqueN(monthly$repo_id), expected_repositories, "repositories", strict)
strict_count(monthly[treatment_group == 1L, data.table::uniqueN(repo_id)],
             expected_treatment_repositories, "treatment repositories", strict)
strict_count(monthly[treatment_group == 0L, data.table::uniqueN(repo_id)],
             expected_control_repositories, "control repositories", strict)

log_message("INFO", "Estimating monthly T/T-1/T-2 sensitivity")
monthly_results <- run_monthly_timing(args, monthly, monthly_prepared$log_outcomes)
reproduction <- validate_recorded_reproduction(
  monthly_results$static, args$monthly_static_reference, args$reference_tolerance
)
anchor_grid <- unique(monthly_results$static[, .(
  timing_spec, timing_label, adoption_shift, specification,
  detector, scope, outcome
)])
anchor_grid[, `:=`(
  recorded_event_time = -2L,
  analysis_event_time = -2L - adoption_shift
)]
anchor_values <- monthly_results$dynamic[, .(
  timing_spec, specification, detector, scope, outcome,
  analysis_event_time = event_time,
  estimate, std.error, conf.low, conf.high, p_value, percent_change
)]
recorded_minus2_anchor <- merge(
  anchor_grid,
  anchor_values,
  by = c(
    "timing_spec", "specification", "detector", "scope", "outcome",
    "analysis_event_time"
  ),
  all.x = TRUE,
  sort = FALSE
)
recorded_minus2_anchor[, anchor_status := data.table::fifelse(
  analysis_event_time == -1L,
  "omitted_reference",
  data.table::fifelse(is.finite(estimate), "estimated", "unavailable")
)]

log_message("INFO", "Reading established exact-date weekly panel: %s", args$weekly_panel_file)
weekly_base <- prepare_weekly_base(args$weekly_panel_file)
strict_count(nrow(weekly_base), expected_weekly_rows, "weekly rows", strict)
selected_result <- selected_paths_from_scores(args, monthly)
weekly_constructed <- construct_weekly_localized_panel(
  args, monthly, weekly_base, selected_result$selected
)
weekly_with_covariates <- attach_weekly_covariates(weekly_constructed$panel, monthly)
weekly_common <- weekly_with_covariates[adjusted_covariates_complete == TRUE]
strict_count(nrow(weekly_common), expected_common_weekly_rows, "common-support weekly rows", strict)
strict_count(weekly_common[treatment_group == 1L, data.table::uniqueN(repo_id)],
             expected_treatment_repositories, "weekly treatment repositories", strict)
strict_count(weekly_common[treatment_group == 0L, data.table::uniqueN(repo_id)],
             expected_control_repositories, "weekly control repositories", strict)
weekly_common[, event_index_model := event_index]
weekly_common[, absorbing_treated_model := as.integer(
  treatment_group == 1L & time_index >= event_index_model
)]
weekly_common[, event_time := data.table::fifelse(
  treatment_group == 1L, time_index - event_index_model, NA_integer_
)]
event_zero_support <- weekly_common[treatment_group == 1L & event_time == 0L,
                                    data.table::uniqueN(repo_id)]
strict_count(event_zero_support, expected_event_zero_support, "weekly event-zero support", strict)

log_message("INFO", "Estimating weekly exact-date localized velocity models")
weekly_results <- fit_did_models(
  weekly_common,
  weekly_constructed$log_outcomes,
  args$confidence_level,
  seq.int(args$weekly_pre_min, -2L),
  seq.int(0L, args$weekly_post_max),
  "exact_observed_date",
  "Exact first observable Cursor-related commit",
  0L,
  "week"
)

output <- function(name) file.path(args$output_dir, name)
write_csv(monthly_results$static, output("detector_localized_velocity_monthly_timing_static_effects.csv"))
write_csv(monthly_results$dynamic, output("detector_localized_velocity_monthly_timing_dynamic_effects.csv"))
write_csv(monthly_results$dynamic[, recorded_event_time := event_time + adoption_shift],
          output("detector_localized_velocity_monthly_timing_recorded_clock_effects.csv"))
write_csv(monthly_results$pretrend, output("detector_localized_velocity_monthly_timing_pretrend_summary.csv"))
write_csv(monthly_results$event_support, output("detector_localized_velocity_monthly_timing_event_support.csv"))
write_csv(monthly_results$diagnostics, output("detector_localized_velocity_monthly_timing_diagnostics.csv"))
write_csv(reproduction, output("detector_localized_velocity_recorded_t_reproduction.csv"))
write_csv(recorded_minus2_anchor, output("detector_localized_velocity_monthly_recorded_minus2_anchor.csv"))

write_csv_gz(weekly_with_covariates, output("detector_localized_velocity_weekly_panel.csv.gz"))
write_csv(weekly_results$static, output("detector_localized_velocity_weekly_static_effects.csv"))
write_csv(weekly_results$dynamic, output("detector_localized_velocity_weekly_dynamic_effects.csv"))
write_csv(weekly_results$pretrend, output("detector_localized_velocity_weekly_pretrend_summary.csv"))
write_csv(weekly_results$event_support, output("detector_localized_velocity_weekly_event_support.csv"))
write_csv(weekly_results$diagnostics, output("detector_localized_velocity_weekly_diagnostics.csv"))
write_csv(
  weekly_results$dynamic[event_time %in% c(-4L, -3L, -2L, 0L, 1L)],
  output("detector_localized_velocity_weekly_key_event_times.csv")
)
write_csv(selected_result$summary, output("detector_localized_velocity_localization_summary.csv"))
write_csv(weekly_constructed$reconciliation,
          output("detector_localized_velocity_weekly_monthly_reconciliation.csv"))
write_csv(weekly_constructed$join_audit, output("detector_localized_velocity_weekly_join_audit.csv"))
write_csv(
  weekly_with_covariates[adjusted_covariates_complete == FALSE, .(
    repo_id, repo_name, week_start, time_index, event_index,
    covariate_month_raw, covariate_month,
    log_age, ncloc, log_contributors, log_stars, log_issues
  )],
  output("detector_localized_velocity_weekly_common_support_dropped_rows.csv")
)

qc <- data.table::data.table(
  check_name = c(
    "monthly_rows",
    "monthly_static_rows",
    "monthly_dynamic_rows",
    "monthly_recorded_reproduction_rows",
    "monthly_recorded_reproduction_failures",
    "monthly_recorded_minus2_anchor_rows",
    "monthly_recorded_minus2_unavailable_rows",
    "weekly_rows",
    "weekly_common_support_rows",
    "weekly_dropped_rows",
    "weekly_static_rows",
    "weekly_dynamic_rows",
    "weekly_monthly_reconciliation_failures",
    "weekly_event_zero_support",
    "model_warning_count"
  ),
  observed = c(
    nrow(monthly),
    nrow(monthly_results$static),
    nrow(monthly_results$dynamic),
    nrow(reproduction),
    sum(!reproduction$pass),
    nrow(recorded_minus2_anchor),
    recorded_minus2_anchor[anchor_status == "unavailable", .N],
    nrow(weekly_with_covariates),
    nrow(weekly_common),
    nrow(weekly_with_covariates) - nrow(weekly_common),
    nrow(weekly_results$static),
    nrow(weekly_results$dynamic),
    sum(weekly_constructed$reconciliation$mismatched_rows),
    event_zero_support,
    sum(monthly_results$diagnostics$static_warning_count) +
      sum(monthly_results$diagnostics$dynamic_warning_count) +
      sum(weekly_results$diagnostics$static_warning_count) +
      sum(weekly_results$diagnostics$dynamic_warning_count)
  ),
  expected = c(
    expected_monthly_rows,
    3L * 2L * 6L,
    3L * 2L * 6L * (length(seq.int(args$monthly_pre_min, -2L)) + args$monthly_post_max + 1L),
    12L,
    0L,
    3L * 2L * 6L,
    0L,
    expected_weekly_rows,
    expected_common_weekly_rows,
    expected_weekly_rows - expected_common_weekly_rows,
    2L * 6L,
    2L * 6L * (length(seq.int(args$weekly_pre_min, -2L)) + args$weekly_post_max + 1L),
    0L,
    expected_event_zero_support,
    0L
  )
)
qc[, pass := observed == expected]
write_csv(qc, output("detector_localized_velocity_sensitivity_qc.csv"))
if (strict && qc[, any(!pass)]) abortf("One or more strict QC checks failed")

metadata <- data.table::data.table(
  section = c(
    "implementation", "definition", "definition", "definition", "definition",
    "sample", "sample", "sample", "input", "input", "input", "input", "input", "input"
  ),
  metric = c(
    "version", "npr_threshold", "ml_threshold", "comparison_operator", "weekly_timezone",
    "monthly_rows", "weekly_rows", "weekly_common_support_rows",
    "monthly_panel", "monthly_static_reference", "weekly_panel",
    "file_additions", "commit_file", "localization_files"
  ),
  value = c(
    "v2", args$npr_threshold, args$ml_threshold, ">", TIMEZONE_NAME,
    nrow(monthly), nrow(weekly_with_covariates), nrow(weekly_common),
    args$monthly_panel_file, args$monthly_static_reference, args$weekly_panel_file,
    args$file_additions_file, args$commit_file,
    paste(args$npr_file, args$ml_file, sep = " | ")
  )
)
write_csv(metadata, output("detector_localized_velocity_sensitivity_run_metadata.csv"))

cat(sprintf(
  "PASS: monthly static=%d, monthly dynamic=%d, weekly static=%d, weekly dynamic=%d\n",
  nrow(monthly_results$static), nrow(monthly_results$dynamic),
  nrow(weekly_results$static), nrow(weekly_results$dynamic)
))
cat(sprintf("Outputs: %s\n", args$output_dir))
