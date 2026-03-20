import csv
import os
import psutil
from datetime import datetime

CSV_PATH = "utilisation.csv"
REPORT_PATH = "utilisation_report.txt"

def get_live_now():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    mem_pct = (mem.total - mem.available) / mem.total * 100 if mem.total else 0
    return round(cpu, 2), round(mem_pct, 2)

# Last 10 minutes from file
lines = ["=== Utilisation: last 10 minutes (from file) ===\n"]
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            ts = row.get("timestamp", "")
            cpu = row.get("cpu", "")
            mem = row.get("memory", "")
            lines.append(f"  {ts}  cpu={cpu}%  memory={mem}%\n")
    lines.append(f"  Total samples: {sum(1 for _ in open(CSV_PATH)) - 1}\n")
else:
    lines.append("  No data yet. Wait for cron to run collect_live_metrics.py.\n")

# Live right now
lines.append("\n=== Live usage now ===\n")
cpu_now, mem_now = get_live_now()
lines.append(f"  cpu={cpu_now}%  memory={mem_now}%\n")

with open(REPORT_PATH, "w") as f:
    f.writelines(lines)
print("Report written to", REPORT_PATH)
