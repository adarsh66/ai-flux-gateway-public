"""Finite local typing receipt; no npm scripts, builds, network or deployment."""
import json
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / ".deployment/feature2-model-access-source-20261103-01"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", choices=["typecheck03", "typecheck04"], default="typecheck03")
    receipt = HOME / (parser.parse_args().receipt + ".json")
    # Exclusive receipt prevents accidental rerun over consumed validation.
    with receipt.open("x") as output:
        results = []
        for project in ("packages/ui", "apps/admin-portal", "apps/customer-portal"):
            run = subprocess.run(["C:/Program Files/nodejs/node.exe", "node_modules/typescript/bin/tsc",
                "--noEmit", "-p", project + "/tsconfig.json"], cwd=ROOT, capture_output=True, timeout=120)
            results.append({"project": project, "exit": run.returncode,
                "stdout": run.stdout.decode(errors="replace"), "stderr": run.stderr.decode(errors="replace")})
        json.dump(results, output, indent=2)
    print(json.dumps(results))
    raise SystemExit(any(r["exit"] for r in results))


if __name__ == "__main__":
    main()