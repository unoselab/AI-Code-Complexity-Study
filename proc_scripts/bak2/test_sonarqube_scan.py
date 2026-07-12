import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load project environment variables explicitly
load_dotenv(dotenv_path=".env")

sonar_host = os.getenv("SONAR_HOST")
sonar_token = os.getenv("SONAR_TOKEN")
scanner_path = os.getenv("SONAR_SCANNER_PATH")

project_dir = Path("tmp_sonar_smoke/tiny_project").resolve()

print("SONAR_HOST:", sonar_host)
print("SONAR_TOKEN is set:", bool(sonar_token))
print("SONAR_SCANNER_PATH:", scanner_path)
print("Project directory:", project_dir)

if not sonar_host:
    raise SystemExit("Missing SONAR_HOST")
if not sonar_token:
    raise SystemExit("Missing SONAR_TOKEN")
if not scanner_path:
    raise SystemExit("Missing SONAR_SCANNER_PATH")
if not project_dir.exists():
    raise SystemExit(f"Missing project directory: {project_dir}")

# Run sonar-scanner from inside the tiny project directory.
# The scanner reads sonar-project.properties from the current working directory.
cmd = [
    scanner_path,
    f"-Dsonar.host.url={sonar_host}",
    f"-Dsonar.token={sonar_token}",
]

print("\nRunning sonar-scanner...")
result = subprocess.run(
    cmd,
    cwd=project_dir,
    text=True,
    capture_output=True,
)

print("\nReturn code:", result.returncode)

print("\nSTDOUT:")
print(result.stdout)

print("\nSTDERR:")
print(result.stderr)

if result.returncode != 0:
    raise SystemExit("Tiny SonarQube scan failed")

print("\nTiny SonarQube scan completed.")
