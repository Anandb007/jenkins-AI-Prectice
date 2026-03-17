import yaml

with open("jenkins_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

print("=== PyYAML config demo ===")
print("Jenkins URL:", cfg["jenkins_url"])
print("Job to run:", cfg["job_to_run"])
print("Params:", cfg.get("params", {}))
print("Report file:", cfg["report_file"])
