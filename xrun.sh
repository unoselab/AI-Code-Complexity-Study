python - <<'PY'
from pathlib import Path

p = Path("proc_scripts/run_sonarqube_v2.py")
s = p.read_text()

if "import time\n" not in s:
    if "import argparse\n" in s:
        s = s.replace("import argparse\n", "import argparse\nimport time\n", 1)
    else:
        s = "import time\n" + s

p.write_text(s)
print("Added import time")
PY