import os
import re
import yaml
import requests
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
with open("jenkins_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

JENKINS_URL = cfg["jenkins_url"]
JOB_NAME = cfg["job_to_run"]
REPORT_FILE = cfg["report_file"]
USER = os.getenv("JENKINS_USER")
TOKEN = os.getenv("JENKINS_API_TOKEN")
auth = (USER, TOKEN)

url = JENKINS_URL.rstrip("/")
job_name = JOB_NAME

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

# Get console for configured job and count errors
if any(j["name"] == job_name for j in jobs):
    r3 = requests.get(f"{url}/job/{job_name}/lastBuild/consoleText", auth=auth)
    if r3.status_code == 200:
        text = r3.text
        err_count = len(re.findall(r"ERROR|FAIL", text, re.I))
        report.append(f"{job_name} last log: ERROR/FAIL count = {err_count}")

# Write report to path from config
with open(REPORT_FILE, "w") as f:
    f.write("\n".join(report))
print(f"Report written to {REPORT_FILE}")
print("\n".join(report))
