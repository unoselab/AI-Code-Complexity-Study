#!/usr/bin/env Rscript

# ============================================================
# run-x-k12 v2: Detector-localized dynamic-panel GMM threshold sweeps
# ============================================================
#
# This script estimates the same FECS reverse-direction dynamic-panel GMM
# across prespecified NPR and ML thresholds for one localization scope per
# invocation. A separate combine mode assembles all six detector/scope runs.
#
# Model:
#   Velocity_t ~ Velocity_{t-1} + LocalizedQuality_{t-1} + treatment_t
#                + size_t + project_controls_t
#   Instruments: Velocity_{t-2}
#   effect="twoways", model="twosteps", transformation="d", collapse=FALSE
#
# The full zero-inclusive repository-month sample is invariant across
# thresholds. The primary-threshold result must reproduce the corresponding
# validated GMM result. Non-primary model failures are retained as cautions.
# ============================================================

options(stringsAsFactors = FALSE, warn = 1)

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)

log_message <- function(level, fmt, ...) {
  message(sprintf(
    "%s [%s] %s",
    format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)
  ))
}

parse_cli_args <- function(args) {
  out <- list()
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) abortf("Unexpected positional argument: %s", token)
    key <- gsub("-", "_", sub("^--", "", token), fixed = TRUE)
    if (index == length(args) || startsWith(args[[index + 1L]], "--")) {
      out[[key]] <- TRUE
      index <- index + 1L
    } else {
      out[[key]] <- args[[index + 1L]]
      index <- index + 2L
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

as_integer_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.integer(value))
  if (is.na(result)) abortf("Argument --%s must be integer-compatible", gsub("_", "-", name, fixed = TRUE))
  result
}

as_numeric_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.numeric(value))
  if (is.na(result)) abortf("Argument --%s must be numeric", gsub("_", "-", name, fixed = TRUE))
  result
}

as_logical_arg <- function(args, name, default = TRUE) {
  value <- args[[name]]
  if (is.null(value)) return(isTRUE(default))
  text <- tolower(trimws(as.character(value)))
  if (text %in% c("1", "true", "yes", "y", "on")) return(TRUE)
  if (text %in% c("0", "false", "no", "n", "off")) return(FALSE)
  abortf("Argument --%s must be boolean-like", gsub("_", "-", name, fixed = TRUE))
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

validate_columns <- function(data, required, label) {
  missing <- setdiff(required, names(data))
  if (length(missing)) abortf("%s is missing required columns: %s", label, paste(missing, collapse = ", "))
}

strict_count_check <- function(actual, expected, label, strict = TRUE) {
  actual_value <- as.integer(actual)
  expected_value <- as.integer(expected)
  if (identical(actual_value, expected_value)) return(invisible(TRUE))
  message_text <- sprintf(
    "Count mismatch for %s: expected %d, observed %d",
    label, expected_value, actual_value
  )
  if (strict) abortf("%s", message_text) else log_message("WARNING", "%s", message_text)
  invisible(FALSE)
}

rename_first <- function(data, target, candidates) {
  if (target %in% names(data)) return(invisible(target))
  source <- candidates[candidates %in% names(data)][1L]
  if (is.na(source)) return(invisible(NA_character_))
  data.table::setnames(data, source, target)
  invisible(source)
}

bool_to_int <- function(x) {
  if (is.logical(x)) return(as.integer(replace(x, is.na(x), FALSE)))
  text <- tolower(trimws(as.character(x)))
  result <- rep(NA_integer_, length(text))
  result[text %in% c("1", "true", "t", "yes", "y")] <- 1L
  result[text %in% c("0", "false", "f", "no", "n", "", "na", "nan", "none")] <- 0L
  numeric_value <- suppressWarnings(as.numeric(text))
  use_numeric <- is.na(result) & !is.na(numeric_value)
  result[use_numeric] <- as.integer(numeric_value[use_numeric] != 0)
  result[is.na(result)] <- 0L
  result
}

sha256_file <- function(path) {
  if (is.na(path) || !nzchar(path) || !file.exists(path)) return(NA_character_)
  binary <- Sys.which("sha256sum")
  if (!nzchar(binary)) return(NA_character_)
  output <- suppressWarnings(system2(binary, path, stdout = TRUE, stderr = TRUE))
  if (!length(output)) return(NA_character_)
  strsplit(output[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

capture_evaluation <- function(expr) {
  warnings <- character()
  started <- proc.time()[[3L]]
  value <- tryCatch(
    withCallingHandlers(
      expr,
      warning = function(condition) {
        warnings <<- c(warnings, conditionMessage(condition))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(condition) structure(
      list(message = conditionMessage(condition)), class = "captured_error"
    )
  )
  list(
    value = value,
    warnings = unique(warnings),
    elapsed = proc.time()[[3L]] - started,
    error = inherits(value, "captured_error")
  )
}

make_key <- function(repo_id, time_index) paste(repo_id, time_index, sep = "::")

exact_calendar_support <- function(panel) {
  keys <- unique(make_key(panel$repo_id, panel$time_index))
  panel[
    make_key(repo_id, time_index - 1L) %in% keys &
      make_key(repo_id, time_index - 2L) %in% keys
  ]
}

extract_dimensions <- function(model) {
  stats_nobs <- tryCatch(as.integer(stats::nobs(model)), error = function(condition) NA_integer_)
  instrument_columns <- integer()
  if (is.list(model$W) && length(model$W)) {
    instrument_columns <- vapply(
      model$W,
      function(matrix) if (is.null(dim(matrix))) 0L else ncol(matrix),
      integer(1)
    )
    instrument_columns <- instrument_columns[instrument_columns > 0L]
  }
  list(
    stats_nobs = stats_nobs,
    instrument_count = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_min = if (length(instrument_columns)) min(instrument_columns) else NA_integer_,
    instrument_columns_max = if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_unique = if (length(instrument_columns)) {
      paste(sort(unique(instrument_columns)), collapse = "|")
    } else {
      ""
    },
    pgmm_internal_repository_slots = if (is.list(model$model)) length(model$model) else NA_integer_,
    pgmm_internal_matrix_rows = if (is.list(model$model)) {
      sum(vapply(
        model$model,
        function(matrix) if (is.null(dim(matrix))) 0L else nrow(matrix),
        integer(1)
      ))
    } else {
      NA_integer_
    }
  )
}

extract_htest <- function(test, threshold_id, threshold, name, primary_analysis) {
  if (is.null(test)) {
    return(data.table::data.table(
      threshold_id = threshold_id,
      threshold = threshold,
      primary_analysis = primary_analysis,
      diagnostic = name,
      statistic = NA_real_,
      parameter = NA_real_,
      p_value = NA_real_,
      method = NA_character_,
      status = "missing"
    ))
  }
  statistic <- if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_
  parameter <- if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_
  p_value <- if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_
  method <- if (!is.null(test$method)) as.character(test$method) else NA_character_
  data.table::data.table(
    threshold_id = threshold_id,
    threshold = threshold,
    primary_analysis = primary_analysis,
    diagnostic = name,
    statistic = statistic,
    parameter = parameter,
    p_value = p_value,
    method = method,
    status = ifelse(is.finite(statistic) && is.finite(p_value), "available", "missing")
  )
}

failed_diagnostics <- function(threshold_id, threshold, primary_analysis, message) {
  data.table::data.table(
    threshold_id = rep(threshold_id, 3L),
    threshold = rep(threshold, 3L),
    primary_analysis = rep(primary_analysis, 3L),
    diagnostic = c("sargan", "ar1", "ar2"),
    statistic = NA_real_,
    parameter = NA_real_,
    p_value = NA_real_,
    method = NA_character_,
    status = "model_failed",
    warning_count = 0L,
    warning_messages = message
  )
}

extract_coefficients <- function(summary_object, threshold_id, threshold,
                                 threshold_role, confidence_level,
                                 primary_threshold, detector, scope_id,
                                 scope_label) {
  matrix <- as.matrix(summary_object$coefficients)
  if (is.null(matrix) || !nrow(matrix)) abortf("No coefficient matrix returned at threshold %.6f", threshold)
  column_names <- colnames(matrix)
  estimate_column <- which(tolower(column_names) == "estimate")[1L]
  se_column <- grep("std\\.?[[:space:]]*error", column_names, ignore.case = TRUE)[1L]
  p_column <- grep("pr\\(", column_names, ignore.case = TRUE)[1L]
  if (is.na(estimate_column) || is.na(se_column)) {
    abortf("Could not identify estimate and standard-error columns at threshold %.6f", threshold)
  }
  estimate <- as.numeric(matrix[, estimate_column])
  standard_error <- as.numeric(matrix[, se_column])
  p_value <- if (!is.na(p_column)) {
    as.numeric(matrix[, p_column])
  } else {
    2 * stats::pnorm(-abs(estimate / standard_error))
  }
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  terms <- rownames(matrix)
  primary_term <- "lag(log1p_selected_issue_total, 1)"
  detector_label <- toupper(detector)
  data.table::data.table(
    detector = detector_label,
    scope_id = scope_id,
    localization_scope = scope_label,
    threshold_id = threshold_id,
    threshold = threshold,
    threshold_role = threshold_role,
    primary_analysis = as.integer(abs(threshold - primary_threshold) <= 1e-12),
    specification = "FECS",
    model = sprintf("%s_%s_threshold_quality_to_velocity", detector, scope_id),
    direction = sprintf("%s-%s Quality_{t-1} -> Velocity_t", detector_label, scope_label),
    term = terms,
    estimate = estimate,
    std_error = standard_error,
    conf_low = estimate - critical * standard_error,
    conf_high = estimate + critical * standard_error,
    p_value = p_value,
    significant = !is.na(p_value) & p_value < (1 - confidence_level),
    is_primary_interaction_term = terms == primary_term
  )
}

normalize_threshold_panel <- function(data, detector, scope_id) {
  rename_first(data, "threshold_id", c("threshold_spec_id"))
  rename_first(data, "comparison_operator", c("ml_operator"))
  rename_first(data, "eligible_file_count", c(
    "eligible_fun_cfun_file_count", "eligible_fun_file_count",
    "eligible_cfun_file_count", "eligible_ml_file_count"
  ))
  if ("scope_id" %in% names(data)) {
    requested <- tolower(scope_id)
    available <- tolower(as.character(data$scope_id))
    if (requested %in% unique(available)) data <- data[available == requested]
  }
  if (!"threshold_role" %in% names(data)) data[, threshold_role := "sensitivity"]
  if (!"comparison_operator" %in% names(data)) data[, comparison_operator := ">"]
  data
}

normalize_global_audit <- function(data, detector, scope_id) {
  rename_first(data, "threshold_id", c("threshold_spec_id"))
  rename_first(data, "comparison_operator", c("ml_operator"))
  rename_first(data, "selected_file_rows", c("selected_file_count"))
  if ("scope_id" %in% names(data)) {
    requested <- tolower(scope_id)
    available <- tolower(as.character(data$scope_id))
    if (requested %in% unique(available)) data <- data[available == requested]
  }
  if (detector == "ml" && "mapping_spec" %in% names(data) &&
      "all_ml_files" %in% unique(as.character(data$mapping_spec))) {
    data <- data[as.character(mapping_spec) == "all_ml_files"]
  }
  if (!"comparison_operator" %in% names(data)) data[, comparison_operator := ">"]
  data
}

threshold_on_grid <- function(value, grid, tolerance = 1e-10) {
  vapply(value, function(number) any(abs(number - grid) <= tolerance), logical(1))
}

empty_model_failures <- function() {
  data.table::data.table(
    detector = character(), scope_id = character(), localization_scope = character(),
    threshold_id = character(), threshold = numeric(), primary_analysis = integer(),
    stage = character(), message = character()
  )
}

add_identifiers <- function(data, detector, scope_id, scope_label) {
  detector_value <- toupper(detector)
  scope_id_value <- scope_id
  scope_label_value <- scope_label
  if (!"detector" %in% names(data)) data[, detector := detector_value]
  if (!"scope_id" %in% names(data)) data[, scope_id := scope_id_value]
  if (!"localization_scope" %in% names(data)) data[, localization_scope := scope_label_value]
  data.table::setcolorder(
    data,
    c("detector", "scope_id", "localization_scope", setdiff(names(data), c("detector", "scope_id", "localization_scope")))
  )
  data
}

run_combine <- function(args) {
  check_packages("data.table")
  input_dirs <- strsplit(require_arg(args, "input_dirs"), ";", fixed = TRUE)[[1L]]
  output_dir <- require_arg(args, "output_dir")
  implementation_version <- if (is.null(args$implementation_version)) "v2" else as.character(args$implementation_version)
  if (length(input_dirs) != 6L) abortf("Combine mode requires six detector/scope input directories")
  missing_dirs <- input_dirs[!dir.exists(input_dirs)]
  if (length(missing_dirs)) abortf("Missing combine input directories: %s", paste(missing_dirs, collapse = ", "))
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  specifications <- list(
    summary = list(pattern = "^dynamic_panel_gmm_.*_threshold_primary_summary[.]csv$", output = "dynamic_panel_gmm_localization_threshold_summary.csv"),
    coefficients = list(pattern = "^dynamic_panel_gmm_.*_threshold_coefficients[.]csv$", output = "dynamic_panel_gmm_localization_threshold_coefficients.csv"),
    diagnostics = list(pattern = "^dynamic_panel_gmm_.*_threshold_diagnostics[.]csv$", output = "dynamic_panel_gmm_localization_threshold_diagnostics.csv"),
    instrument_qc = list(pattern = "^dynamic_panel_gmm_.*_threshold_instrument_qc[.]csv$", output = "dynamic_panel_gmm_localization_threshold_instrument_qc.csv"),
    support = list(pattern = "^dynamic_panel_gmm_.*_threshold_support_diagnostics[.]csv$", output = "dynamic_panel_gmm_localization_threshold_support_diagnostics.csv"),
    reproduction = list(pattern = "^dynamic_panel_gmm_.*_threshold_primary_reproduction[.]csv$", output = "dynamic_panel_gmm_localization_threshold_primary_reproduction.csv"),
    failures = list(pattern = "^dynamic_panel_gmm_.*_threshold_model_failures[.]csv$", output = "dynamic_panel_gmm_localization_threshold_model_failures.csv"),
    qc = list(pattern = "^dynamic_panel_gmm_.*_threshold_qc[.]csv$", output = "dynamic_panel_gmm_localization_threshold_qc.csv"),
    metadata = list(pattern = "^dynamic_panel_gmm_.*_threshold_run_metadata[.]csv$", output = "dynamic_panel_gmm_localization_threshold_run_metadata.csv")
  )

  combined <- list()
  for (name in names(specifications)) {
    specification <- specifications[[name]]
    files <- unlist(lapply(
      input_dirs,
      function(directory) list.files(directory, pattern = specification$pattern, full.names = TRUE)
    ))
    if (length(files) != 6L) {
      abortf("Expected six %s files in combine mode; observed %d", name, length(files))
    }
    parts <- lapply(files, function(path) {
      part <- data.table::fread(path, na.strings = c("", "NA", "NaN"))
      part[, source_output_dir := dirname(path)]
      part
    })
    combined[[name]] <- data.table::rbindlist(parts, use.names = TRUE, fill = TRUE)
    write_csv(combined[[name]], file.path(output_dir, specification$output))
  }

  strict_count_check(nrow(combined$summary), 126L, "combined threshold-summary rows", TRUE)
  strict_count_check(nrow(combined$reproduction), 18L, "combined primary-reproduction rows", TRUE)
  if (any(combined$qc$status == "fail", na.rm = TRUE)) abortf("Combined QC contains hard failures")
  if (any(combined$reproduction$status == "fail", na.rm = TRUE)) abortf("Combined primary reproduction contains failures")

  combinations <- unique(combined$summary[, .(detector, scope_id, localization_scope)])
  strict_count_check(nrow(combinations), 6L, "combined detector/scope combinations", TRUE)
  combination_counts <- combined$summary[, .(
    threshold_rows = .N,
    successful_models = sum(fit_status == "success", na.rm = TRUE),
    failed_models = sum(fit_status != "success", na.rm = TRUE),
    statistically_significant_models = sum(significant == TRUE, na.rm = TRUE)
  ), by = .(detector, scope_id, localization_scope)]
  if (any(combination_counts$threshold_rows != 21L)) {
    abortf("At least one combined detector/scope series does not contain 21 thresholds")
  }
  write_csv(
    combination_counts,
    file.path(output_dir, "dynamic_panel_gmm_localization_threshold_manifest.csv")
  )

  combine_metadata <- data.table::data.table(
    section = c("run", "run", "run", "qc", "qc", "qc"),
    metric = c(
      "run_prefix", "implementation_version", "combined_at",
      "detector_scope_combinations", "threshold_summary_rows", "hard_qc_failures"
    ),
    value = c(
      "run-x-k12", implementation_version, format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
      nrow(combinations), nrow(combined$summary), sum(combined$qc$status == "fail", na.rm = TRUE)
    )
  )
  write_csv(
    combine_metadata,
    file.path(output_dir, "dynamic_panel_gmm_localization_threshold_combine_metadata.csv")
  )
  log_message(
    "INFO",
    "Combined six detector/scope sweeps: summary_rows=%d; successful=%d; failed=%d",
    nrow(combined$summary),
    sum(combined$summary$fit_status == "success", na.rm = TRUE),
    sum(combined$summary$fit_status != "success", na.rm = TRUE)
  )
}

run_fit <- function(args) {
  check_packages(c("data.table", "plm"))
  suppressPackageStartupMessages(library(plm))

  detector <- tolower(require_arg(args, "detector"))
  if (!detector %in% c("npr", "ml")) abortf("--detector must be npr or ml")
  scope_id <- tolower(require_arg(args, "scope_id"))
  if (!scope_id %in% c("rf", "cm", "rf_cm")) abortf("--scope-id must be rf, cm, or rf_cm")
  scope_label <- require_arg(args, "scope_label")
  source_label <- require_arg(args, "source_label")

  input_file <- normalizePath(require_arg(args, "input_file"), mustWork = TRUE)
  b06_panel_file <- normalizePath(require_arg(args, "b06_panel_file"), mustWork = TRUE)
  source_summary_file <- normalizePath(require_arg(args, "source_summary_file"), mustWork = TRUE)
  source_sample_summary_file <- normalizePath(require_arg(args, "source_sample_summary_file"), mustWork = TRUE)
  source_global_audit_file <- normalizePath(require_arg(args, "source_global_audit_file"), mustWork = TRUE)
  reference_coefficients_file <- normalizePath(require_arg(args, "reference_coefficients_file"), mustWork = TRUE)
  output_dir <- require_arg(args, "output_dir")
  script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
  implementation_version <- if (is.null(args$implementation_version)) "v2" else as.character(args$implementation_version)

  confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
  primary_threshold <- as_numeric_arg(args, "primary_threshold", ifelse(detector == "npr", 1.515059, 0.50))
  threshold_min <- as_numeric_arg(args, "threshold_min", ifelse(detector == "npr", 1.015059, 0.10))
  threshold_max <- as_numeric_arg(args, "threshold_max", ifelse(detector == "npr", 2.015059, 0.90))
  threshold_step <- as_numeric_arg(args, "threshold_step", ifelse(detector == "npr", 0.05, 0.04))
  reference_tolerance <- as_numeric_arg(args, "reference_tolerance", 1e-10)
  strict_expected_counts <- as_logical_arg(args, "strict_expected_counts", TRUE)

  expected_long_rows <- as_integer_arg(args, "expected_long_rows", ifelse(detector == "npr", 88987L, 81249L))
  expected_source_thresholds <- as_integer_arg(args, "expected_source_thresholds", ifelse(detector == "npr", 23L, 21L))
  expected_sample_specs <- as_integer_arg(args, "expected_sample_specs", 2L)
  expected_main_thresholds <- as_integer_arg(args, "expected_main_thresholds", 21L)
  expected_rows_per_threshold <- as_integer_arg(args, "expected_rows_per_threshold", 1954L)
  expected_repositories <- as_integer_arg(args, "expected_repositories", 167L)
  expected_treatment_repositories <- as_integer_arg(args, "expected_treatment_repositories", 63L)
  expected_control_repositories <- as_integer_arg(args, "expected_control_repositories", 104L)
  expected_active_rows <- as_integer_arg(args, "expected_active_rows", 1631L)
  expected_active_repositories <- as_integer_arg(args, "expected_active_repositories", 146L)
  expected_active_treatment_repositories <- as_integer_arg(args, "expected_active_treatment_repositories", 61L)
  expected_active_control_repositories <- as_integer_arg(args, "expected_active_control_repositories", 85L)
  expected_primary_selected_files <- as_integer_arg(args, "expected_primary_selected_files", -1L)
  expected_primary_issue_stock <- as_integer_arg(args, "expected_primary_issue_stock", -1L)

  if (confidence_level <= 0 || confidence_level >= 1) abortf("confidence_level must be between 0 and 1")
  if (threshold_step <= 0 || threshold_max <= threshold_min) abortf("Invalid threshold-grid bounds or step")
  number_of_steps <- (threshold_max - threshold_min) / threshold_step
  if (abs(number_of_steps - round(number_of_steps)) > 1e-10) {
    abortf("Threshold range must be an exact multiple of the threshold increment")
  }
  expected_grid <- threshold_min + seq.int(0L, as.integer(round(number_of_steps))) * threshold_step
  if (length(expected_grid) != expected_main_thresholds) {
    abortf("Expected %d threshold values but constructed %d", expected_main_thresholds, length(expected_grid))
  }
  if (!any(abs(expected_grid - primary_threshold) <= 1e-10)) {
    abortf("Primary threshold %.6f is absent from the threshold grid", primary_threshold)
  }

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  prefix <- sprintf("dynamic_panel_gmm_%s_%s_threshold", detector, scope_id)
  paths <- list(
    coefficients = file.path(output_dir, paste0(prefix, "_coefficients.csv")),
    primary_summary = file.path(output_dir, paste0(prefix, "_primary_summary.csv")),
    diagnostics = file.path(output_dir, paste0(prefix, "_diagnostics.csv")),
    instrument_qc = file.path(output_dir, paste0(prefix, "_instrument_qc.csv")),
    support = file.path(output_dir, paste0(prefix, "_support_diagnostics.csv")),
    threshold_input_audit = file.path(output_dir, paste0(prefix, "_input_audit.csv")),
    b06_join_audit = file.path(output_dir, paste0(prefix, "_b06_join_audit.csv")),
    reproduction = file.path(output_dir, paste0(prefix, "_primary_reproduction.csv")),
    model_failures = file.path(output_dir, paste0(prefix, "_model_failures.csv")),
    qc = file.path(output_dir, paste0(prefix, "_qc.csv")),
    metadata = file.path(output_dir, paste0(prefix, "_run_metadata.csv")),
    models = file.path(output_dir, paste0(prefix, "_models.rds"))
  )

  run_started <- Sys.time()
  log_message("INFO", "Reading %s %s threshold panel: %s", toupper(detector), scope_label, input_file)
  long_panel <- data.table::fread(input_file, na.strings = c("", "NA", "NaN"))
  long_panel <- normalize_threshold_panel(long_panel, detector, scope_id)
  if (!nrow(long_panel)) abortf("No source rows remain for %s %s", toupper(detector), scope_label)
  validate_columns(long_panel, c(
    "sample_spec", "threshold_id", "threshold_role", "threshold", "comparison_operator",
    "repo_id", "time_index", "log1p_selected_issue_total",
    "selected_issue_total", "selected_file_count"
  ), "threshold panel")
  strict_count_check(nrow(long_panel), expected_long_rows, "source long-panel rows", strict_expected_counts)
  strict_count_check(data.table::uniqueN(long_panel$threshold_id), expected_source_thresholds, "source threshold specifications", strict_expected_counts)
  strict_count_check(data.table::uniqueN(long_panel$sample_spec), expected_sample_specs, "source sample specifications", strict_expected_counts)

  source_summary <- data.table::fread(source_summary_file, na.strings = c("", "NA", "NaN"))
  validate_columns(source_summary, c("metric", "value"), "source summary")
  summary_lookup <- setNames(as.character(source_summary$value), as.character(source_summary$metric))
  if (!is.null(summary_lookup[["status"]]) && !identical(summary_lookup[["status"]], "PASS")) {
    abortf("Source summary status is not PASS")
  }
  if (!is.null(summary_lookup[["primary_threshold"]])) {
    source_primary <- suppressWarnings(as.numeric(summary_lookup[["primary_threshold"]]))
    if (!is.finite(source_primary) || abs(source_primary - primary_threshold) > 1e-10) {
      abortf("Source primary threshold does not match %.6f", primary_threshold)
    }
  }

  sample_summary <- data.table::fread(source_sample_summary_file, na.strings = c("", "NA", "NaN"))
  scope_id_value <- scope_id
  if ("scope_id" %in% names(sample_summary)) {
    available <- tolower(as.character(sample_summary$scope_id))
    if (scope_id_value %in% unique(available)) {
      sample_summary <- sample_summary[available == scope_id_value]
    }
  }
  validate_columns(sample_summary, c(
    "sample_spec", "repo_month_rows", "repositories",
    "control_repositories", "treatment_repositories"
  ), "source sample summary")
  full_sample_summary <- sample_summary[sample_spec == "full_sample"]
  if (nrow(full_sample_summary) != 1L) {
    abortf(
      "Source sample summary must contain one full_sample row for scope=%s; observed %d",
      scope_id_value,
      nrow(full_sample_summary)
    )
  }
  strict_count_check(full_sample_summary$repo_month_rows, expected_rows_per_threshold, "source full-sample rows", strict_expected_counts)
  strict_count_check(full_sample_summary$repositories, expected_repositories, "source full-sample repositories", strict_expected_counts)
  strict_count_check(full_sample_summary$treatment_repositories, expected_treatment_repositories, "source full-sample treatment repositories", strict_expected_counts)
  strict_count_check(full_sample_summary$control_repositories, expected_control_repositories, "source full-sample control repositories", strict_expected_counts)

  long_panel[, threshold_numeric := suppressWarnings(as.numeric(threshold))]
  if (anyNA(long_panel$threshold_numeric)) abortf("Threshold panel contains non-numeric threshold values")
  main_panel <- data.table::copy(long_panel[
    sample_spec == "full_sample" & comparison_operator == ">" &
      threshold_on_grid(threshold_numeric, expected_grid)
  ])
  main_panel[, grid_index := vapply(
    threshold_numeric,
    function(value) which.min(abs(expected_grid - value)),
    integer(1)
  )]
  main_panel[, threshold_numeric := expected_grid[grid_index]]
  main_panel[, grid_index := NULL]

  expected_main_rows <- expected_rows_per_threshold * expected_main_thresholds
  strict_count_check(nrow(main_panel), expected_main_rows, "main-grid panel rows", TRUE)
  threshold_table <- unique(main_panel[, .(threshold_id, threshold = threshold_numeric, threshold_role)])
  data.table::setorder(threshold_table, threshold)
  strict_count_check(nrow(threshold_table), expected_main_thresholds, "main-grid thresholds", TRUE)
  if (any(abs(threshold_table$threshold - expected_grid) > 1e-10)) abortf("Source threshold grid does not match the prespecified grid")
  threshold_key_qc <- main_panel[, .(
    rows = .N,
    repositories = data.table::uniqueN(repo_id),
    duplicate_repo_months = .N - data.table::uniqueN(paste(repo_id, time_index, sep = "::")),
    selected_file_rows = sum(as.numeric(selected_file_count)),
    selected_issue_total = sum(as.numeric(selected_issue_total))
  ), by = .(threshold_id, threshold = threshold_numeric)]
  data.table::setorder(threshold_key_qc, threshold)
  if (any(threshold_key_qc$rows != expected_rows_per_threshold)) abortf("A threshold does not contain the full repository-month sample")
  if (any(threshold_key_qc$repositories != expected_repositories)) abortf("A threshold does not contain the full repository sample")
  if (any(threshold_key_qc$duplicate_repo_months != 0L)) abortf("A threshold contains duplicate repository-month keys")
  if (any(diff(threshold_key_qc$selected_file_rows) > 0)) abortf("Selected-file support increases as the threshold increases")
  if (any(diff(threshold_key_qc$selected_issue_total) > 0)) abortf("Selected issue burden increases as the threshold increases")
  primary_input <- threshold_key_qc[abs(threshold - primary_threshold) <= 1e-10]
  if (nrow(primary_input) != 1L) abortf("Expected one primary-threshold input row")
  strict_count_check(primary_input$selected_file_rows, expected_primary_selected_files, "primary selected files", strict_expected_counts)
  strict_count_check(primary_input$selected_issue_total, expected_primary_issue_stock, "primary issue stock", strict_expected_counts)

  global_audit <- data.table::fread(source_global_audit_file, na.strings = c("", "NA", "NaN"))
  global_audit <- normalize_global_audit(global_audit, detector, scope_id)
  validate_columns(global_audit, c(
    "sample_spec", "threshold", "comparison_operator",
    "selected_file_rows", "selected_issue_total"
  ), "source global audit")
  global_audit[, threshold_numeric := suppressWarnings(as.numeric(threshold))]
  main_global <- data.table::copy(global_audit[
    sample_spec == "full_sample" & comparison_operator == ">" &
      threshold_on_grid(threshold_numeric, expected_grid)
  ])
  main_global[, grid_index := vapply(
    threshold_numeric,
    function(value) which.min(abs(expected_grid - value)),
    integer(1)
  )]
  main_global[, threshold_numeric := expected_grid[grid_index]]
  main_global[, grid_index := NULL]
  if (nrow(main_global) != expected_main_thresholds) {
    abortf("Expected %d main-grid global-audit rows; observed %d", expected_main_thresholds, nrow(main_global))
  }
  global_support <- main_global[, .(
    audit_selected_file_rows = as.numeric(selected_file_rows),
    audit_selected_issue_total = as.numeric(selected_issue_total)
  ), by = .(threshold = threshold_numeric)]
  input_audit <- merge(
    threshold_key_qc,
    global_support,
    by = "threshold",
    all = TRUE,
    sort = TRUE
  )
  input_audit[, selected_file_difference := selected_file_rows - audit_selected_file_rows]
  input_audit[, selected_issue_difference := selected_issue_total - audit_selected_issue_total]
  input_audit[, status := ifelse(
    selected_file_difference == 0 & selected_issue_difference == 0,
    "pass", "fail"
  )]
  input_audit <- add_identifiers(input_audit, detector, scope_id, scope_label)
  write_csv(input_audit, paths$threshold_input_audit)
  if (any(input_audit$status == "fail")) abortf("Threshold-panel support does not reproduce the source global audit")

  log_message("INFO", "Reading B06 velocity and covariate panel: %s", b06_panel_file)
  b06 <- data.table::fread(b06_panel_file, na.strings = c("", "NA", "NaN"))
  b06_fields <- c(
    "repo_id", "time_index", "treatment_group", "event_index",
    "log_lines_added_py_source", "log_age", "ncloc_py_sonarqube",
    "log_contributors", "log_stars", "log_issues"
  )
  validate_columns(b06, b06_fields, "B06 panel")
  strict_count_check(nrow(b06), expected_rows_per_threshold, "B06 rows", strict_expected_counts)
  strict_count_check(data.table::uniqueN(b06$repo_id), expected_repositories, "B06 repositories", strict_expected_counts)
  b06[, repo_id := suppressWarnings(as.integer(repo_id))]
  b06[, time_index := suppressWarnings(as.integer(time_index))]
  if (anyNA(b06$repo_id) || anyNA(b06$time_index)) abortf("B06 keys must be complete and integer-compatible")
  if (nrow(b06[, .N, by = .(repo_id, time_index)][N > 1L])) abortf("B06 contains duplicate repository-month keys")

  quality_fields <- c(
    "threshold_id", "threshold_numeric", "threshold_role",
    "repo_id", "time_index", "log1p_selected_issue_total",
    "selected_issue_total", "selected_file_count"
  )
  quality_panel <- data.table::copy(main_panel[, ..quality_fields])
  quality_panel[, repo_id := suppressWarnings(as.integer(repo_id))]
  quality_panel[, time_index := suppressWarnings(as.integer(time_index))]
  rows_before_join <- nrow(quality_panel)
  main_panel <- merge(quality_panel, b06[, ..b06_fields], by = c("repo_id", "time_index"), all.x = TRUE, sort = FALSE)
  missing_velocity <- sum(is.na(main_panel$log_lines_added_py_source))
  join_audit <- data.table::data.table(
    detector = toupper(detector),
    scope_id = scope_id,
    localization_scope = scope_label,
    check = c("rows_before_join", "rows_after_join", "missing_b06_velocity", "duplicate_joined_keys"),
    observed = c(
      rows_before_join,
      nrow(main_panel),
      missing_velocity,
      nrow(main_panel[, .N, by = .(threshold_id, repo_id, time_index)][N > 1L])
    ),
    expected = c(rows_before_join, rows_before_join, 0L, 0L)
  )
  join_audit[, status := ifelse(observed == expected, "pass", "fail")]
  write_csv(join_audit, paths$b06_join_audit)
  if (any(join_audit$status == "fail")) abortf("B06 join failed one or more structural checks")

  formula_text <- paste0(
    "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + ",
    "lag(log1p_selected_issue_total, 1) + absorbing_treated + ",
    "log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
    "lag(log_lines_added_py_source, 2)"
  )
  formula <- stats::as.formula(formula_text)
  model_name <- sprintf("%s_%s_threshold_quality_to_velocity", detector, scope_id)

  coefficients_all <- list()
  diagnostics_all <- list()
  instrument_all <- list()
  support_all <- list()
  summary_all <- list()
  qc_all <- list()
  models <- list()
  model_failures <- empty_model_failures()

  for (row_index in seq_len(nrow(threshold_table))) {
    threshold_id_value <- as.character(threshold_table$threshold_id[[row_index]])
    threshold_value <- as.numeric(threshold_table$threshold[[row_index]])
    threshold_role_value <- as.character(threshold_table$threshold_role[[row_index]])
    primary_analysis_value <- as.integer(abs(threshold_value - primary_threshold) <= 1e-10)
    panel <- data.table::copy(main_panel[
      threshold_id == threshold_id_value & abs(threshold_numeric - threshold_value) <= 1e-10
    ])
    if (nrow(panel) != expected_rows_per_threshold) abortf("Threshold %.6f has %d rows", threshold_value, nrow(panel))

    numeric_fields <- c(
      "repo_id", "time_index", "event_index", "treatment_group",
      "log_lines_added_py_source", "log1p_selected_issue_total",
      "selected_issue_total", "selected_file_count", "log_age",
      "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"
    )
    for (field in numeric_fields) panel[, (field) := suppressWarnings(as.numeric(get(field)))]
    if (anyNA(panel[, ..numeric_fields])) abortf("A model field is missing or non-numeric at threshold %.6f", threshold_value)
    if (any(panel$selected_issue_total < 0) || any(panel$selected_file_count < 0) || any(panel$ncloc_py_sonarqube < 0)) {
      abortf("A count or size field is negative at threshold %.6f", threshold_value)
    }
    if (any(abs(panel$log1p_selected_issue_total - log1p(panel$selected_issue_total)) > 1e-12)) {
      abortf("log1p issue burden does not reproduce the issue count at threshold %.6f", threshold_value)
    }

    panel[, `:=`(
      repo_id = as.integer(repo_id),
      time_index = as.integer(time_index),
      event_index = as.integer(event_index),
      treatment_group = as.integer(treatment_group),
      log_ncloc_py_sonarqube = log1p(ncloc_py_sonarqube)
    )]
    panel[, absorbing_treated := as.integer(
      treatment_group == 1L & event_index > 0L & time_index >= event_index
    )]

    active <- exact_calendar_support(panel)
    active_rows <- nrow(active)
    active_repositories <- data.table::uniqueN(active$repo_id)
    active_treatment_repositories <- data.table::uniqueN(active[treatment_group == 1L, repo_id])
    active_control_repositories <- data.table::uniqueN(active[treatment_group == 0L, repo_id])
    strict_count_check(active_rows, expected_active_rows, sprintf("active rows at %.6f", threshold_value), TRUE)
    strict_count_check(active_repositories, expected_active_repositories, sprintf("active repositories at %.6f", threshold_value), TRUE)
    strict_count_check(active_treatment_repositories, expected_active_treatment_repositories, sprintf("active treatment repositories at %.6f", threshold_value), TRUE)
    strict_count_check(active_control_repositories, expected_active_control_repositories, sprintf("active control repositories at %.6f", threshold_value), TRUE)

    source_variation <- panel[, .(unique_quality = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][unique_quality > 1L, .N]
    active_variation <- active[, .(unique_quality = data.table::uniqueN(log1p_selected_issue_total)), by = repo_id][unique_quality > 1L, .N]
    support_row <- data.table::data.table(
      detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
      threshold_id = threshold_id_value, threshold = threshold_value,
      threshold_role = threshold_role_value, primary_analysis = primary_analysis_value,
      source_rows = nrow(panel), source_repositories = data.table::uniqueN(panel$repo_id),
      active_rows = active_rows, active_repositories = active_repositories,
      active_treatment_repositories = active_treatment_repositories,
      active_control_repositories = active_control_repositories,
      active_post_treatment_rows = nrow(active[absorbing_treated == 1L]),
      selected_file_rows = sum(panel$selected_file_count),
      selected_issue_total = sum(panel$selected_issue_total),
      repo_months_with_selected_files = nrow(panel[selected_file_count > 0]),
      repo_months_with_positive_issue_stock = nrow(panel[selected_issue_total > 0]),
      active_rows_with_positive_issue_stock = nrow(active[selected_issue_total > 0]),
      zero_issue_share_source = mean(panel$selected_issue_total == 0),
      zero_issue_share_active = mean(active$selected_issue_total == 0),
      repositories_with_within_quality_variation_source = source_variation,
      repositories_with_within_quality_variation_active = active_variation
    )
    support_all[[threshold_id_value]] <- support_row

    estimation_data <- panel[, .(
      repo_id, time_index, log_lines_added_py_source,
      log1p_selected_issue_total, absorbing_treated,
      log_ncloc_py_sonarqube, log_age,
      log_contributors, log_stars, log_issues
    )]
    data.table::setorder(estimation_data, repo_id, time_index)
    pdata <- plm::pdata.frame(
      as.data.frame(estimation_data),
      index = c("repo_id", "time_index"),
      drop.index = FALSE,
      row.names = FALSE
    )

    log_message("INFO", "Fitting %s %s threshold %.6f", toupper(detector), scope_label, threshold_value)
    fit_capture <- capture_evaluation(plm::pgmm(
      formula,
      data = pdata,
      effect = "twoways",
      model = "twosteps",
      transformation = "d",
      collapse = FALSE
    ))

    failure_stage <- NA_character_
    failure_message <- ""
    summary_capture <- NULL
    coefficient_capture <- NULL
    if (fit_capture$error) {
      failure_stage <- "pgmm"
      failure_message <- fit_capture$value$message
    } else {
      summary_capture <- capture_evaluation(summary(fit_capture$value, robust = TRUE))
      if (summary_capture$error) {
        failure_stage <- "robust_summary"
        failure_message <- summary_capture$value$message
      } else {
        coefficient_capture <- capture_evaluation(extract_coefficients(
          summary_capture$value, threshold_id_value, threshold_value,
          threshold_role_value, confidence_level, primary_threshold,
          detector, scope_id, scope_label
        ))
        if (coefficient_capture$error) {
          failure_stage <- "coefficient_extraction"
          failure_message <- coefficient_capture$value$message
        }
      }
    }

    if (!is.na(failure_stage)) {
      model_failures <- data.table::rbindlist(list(
        model_failures,
        data.table::data.table(
          detector = toupper(detector), scope_id = scope_id,
          localization_scope = scope_label, threshold_id = threshold_id_value,
          threshold = threshold_value, primary_analysis = primary_analysis_value,
          stage = failure_stage, message = failure_message
        )
      ), use.names = TRUE)
      if (primary_analysis_value == 1L) abortf("Primary-threshold model failed during %s: %s", failure_stage, failure_message)
      diagnostics_all[[threshold_id_value]] <- add_identifiers(
        failed_diagnostics(threshold_id_value, threshold_value, primary_analysis_value, failure_message),
        detector, scope_id, scope_label
      )
      instrument_all[[threshold_id_value]] <- data.table::data.table(
        detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
        threshold_id = threshold_id_value, threshold = threshold_value,
        primary_analysis = primary_analysis_value, specification = "FECS",
        model = model_name, collapse = FALSE,
        instrument_specification = "lag(velocity,2)",
        minimum_calendar_support_rows = active_rows,
        minimum_calendar_support_repositories = active_repositories,
        stats_nobs = NA_integer_, instrument_count = NA_integer_,
        instrument_ratio_denominator = active_repositories,
        instrument_to_repository_ratio = NA_real_,
        instrument_proliferation_flag = NA,
        runtime_seconds = fit_capture$elapsed,
        warning_count = length(fit_capture$warnings),
        warning_messages = paste(fit_capture$warnings, collapse = " | "),
        fit_status = "failed"
      )
      summary_all[[threshold_id_value]] <- data.table::data.table(
        detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
        threshold_id = threshold_id_value, threshold = threshold_value,
        threshold_role = threshold_role_value, primary_analysis = primary_analysis_value,
        specification = "FECS", fit_status = "failed",
        estimate = NA_real_, std_error = NA_real_, conf_low = NA_real_,
        conf_high = NA_real_, p_value = NA_real_, significant = NA,
        failure_message = failure_message
      )
      qc_all[[threshold_id_value]] <- data.table::data.table(
        detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
        threshold_id = threshold_id_value, threshold = threshold_value,
        check = c("source_rows", "active_rows", "model_fit"),
        observed = c(nrow(panel), active_rows, NA_real_),
        expected = c(expected_rows_per_threshold, expected_active_rows, NA_real_),
        status = c("pass", "pass", "caution"),
        note = c(
          "Full zero-inclusive repository-month sample.",
          "Exact calendar t-1/t-2 support.",
          paste0("Non-primary model failure: ", failure_message)
        )
      )
      next
    }

    coefficients <- coefficient_capture$value
    primary_term <- coefficients[is_primary_interaction_term == TRUE]
    if (nrow(primary_term) != 1L) abortf("Expected one lagged localized-quality coefficient at threshold %.6f", threshold_value)
    all_warnings <- unique(c(fit_capture$warnings, summary_capture$warnings, coefficient_capture$warnings))
    diagnostics <- data.table::rbindlist(list(
      extract_htest(summary_capture$value$sargan, threshold_id_value, threshold_value, "sargan", primary_analysis_value),
      extract_htest(summary_capture$value$m1, threshold_id_value, threshold_value, "ar1", primary_analysis_value),
      extract_htest(summary_capture$value$m2, threshold_id_value, threshold_value, "ar2", primary_analysis_value)
    ), use.names = TRUE, fill = TRUE)
    diagnostics[, `:=`(
      warning_count = length(all_warnings),
      warning_messages = paste(all_warnings, collapse = " | ")
    )]
    diagnostics <- add_identifiers(diagnostics, detector, scope_id, scope_label)

    dimensions <- extract_dimensions(fit_capture$value)
    instrument_ratio <- if (is.finite(dimensions$instrument_count) && active_repositories > 0L) {
      dimensions$instrument_count / active_repositories
    } else {
      NA_real_
    }
    instrument <- data.table::data.table(
      detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
      threshold_id = threshold_id_value, threshold = threshold_value,
      primary_analysis = primary_analysis_value, specification = "FECS",
      model = model_name, collapse = FALSE,
      instrument_specification = "lag(velocity,2)",
      minimum_calendar_support_rows = active_rows,
      minimum_calendar_support_repositories = active_repositories,
      stats_nobs = dimensions$stats_nobs,
      instrument_count = dimensions$instrument_count,
      instrument_columns_min = dimensions$instrument_columns_min,
      instrument_columns_max = dimensions$instrument_columns_max,
      instrument_columns_unique = dimensions$instrument_columns_unique,
      instrument_ratio_denominator = active_repositories,
      instrument_to_repository_ratio = instrument_ratio,
      instrument_proliferation_flag = is.finite(instrument_ratio) && instrument_ratio >= 1,
      pgmm_internal_matrix_rows = dimensions$pgmm_internal_matrix_rows,
      pgmm_internal_repository_slots = dimensions$pgmm_internal_repository_slots,
      runtime_seconds = fit_capture$elapsed + summary_capture$elapsed,
      warning_count = length(all_warnings),
      warning_messages = paste(all_warnings, collapse = " | "),
      fit_status = "success"
    )

    missing_diagnostics <- diagnostics[status != "available", .N]
    ar1_p <- diagnostics[diagnostic == "ar1", p_value][1L]
    ar2_p <- diagnostics[diagnostic == "ar2", p_value][1L]
    sargan_p <- diagnostics[diagnostic == "sargan", p_value][1L]
    threshold_qc <- data.table::data.table(
      detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
      threshold_id = threshold_id_value, threshold = threshold_value,
      check = c(
        "source_rows", "source_repositories", "active_rows", "active_repositories",
        "stats_nobs_matches_active_rows", "primary_term_rows", "diagnostics_available",
        "ar1_expected_pattern", "ar2_no_second_order_serial_correlation",
        "sargan_overidentification", "model_warning_count", "instrument_ratio"
      ),
      observed = c(
        nrow(panel), data.table::uniqueN(panel$repo_id), active_rows, active_repositories,
        dimensions$stats_nobs, nrow(primary_term), missing_diagnostics,
        ar1_p, ar2_p, sargan_p, length(all_warnings), instrument_ratio
      ),
      expected = c(
        expected_rows_per_threshold, expected_repositories,
        expected_active_rows, expected_active_repositories,
        expected_active_rows, 1, 0, NA, NA, NA, 0, NA
      ),
      status = c(
        ifelse(nrow(panel) == expected_rows_per_threshold, "pass", "fail"),
        ifelse(data.table::uniqueN(panel$repo_id) == expected_repositories, "pass", "fail"),
        ifelse(active_rows == expected_active_rows, "pass", "fail"),
        ifelse(active_repositories == expected_active_repositories, "pass", "fail"),
        ifelse(is.finite(dimensions$stats_nobs) && dimensions$stats_nobs == expected_active_rows, "pass", "fail"),
        ifelse(nrow(primary_term) == 1L, "pass", "fail"),
        ifelse(missing_diagnostics == 0L, "pass", "fail"),
        ifelse(is.finite(ar1_p) && ar1_p < 0.05, "pass", "caution"),
        ifelse(is.finite(ar2_p) && ar2_p >= 0.05, "pass", "caution"),
        ifelse(is.finite(sargan_p) && sargan_p >= 0.05, "pass", "caution"),
        ifelse(length(all_warnings) == 0L, "pass", "caution"),
        ifelse(is.finite(instrument_ratio) && instrument_ratio < 1, "pass", "caution")
      ),
      note = c(
        "Full zero-inclusive repository-month sample.",
        "Full-sample repository membership.",
        "Exact calendar t-1/t-2 support.",
        "Exact-calendar active repositories.",
        "pgmm observations should equal exact-calendar support.",
        "One lagged detector-localized quality coefficient.",
        "Sargan, AR(1), and AR(2) should be available.",
        "Difference GMM commonly yields first-order serial correlation.",
        "AR(2) p<.05 cautions lag-instrument validity.",
        "Sargan p<.05 cautions overidentification validity.",
        "Model warnings are retained for review.",
        "Instrument count should remain below the active repository count."
      )
    )

    coefficients_all[[threshold_id_value]] <- coefficients
    diagnostics_all[[threshold_id_value]] <- diagnostics
    instrument_all[[threshold_id_value]] <- instrument
    summary_all[[threshold_id_value]] <- data.table::data.table(
      detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
      threshold_id = threshold_id_value, threshold = threshold_value,
      threshold_role = threshold_role_value, primary_analysis = primary_analysis_value,
      specification = "FECS", fit_status = "success",
      estimate = primary_term$estimate[[1L]],
      std_error = primary_term$std_error[[1L]],
      conf_low = primary_term$conf_low[[1L]],
      conf_high = primary_term$conf_high[[1L]],
      p_value = primary_term$p_value[[1L]],
      significant = primary_term$significant[[1L]],
      failure_message = ""
    )
    qc_all[[threshold_id_value]] <- threshold_qc
    models[[threshold_id_value]] <- fit_capture$value
  }

  coefficients_output <- data.table::rbindlist(coefficients_all, use.names = TRUE, fill = TRUE)
  diagnostics_output <- data.table::rbindlist(diagnostics_all, use.names = TRUE, fill = TRUE)
  instrument_output <- data.table::rbindlist(instrument_all, use.names = TRUE, fill = TRUE)
  support_output <- data.table::rbindlist(support_all, use.names = TRUE, fill = TRUE)
  summary_output <- data.table::rbindlist(summary_all, use.names = TRUE, fill = TRUE)
  qc_output <- data.table::rbindlist(qc_all, use.names = TRUE, fill = TRUE)
  data.table::setorder(summary_output, threshold)
  data.table::setorder(support_output, threshold)
  data.table::setorder(instrument_output, threshold)
  data.table::setorder(diagnostics_output, threshold, diagnostic)
  data.table::setorder(qc_output, threshold, check)
  strict_count_check(nrow(summary_output), expected_main_thresholds, "threshold-summary rows", TRUE)
  strict_count_check(nrow(support_output), expected_main_thresholds, "support rows", TRUE)
  if (any(abs(summary_output$threshold - expected_grid) > 1e-10)) abortf("Result threshold grid is incomplete or out of order")

  reference <- data.table::fread(reference_coefficients_file, na.strings = c("", "NA", "NaN"))
  validate_columns(reference, c(
    "sample_spec", "term", "estimate", "std_error", "p_value", "is_primary_interaction_term"
  ), "reference coefficients")
  if ("mapping_spec" %in% names(reference) &&
      "all_ml_files" %in% unique(as.character(reference$mapping_spec))) {
    reference <- reference[as.character(mapping_spec) == "all_ml_files"]
  }
  if ("primary_analysis" %in% names(reference)) {
    reference <- reference[bool_to_int(primary_analysis) == 1L]
  }
  reference_primary <- reference[
    sample_spec == "full_sample" &
      bool_to_int(is_primary_interaction_term) == 1L &
      term == "lag(log1p_selected_issue_total, 1)"
  ]
  if (nrow(reference_primary) != 1L) abortf("Expected one full-sample primary coefficient in the reference file")
  k12_primary <- summary_output[
    abs(threshold - primary_threshold) <= 1e-10 & fit_status == "success"
  ]
  if (nrow(k12_primary) != 1L) abortf("Expected one successful K12 primary-threshold result")
  reproduction <- data.table::data.table(
    detector = toupper(detector), scope_id = scope_id, localization_scope = scope_label,
    metric = c("estimate", "std_error", "p_value"),
    reference_value = c(
      reference_primary$estimate[[1L]],
      reference_primary$std_error[[1L]],
      reference_primary$p_value[[1L]]
    ),
    k12_primary_value = c(
      k12_primary$estimate[[1L]],
      k12_primary$std_error[[1L]],
      k12_primary$p_value[[1L]]
    )
  )
  reproduction[, absolute_difference := abs(reference_value - k12_primary_value)]
  reproduction[, tolerance := reference_tolerance]
  reproduction[, status := ifelse(absolute_difference <= tolerance, "pass", "fail")]
  if (any(reproduction$status == "fail")) abortf("Primary threshold does not reproduce the validated reference result")

  if (any(qc_output$status == "fail") && strict_expected_counts) {
    failed <- qc_output[status == "fail"]
    abortf("Threshold GMM QC contains hard failures: %s", paste(paste(failed$threshold_id, failed$check, sep = "/"), collapse = ", "))
  }

  summary_output <- merge(
    summary_output,
    support_output[, .(
      threshold_id, selected_file_rows, selected_issue_total,
      repo_months_with_selected_files, repo_months_with_positive_issue_stock,
      active_rows_with_positive_issue_stock, zero_issue_share_source,
      zero_issue_share_active,
      repositories_with_within_quality_variation_source,
      repositories_with_within_quality_variation_active
    )],
    by = "threshold_id",
    all.x = TRUE,
    sort = FALSE
  )
  data.table::setorder(summary_output, threshold)

  write_csv(coefficients_output, paths$coefficients)
  write_csv(summary_output, paths$primary_summary)
  write_csv(diagnostics_output, paths$diagnostics)
  write_csv(instrument_output, paths$instrument_qc)
  write_csv(support_output, paths$support)
  write_csv(reproduction, paths$reproduction)
  write_csv(model_failures, paths$model_failures)
  write_csv(qc_output, paths$qc)
  saveRDS(models, paths$models)

  run_finished <- Sys.time()
  metadata <- data.table::data.table(
    section = c(
      rep("run", 16L), rep("definition", 19L), rep("qc", 7L), rep("software", 3L)
    ),
    metric = c(
      "run_prefix", "implementation_version", "started", "finished", "runtime_seconds",
      "detector", "scope_id", "localization_scope", "source_label",
      "input_file", "input_sha256", "b06_panel_file", "b06_panel_sha256",
      "reference_coefficients_file", "reference_coefficients_sha256", "script_path",
      "specification", "sample_spec", "primary_threshold", "threshold_min",
      "threshold_max", "threshold_step", "threshold_count", "threshold_operator",
      "localized_quality", "velocity", "treatment", "size_control", "other_controls",
      "gmm_effect", "gmm_model", "gmm_transformation", "instrument_specification",
      "collapse", "formula",
      "thresholds_successful", "thresholds_failed", "hard_qc_failures",
      "caution_qc_rows", "primary_reproduction_status",
      "expected_primary_selected_files", "expected_primary_issue_stock",
      "R", "data.table", "plm"
    ),
    value = c(
      "run-x-k12", implementation_version,
      format(run_started, "%Y-%m-%d %H:%M:%S %Z"),
      format(run_finished, "%Y-%m-%d %H:%M:%S %Z"),
      as.numeric(difftime(run_finished, run_started, units = "secs")),
      toupper(detector), scope_id, scope_label, source_label,
      input_file, sha256_file(input_file), b06_panel_file, sha256_file(b06_panel_file),
      reference_coefficients_file, sha256_file(reference_coefficients_file), script_path,
      "FECS", "full_sample", primary_threshold, threshold_min,
      threshold_max, threshold_step, expected_main_thresholds, ">",
      "log1p_selected_issue_total", "log_lines_added_py_source", "absorbing_treated",
      "log1p(ncloc_py_sonarqube)",
      "log_age|log_contributors|log_stars|log_issues",
      "twoways", "twosteps", "d", "lag(velocity,2)", FALSE, formula_text,
      sum(summary_output$fit_status == "success", na.rm = TRUE),
      sum(summary_output$fit_status != "success", na.rm = TRUE),
      sum(qc_output$status == "fail", na.rm = TRUE),
      sum(qc_output$status == "caution", na.rm = TRUE),
      ifelse(all(reproduction$status == "pass"), "PASS", "FAIL"),
      expected_primary_selected_files, expected_primary_issue_stock,
      R.version.string,
      as.character(utils::packageVersion("data.table")),
      as.character(utils::packageVersion("plm"))
    )
  )
  write_csv(metadata, paths$metadata)
  log_message(
    "INFO",
    "Completed %s %s sweep: thresholds=%d; successful=%d; failed=%d; cautions=%d",
    toupper(detector), scope_label, nrow(summary_output),
    sum(summary_output$fit_status == "success", na.rm = TRUE),
    sum(summary_output$fit_status != "success", na.rm = TRUE),
    sum(qc_output$status == "caution", na.rm = TRUE)
  )
}

arguments <- parse_cli_args(commandArgs(trailingOnly = TRUE))
mode <- if (is.null(arguments$mode)) "fit" else tolower(as.character(arguments$mode))
if (mode == "fit") {
  run_fit(arguments)
} else if (mode == "combine") {
  run_combine(arguments)
} else {
  abortf("--mode must be fit or combine")
}
