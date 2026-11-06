"""Read-only offline Dockerfile scan; no builds, plans, runtime or dependency writes."""
import json
import subprocess
import sys

from scripts.deployment import admin_showback_release as s


def main():
    rt = s.r.rt
    existing = s.HOME / "scanner.json"
    if existing.exists():
        proof = s.load(existing)
        for result in proof["results"]:
            rt.require(result["sha256"] == s.r.sha((rt.ROOT / result["path"]).read_bytes())
                and result["exit_code"] == 0 and not result["failed_checks"]
                and result["summary"]["parsing_errors"] == 0, "retained_scanner_binding")
        print(json.dumps({"retained_existing_scan": True, **proof}), flush=True)
        return
    tools = rt.HOME / "finops-runner/security-tools"
    env = {**rt.ENV, "PYTHONPATH": str(tools), "CKV_SKIP_UPDATE_CHECK": "true", "LOG_LEVEL": "ERROR"}
    env.pop("BC_API_KEY", None)
    results = []
    for name in ("services/control-plane/Dockerfile", "apps/admin-portal/Dockerfile"):
        path = rt.ROOT / name
        child = subprocess.run([sys.executable, str(tools / "bin/checkov"), "--file", str(path), "--framework",
            "dockerfile", "--skip-download", "--output", "json", "--compact"], env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=180)
        value = json.loads(child.stdout)
        results.append({"path": name, "sha256": s.r.sha(path.read_bytes()), "exit_code": child.returncode,
            "summary": value["summary"], **{key: [{"id": c["check_id"], "name": c["check_name"]}
                for c in value["results"].get(key, [])] for key in ("failed_checks", "skipped_checks")}})
    proof = {"at": s.r.fs.stamp(), "scanner": "checkov==3.2.495", "results": results,
             "dependencies_upgraded": False, "remote_policy_downloads": False}
    s.exclusive("scanner.json", proof)
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    main()