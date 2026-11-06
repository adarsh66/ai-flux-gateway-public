"""Local-only worker and durable-marker inspection; never starts other work."""
import json
from pathlib import Path
import psutil


if __name__ == "__main__":
    processes = []
    for p in psutil.process_iter(["name", "cmdline"]):
        if p.info["name"] and any(x in p.info["name"].lower() for x in ("python", "terraform")):
            args = p.info["cmdline"] or []
            modules = [a for a in args if a.startswith("scripts.deployment.poc_activation")]
            processes.append({"pid": p.pid, "name": p.info["name"], "activation_modules": modules})
    home = Path(__file__).resolve().parents[2] / ".deployment/poc-activation-20261028-packaged"
    print(json.dumps({"processes": processes, "markers": [str(p.relative_to(home)) for p in home.glob("*.json")],
                      "policy_directory_exists": (home / "policy").exists()}, indent=2), flush=True)