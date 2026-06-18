cp proc_scripts/run_sonarqube_v2.py proc_scripts/run_sonarqube_v2.py.bak-dynamic-dates

python - <<'PY'
from pathlib import Path
import re

p = Path("proc_scripts/run_sonarqube_v2.py")
s = p.read_text()

# Insert a helper function before main().
helper = r'''
def infer_date_range_from_input(ts_df: pd.DataFrame, time_key: str) -> tuple[str, str]:
    """Infer START_DATE and END_DATE from the input time-series file."""
    if time_key not in ts_df.columns:
        raise ValueError(f"Missing time column: {time_key}")

    values = (
        ts_df[time_key]
        .dropna()
        .astype(str)
        .str.strip()
    )

    if values.empty:
        raise ValueError(f"No valid values found in time column: {time_key}")

    # Accept both YYYY-MM and YYYYMM formats, but normalize to YYYY-MM.
    normalized = []
    for value in values:
        if re.fullmatch(r"\d{6}", value):
            normalized.append(f"{value[:4]}-{value[4:]}")
        elif re.fullmatch(r"\d{4}-\d{2}", value):
            normalized.append(value)
        else:
            raise ValueError(
                f"Unsupported time value format in {time_key}: {value}. "
                "Expected YYYY-MM or YYYYMM."
            )

    return min(normalized), max(normalized)

'''

if "def infer_date_range_from_input" not in s:
    s = s.replace("\ndef main() -> None:", "\n" + helper + "\ndef main() -> None:")

# After ts_df = pd.read_csv(ts_repos_file), assign global START_DATE and END_DATE.
pattern = r'(\s+ts_df\s*=\s*pd\.read_csv\(ts_repos_file\)\n)'
replacement = r'''\1
    global START_DATE, END_DATE
    START_DATE, END_DATE = infer_date_range_from_input(ts_df, TIME_KEY)
    logging.info("Using input-derived date range: %s to %s", START_DATE, END_DATE)
'''

if "Using input-derived date range" not in s:
    s = re.sub(pattern, replacement, s, count=1)

p.write_text(s)
print("Patched dynamic START_DATE/END_DATE in", p)
PY