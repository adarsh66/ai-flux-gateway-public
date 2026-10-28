"""Authorized one-shot DBA operation, with Terraform-only ARM writes and finally cleanup."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".deployment"
TF = "C:/Program Files/Terraform/terraform.exe"
CLI = "C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe"
SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
ADMIN = "dd928302-055b-4516-9b8e-b06ae823057b"
RG = "IDS-TOKEN-EXCHANGE-POC"
SERVER = "poc-ids-token-ex-pg"
ARM = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.DBforPostgreSQL/flexibleServers/{SERVER}"
BASE = "azurerm_postgresql_flexible_server.main[0]"
FIREWALL = "azurerm_postgresql_flexible_server_firewall_rule.bootstrap[0]"
RETIRED = "azurerm_postgresql_flexible_server_firewall_rule.bootstrap_retired"
REPORT = {"schema": False, "principals": False, "closed": False, "runtime_applied": False}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def run(args, label):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    (OUT / f"postgres-execute-{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(json.dumps({"step": label, "exit": result.returncode}), flush=True)
    require(result.returncode == 0, f"{label} failed; see its log")
    return result.stdout


def read(path):
    return json.loads(run([CLI, "-X", "utf8", "-IBm", "azure.cli", "rest", "--method", "get",
                           "--url", "https://management.azure.com" + path + "?api-version=2024-08-01",
                           "--only-show-errors", "-o", "json"], "arm-" + path.rsplit("/", 1)[-1]))


def tf(args, label):
    return run([TF, "-chdir=infra/terraform"] + args, label)


def inputs(opening, retired=None):
    args = ["-var-file=" + str(OUT / "rebuild-platform.tfvars.json"),
            "-var-file=" + str(OUT / ("postgres-bootstrap.tfvars.json" if opening else
                                      "postgres-bootstrap-containment.tfvars.json"))]
    if retired:
        args += ["-var=postgres_bootstrap_rules_to_retire=" + json.dumps(retired)]
    return args


def guarded_apply(opening):
    label = "open" if opening else "close"
    plan_path = OUT / f"postgres-execute-{label}.tfplan"
    tf(["plan", "-input=false", "-no-color"] + inputs(opening) +
       ["-target=" + BASE, "-target=" + FIREWALL, "-target=" + RETIRED,
        "-out=" + str(plan_path)], label + "-plan")
    result = subprocess.run([TF, "-chdir=infra/terraform", "show", "-json", str(plan_path)],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    require(result.returncode == 0, "Cannot inspect saved plan")
    plan = json.loads(result.stdout)
    require(not plan.get("errored"), "Plan contains errors")
    actions = []
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        action = change["actions"]
        if action in (["no-op"], ["read"]):
            continue
        address = resource["address"]
        before, after = change.get("before"), change.get("after")
        if address == BASE:
            require(action == ["update"], "Server replacement prohibited")
            changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
            require(changed == {"public_network_access_enabled"} and
                    after["public_network_access_enabled"] == opening, "Unexpected server change")
        elif address == FIREWALL:
            require(action == (["create"] if opening else ["delete"]), "Unexpected firewall action")
            if opening:
                require(after["start_ip_address"] == REPORT["workstation_ipv4"] == after["end_ip_address"],
                        "Firewall IP mismatch")
        elif address.startswith(RETIRED + "["):
            require(action == ["delete"], "Retired rules must only be removed")
        else:
            raise RuntimeError("Plan would change an unrelated resource: " + address)
        actions.append({"address": address, "actions": action})
    REPORT[label + "_actions"] = actions
    print(json.dumps({"reviewed_plan": label, "actions": actions}), flush=True)
    if actions:
        require(plan.get("applyable"), "Plan is not applyable")
        tf(["apply", "-input=false", "-no-color", str(plan_path)], label + "-apply")


def main():
    if "--contain-only" in sys.argv:
        guarded_apply(False)
        server = read(ARM)
        rules = read(ARM + "/firewallRules")["value"]
        REPORT["closed"] = server["properties"]["network"]["publicNetworkAccess"] == "Disabled" and not rules
        require(REPORT["closed"], "URGENT: PostgreSQL containment not verified")
        print(json.dumps({"containment_verified": True}), flush=True)
        return
    spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "infra/sql/bootstrap-postgres.py")
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    args = bootstrap.parser().parse_args([
        "audit", "--release-dir", str(OUT / "image-build" / bootstrap.RELEASE),
        "--subscription", SUB, "--tenant", TENANT, "--resource-group", RG,
        "--server", SERVER, "--admin-object-id", ADMIN, "--cli-python", CLI])
    # Do not print tokens or secret-bearing application configuration.
    audit = bootstrap.audit_admin(args)
    REPORT["initial_public_access"] = audit["public_access"]
    REPORT["initial_firewall_rules"] = audit["firewall_rules"]
    with urlopen("https://ifconfig.me/ip", timeout=25) as response:
        ip = response.read().decode().strip()
    require(ipaddress.IPv4Address(ip).is_global, "Workstation endpoint did not return public IPv4")
    configured = json.loads((OUT / "postgres-bootstrap.tfvars.json").read_text())["postgres_bootstrap_public_ipv4"]
    require(ip == configured, "Fresh workstation IP differs from reviewed input")
    REPORT["workstation_ipv4"] = ip
    tf(["validate", "-no-color"], "validate")
    state = set(tf(["state", "list"], "state-list").splitlines())
    retired = [rule["name"] for rule in audit["firewall_rules"]
               if rule["name"] != "temporary-reviewed-dba-bootstrap"]
    try:
        for index, name in enumerate(retired):
            address = RETIRED + "[" + json.dumps(name) + "]"
            if address not in state:
                tf(["import", "-input=false", "-no-color"] + inputs(True, retired) +
                   [address, ARM + "/firewallRules/" + name], f"adopt-{index}")
        guarded_apply(True)
        audit = bootstrap.audit_admin(args)
        bootstrap.verify_network(audit, ip)
        common = [sys.executable, str(ROOT / "infra/sql/bootstrap-postgres.py"),
                  "--release-dir", str(args.release_dir), "--subscription", SUB, "--tenant", TENANT,
                  "--resource-group", RG, "--server", SERVER, "--admin-object-id", ADMIN,
                  "--cli-python", CLI, "--approved-public-ip", ip, "--execute"]
        run(common[:2] + ["schema"] + common[2:], "schema")
        REPORT["schema"] = True
        identity_args = []
        for kind in ("api", "ingestion"):
            identity = bootstrap.cli_read(["identity", "show", "--resource-group", RG,
                                           "--name", f"poc-ids-token-ex-{kind}-identity"], Path(CLI))
            identity_args += [f"--{kind}-name", identity["name"], f"--{kind}-object-id", identity["principalId"]]
        run(common[:2] + ["principals"] + common[2:] + identity_args, "principals")
        REPORT["principals"] = True
    finally:
        # Includes failed imports, failed opens, token/network/SQL failures.
        guarded_apply(False)
        server = read(ARM)
        rules = read(ARM + "/firewallRules")["value"]
        REPORT["closed"] = server["properties"]["network"]["publicNetworkAccess"] == "Disabled" and not rules
        require(REPORT["closed"], "URGENT: PostgreSQL containment not verified")
        print(json.dumps({"containment_verified": True}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        REPORT["error_type"] = type(error).__name__
        REPORT["error"] = str(error) if type(error) is RuntimeError else "Failed; inspect sanitized step logs"
        print(json.dumps({"failure": REPORT["error"]}), flush=True)
        sys.exit_code = 1
    finally:
        (OUT / "postgres-execute-result.json").write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
    sys.exit(getattr(sys, "exit_code", 0))