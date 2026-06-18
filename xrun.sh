echo "Step 3: Create patched small-batch copy of run_sonarqube.py"

cp scripts/run_sonarqube.py proc_scripts/run_sonarqube_small_batch_test.py

python - <<'PY'
from pathlib import Path
import re

p = Path("proc_scripts/run_sonarqube_small_batch_test.py")
s = p.read_text()

# Patch 1: use temporary small-batch data directory.
s = re.sub(
    r'DATA_DIR\s*=\s*SCRIPT_DIR\.parent\s*/\s*"data"',
    'DATA_DIR = SCRIPT_DIR.parent / "tmp_sonar_batch" / "data"',
    s,
)

# Patch 2: use one process for a controlled smoke test.
s = re.sub(
    r'NUM_PROCESSES\s*=\s*\d+.*',
    'NUM_PROCESSES = 1  # small-batch smoke test',
    s,
)

# Patch 3: use SonarQube token basic authentication instead of Bearer auth.
s = s.replace(
    'headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}',
    'auth = (SONAR_TOKEN, "")',
)

s = s.replace(
    'requests.get(url, headers=headers, params=params)',
    'requests.get(url, auth=auth, params=params)',
)

p.write_text(s)

print("Patched:", p)
PY

echo
echo "Patch check:"
grep -n "DATA_DIR\|NUM_PROCESSES\|Authorization\|auth =\|requests.get" proc_scripts/run_sonarqube_small_batch_test.py
echo