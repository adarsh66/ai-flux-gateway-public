"""Sanitized checkpoints for the authorized GLM application release only."""
import argparse
import copy
import json
import subprocess
import ssl
import sys
from datetime import UTC, datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from scripts.deployment import glm_runtime_release as glm
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.deploy_portals import workflow


def inspect():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    runs = rt.cli(["acr", "task", "list-runs", "-r", portals.REGISTRY,
                   "--subscription", rt.SUB, "--top", "8", "--query",
                   "[].{runId:runId,status:status,finishTime:finishTime}"])
    baseline = portals.baseline()
    api_tag = "glm-20261026t154044z-dfb523bedf4e"
    manifest = json.loads((glm.HOME / api_tag / "source-manifest.json").read_text())
    changed = []
    for kind, tag in [("admin", "local-20261026t125458z-3deae1c32e3f"),
                      ("customer", "local-20261023t173114z-571d75366033")]:
        path = portals.HOME / tag / "source-manifest.json"
        previous = {e["path"]: e["sha256"] for e in json.loads(path.read_text())["entries"]}
        differences = [p.relative_to(rt.ROOT).as_posix() for p in portals.source_files()
                       if previous.get(p.relative_to(rt.ROOT).as_posix()) != portals.digest(p.read_bytes())]
        changed.append({"portal": kind, "source_differences": differences})
    report = {"at": datetime.now(UTC).isoformat(), "subscription": account["id"],
              "runs": runs, "api_sources_match_built": manifest["entries"] == glm.source_entries(),
              "images": {k: v["image"] for k, v in baseline["sites"].items()},
              "portal_comparison": changed}
    rt.save(glm.HOME / "resume-inspection.json", report)
    print(json.dumps(report), flush=True)


def bestpractices():
    exe = "C:/Program Files/Microsoft VS Code/Extensions/ms-azuretools.vscode-azure-mcp-server-3.0.51-win32-x64/server/azmcp.exe"
    process = subprocess.run([exe, "get_azure_bestpractices", "get", "--resource", "general",
                              "--action", "all"], env=rt.ENV, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=120)
    rt.require(process.returncode == 0, "bestpractices_failed")
    print(process.stdout, flush=True)


def validate(api_tag, portal_tag):
    for step in ["None", "LoadPlan", "AddValidationSteps"]:
        print(json.dumps(workflow(step)), flush=True)
    tests = ["test_glm_runtime_release.py", "test_portal_fix.py", "test_external_inventory.py",
             "test_foundry_inventory.py", "test_project_route_external.py",
             "test_project_route_models.py", "test_project_route_persistent.py",
             "test_glm_secret_installer.py"]
    output = rt.run(["C:/Program Files/Python313/python.exe", "-m", "pytest", "-q",
                     *["tests/unit/" + name for name in tests]])
    print(output, flush=True)
    rt.tf(["init", "-input=false", "-lockfile=readonly", "-no-color"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    mock = rt.run([rt.TF, "-chdir=infra/project-route", "test", "-no-color",
                   "-filter=tests\\external.tftest.hcl", "-filter=tests\\defaults.tftest.hcl"])
    print(mock, flush=True)
    glm.plan_release(api_tag, portal_tag)
    print(json.dumps(workflow("RunValidation")), flush=True)
    built = glm.release(api_tag, portal_tag)
    print(json.dumps(workflow("BuildVerification")), flush=True)
    review = json.loads((glm.HOME / api_tag / "review.json").read_text())
    current = review["baseline"]
    registry_scope = rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + portals.REGISTRY
    for kind in glm.KINDS:
        identities = current["sites"][kind]["protected"]["identity"]["userAssignedIdentities"]
        rt.require(any(r[1] == identity["principalId"] and
                       r[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d") and
                       r[3].lower() == registry_scope.lower() and not r[4]
                       for identity in identities.values() for r in current["roleAssignments"]),
                   "missing_acr_pull:" + kind)
    policies = rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + rt.SUB,
                       "--disable-scope-strict-match"])
    rt.require(rt.tf(["workspace", "show"]).strip() == "default", "terraform_workspace")
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    proof = {"at": datetime.now(UTC).isoformat(), "api_tag": api_tag, "portal_tag": portal_tag,
             "plan_sha256": review["plan_sha256"], "images": review["images"],
             "tests": output.strip(), "mocks": "external and defaults passed",
             "terraform": "init readonly, fmt, validate, exact saved-plan guard passed",
             "live_acr_pull": list(glm.KINDS), "policy_assignments": len(policies),
             "security": "all non-image fields and observed baseline preserved; no role writes",
             "checks_passed": True}
    rt.save(glm.HOME / api_tag / "validation.json", proof)
    print(json.dumps(proof), flush=True)


def diagnose():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    storage = rt.cli(["storage", "account", "show", "--name", "projpoctokenex",
                       "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB])
    roles = rt.cli(["role", "assignment", "list", "--subscription", rt.SUB, "--all", "--include-inherited"])
    backend = json.loads((rt.ROOT / "infra/terraform/.terraform/terraform.tfstate").read_text())["backend"]["config"]
    tls = ssl.create_default_context(cafile=rt.CA)
    token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                    "--resource", "https://storage.azure.com/"])["accessToken"]
    req = Request("https://projpoctokenex.blob.core.windows.net/tfstate?restype=container&comp=list&maxresults=1",
                  headers={"Authorization": "Bearer " + token, "x-ms-version": "2023-11-03"})
    try:
        with urlopen(req, context=tls, timeout=60) as response:
            state_read = {"status": response.status, "error_code": None}
    except HTTPError as error:
        state_read = {"status": error.code, "error_code": error.headers.get("x-ms-error-code"),
                      "request_id": error.headers.get("x-ms-request-id")}
    token = None
    external_ip = None
    try:
        with urlopen("https://api.ipify.org", context=tls, timeout=30) as response:
            external_ip = response.read(64).decode().strip()
    except Exception:
        pass
    baseline = portals.baseline()
    before = json.loads((portals.HOME / "local-20261026t155324z-218874b8d8d4/baseline.json").read_text())["snapshot"]
    report = {"at": datetime.now(UTC).isoformat(), "account": {k: account[k] for k in ["id", "tenantId"]},
              "backend": {k: backend.get(k) for k in ["resource_group_name", "storage_account_name",
                  "container_name", "key", "subscription_id", "tenant_id", "use_azuread_auth", "use_cli"]},
              "storage": {k: storage.get(k) for k in ["publicNetworkAccess", "networkRuleSet", "allowSharedKeyAccess"]},
              "operator_roles": [{"role": r.get("roleDefinitionName"), "scope": r["scope"]}
                                 for r in roles if r["principalId"].lower() == rt.OPERATOR],
              "state_read": state_read, "observed_https_egress_ip": external_ip,
              "security_and_images_unchanged": baseline == before,
              "images": {k: v["image"] for k, v in baseline["sites"].items()},
              "no_runtime_apply": not (glm.HOME / "glm-20261026t154044z-dfb523bedf4e/applied.json").exists()}
    rt.save(glm.HOME / "runtime-blocker.json", report)
    print(json.dumps(report), flush=True)


def applied_baseline(review, applied, portal_before, portal_release, portal_apply):
    """Verify the two-stage apply chain without accepting arbitrary live drift."""
    rt.require(applied["images"] == review["images"] and
               applied["plan_sha256"] == review["plan_sha256"] and
               applied.get("image_only_readback_verified") is True, "runtime_apply_binding")
    expected = copy.deepcopy(review["baseline"])
    for kind, image in applied["images"].items():
        expected["sites"][kind]["image"] = "DOCKER|" + image
    rt.require(portal_before == expected, "portal_correction_predecessor_changed")
    rt.require(portal_apply.get("applied") is True and portal_apply.get("guard") == "passed"
               and portal_apply["tag"] == portal_release["tag"]
               and portal_apply["portals"] == ["admin", "customer"], "portal_apply_binding")
    rt.require(portal_apply["changes"] == [
        {"address": f'azurerm_linux_web_app.main["{kind}"]', "actions": ["update"],
         "changedFields": ["site_config"]} for kind in ("admin", "customer")],
        "portal_apply_scope")
    for kind in ("admin", "customer"):
        expected["sites"][kind]["image"] = "DOCKER|" + portal_release["results"][kind]["image"]
    return expected


def verify_live():
    """Read-only deployed-image/security and unauthenticated readiness evidence."""
    api_tag = "glm-20261026t154044z-dfb523bedf4e"
    folder = glm.HOME / api_tag
    applied = json.loads((folder / "applied.json").read_text())
    review = json.loads((folder / "review.json").read_text())
    current = portals.baseline()
    portal_tag = "local-20261026t165602z-eee5c65cfe99"
    portal_folder = portals.HOME / portal_tag
    portal_release = portals.verify_release(portal_folder)
    portal_apply = json.loads((portal_folder / "apply-result.json").read_text())
    portal_before = json.loads((portal_folder / "preplan-baseline.json").read_text())["snapshot"]
    expected = applied_baseline(review, applied, portal_before, portal_release, portal_apply)
    probes = []
    tls = ssl.create_default_context(cafile=rt.CA)
    for kind in ("admin", "customer"):
        for path in ("/healthz", "/api/me", "/api/model-deployments", "/api/models"):
            record = {"portal": kind, "path": path}
            try:
                with urlopen(f"https://poc-ids-token-ex-{kind}.azurewebsites.net{path}",
                             context=tls, timeout=60) as response:
                    record.update(status=response.status,
                                  content_type=response.headers.get("Content-Type"))
            except HTTPError as error:
                record.update(status=error.code,
                              content_type=error.headers.get("Content-Type"))
            except Exception as error:
                record["error_type"] = type(error).__name__
            probes.append(record)
    portals.check_sources(portals.HOME / portal_tag)
    result = {"at": datetime.now(UTC).isoformat(), "applied_at": applied["applied_at"],
              "portal_correction_applied_at": portal_apply["timestamp"],
              "portal_correction_plan_sha256": portal_apply["planSha256"],
              "installed_images": {k: v["image"] for k, v in current["sites"].items()},
              "protected_baseline_matches_applied": current == expected,
              "api_sources_match_installed": review["sources"] == glm.source_entries(),
              "latest_portal_sources_match": portal_tag,
              "probes": probes, "authenticated_acceptance": False}
    rt.save(glm.HOME / "current-live-verification.json", result)
    print(json.dumps(result), flush=True)
    rt.require(current == expected, "post_apply_protected_baseline_changed")


def probe_live():
    """One bounded request per selected model; client key stays in runner memory."""
    import os
    import hashlib
    from scripts.deployment.project_route_models import ModelsRun
    from scripts.deployment.apim_route_repair import SUBSCRIBER
    os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA)
    run = ModelsRun()
    protected = run.hashes()
    policy = run.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
    applied = json.loads((rt.HOME / "project-glm-apply.json").read_text())
    rt.require(protected == applied["protected"], "protected_policy_changed")
    key = run.arm("/subscriptions/" + SUBSCRIBER + "/listSecrets", "POST")["primaryKey"]
    base = "/dev/llm/v1"
    origin = "https://poc-ids-token-ex-customer.azurewebsites.net"
    body = {"model": "glm-5.3", "messages": [{"role": "user", "content": "Reply with Hello."}],
            "max_completion_tokens": 200, "stream": False}
    try:
        for alias in ("glm-5.3", "gpt-5.6-luna", "gpt-4o"):
            run.probe(alias, base + "/chat/completions", key=key, origin=origin,
                      body={**body, "model": alias,
                            "max_completion_tokens": 200 if alias == "glm-5.3" else 32})
        for name, supplied in (("missing-key", None), ("invalid-key", "invalid-synthetic-key")):
            run.probe(name, base + "/models", key=supplied)
        run.probe("over-cap", base + "/chat/completions", key=key,
                  body={**body, "max_completion_tokens": 1025})
        run.probe("unknown-model", base + "/chat/completions", key=key,
                  body={**body, "model": "unapproved"})
        for allowed in (origin, "https://poc-ids-token-ex-admin.azurewebsites.net", "https://untrusted.invalid"):
            run.probe("cors:" + allowed, base + "/chat/completions", method="OPTIONS", origin=allowed)
    finally:
        key = None
        result = {"at": datetime.now(UTC).isoformat(), "checks": run.report["checks"],
                  "policy_sha256": hashlib.sha256(policy.encode()).hexdigest(),
                  "protected_after_unchanged": run.hashes() == protected,
                  "all_ten_tested": False, "inference_retries": 0, "quota_resets": 0}
        rt.save(glm.HOME / "current-gateway-probes.json", result)
        print(json.dumps(result), flush=True)
    checks = result["checks"]
    rt.require(len(checks) == 10 and result["protected_after_unchanged"], "incomplete_probe_evidence")
    rt.require(all(c["status"] == 200 and c["assistant_text"] for c in checks[:3]),
               "bounded_inference_failed")
    usage = checks[0].get("usage") or {}
    rt.require(checks[0]["response_model"] == "glm-5.3"
               and 0 < usage.get("completion_tokens", 0) <= 200
               and usage.get("prompt_tokens", -1) >= 0
               and usage.get("total_tokens") == usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
               "glm_metering_failed")
    rt.require([c["status"] for c in checks[3:7]] == [401, 401, 400, 400], "rejection_probe_failed")
    rt.require([c["allow_origin"] for c in checks[7:]] == [origin,
               "https://poc-ids-token-ex-admin.azurewebsites.net", None], "exact_origin_cors_failed")


def diagnose_activation():
    """Fixed-scope filtered runtime metadata; never expose env/settings or logs."""
    result = {"at": datetime.now(UTC).isoformat(), "sites": {}}
    release = json.loads((portals.HOME / "local-20261026t165602z-eee5c65cfe99/results.json").read_text())
    for kind in ("api", "admin", "customer"):
        rid = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        props = rt.arm(rid)["properties"]
        record = {k: props.get(k) for k in ("state", "availabilityState", "lastModifiedTimeUtc")}
        try:
            record["instances"] = [{"state": i.get("properties", {}).get("state"),
                                     "containers": len(i.get("properties", {}).get("containers") or {})}
                                    for i in rt.arm(rid + "/instances").get("value", [])]
        except (HTTPError, json.JSONDecodeError) as error:
            record["instances_error"] = type(error).__name__
        try:
            containers = rt.arm(rid + "/sitecontainers").get("value", [])
            record["sidecars"] = [{k: c.get("properties", {}).get(k) for k in ("image", "isMain", "targetPort")}
                                   for c in containers]
        except (HTTPError, json.JSONDecodeError) as error:
            record["sidecar_error"] = type(error).__name__
            if isinstance(error, HTTPError):
                record["sidecar_status"] = error.code
        if kind in ("api", "customer"):
            try:
                raw = rt.arm(rid + "/containerlogs", "POST", raw=True)
                record["logs"] = rt.log_summary(raw)
                if kind == "customer":
                    record["logs"]["current_digest_mentioned"] = release["results"][kind]["digest"].encode() in raw
                for label, marker in {"nginx_config_unwritable": b"can not modify /etc/nginx/conf.d/default.conf",
                                      "template_not_writable": b"not writable",
                                      "template_rendered": b"Running envsubst",
                                      "permission_denied": b"Permission denied"}.items():
                    record.setdefault("log_flags", {})[label] = marker.lower() in raw.lower()
            except HTTPError as error:
                record["logs_status"] = error.code
        result["sites"][kind] = record
    rt.save(glm.HOME / "activation-diagnosis-current.json", result)
    print(json.dumps(result), flush=True)


def checkpoint():
    """Capture actual routine exit codes and safe evidence, with no cloud writes."""
    result = {"at": datetime.now(UTC).isoformat(), "commands": [], "cloud_configuration_writes": 0}
    for action in ("verify-live", "probe-live", "diagnose-activation"):
        process = subprocess.run([sys.executable, "-u", "-m", "scripts.deployment.glm_resume", action],
                                 cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace")
        record = {"action": action, "exit_code": process.returncode,
                  "stderr_present": bool(process.stderr)}
        result["commands"].append(record)
        # Child routines emit sanitized JSON only, never raw ARM or credential bodies.
        print(process.stdout, flush=True)
        print(json.dumps(record), flush=True)
        rt.save(glm.HOME / "execution-checkpoint.json", result)
    storage = rt.cli(["storage", "account", "show", "--name", "projpoctokenex",
                      "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB,
                      "--query", "{publicNetworkAccess:publicNetworkAccess,networkRuleSet:networkRuleSet}"])
    result["storage"] = storage
    rules = {r["ipAddressOrRange"] for r in storage["networkRuleSet"]["ipRules"]}
    result["approved_storage_rules_preserved"] = {"167.103.66.93", "167.103.66.248"} <= rules
    result["all_commands_passed"] = all(r["exit_code"] == 0 for r in result["commands"])
    rt.save(glm.HOME / "execution-checkpoint.json", result)
    print(json.dumps(result), flush=True)
    rt.require(result["all_commands_passed"] and result["approved_storage_rules_preserved"]
               and storage["networkRuleSet"]["defaultAction"] == "Deny", "checkpoint_failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "bestpractices", "build-portals", "validate", "diagnose", "verify-live", "probe-live", "diagnose-activation", "checkpoint"])
    parser.add_argument("--api-tag")
    parser.add_argument("--portal-tag")
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            inspect()
        elif args.action == "bestpractices":
            bestpractices()
        elif args.action == "validate":
            rt.require(bool(args.api_tag and args.portal_tag), "release_tags_required")
            validate(args.api_tag, args.portal_tag)
        elif args.action == "diagnose":
            diagnose()
        elif args.action == "verify-live":
            verify_live()
        elif args.action == "probe-live":
            probe_live()
        elif args.action == "diagnose-activation":
            diagnose_activation()
        elif args.action == "checkpoint":
            checkpoint()
        else:
            print(json.dumps({"portal_tag": portals.remote_build()}), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({"blocked": True, "reason": str(error) if isinstance(error, RuntimeError)
                          else type(error).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())