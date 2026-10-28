"""GLM runtime release: reuse existing builders and strict image-only protection.

Never read appsettings, provider credentials, log bodies or publishing credentials.
The saved main-root plan is targeted to the three existing apps and independently
rejects every change except the three immutable image names. No worker release.
"""
import argparse
import copy
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime

from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt

HOME = rt.HOME / "glm-runtime"
KINDS = ("api", "admin", "customer")


def api_sources():
    paths = [rt.ROOT / "pyproject.toml", rt.ROOT / "services/control-plane/Dockerfile",
             rt.ROOT / "services/control-plane/alembic.ini",
             rt.ROOT / "gateway/policies/settings-unconfigured.xml"]
    for folder, suffixes in [("services/control-plane/src", {".py", ".kql"}),
                             ("services/control-plane/migrations", {".py"}),
                             ("gateway/catalog", {".json"})]:
        for path in (rt.ROOT / folder).rglob("*"):
            if (path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
                    and path.name != "0003_portal_users.py"):
                rt.require(not path.is_symlink(), "source_symlink")
                paths.append(path)
    return sorted(set(paths))


def source_entries():
    return [{"path": p.relative_to(rt.ROOT).as_posix(), "sha256": portals.digest(p.read_bytes())}
            for p in api_sources()]


def build_api():
    HOME.mkdir(parents=True, exist_ok=True)
    entries = source_entries()
    source_hash = portals.digest(json.dumps(entries, sort_keys=True).encode())
    tag = "glm-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz") + "-" + source_hash[:12]
    folder = HOME / tag
    context = folder / "context"
    for entry in entries:
        path = rt.ROOT / entry["path"]
        content = path.read_bytes()
        rt.require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", content), "source_secret_pattern")
        dest = context / entry["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    rt.save(folder / "source-manifest.json", {"tag": tag, "sourceHash": source_hash, "entries": entries})
    command = rt.CLI + ["acr", "build", "--registry", portals.REGISTRY, "--subscription", rt.SUB,
                       "--platform", "linux/amd64", "--timeout", "1800", "--file",
                       "services/control-plane/Dockerfile", "--image", "aiflux-api:" + tag, "."]
    process = subprocess.run(command, cwd=context, env=rt.ENV, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=1900)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', "[signed-url-redacted]", process.stdout + process.stderr)
    (folder / "api-build.log").write_text(text, encoding="utf-8")
    ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    rt.require(process.returncode == 0 and ids, "api_remote_build_failed")
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", ids[-1], "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded", "api_build_not_succeeded")
    image = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-api:" + tag, "--subscription", rt.SUB])
    rt.require(re.fullmatch(r"sha256:[a-f0-9]{64}", image["digest"]), "api_digest_invalid")
    result = {"runId": ids[-1], "status": run["status"], "finishedAt": run.get("finishTime"),
              "digest": image["digest"], "image": portals.HOST + "/aiflux-api@" + image["digest"]}
    rt.save(folder / "result.json", result)
    print(json.dumps({"tag": tag, "api": result}), flush=True)


def release(api_tag, portal_tag):
    folder = HOME / api_tag
    manifest = json.loads((folder / "source-manifest.json").read_text(encoding="utf-8"))
    rt.require(manifest["entries"] == source_entries(), "api_source_changed")
    api = json.loads((folder / "result.json").read_text())
    remote = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", api["runId"], "--subscription", rt.SUB])
    rt.require(remote["status"] == "Succeeded" and remote.get("finishTime") == api["finishedAt"], "api_run_changed")
    meta = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-api:" + api_tag, "--subscription", rt.SUB])
    rt.require(meta["digest"] == api["digest"] and api["image"] == portals.HOST + "/aiflux-api@" + api["digest"], "api_pin_changed")
    portal_release = portals.verify_release(portals.HOME / portal_tag)
    rt.require(portals.release_kinds(portal_release) == ("admin", "customer"), "both_changed_portals_required")
    return {"results": {"api": api, **{k: portal_release["results"][k] for k in ("admin", "customer")}}}


def guard(plan, built):
    rt.require(not plan.get("errored") and plan.get("applyable") is True and not plan.get("deferred_changes"), "unresolved_plan")
    expected = {f'azurerm_linux_web_app.main["{k}"]': k for k in KINDS}
    seen = set()
    computed = {"possible_outbound_ip_address_list", "possible_outbound_ip_addresses",
                "outbound_ip_address_list", "outbound_ip_addresses", "custom_domain_verification_id"}
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        if change["actions"] == ["no-op"]:
            continue
        address = resource["address"]
        rt.require(resource.get("mode") == "managed" and address in expected and address not in seen
                   and change["actions"] == ["update"], "non_image_resource")
        seen.add(address)
        before, after = copy.deepcopy(change["before"]), copy.deepcopy(change["after"])
        unknown = change.get("after_unknown") or {}
        rt.require(not any(rt.any_true(v) for k, v in unknown.items() if k not in computed), "unknown_writable_input")
        for key in computed:
            if rt.any_true(unknown.get(key)):
                after[key] = before.get(key)
        rt.require(portals.changed(before, after) == {"site_config"}, "settings_identity_or_network_change")
        old, new = before["site_config"][0], after["site_config"][0]
        rt.require(portals.changed(old, new) == {"application_stack"}, "security_config_change")
        old, new = old["application_stack"][0], new["application_stack"][0]
        rt.require(portals.changed(old, new) == {"docker_image_name"}, "registry_or_non_image_stack_change")
        image = built["results"][expected[address]]["image"]
        rt.require(image.startswith(portals.HOST + "/aiflux-" + expected[address] + "@sha256:")
                   and new["docker_registry_url"] == "https://" + portals.HOST
                   and new["docker_image_name"] == image.split("/", 1)[1], "wrong_image_pin")
    rt.require(seen == set(expected), "exact_three_image_updates_required")


def plan_release(api_tag, portal_tag, apply=False):
    folder = HOME / api_tag
    built = release(api_tag, portal_tag)
    fresh = portals.baseline()  # Filtered web config, never appsettings/list.
    target = folder / "runtime.tfplan"
    if not apply:
        sid = re.search(r"S-1-5-[0-9-]+", rt.run(["whoami", "/user", "/fo", "csv", "/nh"])).group(0)
        rt.run(["icacls", str(folder), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
        variables = portals.runtime_variables({"results": built["results"]}, fresh)
        variables["apps"]["api"]["image"] = built["results"]["api"]["image"].split("/", 1)[1]
        rt.save(folder / "runtime-images.tfvars.json", variables)
        rt.tf(["validate", "-no-color"])
        rt.tf(["plan", "-input=false", "-no-color", "-lock-timeout=60s",
               "-var-file=" + str(rt.HOME / "rebuild-platform.tfvars.json"),
               "-var-file=" + str(folder / "runtime-images.tfvars.json"),
               "-var-file=" + str(rt.HOME / "jwt-runtime.tfvars.json"),
               *['-target=azurerm_linux_web_app.main["' + k + '"]' for k in KINDS], "-out=" + str(target)])
    parsed = json.loads(rt.tf(["show", "-json", str(target)]))
    guard(parsed, built)
    binding = {"api_tag": api_tag, "portal_tag": portal_tag, "plan_sha256": portals.digest(target.read_bytes()),
               "sources": source_entries(), "images": {k: built["results"][k]["image"] for k in KINDS},
               "baseline": fresh, "guard_verified": True}
    if not apply:
        rt.save(folder / "review.json", binding)
    else:
        rt.require(json.loads((folder / "review.json").read_text()) == binding, "review_or_baseline_changed")
        status = json.loads((rt.ROOT / ".azure/validate-status.json").read_text())
        doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
        rt.require(status.get("completedStep") == "UpdateStatus" and
                   "GLM runtime validation status: Validated" in doc and binding["plan_sha256"] in doc, "current_runtime_validation_missing")
        rt.tf(["apply", "-input=false", "-no-color", str(target)])
        expected = copy.deepcopy(fresh)
        for kind in KINDS:
            expected["sites"][kind]["image"] = "DOCKER|" + built["results"][kind]["image"]
        rt.require(portals.baseline() == expected, "post_apply_security_or_image_mismatch")
        rt.save(folder / "applied.json", {"plan_sha256": binding["plan_sha256"], "images": binding["images"],
                "applied_at": datetime.now(UTC).isoformat(), "image_only_readback_verified": True})
    print(json.dumps({"plan_sha256": binding["plan_sha256"], "guard_verified": True,
                      "images": binding["images"], "applied": apply}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build-api", "plan", "apply"])
    parser.add_argument("--api-tag")
    parser.add_argument("--portal-tag")
    args = parser.parse_args()
    try:
        if args.action == "build-api":
            build_api()
        else:
            rt.require(bool(args.api_tag and args.portal_tag) and
                       re.fullmatch(r"glm-[0-9]{8}t[0-9]{6}z-[a-f0-9]{12}", args.api_tag) and
                       re.fullmatch(r"local-[0-9]{8}t[0-9]{6}z-[a-f0-9]{12}", args.portal_tag), "invalid_release_tags")
            plan_release(args.api_tag, args.portal_tag, args.action == "apply")
        return 0
    except Exception as error:
        # Our RuntimeError messages are fixed guard labels or runtime_rollout's
        # structural command diagnostics, never request/settings/response values.
        reason = str(error) if isinstance(error, RuntimeError) else "Protected diagnostics only"
        print(json.dumps({"blocked": True, "reason": reason}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())