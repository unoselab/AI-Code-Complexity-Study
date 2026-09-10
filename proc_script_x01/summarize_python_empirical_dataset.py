#!/usr/bin/env python3
"""Reproduce tb:python-empirical-dataset (Python 3.10+, standard library only).

Default: aggregate B05/B06 snapshot rows and reconcile audited A12/A15/C04/I06
accounting. Optional --npr-files/--ml-files/--issues independently scan row data.
No detector threshold is applied: this is a dataset-scope table.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = "run-y-b01-v1"
NPR_METRIC = "file_npr_fun_cfun_space_by_token_weighted"
ML_METRIC = "file_ml_fun_cfun_agc_share_space_by_token_weighted"
ROWS = [
    ("repo_months", "Repository-month observations", "repository-month", "B06 snapshot mapping: sum of mapped_repo_month_rows"),
    ("repositories", "Repositories (treatment + controls)", "repository", "B06 snapshot mapping: unique repository names by group"),
    ("snapshots", "Historical repository--commit snapshots", "repository-commit", "B06 snapshot mapping, reconciled against B05"),
    ("python_files", "Python file instances", "snapshot-file", "A12 files.file_unique_keys; A15 and C04/I06 reconciliation"),
    ("prepared_files", "Prepared Python file instances", "snapshot-file", "I06 files.prepared_files; A12/A15 status reconciliation"),
    ("rf_files", "RF-bearing Python file instances", "snapshot-file", "A12 occurrences.files_with_fun; I06 presence-pattern reconciliation"),
    ("rf_occurrences", "RF occurrences", "snapshot-procedure", "A12 occurrences.fun_occurrences; I06 accounting reconciliation"),
    ("cm_files", "CM-bearing Python file instances", "snapshot-file", "A15 occurrences.files_with_cfun; I06 presence-pattern reconciliation"),
    ("cm_occurrences", "CM occurrences", "snapshot-procedure", "A15 occurrences.cfun_occurrences; I06 accounting reconciliation"),
    ("npr_files", "File instances with finite RF+CM NPR signal", "snapshot-file", "C04 audit.eligible_unique_snapshot_files"),
    ("ml_files", "File instances with eligible RF+CM ML signal", "snapshot-file", "I06 files.eligible_combined_files"),
    ("issue_records", "Static-analysis issue records", "snapshot-issue", "Sum of B05 issue_rows over B06 snapshot keys"),
]


class DataError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DataError(message)


def integer(value, name):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DataError(f"Invalid integer for {name}: {value!r}") from None
    require(n.is_finite() and n >= 0 and n == n.to_integral_value(),
            f"Expected a nonnegative integer for {name}: {value!r}")
    return int(n)


def truth(value, name):
    s = str(value).strip().lower()
    require(s in {"true", "false", "1", "0"}, f"Invalid Boolean for {name}: {value!r}")
    return s in {"true", "1"}


def finite(value, name):
    s = str(value).strip()
    if s.lower() in {"", "na", "nan", "none", "null"}:
        return None
    try:
        n = float(s)
    except ValueError:
        raise DataError(f"Invalid numeric value for {name}: {value!r}") from None
    return n if math.isfinite(n) else None


def read_rows(path, required):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        require(set(required) <= set(reader.fieldnames or []),
                f"{path}: missing columns {sorted(set(required) - set(reader.fieldnames or []))}")
        for line, row in enumerate(reader, 2):
            require(None not in row and all(v is not None for v in row.values()),
                    f"{path}:{line}: malformed CSV row")
            yield row


def get(data, dotted):
    for key in dotted.split("."):
        require(isinstance(data, dict) and key in data, f"Missing JSON field: {dotted}")
        data = data[key]
    return data


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def compute(paths, expected_npr_threshold="1.515059", expected_c04_version="run-x-c04-v2"):
    checks, sources = [], []

    def equal(name, observed, expected):
        require(observed == expected, f"{name}: observed={observed!r}, expected={expected!r}")
        checks.append({"check": name, "observed": observed, "expected": expected, "status": "pass"})

    def source(name):
        p = paths[name]
        require(p.is_file(), f"Input not found: {p}")
        sources.append({"role": name, "path": str(p.resolve()), "bytes": p.stat().st_size,
                        "sha256": sha256(p)})
        return p

    summaries = {}
    for name in ("a12", "a15", "c04", "i06"):
        with source(name).open(encoding="utf-8-sig") as f:
            s = json.load(f)
        allowed = {"PASS", "PASS_WITH_EXPECTED_EXCLUSIONS"} if name in {"a12", "a15"} else {"PASS", "PASS_WITH_WARNINGS"}
        require(s.get("status") in allowed, f"{name}: unacceptable upstream status {s.get('status')!r}")
        failure_key = "failed_hard_checks" if name == "i06" else "hard_check_failures"
        equal(name + ".hard_failures", integer(get(s, failure_key), failure_key), 0)
        summaries[name] = s
    a12, a15, c04, i06 = (summaries[k] for k in ("a12", "a15", "c04", "i06"))
    # Eligibility and threshold selection are different quantities. Validate the
    # current experiment, but keep its selected counts outside the dataset table.
    equal("c04.script_version", get(c04, "script_version"), expected_c04_version)
    equal("c04.primary_metric", get(c04, "primary_result.metric"), NPR_METRIC)
    equal("c04.comparison_operator", get(c04, "primary_result.comparison_operator"), ">")
    threshold_values = [expected_npr_threshold, get(c04, "threshold.primary"),
                        get(c04, "primary_result.threshold")]
    try:
        threshold_numbers = [Decimal(str(v)) for v in threshold_values]
    except InvalidOperation:
        raise DataError(f"Invalid NPR threshold: {threshold_values}") from None
    require(all(v.is_finite() and v > 0 for v in threshold_numbers), "NPR thresholds must be finite and positive")
    equal("c04.configured_primary_threshold", str(threshold_numbers[1].normalize()), str(threshold_numbers[0].normalize()))
    equal("c04.result_primary_threshold", str(threshold_numbers[2].normalize()), str(threshold_numbers[0].normalize()))
    primary_threshold = float(threshold_numbers[0])

    # A snapshot may occur in several months. Sum reuse counts for months,
    # but count each repository-commit and each issue stock only once here.
    snapshots, identities, repos, groups = {}, set(), {}, Counter()
    monthly, monthly_groups = 0, Counter()
    for r in read_rows(source("snapshot_map"), ["snapshot_key", "quality_repo_name", "quality_dataset_source",
            "quality_snapshot_commit_sha", "quality_expected_repo_month_rows", "mapped_repo_month_rows",
            "repo_month_reuse_count_match", "snapshot_used_by_panel", "issue_total_py_sonarqube"]):
        key, repo, group, commit = (r[k].strip() for k in
            ("snapshot_key", "quality_repo_name", "quality_dataset_source", "quality_snapshot_commit_sha"))
        require(key and repo and commit, "B06 contains a blank snapshot/repository/commit key")
        require(group in {"treatment", "control"}, f"B06: unexpected group {group!r}")
        require(key not in snapshots, f"B06: duplicate snapshot key {key}")
        require((repo, commit) not in identities, f"B06: duplicate repository-commit {repo} {commit}")
        require(repo not in repos or repos[repo] == group, f"Repository changes group: {repo}")
        require(truth(r["snapshot_used_by_panel"], "snapshot_used_by_panel"), f"B06: unused snapshot {key}")
        require(truth(r["repo_month_reuse_count_match"], "reuse_match"), f"B06: reuse mismatch {key}")
        n = integer(r["mapped_repo_month_rows"], "mapped_repo_month_rows")
        require(n > 0 and n == integer(r["quality_expected_repo_month_rows"], "expected reuse"), f"B06: invalid reuse count {key}")
        snapshots[key] = {"repo": repo, "group": group, "commit": commit, "months": n,
                          "issues": integer(r["issue_total_py_sonarqube"], "B06 issues")}
        identities.add((repo, commit)); repos[repo] = group; groups[group] += 1
        monthly += n; monthly_groups[group] += n
    require(bool(snapshots), "Empty B06 snapshot map")

    seen, issue_records, issue_by_snapshot = set(), 0, {}
    b05_columns = ["snapshot_key", "dataset_source", "repo_name", "commit_sha", "repo_month_rows", "issue_rows",
                   "issue_total_py_sonarqube", "issue_key_distinct", "duplicate_issue_keys_within_snapshot",
                   "issue_rows_complete", "issue_retrieval_error", "resolved_issue_total"]
    for r in read_rows(source("snapshot_issues"), b05_columns):
        key = r["snapshot_key"].strip()
        require(key in snapshots and key not in seen, f"B05: unknown or duplicate snapshot {key}")
        s = snapshots[key]
        require((r["repo_name"], r["dataset_source"], r["commit_sha"]) == (s["repo"], s["group"], s["commit"]),
                f"B05/B06 identity mismatch: {key}")
        n = integer(r["issue_rows"], "issue_rows")
        require(n == s["issues"] == integer(r["issue_total_py_sonarqube"], "issue total") ==
                integer(r["issue_key_distinct"], "issue key count"), f"B05/B06 issue reconciliation failed: {key}")
        require(integer(r["repo_month_rows"], "B05 reuse") == s["months"], f"B05/B06 reuse mismatch: {key}")
        require(integer(r["duplicate_issue_keys_within_snapshot"], "duplicate issues") == 0, f"B05 duplicate issues: {key}")
        require(integer(r["resolved_issue_total"], "resolved issues") == 0, f"B05 includes resolved issues: {key}")
        require(truth(r["issue_rows_complete"], "issue_rows_complete") and not r["issue_retrieval_error"].strip(),
                f"B05 incomplete issue retrieval: {key}")
        seen.add(key); issue_records += n; issue_by_snapshot[key] = n
    equal("B05_B06_snapshot_sets", seen, set(snapshots))

    def count(s, field):
        return integer(get(s, field), field)

    values = {
        "repo_months": monthly, "repositories": len(repos), "snapshots": len(snapshots),
        "python_files": count(a12, "files.file_unique_keys"),
        "prepared_files": count(i06, "files.prepared_files"),
        "rf_files": count(a12, "occurrences.files_with_fun"),
        "rf_occurrences": count(a12, "occurrences.fun_occurrences"),
        "cm_files": count(a15, "occurrences.files_with_cfun"),
        "cm_occurrences": count(a15, "occurrences.cfun_occurrences"),
        "npr_files": count(c04, "audit.eligible_unique_snapshot_files"),
        "ml_files": count(i06, "files.eligible_combined_files"), "issue_records": issue_records,
    }
    for name, s in (("a12", a12), ("a15", a15)):
        for field, value in (("files.file_manifest_rows", values["python_files"]),
                             ("files.file_unique_keys", values["python_files"]),
                             ("repo_month_panel.panel_rows", monthly),
                             ("repo_month_panel.panel_unique_repo_months", monthly),
                             ("repo_month_panel.panel_repositories", len(repos)),
                             ("repo_month_panel.panel_unique_snapshots", len(snapshots)),
                             ("repo_month_panel.unresolved_rows", 0)):
            equal(name + "." + field, count(s, field), value)
        statuses = get(s, "files.file_status_counts")
        equal(name + ".status_total", sum(integer(v, k) for k, v in statuses.items()), values["python_files"])
        equal(name + ".prepared_files", values["python_files"] - count(s, "files.file_status_counts.file_not_prepared"), values["prepared_files"])
    equal("a12_a15_manifest_hash", get(a12, "a05_code_manifest_sha256"), get(a15, "a05_code_manifest_sha256"))
    for field, value in (("audit.unique_snapshot_files", values["python_files"]), ("audit.repo_months", monthly),
                         ("audit.repositories", len(repos)), ("audit.treatment_repositories", sum(g == "treatment" for g in repos.values())),
                         ("audit.control_repositories", sum(g == "control" for g in repos.values())),
                         ("combine.row_key_mismatch", 0), ("combine.unexpected_missing", 0)):
        equal("c04." + field, count(c04, field), value)
    equal("c04.primary_eligible_reconciliation", count(c04, "primary_result.eligible_unique_snapshot_files"), values["npr_files"])
    equal("c04.expanded_finite_reconciliation", count(c04, "audit.eligible_finite_fun_cfun_rows"), count(c04, "combine.finite_combined"))
    equal("c04.expanded_rows_reconciliation", count(c04, "audit.input_rows"), count(c04, "combine.rows"))
    selected_unique = count(c04, "primary_result.selected_unique_snapshot_files")
    selected_rows = count(c04, "primary_result.selected_file_rows")
    require(selected_unique <= values["npr_files"], "Selected NPR snapshot-files exceed eligible files")
    require(selected_unique <= selected_rows <= count(c04, "audit.eligible_finite_fun_cfun_rows"),
            "Selected NPR monthly-row counts are inconsistent")
    timing = get(c04, "audit.repo_month_group_counts")
    equal("c04.control_months", integer(timing["control"], "control months"), monthly_groups["control"])
    equal("c04.treatment_months", integer(timing["treatment_pre"], "pre") + integer(timing["treatment_post"], "post"), monthly_groups["treatment"])
    equal("i06.file_rows", count(i06, "files.file_rows"), values["python_files"])
    equal("i06.preparation_total", values["prepared_files"] + count(i06, "files.not_prepared_files"), values["python_files"])
    patterns = get(i06, "files.presence_pattern_counts")
    equal("i06.rf_files", integer(patterns["fun_only"], "RF only") + integer(patterns["fun_and_class_method"], "both"), values["rf_files"])
    equal("i06.cm_files", integer(patterns["class_method_only"], "CM only") + integer(patterns["fun_and_class_method"], "both"), values["cm_files"])
    equal("i06.pattern_total", sum(integer(v, k) for k, v in patterns.items()), values["python_files"])
    equal("i06.rf_occurrences", count(i06, "accounting.fun_occurrences"), values["rf_occurrences"])
    equal("i06.cm_occurrences", count(i06, "accounting.cfun_occurrences"), values["cm_occurrences"])
    equal("i06.total_occurrences", count(i06, "accounting.combined_occurrences"), values["rf_occurrences"] + values["cm_occurrences"])
    for k in ("prepared_files", "rf_files", "cm_files", "npr_files", "ml_files"):
        require(values[k] <= values["python_files"], f"Impossible count: {k}")
    for k in ("npr_files", "ml_files", "rf_files", "cm_files"):
        require(values[k] <= values["prepared_files"], f"Count exceeds prepared files: {k}")

    # Optional independent row scans. They never overwrite a discrepant summary.
    raw = []
    weights = {(s["group"], s["repo"], s["commit"]): s["months"] for s in snapshots.values()}
    for role in ("ml_files", "npr_files"):
        if role not in paths:
            continue
        metric = ML_METRIC if role == "ml_files" else NPR_METRIC
        required = ["dataset_source", "repo_name", "snapshot_commit", "relative_path", metric]
        if role == "ml_files":
            required += ["ml_fun_occurrences_total", "ml_cfun_occurrences_total", "file_ml_fun_cfun_agc_status"]
        else:
            required += ["repo_month"]
        file_values, repeats, totals = {}, Counter(), Counter()
        month_files = set()
        for r in read_rows(source(role), required):
            snap = tuple(r[k].strip() for k in ("dataset_source", "repo_name", "snapshot_commit"))
            require(snap in weights, f"{role}: file outside the analysis snapshots: {snap}")
            path = r["relative_path"].strip()
            require(bool(path), f"{role}: blank relative_path")
            key = snap + (path,)
            if role == "npr_files":
                month_key = (snap[0], snap[1], r["repo_month"].strip(), path)
                require(bool(month_key[2]) and month_key not in month_files,
                        f"NPR blank month or duplicate repository-month-file: {month_key}")
                month_files.add(month_key)
            value = finite(r[metric], metric)
            if role == "ml_files":
                require(key not in file_values, f"ML duplicate snapshot-file: {key}")
                nf = integer(r["ml_fun_occurrences_total"], "ML RF occurrences")
                nc = integer(r["ml_cfun_occurrences_total"], "ML CM occurrences")
                status = r["file_ml_fun_cfun_agc_status"]
                require(status in {"scored", "no_ml_fun_cfun", "file_not_prepared"}, f"ML unknown status: {status}")
                require((value is not None) == (status == "scored"), f"ML eligibility/status mismatch: {key}")
                if value is not None:
                    require(0 <= value <= 1, f"ML token share outside [0,1]: {key}")
                totals.update({"rf_occurrences": nf, "cm_occurrences": nc, "rf_files": int(nf > 0),
                               "cm_files": int(nc > 0), "prepared_files": int(status != "file_not_prepared")})
            if key in file_values:
                require(file_values[key] == value, f"NPR value changes across repeated snapshot-file: {key}")
            file_values[key] = value; repeats[key] += 1
            totals["rows"] += 1; totals["finite_rows"] += int(value is not None)
            if role == "npr_files":
                totals["selected_rows"] += int(value is not None and value > primary_threshold)
        equal(role + ".unique_files", len(file_values), values["python_files"])
        equal(role + ".eligible_unique_files", sum(v is not None for v in file_values.values()), values[role])
        if role == "ml_files":
            for k in ("prepared_files", "rf_files", "rf_occurrences", "cm_files", "cm_occurrences"):
                equal("raw_ml." + k, totals[k], values[k])
        else:
            equal("raw_npr.expanded_rows", totals["rows"], count(c04, "audit.input_rows"))
            equal("raw_npr.expanded_finite", totals["finite_rows"], count(c04, "audit.eligible_finite_fun_cfun_rows"))
            equal("raw_npr.selected_unique", sum(v is not None and v > primary_threshold for v in file_values.values()), selected_unique)
            equal("raw_npr.selected_rows", totals["selected_rows"], selected_rows)
            require(all(n == weights[k[:3]] for k, n in repeats.items()), "NPR snapshot-file repetition disagrees with B06 mapping")
        raw.append(role)
    if "issues" in paths:
        seen_issues, counts = set(), Counter()
        # B05 uses snapshot_key + issue_key; do not deduplicate issue keys across snapshots.
        for r in read_rows(source("issues"), ["snapshot_key", "issue_key"]):
            key = (r["snapshot_key"], r["issue_key"])
            require(key[0] in snapshots and bool(key[1]), f"Invalid raw issue identity: {key}")
            require(key not in seen_issues, f"Duplicate issue within snapshot: {key}")
            seen_issues.add(key); counts[key[0]] += 1
        equal("raw_issues.total", len(seen_issues), issue_records)
        require(all(counts[k] == n for k, n in issue_by_snapshot.items()), "Raw issues disagree with B05 per-snapshot counts")
        raw.append("issues")

    # Compact set checks before JSON serialization.
    for check in checks:
        for k in ("observed", "expected"):
            if isinstance(check[k], set):
                check[k] = len(check[k])
    details = {
        "repository_groups": dict(Counter(repos.values())), "snapshot_groups": dict(groups),
        "repo_month_groups": dict(monthly_groups), "not_prepared_files": values["python_files"] - values["prepared_files"],
        "npr_repo_month_file_rows": count(c04, "audit.input_rows"),
        "finite_npr_repo_month_file_rows": count(c04, "audit.eligible_finite_fun_cfun_rows"),
        "repo_month_weighted_issue_stock": sum(s["months"] * s["issues"] for s in snapshots.values()),
        "upstream_statuses": {k: s["status"] for k, s in summaries.items()},
        "ml_mapping_warning_files": count(i06, "files.mapping_warning_files"),
        "raw_sources_verified": raw,
        "count_basis": "B05/B06 per-snapshot rows plus reconciled A12/A15/C04/I06 accounting; optional raw scans listed separately",
        "threshold_applied": False,
        "npr_experiment": {
            "script_version": get(c04, "script_version"),
            "primary_threshold": str(threshold_numbers[0]), "comparison_operator": ">",
            "metric": NPR_METRIC,
            "selected_unique_snapshot_files": selected_unique,
            "selected_repo_month_file_rows": selected_rows,
            "note": "Selected counts are supplemental; the manuscript table reports finite-signal eligibility without threshold filtering.",
        },
    }
    return values, details, checks, sources


def table_rows(values, details):
    rows = []
    for key, label, unit, basis in ROWS:
        display = f"{values[key]:,}"
        if key in {"repositories", "snapshots"}:
            g = details["repository_groups" if key == "repositories" else "snapshot_groups"]
            display += f" ({g.get('treatment', 0):,} $+$ {g.get('control', 0):,})"
        rows.append({"metric": key, "quantity": label, "value": values[key], "formatted_value": display,
                     "unit": unit, "source_basis": basis})
    return rows


def latex(rows):
    lines = [r"\begin{table}[h]", r"\centering", r"\scriptsize",
             r"\caption{Construction and scope of the Python empirical dataset. File instances, procedure occurrences, and issue records are counted once per historical repository--commit snapshot. Parentheses report treatment and control counts, respectively.}",
             r"\label{tb:python-empirical-dataset}", r"\begin{tabular}{l|r}",
             r"\textbf{Quantity} & \textbf{Value} \\", r"\midrule"]
    for row in rows:
        if row["metric"] in {"rf_files", "npr_files", "issue_records"}:
            lines.append(r"\addlinespace")
        lines.append(row["quantity"] + " & " + row["formatted_value"] + r" \\")
    lines += [r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="ai-code-complexity-study root (default: current directory)")
    parser.add_argument("--npr-root", type=Path, help="DetectCodeGPT output/snapshot_npr; default: PROJECT/../../detect_code_gpt/output/snapshot_npr")
    parser.add_argument("--expected-npr-threshold", default="1.515059", help="Validate C04's current primary threshold; does not filter dataset-table counts")
    parser.add_argument("--expected-c04-version", default="run-x-c04-v2", help="Required C04 experiment version")
    for flag in ("snapshot-map", "snapshot-issues", "a12-summary", "a15-summary", "c04-summary", "i06-summary"):
        parser.add_argument("--" + flag, type=Path)
    for flag in ("npr-files", "ml-files", "issues"):
        parser.add_argument("--" + flag, type=Path, help="Optional raw CSV/CSV.GZ for independent row-level verification")
    parser.add_argument("--output-dir", type=Path, help="Default: PROJECT/repo_x01/run-y-b01/python-empirical-dataset-v1")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    npr = args.npr_root or root / "../../detect_code_gpt/output/snapshot_npr"
    paths = {
        "snapshot_map": args.snapshot_map or root / "repo_x01/run-x-b06/python_quality_snapshot_join_audit.csv",
        "snapshot_issues": args.snapshot_issues or root / "repo_x01/run-x-b05/python_sonarqube_issue_snapshot_counts.csv",
        "a12": args.a12_summary or npr / "run-x-a12/summary.json",
        "a15": args.a15_summary or npr / "run-x-a15/summary.json",
        "c04": args.c04_summary or npr / "run-x-c04/fun-cfun-threshold-v2/summary.json",
        "i06": args.i06_summary or root / "repo_x01/run-x-i06/summary.json",
    }
    for role in ("npr_files", "ml_files", "issues"):
        if getattr(args, role) is not None:
            paths[role] = getattr(args, role)
    out = args.output_dir or root / "repo_x01/run-y-b01/python-empirical-dataset-v1"
    try:
        values, details, checks, sources = compute(paths, args.expected_npr_threshold, args.expected_c04_version)
        rows = table_rows(values, details)
        # All validation finishes before opening outputs. Use a new destination
        # to preserve earlier results and avoid leaving a misleading success file.
        require(not out.exists(), f"Output directory already exists: {out}; choose a new --output-dir")
        out.mkdir(parents=True)
        for name, data in (("python_empirical_dataset.csv", rows), ("python_empirical_dataset_checks.csv", checks)):
            with (out / name).open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
        (out / "python_empirical_dataset.tex").write_text(latex(rows), encoding="utf-8")
        report = {"script_version": VERSION, "status": "PASS", "created_utc": datetime.now(timezone.utc).isoformat(),
                  "script_sha256": sha256(Path(__file__)), "values": values, "details": details,
                  "checks_passed": len(checks), "sources": sources}
        (out / "python_empirical_dataset.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for row in rows:
            print(f"{row['quantity']}: {row['formatted_value'].replace('$+$', '+')}")
        experiment = details["npr_experiment"]
        print(f"Verified NPR experiment: {experiment['script_version']}; NPR > {experiment['primary_threshold']}")
        print(f"Supplemental selected snapshot-files (not the table's finite count): {experiment['selected_unique_snapshot_files']:,}")
        print(f"Supplemental selected repo-month-file rows: {experiment['selected_repo_month_file_rows']:,}")
        print(f"PASS: {len(checks)} reconciliation checks; raw sources verified: {details['raw_sources_verified'] or 'none (accounting mode)'}")
        print(f"Outputs: {out.resolve()}")
        return 0
    except (DataError, OSError, json.JSONDecodeError, csv.Error, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    sys.exit(main())
