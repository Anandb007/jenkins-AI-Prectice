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

job_name = "demo-pipeline"
build_num = "lastBuild"  # or use a number like "1"

r = requests.get(f"{url}/job/{job_name}/{build_num}/consoleText", auth=auth)
r.raise_for_status()
lines = r.text.strip().split("\n")

# Patterns to count
patterns = {
    "ERROR": re.compile(r"ERROR", re.I),
    "FAIL": re.compile(r"FAIL", re.I),
    "Exception": re.compile(r"Exception", re.I),
}
counts = defaultdict(int)
matched_lines = []

for line in lines:
    for name, pat in patterns.items():
        if pat.search(line):
            counts[name] += 1
            matched_lines.append((name, line.strip()[:80]))

print("=== Log summary ===")
print("Total lines:", len(lines))
print("\nMatches by pattern:")
for k, v in sorted(counts.items()):
    print(f"  {k}: {v}")
print("\nSample matched lines:")
for name, line in matched_lines[:10]:
    print(f"  [{name}] {line}")
