import os
import re
import requests
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
url = os.getenv("JENKINS_URL").rstrip("/")
user = os.getenv("JENKINS_USER")
token = os.getenv("JENKINS_API_TOKEN")
auth = (user, token)

# Get jobs
r = requests.get(f"{url}/api/json", auth=auth)
r.raise_for_status()
jobs = r.json().get("jobs", [])

report = []
for j in jobs:
    name = j["name"]
    r2 = requests.get(f"{url}/job/{name}/lastBuild/api/json", auth=auth)
    if r2.status_code != 200:
        report.append(f"{name}: no build")
        continue
    build = r2.json()
    report.append(f"{name}: build #{build['number']} = {build.get('result', '?')}")

# Get console for demo-pipeline and count errors
if any(j["name"] == "demo-pipeline" for j in jobs):
    r3 = requests.get(f"{url}/job/demo-pipeline/lastBuild/consoleText", auth=auth)
    if r3.status_code == 200:
        text = r3.text
        err_count = len(re.findall(r"ERROR|FAIL", text, re.I))
        report.append(f"demo-pipeline last log: ERROR/FAIL count = {err_count}")

# Write report
with open("report.txt", "w") as f:
    f.write("\n".join(report))
print("Report written to report.txt")
print("\n".join(report))
