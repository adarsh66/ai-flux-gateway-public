"""Reconcile exact historical regression coverage plus new affected checks locally."""
from pathlib import Path
import os
import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / ".deployment/feature2-model-access-source-20261103-01"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", choices=["regression04", "regression05"], default="regression04")
    label = parser.parse_args().receipt
    target = HOME / (label + ".xml")
    if target.exists():
        raise SystemExit("Receipt already consumed")
    files = sorted({"tests/unit/" + case.attrib["classname"].split(".")[-1] + ".py"
                    for case in ET.parse(HOME / "regression02.xml").iter("testcase")})
    files += ["tests/unit/test_model_access_finish.py", "tests/unit/test_model_access.py",
              "tests/unit/test_model_access_publication.py"]
    files = sorted(set(files))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, [ROOT / "services/control-plane/src", ROOT,
                                                             ROOT / ".venv/Lib/site-packages"])))
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *files, "--junitxml=" + str(target)],
                            cwd=ROOT, env=env, capture_output=True, timeout=180)
    with (HOME / (label + ".stdout.txt")).open("xb") as output:
        output.write(result.stdout + result.stderr)
    print(result.stdout.decode(errors="replace"))
    print("EXIT", result.returncode)
    raise SystemExit(result.returncode)