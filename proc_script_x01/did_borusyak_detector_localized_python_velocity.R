#!/usr/bin/env Rscript

# run-x-b08 v4: detector-localized Python velocity DiD
#
# Inputs:
#   1. The B06 matched repository-month panel, which supplies treatment timing,
#      repository identifiers, covariates, and whole-Python additions.
#   2. B02 file-change records, which supply monthly Python source additions by
#      repository-relative path.
#   3. C05 file-level NPR measurements for RF, CM, and RF+CM.
#   4. I06 file-level ML shares for RF, CM, and RF+CM.
#
# Outputs:
#   - a repository-month panel with six localized velocity outcomes;
#   - static and event-time Borusyak et al. DiD estimates for FECS and FEOS;
#   - localization, join, and reconciliation audits;
#   - a LaTeX table for the post-adoption velocity section.
#
# The script is independent of prior shell wrappers. Its estimation design
# follows the established whole-Python velocity analysis.

options(stringsAsFactors = FALSE, warn = 1)

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
  value
}

arg_value <- function(args, name, default) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) default else value
}

as_flag <- function(value, name) {
  if (!value %in% c("0", "1")) abortf("--%s must be 0 or 1", gsub("_", "-", name))
  identical(value, "1")
}

require_packages <- function() {
  packages <- c("data.table", "didimputation", "fixest")
  missing <- packages[!vapply(packages, requireNamespace, logical(1L), quietly = TRUE)]
  if (length(missing) > 0L) abortf("Missing R packages: %s", paste(missing, collapse = ", "))
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
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

# B02 retains excluded file-change records, including binary files whose
# numstat counts are absent. Such records are not observations of zero lines.
# Audit all records; validate counts only for source-included records. Included
# binary Python files remain errors, as in the upstream collector.
prepare_source_additions <- function(input, audit_path = NULL) {
  data <- data.table::copy(input)
  validate_columns(data, c("included_in_py_source", "lines_added"), "B02 file additions")
  data[, included_in_py_source := bool_int(included_in_py_source, "included_in_py_source")]
  raw <- trimws(as.character(data$lines_added))
  parsed <- suppressWarnings(as.numeric(raw))
  missing <- is.na(raw) | !nzchar(raw) | tolower(raw) %in% c("na", "nan", "none", "null")
  valid <- is.finite(parsed) & parsed >= 0 & parsed == floor(parsed)
  category <- rep("valid_nonnegative_integer", length(parsed))
  category[!valid] <- "invalid_numeric_count"
  category[is.na(parsed) & !missing] <- "nonnumeric_count"
  category[missing] <- "missing_count"
  diagnostic <- data.table::data.table(
    included_in_py_source = data$included_in_py_source,
    count_status = category,
    file_status = if ("file_status" %in% names(data)) as.character(data$file_status) else "not_provided",
    is_binary = if ("is_binary" %in% names(data)) as.character(data$is_binary) else "not_provided"
  )
  audit <- diagnostic[, .(rows = .N), by = .(included_in_py_source, count_status, file_status, is_binary)]
  data.table::setorder(audit, included_in_py_source, count_status, file_status, is_binary)
  if (!is.null(audit_path)) write_csv(audit, audit_path)
  invalid_included <- which(data$included_in_py_source == 1L & !valid)
  if (length(invalid_included)) {
    abortf("B02 source-included lines_added contains %d missing or invalid counts; no values were replaced by zero. Inspect the B02 count audit.", length(invalid_included))
  }
  data[, lines_added := parsed]
  kept <- data[included_in_py_source == 1L]
  log_message("INFO", "B02 count audit: rows=%d; included=%d; excluded=%d; excluded missing=%d; included invalid=0",
              nrow(data), nrow(kept), sum(data$included_in_py_source == 0L),
              sum(data$included_in_py_source == 0L & missing))
  list(data = kept, audit = audit)
}

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

strict_count <- function(observed, expected, label, strict) {
  if (is.na(expected) || expected < 0L) return(invisible(TRUE))
  if (as.integer(observed) != as.integer(expected)) {
    text <- sprintf("Count mismatch for %s: expected %d, observed %d", label, expected, observed)
    if (strict) abortf("%s", text) else log_message("WARNING", "%s", text)
  }
  invisible(TRUE)
}

read_selected <- function(path, columns, label) {
  header <- names(data.table::fread(path, nrows = 0L, showProgress = FALSE))
  missing <- setdiff(columns, header)
  if (length(missing) > 0L) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
  data.table::fread(path, select = columns, showProgress = TRUE, na.strings = c("", "NA", "NaN"))
}

build_localization_long <- function(npr, ml, npr_threshold, ml_threshold) {
  npr_specs <- data.table::data.table(
    scope = c("RF", "CM", "RF+CM"),
    score_column = c(
      "file_npr_fun_space_by_token_weighted",
      "file_npr_cfun_space_by_token_weighted",
      "file_npr_fun_cfun_space_by_token_weighted"
    ),
    status_column = c("file_npr_fun_status", "file_npr_cfun_status", "file_npr_fun_cfun_status")
  )
  ml_specs <- data.table::data.table(
    scope = c("RF", "CM", "RF+CM"),
    score_column = c(
      "file_ml_agc_share_space_by_token_weighted",
      "file_ml_cfun_agc_share_space_by_token_weighted",
      "file_ml_fun_cfun_agc_share_space_by_token_weighted"
    ),
    status_column = c("file_ml_agc_status", "file_ml_cfun_agc_status", "file_ml_fun_cfun_agc_status")
  )

  make_rows <- function(source, detector, specs, threshold, time_column) {
    parts <- lapply(seq_len(nrow(specs)), function(index) {
      spec <- specs[index]
      score <- numeric_strict(source[[spec$score_column]], spec$score_column, allow_missing = TRUE)
      status <- trimws(as.character(source[[spec$status_column]]))
      data.table::data.table(
        snapshot_id = trimws(as.character(source$snapshot_id)),
        dataset_source = normalize_source(source$dataset_source),
        repo_name = normalize_repo(source$repo_name),
        time = normalize_month(source[[time_column]], paste(detector, time_column)),
        relative_path = normalize_path(source$relative_path),
        detector = detector,
        scope = spec$scope,
        score = score,
        status = status,
        eligible = as.integer(is.finite(score)),
        selected = as.integer(is.finite(score) & score > threshold),
        threshold = threshold,
        comparison_operator = ">"
      )
    })
    data.table::rbindlist(parts, use.names = TRUE)
  }

  result <- data.table::rbindlist(list(
    make_rows(npr, "NPR", npr_specs, npr_threshold, "repo_month"),
    make_rows(ml, "ML", ml_specs, ml_threshold, "snapshot_time")
  ), use.names = TRUE)
  if (result[, any(!nzchar(snapshot_id) | !nzchar(relative_path))]) {
    abortf("Localization inputs contain empty snapshot identifiers or paths")
  }
  duplicate <- result[, .N, by = .(
    dataset_source, repo_name, time, snapshot_id, relative_path, detector, scope
  )][N > 1L]
  if (nrow(duplicate) > 0L) {
    abortf("Localization inputs contain %d duplicate repository-month/snapshot/path/detector/scope keys", nrow(duplicate))
  }
  result
}

build_panel <- function(args) {
  b06_columns <- c(
    "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
    "time", "time_index", "event", "event_index", "time_to_event", "snapshot_key",
    "log_age", "ncloc", "log_contributors", "log_stars", "log_issues",
    "lines_added_py_source", "log_lines_added_py_source", "is_treatment", "post_event", "cursor"
  )
  npr_columns <- c(
    "snapshot_id", "dataset_source", "repo_name", "repo_month", "relative_path",
    "file_npr_fun_space_by_token_weighted", "file_npr_fun_status",
    "file_npr_cfun_space_by_token_weighted", "file_npr_cfun_status",
    "file_npr_fun_cfun_space_by_token_weighted", "file_npr_fun_cfun_status"
  )
  ml_columns <- c(
    "snapshot_id", "dataset_source", "repo_name", "snapshot_time", "relative_path",
    "file_ml_agc_share_space_by_token_weighted", "file_ml_agc_status",
    "file_ml_cfun_agc_share_space_by_token_weighted", "file_ml_cfun_agc_status",
    "file_ml_fun_cfun_agc_share_space_by_token_weighted", "file_ml_fun_cfun_agc_status"
  )
  addition_columns <- c(
    "repo_name", "dataset_source", "commit_month", "post_path", "lines_added", "included_in_py_source",
    "file_status", "is_binary"
  )

  log_message("INFO", "Reading B06 matched panel: %s", args$b06_panel_file)
  panel <- read_selected(args$b06_panel_file, b06_columns, "B06 panel")
  panel[, `:=`(
    repo_id = as.integer(numeric_strict(repo_id, "B06 repo_id")),
    time_index = as.integer(numeric_strict(time_index, "B06 time_index")),
    event_index = as.integer(numeric_strict(event_index, "B06 event_index")),
    treatment_group = as.integer(numeric_strict(treatment_group, "B06 treatment_group")),
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    time = normalize_month(time, "B06 time"),
    snapshot_id = trimws(as.character(snapshot_key))
  )]
  duplicate_panel <- panel[, .N, by = .(repo_id, time_index)][N > 1L]
  if (nrow(duplicate_panel) > 0L) abortf("B06 contains %d duplicate repository-month keys", nrow(duplicate_panel))
  if (panel[, any(!nzchar(snapshot_id))]) abortf("B06 contains empty snapshot identifiers")

  log_message("INFO", "Reading C05 NPR file scores: %s", args$npr_file)
  npr <- read_selected(args$npr_file, npr_columns, "C05 NPR file scores")
  log_message("INFO", "Reading I06 ML file scores: %s", args$ml_file)
  ml <- read_selected(args$ml_file, ml_columns, "I06 ML file scores")
  localization <- build_localization_long(npr, ml, args$npr_threshold, args$ml_threshold)
  rm(npr, ml)
  invisible(gc())

  snapshot_map <- unique(panel[, .(
    dataset_source, repo_name, time, snapshot_id, repo_id, time_index
  )])
  duplicate_snapshot_month <- snapshot_map[, .N, by = .(
    dataset_source, repo_name, time, snapshot_id
  )][N > 1L]
  if (nrow(duplicate_snapshot_month) > 0L) {
    abortf("B06 contains %d duplicate repository-month/snapshot keys", nrow(duplicate_snapshot_month))
  }
  localization <- merge(
    localization,
    snapshot_map,
    by = c("dataset_source", "repo_name", "time", "snapshot_id"),
    all.x = TRUE,
    sort = FALSE
  )
  unmatched_localization <- localization[is.na(repo_id)]
  if (nrow(unmatched_localization) > 0L) {
    abortf("Localization/B06 repository-month identity mismatches: %d", nrow(unmatched_localization))
  }

  snapshot_reuse <- localization[, .(
    observed_months = data.table::uniqueN(time)
  ), by = .(dataset_source, repo_name, snapshot_id, relative_path, detector, scope)]
  snapshot_reuse_summary <- snapshot_reuse[, .(
    snapshot_file_keys_reused_across_months = sum(observed_months > 1L),
    maximum_months_per_snapshot_file_key = max(observed_months)
  ), by = .(detector, scope)]

  localization_summary <- localization[, .(
    file_rows = .N,
    eligible_files = sum(eligible),
    selected_files = sum(selected),
    repositories_with_selected_files = data.table::uniqueN(repo_id[selected == 1L]),
    repository_months_with_selected_files = data.table::uniqueN(paste(repo_id[selected == 1L], time_index[selected == 1L], sep = ":"))
  ), by = .(detector, scope, threshold, comparison_operator)]
  localization_summary <- merge(
    localization_summary,
    snapshot_reuse_summary,
    by = c("detector", "scope"),
    all.x = TRUE,
    sort = FALSE
  )

  selected <- localization[selected == 1L, .(
    dataset_source,
    repo_name,
    time,
    relative_path,
    repo_id,
    time_index,
    detector,
    scope
  )]
  rm(localization)
  invisible(gc())

  log_message("INFO", "Reading B02 file additions: %s", args$file_additions_file)
  additions <- read_selected(args$file_additions_file, addition_columns, "B02 file additions")
  prepared <- prepare_source_additions(additions, file.path(args$output_dir,
    "detector_localized_python_velocity_b02_count_audit.csv"))
  additions <- prepared$data
  additions <- additions[lines_added > 0, .(
    lines_added = sum(lines_added)
  ), by = .(
    dataset_source = normalize_source(dataset_source),
    repo_name = normalize_repo(repo_name),
    time = normalize_month(commit_month, "B02 commit_month"),
    relative_path = normalize_path(post_path)
  )]
  if (additions[, any(!nzchar(relative_path))]) abortf("Included B02 source additions contain empty post paths")

  # Reconcile the complete source-addition total before applying localization.
  # This check detects undercounting, not only localized totals above B06.
  monthly <- additions[, .(b02_source_additions = sum(lines_added)), by = .(dataset_source, repo_name, time)]
  monthly_audit <- merge(panel[, .(repo_id, time_index, dataset_source, repo_name, time,
                                 b06_source_additions = lines_added_py_source)], monthly,
                         by = c("dataset_source", "repo_name", "time"), all.x = TRUE, sort = FALSE)
  monthly_audit[is.na(b02_source_additions), b02_source_additions := 0]
  monthly_audit[, b06_source_additions := numeric_strict(b06_source_additions, "B06 source additions")]
  monthly_audit[, difference := b02_source_additions - b06_source_additions]
  write_csv(monthly_audit, file.path(args$output_dir,
    "detector_localized_python_velocity_b02_monthly_reconciliation.csv"))
  if (monthly_audit[, any(!is.finite(difference) | difference != 0)]) {
    abortf("B02 source-addition totals do not reproduce B06; inspect the monthly reconciliation before estimation")
  }

  selected_additions <- merge(
    selected,
    additions,
    by = c("dataset_source", "repo_name", "time", "relative_path"),
    all.x = TRUE,
    sort = FALSE
  )
  selected_additions[is.na(lines_added), lines_added := 0]
  selected_additions[, outcome_id := paste(tolower(detector), gsub("\\+", "_", tolower(scope)), sep = "_")]
  localized <- selected_additions[, .(
    localized_lines_added = sum(lines_added),
    selected_files = .N,
    selected_files_with_additions = sum(lines_added > 0)
  ), by = .(repo_id, time_index, outcome_id)]

  outcome_ids <- c("npr_rf", "npr_cm", "npr_rf_cm", "ml_rf", "ml_cm", "ml_rf_cm")
  outcome_names <- paste0("lines_added_py_source_localized_", outcome_ids)
  wide <- data.table::dcast(
    localized,
    repo_id + time_index ~ outcome_id,
    value.var = "localized_lines_added",
    fill = 0
  )
  for (outcome_id in outcome_ids) if (!outcome_id %in% names(wide)) wide[, (outcome_id) := 0]
  data.table::setnames(wide, outcome_ids, outcome_names)
  panel <- merge(panel, wide, by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
  for (outcome in outcome_names) {
    panel[is.na(get(outcome)), (outcome) := 0]
    panel[, (paste0("log_", outcome)) := log1p(get(outcome))]
  }
  data.table::setorder(panel, repo_id, time_index)

  reconciliation <- data.table::rbindlist(lapply(outcome_names, function(outcome) {
    data.table::data.table(
      outcome = outcome,
      localized_total = sum(panel[[outcome]]),
      whole_python_total = sum(panel$lines_added_py_source),
      rows_exceeding_whole_python = sum(panel[[outcome]] > panel$lines_added_py_source),
      maximum_excess = max(panel[[outcome]] - panel$lines_added_py_source)
    )
  }))
  if (reconciliation[, any(rows_exceeding_whole_python > 0L)]) {
    abortf("One or more localized outcomes exceed whole-Python source additions")
  }

  join_audit <- data.table::data.table(
    metric = c(
      "b06_rows", "b06_repositories", "localization_selected_rows",
      "selected_rows_with_positive_additions", "selected_rows_with_zero_additions",
      "b02_positive_source_path_months"
    ),
    value = c(
      nrow(panel), data.table::uniqueN(panel$repo_id), nrow(selected_additions),
      selected_additions[, sum(lines_added > 0)], selected_additions[, sum(lines_added == 0)], nrow(additions)
    )
  )
  list(
    panel = panel,
    localization_summary = localization_summary,
    join_audit = join_audit,
    reconciliation = reconciliation,
    outcome_names = paste0("log_", outcome_names)
  )
}

extract_effects <- function(result, confidence_level) {
  table <- data.table::as.data.table(result)
  validate_columns(table, c("term", "estimate", "std.error"), "did_imputation result")
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  table[, `:=`(
    conf.low = estimate - critical * std.error,
    conf.high = estimate + critical * std.error,
    p_value = data.table::fifelse(std.error > 0, 2 * stats::pnorm(-abs(estimate / std.error)), NA_real_),
    percent_change = 100 * (exp(estimate) - 1)
  )]
  table
}

fit_models <- function(panel, outcome_names, confidence_level, min_event, max_event,
                       estimator = didimputation::did_imputation, report = TRUE) {
  panel[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
  panel[, event_time_normalized := data.table::fifelse(
    treatment_group == 1L, time_index - event_index, NA_integer_
  )]
  specs <- list(
    FECS = list(
      formula = ~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index,
      formula_text = "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
    ),
    FEOS = list(
      formula = ~ 1 | repo_id + time_index,
      formula_text = "~ 1 | repo_id + time_index"
    )
  )
  outcome_map <- data.table::data.table(
    outcome = outcome_names,
    detector = rep(c("NPR", "ML"), each = 3L),
    scope = rep(c("RF", "CM", "RF+CM"), 2L)
  )
  static_parts <- list()
  dynamic_parts <- list()
  diagnostics <- list()
  index <- 0L
  for (spec_name in names(specs)) {
    spec <- specs[[spec_name]]
    for (outcome_name in outcome_names) {
      index <- index + 1L
      identity <- outcome_map[which(outcome_map[["outcome"]] == outcome_name)]
      if (nrow(identity) != 1L) abortf("Missing outcome identity for %s", outcome_name)
      started <- proc.time()[[3L]]
      static_fit <- tryCatch(
        estimator(
          data = panel, yname = outcome_name, gname = "event_index", tname = "time_index",
          idname = "repo_id", first_stage = spec$formula, cluster_var = "repo_id"
        ),
        error = function(error) error
      )
      if (inherits(static_fit, "error")) abortf("Static model failed for %s/%s: %s", spec_name, outcome_name, conditionMessage(static_fit))
      static <- extract_effects(static_fit, confidence_level)[term == "treat"]
      if (nrow(static) != 1L) abortf("Expected one static ATT for %s/%s; observed %d", spec_name, outcome_name, nrow(static))
      static[, `:=`(
        specification = spec_name,
        first_stage_formula = spec$formula_text,
        outcome = outcome_name,
        detector = identity$detector,
        scope = identity$scope,
        treated_observations = panel[, sum(absorbing_treated)],
        first_stage_observations = panel[, sum(absorbing_treated == 0L)],
        treatment_repositories = panel[treatment_group == 1L, data.table::uniqueN(repo_id)],
        control_repositories = panel[treatment_group == 0L, data.table::uniqueN(repo_id)]
      )]
      static_parts[[index]] <- static

      pretrends <- seq.int(min_event, -2L)
      horizon <- seq.int(min_event, max_event)
      dynamic_fit <- tryCatch(
        estimator(
          data = panel, yname = outcome_name, gname = "event_index", tname = "time_index",
          idname = "repo_id", first_stage = spec$formula,
          horizon = horizon, pretrends = pretrends, cluster_var = "repo_id"
        ),
        error = function(error) error
      )
      if (inherits(dynamic_fit, "error")) abortf("Dynamic model failed for %s/%s: %s", spec_name, outcome_name, conditionMessage(dynamic_fit))
      dynamic <- extract_effects(dynamic_fit, confidence_level)
      dynamic[, event_time := suppressWarnings(as.integer(as.character(term)))]
      dynamic <- dynamic[!is.na(event_time)]
      dynamic[, `:=`(
        specification = spec_name,
        first_stage_formula = spec$formula_text,
        outcome = outcome_name,
        detector = identity$detector,
        scope = identity$scope,
        term_type = data.table::fifelse(event_time < 0L, "placebo_pretrend", "post_treatment")
      )]
      dynamic_parts[[index]] <- dynamic
      diagnostics[[index]] <- data.table::data.table(
        specification = spec_name,
        outcome = outcome_name,
        detector = identity$detector,
        scope = identity$scope,
        static_terms = nrow(static),
        dynamic_terms = nrow(dynamic),
        elapsed_seconds = proc.time()[[3L]] - started
      )
      if (report) log_message("INFO", "%s %s/%s: ATT=%.3f, SE=%.3f, change=%+.1f%%", spec_name, identity$detector, identity$scope, static$estimate, static$std.error, static$percent_change)
    }
  }
  static <- data.table::rbindlist(static_parts, fill = TRUE)
  dynamic <- data.table::rbindlist(dynamic_parts, fill = TRUE)
  diagnostics <- data.table::rbindlist(diagnostics)
  static[, `:=`(detector_order = match(detector, c("NPR", "ML")), scope_order = match(scope, c("RF", "CM", "RF+CM")))]
  dynamic[, `:=`(detector_order = match(detector, c("NPR", "ML")), scope_order = match(scope, c("RF", "CM", "RF+CM")))]
  data.table::setorder(static, detector_order, scope_order, specification)
  data.table::setorder(dynamic, detector_order, scope_order, specification, event_time)
  static[, c("detector_order", "scope_order") := NULL]
  dynamic[, c("detector_order", "scope_order") := NULL]
  list(static = static, dynamic = dynamic, diagnostics = diagnostics)
}

significance_stars <- function(p) {
  if (is.na(p)) return("")
  if (p < 0.001) return("^{***}")
  if (p < 0.01) return("^{**}")
  if (p < 0.05) return("^{*}")
  if (p < 0.10) return("^{\\dagger}")
  ""
}

format_att <- function(row) {
  marker <- if (!is.na(row$p_value) && row$p_value < 0.05) "\\checkmark" else "\\times"
  sprintf("$%.3f%s\\;(%s)\\;(%.3f)$", row$estimate, significance_stars(row$p_value), marker, row$std.error)
}

format_change <- function(value) sprintf("$%+.1f\\%%$", value)

write_latex_table <- function(static, path) {
  order <- data.table::CJ(
    detector = c("NPR", "ML"),
    scope = c("RF", "CM", "RF+CM"),
    unique = TRUE
  )
  order[, `:=`(detector_order = match(detector, c("NPR", "ML")), scope_order = match(scope, c("RF", "CM", "RF+CM")))]
  data.table::setorder(order, detector_order, scope_order)
  rows <- vapply(seq_len(nrow(order)), function(index) {
    key <- order[index]
    fecs <- static[detector == key$detector & scope == key$scope & specification == "FECS"]
    feos <- static[detector == key$detector & scope == key$scope & specification == "FEOS"]
    if (nrow(fecs) != 1L || nrow(feos) != 1L) abortf("Missing table estimate for %s/%s", key$detector, key$scope)
    sprintf(
      "%s & %s & %s & %s & %s & %s \\\\",
      key$detector, key$scope, format_att(fecs), format_change(fecs$percent_change),
      format_att(feos), format_change(feos$percent_change)
    )
  }, character(1L))
  lines <- c(
    "% Generated by run-x-b08 v4.",
    "\\begin{table}[!t]",
    "\\centering",
    "\\scriptsize",
    "\\caption{Effects of Cursor adoption on monthly Python source-code additions within $\\FpyLocalized{d}{s}{\\tau_d}$.}",
    "\\label{tb:did-velocity-python-localized}",
    "\\begin{tabular}{@{}ll|cc|cc@{}}",
    "\\tableheader{Detector} & \\tableheader{Scope} & \\tableheader{\\FECS{} ATT} & \\tableheader{$\\Delta\\%$} & \\tableheader{\\FEOS{} ATT} & \\tableheader{$\\Delta\\%$} \\\\",
    "\\midrule",
    rows[1:3],
    "\\addlinespace",
    rows[4:6],
    "\\end{tabular}",
    "\\vspace{-.05in}",
    "\\begin{minipage}{\\linewidth}",
    "\\scriptsize Percentage changes are $100(e^{\\mathrm{ATT}}-1)$. $\\checkmark$ and $\\times$ denote 95\\% CIs excluding and including zero, respectively. Repository-clustered SEs appear in parentheses. Significance: $^{***}p<0.001$, $^{**}p<0.01$, $^{*}p<0.05$, and $^{\\dagger}p<0.10$.",
    "\\end{minipage}",
    "\\vspace{-.1in}",
    "\\end{table}"
  )
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, path, useBytes = TRUE)
  log_message("INFO", "Wrote LaTeX table to %s", path)
}

self_test <- function() {
  npr <- data.table::data.table(
    snapshot_id = c("s1", "s1", "s1"), dataset_source = "control", repo_name = "Owner/Repo",
    repo_month = c("2025-01", "2025-01", "2025-02"),
    relative_path = c("src/a.py", "src/b.py", "src/a.py"),
    file_npr_fun_space_by_token_weighted = c(1.6, 1.4, 1.6), file_npr_fun_status = "scored",
    file_npr_cfun_space_by_token_weighted = c(1.7, NA, 1.7), file_npr_cfun_status = c("scored", "no_cfun", "scored"),
    file_npr_fun_cfun_space_by_token_weighted = c(1.8, 1.2, 1.8), file_npr_fun_cfun_status = "scored"
  )
  ml <- data.table::data.table(
    snapshot_id = c("s1", "s1", "s1"), dataset_source = "control", repo_name = "Owner/Repo",
    snapshot_time = c("2025-01-31T23:59:59Z", "2025-01-31T23:59:59Z", "2025-02-28T23:59:59Z"),
    relative_path = c("src/a.py", "src/b.py", "src/a.py"),
    file_ml_agc_share_space_by_token_weighted = c(0.6, 0.5, 0.6), file_ml_agc_status = "scored",
    file_ml_cfun_agc_share_space_by_token_weighted = c(0.7, NA, 0.7), file_ml_cfun_agc_status = c("scored", "no_ml_cfun", "scored"),
    file_ml_fun_cfun_agc_share_space_by_token_weighted = c(0.8, 0.3, 0.8), file_ml_fun_cfun_agc_status = "scored"
  )
  result <- build_localization_long(npr, ml, 1.515059, 0.50)
  stopifnot(nrow(result) == 18L)
  stopifnot(result[detector == "NPR" & scope == "RF", sum(selected)] == 2L)
  stopifnot(result[detector == "ML" & scope == "RF", sum(selected)] == 2L)
  stopifnot(result[detector == "ML" & scope == "RF" & relative_path == "src/b.py", selected] == 0L)
  stopifnot(result[snapshot_id == "s1" & relative_path == "src/a.py", data.table::uniqueN(time)] == 2L)

  # Regression tests for the reported B02 failure. Excluded missing counts
  # must not invalidate source additions, and included missing counts must fail.
  fixture <- data.table::data.table(
    repo_name = "Owner/Repo", dataset_source = "control",
    commit_month = c(rep("2025-01", 8L), "2025-02"),
    post_path = c("src/a.py", "src/a.py", "src/b.py", "src/zero.py",
                  "asset.bin", "asset2.bin", "asset3.bin", "vendor/v.py", "src/a.py"),
    lines_added = c("10", "3", "5", "0", NA_character_, "", "-", "99", "2"),
    included_in_py_source = c(1, 1, 1, 1, 0, 0, 0, 0, 1),
    file_status = c(rep("included_all_outcomes", 4L), rep("excluded_non_python_or_nonregular", 3L),
                    "included_no_merge_excluded_source", "included_all_outcomes"),
    is_binary = c(0, 0, 0, 0, 1, 1, 1, 0, 0)
  )
  prepared <- prepare_source_additions(fixture)
  stopifnot(nrow(prepared$data) == 5L, sum(prepared$data$lines_added) == 20)
  stopifnot(prepared$audit[included_in_py_source == 0L & count_status == "missing_count", sum(rows)] == 2L)
  for (bad in c(NA_character_, "", "NA", "-", "bad", "Inf", "-1", "1.5")) {
    broken <- data.table::copy(fixture[1L])
    broken[, lines_added := bad]
    error <- tryCatch({ prepare_source_additions(broken); NULL }, error = function(e) e)
    stopifnot(inherits(error, "error"), grepl("source-included", conditionMessage(error)))
  }

  # Exercise the same CSV read/build/join/write path as a real run, including
  # reused snapshots, multiple commits per path, zero additions and exclusions.
  temp_dir <- tempfile("b08-v4-self-test-")
  dir.create(temp_dir)
  on.exit(unlink(temp_dir, recursive = TRUE), add = TRUE)
  panel_fixture <- data.table::data.table(
    repo_id = 1L, repo_name = "Owner/Repo", dataset_source = "control", scope_role = "control",
    treatment_group = 0L, time = c("2025-01", "2025-02"), time_index = 1:2,
    event = "", event_index = 0L, time_to_event = NA_integer_, snapshot_key = "s1",
    log_age = 1, ncloc = 100, log_contributors = 1, log_stars = 1, log_issues = 1,
    lines_added_py_source = c(18, 2), log_lines_added_py_source = log1p(c(18, 2)),
    is_treatment = 0L, post_event = 0L, cursor = 0L
  )
  test_args <- list(
    b06_panel_file = file.path(temp_dir, "b06.csv"),
    file_additions_file = file.path(temp_dir, "b02.csv"),
    npr_file = file.path(temp_dir, "npr.csv"), ml_file = file.path(temp_dir, "ml.csv"),
    output_dir = temp_dir, npr_threshold = 1.515059, ml_threshold = 0.50
  )
  data.table::fwrite(panel_fixture, test_args$b06_panel_file)
  data.table::fwrite(fixture, test_args$file_additions_file)
  data.table::fwrite(npr, test_args$npr_file)
  data.table::fwrite(ml, test_args$ml_file)
  built <- build_panel(test_args)
  stopifnot(nrow(built$panel) == 2L, length(built$outcome_names) == 6L)
  for (outcome in built$outcome_names) {
    stopifnot(isTRUE(all.equal(built$panel[[outcome]], log1p(c(13, 2)))))
  }

  # Test model dispatch and table construction without presenting fixture
  # estimates as statistical evidence. The production estimator is unchanged.
  calls <- 0L
  mock_estimator <- function(data, yname, gname, tname, idname, first_stage,
                             cluster_var, horizon = NULL, pretrends = NULL) {
    calls <<- calls + 1L
    stopifnot(yname %in% built$outcome_names, cluster_var == "repo_id")
    terms <- if (is.null(horizon)) "treat" else as.character(c(pretrends, 0:6))
    data.table::data.table(term = terms, estimate = 0.1, std.error = 0.05)
  }
  models <- fit_models(built$panel, built$outcome_names, 0.95, -6L, 6L, estimator = mock_estimator, report = FALSE)
  stopifnot(calls == 24L, nrow(models$static) == 12L, nrow(models$dynamic) == 144L)
  stopifnot(models$static[, data.table::uniqueN(paste(detector, scope, specification))] == 12L)
  table_path <- file.path(temp_dir, "test-table.tex")
  write_latex_table(models$static, table_path)
  stopifnot(any(grepl("\\FECS{} ATT", readLines(table_path), fixed = TRUE)))
  cat("SELF-TEST PASS: missing counts, excluded binary records, included-count rejection, repeated snapshots, panel aggregation, model dispatch (mock only), and LaTeX output\n")
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
if (as_flag(arg_value(args, "version", "0"), "version")) {
  cat("run-x-b08-v4\n")
  quit(save = "no", status = 0L)
}
if (as_flag(arg_value(args, "self_test", "0"), "self_test")) {
  require_packages()
  self_test()
  quit(save = "no", status = 0L)
}

require_packages()
args$b06_panel_file <- normalizePath(arg_required(args, "b06_panel_file"), mustWork = TRUE)
args$file_additions_file <- normalizePath(arg_required(args, "file_additions_file"), mustWork = TRUE)
args$npr_file <- normalizePath(arg_required(args, "npr_file"), mustWork = TRUE)
args$ml_file <- normalizePath(arg_required(args, "ml_file"), mustWork = TRUE)
args$output_dir <- arg_required(args, "output_dir")
args$table_output <- arg_required(args, "table_output")
args$npr_threshold <- as.numeric(arg_value(args, "npr_threshold", "1.515059"))
args$ml_threshold <- as.numeric(arg_value(args, "ml_threshold", "0.50"))
confidence_level <- as.numeric(arg_value(args, "confidence_level", "0.95"))
min_event <- as.integer(arg_value(args, "min_event", "-6"))
max_event <- as.integer(arg_value(args, "max_event", "6"))
strict <- as_flag(arg_value(args, "strict_expected_counts", "1"), "strict_expected_counts")
expected_rows <- as.integer(arg_value(args, "expected_rows", "1954"))
expected_repositories <- as.integer(arg_value(args, "expected_repositories", "167"))
expected_treatment_repositories <- as.integer(arg_value(args, "expected_treatment_repositories", "63"))
expected_control_repositories <- as.integer(arg_value(args, "expected_control_repositories", "104"))

if (!is.finite(args$npr_threshold) || !is.finite(args$ml_threshold)) abortf("Thresholds must be finite")
if (!is.finite(confidence_level) || confidence_level <= 0 || confidence_level >= 1) abortf("Confidence level must lie in (0,1)")
if (min_event > -2L || max_event < 0L) abortf("Event window must include placebo months through -2 and post-adoption month 0")

dir.create(args$output_dir, recursive = TRUE, showWarnings = FALSE)
built <- build_panel(args)
panel <- built$panel
strict_count(nrow(panel), expected_rows, "repository-month rows", strict)
strict_count(data.table::uniqueN(panel$repo_id), expected_repositories, "repositories", strict)
strict_count(panel[treatment_group == 1L, data.table::uniqueN(repo_id)], expected_treatment_repositories, "treatment repositories", strict)
strict_count(panel[treatment_group == 0L, data.table::uniqueN(repo_id)], expected_control_repositories, "control repositories", strict)

model_fields <- c(
  built$outcome_names, "log_age", "ncloc", "log_contributors", "log_stars", "log_issues",
  "repo_id", "time_index", "event_index", "treatment_group"
)
if (any(!stats::complete.cases(panel[, ..model_fields]))) abortf("Model fields contain missing values")
if (any(!vapply(panel[, ..model_fields], function(column) all(is.finite(as.numeric(column))), logical(1L)))) {
  abortf("Model fields contain nonfinite values")
}

write_csv_gz(panel, file.path(args$output_dir, "detector_localized_python_velocity_panel.csv.gz"))
write_csv(built$localization_summary, file.path(args$output_dir, "detector_localized_python_velocity_localization_summary.csv"))
write_csv(built$join_audit, file.path(args$output_dir, "detector_localized_python_velocity_join_audit.csv"))
write_csv(built$reconciliation, file.path(args$output_dir, "detector_localized_python_velocity_reconciliation.csv"))

models <- fit_models(panel, built$outcome_names, confidence_level, min_event, max_event)
write_csv(models$static, file.path(args$output_dir, "detector_localized_python_velocity_static_effects.csv"))
write_csv(models$dynamic, file.path(args$output_dir, "detector_localized_python_velocity_dynamic_effects.csv"))
write_csv(models$diagnostics, file.path(args$output_dir, "detector_localized_python_velocity_model_diagnostics.csv"))
write_latex_table(models$static, args$table_output)

metadata <- data.table::data.table(
  section = c(
    "implementation", "definition", "definition", "definition", "definition",
    "sample", "sample", "sample", "sample", "output"
  ),
  metric = c(
    "version", "npr_threshold", "ml_threshold", "comparison_operator", "file_additions_policy",
    "repository_month_rows", "repositories", "treatment_repositories", "control_repositories", "table"
  ),
  value = c(
    "v4", args$npr_threshold, args$ml_threshold, ">",
    "B02 lines_added where included_in_py_source=1; tests retained",
    nrow(panel), data.table::uniqueN(panel$repo_id),
    panel[treatment_group == 1L, data.table::uniqueN(repo_id)],
    panel[treatment_group == 0L, data.table::uniqueN(repo_id)], args$table_output
  )
)
write_csv(metadata, file.path(args$output_dir, "detector_localized_python_velocity_run_metadata.csv"))
cat(sprintf("PASS: %d static estimates and %d dynamic estimates\n", nrow(models$static), nrow(models$dynamic)))
cat(sprintf("Table: %s\n", args$table_output))
cat(sprintf("Outputs: %s\n", args$output_dir))
