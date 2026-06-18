import os
import requests
from dotenv import load_dotenv

# Load SonarQube settings from .env
load_dotenv(dotenv_path=".env")

sonar_host = os.getenv("SONAR_HOST", "http://localhost:9000").rstrip("/")
sonar_token = os.getenv("SONAR_TOKEN")

if not sonar_token:
    raise SystemExit("Missing SONAR_TOKEN in .env")

project_key = "cursorstudy-tiny-test"

metrics = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "cognitive_complexity",
    "sqale_index",
]

url = f"{sonar_host}/api/measures/component"

params = {
    "component": project_key,
    "metricKeys": ",".join(metrics),
}

print("SONAR_HOST:", sonar_host)
print("Project key:", project_key)
print("Metrics:", ", ".join(metrics))
print("API:", url)
print()

# SonarQube token authentication uses token as username and empty password.
response = requests.get(url, params=params, auth=(sonar_token, ""), timeout=60)

print("HTTP:", response.status_code)
print(response.text)

if response.status_code != 200:
    raise SystemExit("Failed to query SonarQube metrics")

data = response.json()
component = data.get("component", {})
measures = component.get("measures", [])

print()
print("Parsed metrics:")
for m in measures:
    metric = m.get("metric")
    value = m.get("value", "")
    print(f"{metric}: {value}")

missing = sorted(set(metrics) - {m.get("metric") for m in measures})
if missing:
    print()
    print("Missing metrics:", ", ".join(missing))
    print("This may be okay for a tiny test if the metric is not produced.")
