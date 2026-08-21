#!/usr/bin/env Rscript

# ============================================================
# run-x-e03 v8: low-range ML-threshold sensitivity for dynamic panel GMM
# ============================================================
#
# Purpose:
#   Re-estimate the frozen E03 ML-localized Quality_t -> Velocity_{t+1}
#   dynamic-panel GMM across a prespecified sensitivity grid of strict file-level
#   ML composition thresholds: 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, and 0.50.
#
# Scientific guardrails:
#   - 0.50 remains the frozen primary threshold.
#   - Every threshold is reported; no p-value-based threshold selection.
#   - The GMM specification is identical at every threshold.
#   - The 0.50 estimate must reproduce the frozen E03-v2 primary result.
#
# Model:
#   Velocity_t ~ Velocity_{t-1} + MLQuality_{t-1} + treatment_t + controls_t
#   Instruments: Velocity_{t-2}
#   effect="twoways", model="twosteps", transformation="d", collapse=FALSE
# ============================================================

options(stringsAsFactors = FALSE, warn = 1)

abortf <- function(fmt, ...) stop(sprintf(fmt, ...), call. = FALSE)
log_message <- function(level, fmt, ...) {
  message(sprintf("%s [%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, sprintf(fmt, ...)))
}

parse_cli_args <- function(args) {
  out <- list(); i <- 1L
  while (i <= length(args)) {
    token <- args[[i]]
    if (!startsWith(token, "--")) abortf("Unexpected positional argument: %s", token)
    key <- gsub("-", "_", sub("^--", "", token), fixed = TRUE)
    if (i == length(args) || startsWith(args[[i + 1L]], "--")) {
      out[[key]] <- TRUE; i <- i + 1L
    } else {
      out[[key]] <- args[[i + 1L]]; i <- i + 2L
    }
  }
  out
}

require_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(as.character(value))) abortf("Missing required argument: --%s", gsub("_", "-", name))
  as.character(value)
}
as_integer_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.integer(value)); if (is.na(result)) abortf("Invalid integer --%s", name); result
}
as_numeric_arg <- function(args, name, default) {
  value <- if (is.null(args[[name]])) default else args[[name]]
  result <- suppressWarnings(as.numeric(value)); if (is.na(result)) abortf("Invalid numeric --%s", name); result
}

check_packages <- function(packages) {
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) abortf("Missing required R packages: %s", paste(missing, collapse = ", "))
}

sha256_file <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  tool <- Sys.which("sha256sum"); if (!nzchar(tool)) return(NA_character_)
  out <- suppressWarnings(system2(tool, path, stdout = TRUE, stderr = TRUE))
  if (!length(out)) return(NA_character_)
  strsplit(out[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_csv <- function(data, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  data.table::fwrite(data, path, na = "")
  log_message("INFO", "Wrote %d rows to %s", nrow(data), path)
}

capture_evaluation <- function(expr) {
  warnings <- character(); started <- proc.time()[[3L]]
  value <- tryCatch(
    withCallingHandlers(expr, warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning")
    }),
    error = function(e) structure(list(message = conditionMessage(e)), class = "captured_error")
  )
  list(value = value, warnings = unique(warnings), elapsed = proc.time()[[3L]] - started,
       error = inherits(value, "captured_error"))
}

bool_to_int <- function(x) {
  if (is.logical(x)) return(as.integer(replace(x, is.na(x), FALSE)))
  text <- tolower(trimws(as.character(x)))
  result <- rep(NA_integer_, length(text))
  result[text %in% c("1","true","t","yes","y")] <- 1L
  result[text %in% c("0","false","f","no","n","","na","nan","none")] <- 0L
  numeric_value <- suppressWarnings(as.numeric(text))
  idx <- is.na(result) & !is.na(numeric_value)
  result[idx] <- as.integer(numeric_value[idx] != 0)
  result[is.na(result)] <- 0L
  result
}

validate_columns <- function(data, required) {
  missing <- setdiff(required, names(data))
  if (length(missing)) abortf("Input is missing required columns: %s", paste(missing, collapse = ", "))
}

extract_htest <- function(test, threshold_id, diagnostic_name) {
  if (is.null(test)) {
    return(data.table::data.table(threshold_id=threshold_id, diagnostic=diagnostic_name,
      statistic=NA_real_, parameter=NA_real_, p_value=NA_real_, method=NA_character_, status="missing"))
  }
  data.table::data.table(
    threshold_id=threshold_id,
    diagnostic=diagnostic_name,
    statistic=if (length(test$statistic)) as.numeric(test$statistic[[1L]]) else NA_real_,
    parameter=if (length(test$parameter)) as.numeric(test$parameter[[1L]]) else NA_real_,
    p_value=if (length(test$p.value)) as.numeric(test$p.value[[1L]]) else NA_real_,
    method=if (!is.null(test$method)) as.character(test$method) else NA_character_,
    status="available"
  )
}

extract_coefficients <- function(summary_object, threshold_id, threshold, confidence_level) {
  matrix <- as.matrix(summary_object$coefficients)
  if (is.null(matrix) || !nrow(matrix)) abortf("No coefficient matrix for threshold %.2f", threshold)
  cn <- colnames(matrix)
  estimate_col <- which(tolower(cn) == "estimate")[1L]
  se_col <- grep("std\\.?[[:space:]]*error", cn, ignore.case = TRUE)[1L]
  p_col <- grep("pr\\(", cn, ignore.case = TRUE)[1L]
  if (is.na(estimate_col) || is.na(se_col)) abortf("Could not identify coefficient columns")
  estimate <- as.numeric(matrix[, estimate_col]); se <- as.numeric(matrix[, se_col])
  p <- if (!is.na(p_col)) as.numeric(matrix[, p_col]) else 2 * stats::pnorm(-abs(estimate / se))
  alpha <- 1 - confidence_level; critical <- stats::qnorm(1 - alpha / 2)
  terms <- rownames(matrix)
  primary_term <- "lag(log1p_selected_issue_total, 1)"
  data.table::data.table(
    threshold_id=threshold_id,
    threshold=threshold,
    primary_analysis=as.integer(abs(threshold - 0.50) < 1e-12),
    model="ml_quality_to_velocity",
    direction="MLQuality_{t-1} -> Velocity_t",
    term=terms,
    estimate=estimate,
    std_error=se,
    conf_low=estimate-critical*se,
    conf_high=estimate+critical*se,
    p_value=p,
    significant=!is.na(p) & p < alpha,
    is_primary_interaction_term=terms == primary_term
  )
}

extract_dimensions <- function(model) {
  nobs <- tryCatch(as.integer(stats::nobs(model)), error=function(e) NA_integer_)
  instrument_columns <- integer()
  if (is.list(model$W) && length(model$W)) {
    instrument_columns <- vapply(model$W, function(x) if (is.null(dim(x))) 0L else ncol(x), integer(1))
    instrument_columns <- instrument_columns[instrument_columns > 0L]
  }
  list(
    stats_nobs=nobs,
    instrument_count=if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    instrument_columns_min=if (length(instrument_columns)) min(instrument_columns) else NA_integer_,
    instrument_columns_max=if (length(instrument_columns)) max(instrument_columns) else NA_integer_,
    pgmm_internal_repository_slots=if (is.list(model$model)) length(model$model) else NA_integer_,
    pgmm_internal_matrix_rows=if (is.list(model$model)) sum(vapply(model$model, function(x) if(is.null(dim(x))) 0L else nrow(x), integer(1))) else NA_integer_
  )
}

exact_calendar_support <- function(panel) {
  keys <- paste(panel$repo_id, panel$time_index, sep="::")
  lag1 <- paste(panel$repo_id, panel$time_index - 1L, sep="::")
  lag2 <- paste(panel$repo_id, panel$time_index - 2L, sep="::")
  active <- panel[lag1 %in% keys & lag2 %in% keys]
  active
}

args <- parse_cli_args(commandArgs(trailingOnly=TRUE))
input_file <- normalizePath(require_arg(args, "input_file"), mustWork=TRUE)
reference_coefficients_file <- normalizePath(require_arg(args, "reference_coefficients_file"), mustWork=TRUE)
output_dir <- require_arg(args, "output_dir")
script_path <- if (is.null(args$script_path)) NA_character_ else as.character(args$script_path)
implementation_version <- if (is.null(args$implementation_version)) "v8" else as.character(args$implementation_version)
confidence_level <- as_numeric_arg(args, "confidence_level", 0.95)
expected_rows_per_threshold <- as_integer_arg(args, "expected_rows_per_threshold", 1954L)
expected_active_rows <- as_integer_arg(args, "expected_active_rows", 1631L)
expected_active_repositories <- as_integer_arg(args, "expected_active_repositories", 146L)
reference_tolerance <- as_numeric_arg(args, "reference_tolerance", 1e-10)

check_packages(c("data.table", "plm"))
suppressPackageStartupMessages(library(plm))
if (!exists("plm", mode="function", inherits=TRUE)) abortf("plm() not visible after package attachment")
dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)

paths <- list(
  coefficients=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_coefficients.csv"),
  primary_summary=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_primary_summary.csv"),
  diagnostics=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_diagnostics.csv"),
  instrument_qc=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_instrument_qc.csv"),
  support=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_support_diagnostics.csv"),
  reproduction=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_e03_reproduction.csv"),
  qc=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_qc.csv"),
  metadata=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_run_metadata.csv"),
  models=file.path(output_dir, "dynamic_panel_gmm_ml_threshold_models.rds")
)

log_message("INFO", "Reading ML threshold sensitivity panel: %s", input_file)
panel_long <- data.table::fread(input_file, na.strings=c("", "NA", "NaN"))
required <- c(
  "threshold_id","ml_threshold","primary_analysis","repo_id","repo_name","dataset_source",
  "treatment_group","time_index","event_index","time_to_event","is_treatment","post_event","cursor",
  "log_lines_added_py_source","log1p_selected_issue_total","selected_issue_total","selected_file_rows",
  "log_age","ncloc_py_sonarqube","log_contributors","log_stars","log_issues"
)
validate_columns(panel_long, required)

thresholds <- sort(unique(as.numeric(panel_long$ml_threshold)))
expected_thresholds <- c(0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50)
if (length(thresholds) != 10L || any(abs(thresholds - expected_thresholds) > 1e-12)) {
  abortf("Expected threshold grid 0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50; found %s", paste(thresholds, collapse=","))
}
if (nrow(panel_long) != expected_rows_per_threshold * length(thresholds)) abortf("Unexpected long panel row count")

# Coerce numeric columns without treating pre-existing audit-only NA values as
# fatal. This mirrors the validated E03-v2 contract: controls may legitimately
# have missing time_to_event, and legacy flags may contain missing values. Only
# core indexes and actual GMM model fields are required to be complete.
numeric_columns <- c("repo_id","treatment_group","time_index","event_index","time_to_event","is_treatment","post_event",
  "log_lines_added_py_source","log1p_selected_issue_total","selected_issue_total","selected_file_rows","log_age","ncloc_py_sonarqube","log_contributors","log_stars","log_issues")
coercion_generated_na <- 0L
for (column in numeric_columns) {
  before_missing <- is.na(panel_long[[column]]) | trimws(as.character(panel_long[[column]])) == ""
  converted <- suppressWarnings(as.numeric(panel_long[[column]]))
  after_missing <- is.na(converted)
  generated <- sum(after_missing & !before_missing)
  coercion_generated_na <- coercion_generated_na + generated
  panel_long[, (column) := converted]
}
if (coercion_generated_na > 0L) abortf("Numeric coercion generated %d new missing values", coercion_generated_na)

core_index_columns <- c("repo_id","treatment_group","time_index","event_index")
if (anyNA(panel_long[, ..core_index_columns])) abortf("Core panel indexes contain missing values")
for (column in core_index_columns) if (any(!is.finite(panel_long[[column]]))) abortf("Non-finite core index values in %s", column)

model_fields <- c("log_lines_added_py_source","log1p_selected_issue_total","selected_issue_total","selected_file_rows",
  "log_age","ncloc_py_sonarqube","log_contributors","log_stars","log_issues")
if (anyNA(panel_long[, ..model_fields])) abortf("Primary GMM model fields contain missing values")
for (column in model_fields) if (any(!is.finite(panel_long[[column]]))) abortf("Non-finite GMM model values in %s", column)
if (any(panel_long$selected_issue_total < 0) || any(panel_long$selected_file_rows < 0) || any(panel_long$ncloc_py_sonarqube < 0)) {
  abortf("Negative count/size values found in threshold panel")
}

# time_to_event is only required for treatment repositories. Control rows may
# legitimately carry NA because they have no adoption-relative event time.
timing_errors <- panel_long[treatment_group == 1 & (is.na(time_to_event) | as.integer(time_to_event) != (as.integer(time_index) - as.integer(event_index)))]
if (nrow(timing_errors) > 0L) abortf("Normalized treatment timing errors found: %d rows", nrow(timing_errors))
control_event_errors <- panel_long[treatment_group == 0 & event_index != 0]
treatment_event_errors <- panel_long[treatment_group == 1 & event_index <= 0]
if (nrow(control_event_errors) > 0L || nrow(treatment_event_errors) > 0L) {
  abortf("Treatment/control event-index invariant failed")
}

formula_text <- paste0(
  "log_lines_added_py_source ~ lag(log_lines_added_py_source, 1) + lag(log1p_selected_issue_total, 1) + ",
  "absorbing_treated + log_ncloc_py_sonarqube + log_age + log_contributors + log_stars + log_issues | ",
  "lag(log_lines_added_py_source, 2)"
)
formula <- stats::as.formula(formula_text)

coefficients_all <- list(); diagnostics_all <- list(); instrument_all <- list(); support_all <- list(); qc_all <- list(); models <- list()

for (threshold in thresholds) {
  threshold_id <- sprintf("t%02d", as.integer(round(threshold * 100)))
  data <- data.table::copy(panel_long[abs(ml_threshold - threshold) < 1e-12])
  if (nrow(data) != expected_rows_per_threshold) abortf("Threshold %.2f has %d rows", threshold, nrow(data))
  if (nrow(data[, .N, by=.(repo_id,time_index)][N>1L])) abortf("Duplicate repo-time rows at threshold %.2f", threshold)

  data[, repo_id := as.integer(repo_id)]
  data[, time_index := as.integer(time_index)]
  data[, event_index := as.integer(event_index)]
  data[, treatment_group := as.integer(treatment_group)]
  data[, absorbing_treated := as.integer(treatment_group == 1L & event_index > 0L & time_index >= event_index)]
  data[, log_ncloc_py_sonarqube := log1p(ncloc_py_sonarqube)]
  if (any(data$ncloc_py_sonarqube < 0)) abortf("Negative NCLOC at threshold %.2f", threshold)
  recompute_mismatch <- sum(abs(log1p(data$selected_issue_total) - data$log1p_selected_issue_total) > 1e-12)
  if (recompute_mismatch) abortf("log1p selected issue mismatch at threshold %.2f", threshold)

  active <- exact_calendar_support(data)
  if (nrow(active) != expected_active_rows || data.table::uniqueN(active$repo_id) != expected_active_repositories) {
    abortf("Exact-calendar support mismatch at threshold %.2f: rows=%d repos=%d", threshold, nrow(active), data.table::uniqueN(active$repo_id))
  }

  # Descriptive support before fitting. Difference-GMM uses within-repository
  # changes, so zero mass and within-quality variation are recorded for every threshold.
  source_variation_repos <- data[, .(quality_unique=data.table::uniqueN(log1p_selected_issue_total)), by=repo_id][quality_unique > 1L, .N]
  active_variation_repos <- active[, .(quality_unique=data.table::uniqueN(log1p_selected_issue_total)), by=repo_id][quality_unique > 1L, .N]
  support_all[[threshold_id]] <- data.table::data.table(
    threshold_id=threshold_id,
    threshold=threshold,
    primary_analysis=as.integer(abs(threshold-0.50)<1e-12),
    source_rows=nrow(data),
    source_repositories=data.table::uniqueN(data$repo_id),
    active_rows=nrow(active),
    active_repositories=data.table::uniqueN(active$repo_id),
    zero_issue_share_source=mean(data$selected_issue_total == 0),
    zero_issue_share_active=mean(active$selected_issue_total == 0),
    repositories_with_within_quality_variation_source=source_variation_repos,
    repositories_with_within_quality_variation_active=active_variation_repos,
    selected_issue_total=sum(data$selected_issue_total),
    selected_file_rows=sum(data$selected_file_rows)
  )

  data.table::setorder(data, repo_id, time_index)
  pdata <- plm::pdata.frame(as.data.frame(data), index=c("repo_id","time_index"), drop.index=FALSE, row.names=FALSE)
  log_message("INFO", "Fitting threshold %.2f", threshold)
  fit <- capture_evaluation(plm::pgmm(formula, data=pdata, effect="twoways", model="twosteps", transformation="d", collapse=FALSE))
  if (fit$error) abortf("pgmm failed at threshold %.2f: %s", threshold, fit$value$message)
  model <- fit$value
  summary_capture <- capture_evaluation(summary(model, robust=TRUE))
  if (summary_capture$error) abortf("Robust summary failed at threshold %.2f: %s", threshold, summary_capture$value$message)
  coef <- extract_coefficients(summary_capture$value, threshold_id, threshold, confidence_level)
  primary_rows <- coef[is_primary_interaction_term == TRUE]
  if (nrow(primary_rows) != 1L) abortf("Expected exactly one primary quality coefficient at threshold %.2f", threshold)

  all_warnings <- unique(c(fit$warnings, summary_capture$warnings))
  diag <- data.table::rbindlist(list(
    extract_htest(summary_capture$value$sargan, threshold_id, "sargan"),
    extract_htest(summary_capture$value$m1, threshold_id, "ar1"),
    extract_htest(summary_capture$value$m2, threshold_id, "ar2")
  ), use.names=TRUE, fill=TRUE)
  diag[, `:=`(threshold=threshold, primary_analysis=as.integer(abs(threshold-0.50)<1e-12), warning_count=length(all_warnings), warning_messages=paste(all_warnings,collapse=" | "))]

  dims <- extract_dimensions(model)
  instrument <- data.table::data.table(
    threshold_id=threshold_id, threshold=threshold, primary_analysis=as.integer(abs(threshold-0.50)<1e-12),
    model="ml_quality_to_velocity", collapse=FALSE, instrument_specification="lag(velocity,2)",
    minimum_calendar_support_rows=nrow(active), minimum_calendar_support_repositories=data.table::uniqueN(active$repo_id),
    stats_nobs=dims$stats_nobs, active_gmm_repositories=data.table::uniqueN(active$repo_id),
    instrument_count=dims$instrument_count, instrument_ratio_denominator=data.table::uniqueN(active$repo_id),
    instrument_to_repository_ratio=dims$instrument_count/data.table::uniqueN(active$repo_id),
    instrument_proliferation_flag=!is.na(dims$instrument_count) & dims$instrument_count >= data.table::uniqueN(active$repo_id),
    pgmm_internal_matrix_rows=dims$pgmm_internal_matrix_rows, pgmm_internal_repository_slots=dims$pgmm_internal_repository_slots,
    runtime_seconds=fit$elapsed, warning_count=length(all_warnings), warning_messages=paste(all_warnings,collapse=" | ")
  )

  diag_missing <- sum(diag$status != "available")
  ar1_p <- diag[diagnostic=="ar1", p_value]; ar2_p <- diag[diagnostic=="ar2", p_value]; sargan_p <- diag[diagnostic=="sargan", p_value]
  qc <- data.table::data.table(
    threshold_id=threshold_id, threshold=threshold,
    check=c("source_rows","active_rows","stats_nobs_matches_active_rows","primary_term_rows","diagnostics_available","ar1_expected_pattern","ar2_no_second_order_serial_correlation","sargan_overidentification","model_warning_count","instrument_ratio"),
    observed=c(nrow(data),nrow(active),dims$stats_nobs,nrow(primary_rows),diag_missing,ar1_p,ar2_p,sargan_p,length(all_warnings),instrument$instrument_to_repository_ratio),
    expected=c(expected_rows_per_threshold,expected_active_rows,expected_active_rows,1,0,NA,NA,NA,0,NA),
    status=c(
      ifelse(nrow(data)==expected_rows_per_threshold,"pass","fail"),
      ifelse(nrow(active)==expected_active_rows,"pass","fail"),
      ifelse(dims$stats_nobs==expected_active_rows,"pass","fail"),
      ifelse(nrow(primary_rows)==1L,"pass","fail"),
      ifelse(diag_missing==0L,"pass","fail"),
      ifelse(is.finite(ar1_p) && ar1_p < .05,"pass","caution"),
      ifelse(is.finite(ar2_p) && ar2_p >= .05,"pass","caution"),
      ifelse(is.finite(sargan_p) && sargan_p >= .05,"pass","caution"),
      ifelse(length(all_warnings)==0L,"pass","caution"),
      ifelse(!instrument$instrument_proliferation_flag,"pass","caution")
    ),
    note=c("Full B06 repo-month sample.","Exact calendar t-1/t-2 support.","pgmm N must equal exact calendar support.","Exactly one lagged ML-quality term.","Sargan, AR(1), AR(2) required.","Difference-GMM commonly yields AR(1).","AR(2) p<.05 cautions lag-instrument validity.","Sargan p<.05 cautions overidentification validity.","Model warnings retained.","Instrument count must remain below active repository count.")
  )

  coefficients_all[[threshold_id]] <- coef; diagnostics_all[[threshold_id]] <- diag; instrument_all[[threshold_id]] <- instrument; qc_all[[threshold_id]] <- qc; models[[threshold_id]] <- model
}

coefficients <- data.table::rbindlist(coefficients_all, use.names=TRUE, fill=TRUE)
diagnostics <- data.table::rbindlist(diagnostics_all, use.names=TRUE, fill=TRUE)
instrument_qc <- data.table::rbindlist(instrument_all, use.names=TRUE, fill=TRUE)
support <- data.table::rbindlist(support_all, use.names=TRUE, fill=TRUE)
qc <- data.table::rbindlist(qc_all, use.names=TRUE, fill=TRUE)
primary_summary <- coefficients[is_primary_interaction_term==TRUE, .(threshold_id,threshold,primary_analysis,estimate,std_error,conf_low,conf_high,p_value,significant)]
data.table::setorder(primary_summary, threshold)

# Frozen E03-v2 reproduction gate at threshold 0.50.
reference <- data.table::fread(reference_coefficients_file, na.strings=c("","NA","NaN"))
validate_columns(reference, c("sample_spec","mapping_spec","term","estimate","std_error","p_value","is_primary_interaction_term"))
ref <- reference[sample_spec=="full_sample" & mapping_spec=="all_ml_files" & bool_to_int(is_primary_interaction_term)==1L]
if (nrow(ref) != 1L) abortf("Expected exactly one frozen E03-v2 primary ML-quality coefficient")
new <- primary_summary[abs(threshold-0.50)<1e-12]
reproduction <- data.table::data.table(
  metric=c("estimate","std_error","p_value"),
  e03_v2=c(ref$estimate,ref$std_error,ref$p_value),
  threshold_current=c(new$estimate,new$std_error,new$p_value)
)
reproduction[, absolute_difference := abs(as.numeric(e03_v2)-as.numeric(threshold_current))]
reproduction[, tolerance := reference_tolerance]
reproduction[, status := ifelse(absolute_difference <= reference_tolerance,"pass","fail")]
if (any(reproduction$status=="fail")) abortf("0.50 GMM estimate failed frozen E03-v2 reproduction")

failed <- qc[status=="fail"]
if (nrow(failed)) abortf("Threshold GMM QC contains %d hard failures", nrow(failed))

write_csv(coefficients, paths$coefficients)
write_csv(primary_summary, paths$primary_summary)
write_csv(diagnostics, paths$diagnostics)
write_csv(instrument_qc, paths$instrument_qc)
write_csv(support, paths$support)
write_csv(reproduction, paths$reproduction)
write_csv(qc, paths$qc)
saveRDS(models, paths$models)

metadata <- data.table::data.table(
  section=c(rep("run",6),rep("definition",8),rep("software",3)),
  metric=c("implementation_version","input_file","input_sha256","reference_coefficients_file","reference_sha256","finished",
    "threshold_grid","primary_threshold","threshold_operator","ml_metric","outcome","velocity","gmm_specification","interpretation_policy",
    "R","data.table","plm"),
  value=c(implementation_version,input_file,sha256_file(input_file),reference_coefficients_file,sha256_file(reference_coefficients_file),format(Sys.time(),"%Y-%m-%d %H:%M:%S %Z"),
    paste(sprintf("%.2f",thresholds),collapse=","),"0.50",">","file_ml_agc_share_space_by_token_weighted","log1p_selected_issue_total","log_lines_added_py_source",
    "twoways; twosteps; difference GMM; lag(velocity,2); collapse=FALSE","report all thresholds; do not select threshold by GMM significance",
    R.version.string,as.character(utils::packageVersion("data.table")),as.character(utils::packageVersion("plm")))
)
write_csv(metadata, paths$metadata)

cautions <- nrow(qc[status=="caution"])
log_message("INFO", "Completed ML threshold sensitivity: thresholds=%d; significant=%d; cautions=%d", nrow(primary_summary), sum(primary_summary$significant), cautions)
