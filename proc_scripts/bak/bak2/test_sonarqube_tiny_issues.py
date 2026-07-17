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

# These are the issue types used in the original warning collection script.
issue_types = ["BUG", "VULNERABILITY", "CODE_SMELL"]

url = f"{sonar_host}/api/issues/search"

print("SONAR_HOST:", sonar_host)
print("Project key:", project_key)
print("API:", url)
print()

for issue_type in issue_types:
    params = {
        "componentKeys": project_key,
        "types": issue_type,
        "ps": 100,
        "p": 1,
    }

    response = requests.get(
        url,
        params=params,
        auth=(sonar_token, ""),
        timeout=60,
    )

    print("=" * 60)
    print("Issue type:", issue_type)
    print("HTTP:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        raise SystemExit("Failed to query SonarQube issues")

    data = response.json()
    total = data.get("total", 0)
    issues = data.get("issues", [])

    print("Total issues:", total)
    print("Returned issues:", len(issues))

    for issue in issues[:5]:
        print(
            "-",
            issue.get("type"),
            issue.get("severity"),
            issue.get("rule"),
            issue.get("message"),
        )
