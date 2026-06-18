cp proc_scripts/run_sonarqube_v2.py proc_scripts/run_sonarqube_v2.py.bak-fix-syntax

python - <<'PY'
from pathlib import Path

p = Path("proc_scripts/run_sonarqube_v2.py")
lines = p.read_text().splitlines()

fixed = []

for line in lines:
    # Remove only the wrongly inserted unindented duplicate dynamic-date lines.
    # Keep the correctly indented lines inside the try block.
    if line == "global START_DATE, END_DATE":
        continue

    if line.startswith("START_DATE, END_DATE = infer_date_range_from_input"):
        continue

    if line.startswith('logging.info("Using input-derived date range'):
        continue

    fixed.append(line)

p.write_text("\n".join(fixed) + "\n")

print("Removed unindented duplicate dynamic-date lines from", p)
PY