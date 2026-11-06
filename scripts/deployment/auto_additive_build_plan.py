"""Narrow additive Auto build/plan preparation. No apply/config write/model API.

Exclusive stage outputs retain original commands and worker IDs. A consumed
stage must be reconciled, never rerun. Raw state/settings stay owner-only.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import UTC, datetime
import difflib
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import importlib.util
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / ".deployment/auto-additive-buildplan01"
CLEAN = ROOT / ".deployment/auto-additive-clean01"
CONTEXT = HOME / "api"
CA = Path("C:/Users/p4032099/.azure/ca-bundle-zscaler.pem")
CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe", "-X", "utf8", "-IBm", "azure.cli"]
SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
REVIEW = Path("C:/Users/p4032099/AppData/Roaming/Code/User/workspaceStorage/c0077ec5e47287d6bf3fec331f95ec27/GitHub.copilot-chat/chat-session-resources/1fb13269-8028-40f5-82a2-14e156d03d63/call_pkfcs3RP6tIj3H6e0ZBCooHD__vscode-1793365380953/content.txt")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def load(path):
    return json.loads(path.read_bytes())


def write(name, value):
    path = HOME / name
    assert path.resolve().is_relative_to(HOME.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha(raw)


def tree(path):
    return {p.relative_to(path).as_posix(): sha(p.read_bytes()) for p in sorted(path.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def environment():
    assert sha(CA.read_bytes()) == "e747e9880a4e63c73f55af589941139d0a4f90ceec5df745cfd6fee5bbe257dc"
    return {**os.environ, "REQUESTS_CA_BUNDLE": str(CA), "SSL_CERT_FILE": str(CA),
            "AZURE_CORE_COLLECT_TELEMETRY": "false", "PYTHONDONTWRITEBYTECODE": "1"}


def command(label, argv, cwd=ROOT, stdin=None, env=None):
    write("commands/" + label + "-intent.json", {"at": now(), "argv": argv,
        "cwd": str(cwd), "max_invocations": 1, "stdin_sha256": sha(stdin) if stdin else None})
    with (HOME / ("commands/" + label + ".stdout.txt")).open("xb") as out, (HOME / ("commands/" + label + ".stderr.txt")).open("xb") as err:
        child = subprocess.Popen(argv, cwd=cwd, env=env or environment(),
            stdin=subprocess.PIPE if stdin else subprocess.DEVNULL, stdout=out, stderr=err)
        write("commands/" + label + "-worker.json", {"at": now(), "pid": child.pid, "parent": os.getpid()})
        child.communicate(stdin)
    write("commands/" + label + "-result.json", {"at": now(), "exit_code": child.returncode})
    assert child.returncode == 0, "original command failed; reconcile without replay: " + label
    return (HOME / ("commands/" + label + ".stdout.txt")).read_bytes()


def compose():
    assert not HOME.exists(), "exclusive composition already consumed"
    HOME.mkdir()
    write("compose-intent.json", {"at": now(), "pid": os.getpid(), "applies": 0, "model_calls": 0})
    assert sha((CLEAN / "api.tar.gz").read_bytes()) == "e3a4c4ea914a63fbb29dde6960df5f3082ba59bbdb2977e8beec13d4054a32d6"
    original = load(CLEAN / "source-manifest.json")["contexts"]["api"]
    assert tree(CLEAN / "contexts/api") == original
    with tarfile.open(CLEAN / "api.tar.gz") as archive:
        assert {m.name: sha(archive.extractfile(m).read()) for m in archive.getmembers()} == original
    shutil.copytree(CLEAN / "contexts/api", CONTEXT)
    # Preserve the reviewed clean composition, changing ONLY receipt transport.
    source = ROOT / "services/control-plane/src/aiflux"
    old_snapshot = (CONTEXT / "modules/auto_snapshot.py").read_text(encoding="utf-8")
    workspace_snapshot = (source / "auto_snapshot.py").read_text(encoding="utf-8")
    marker = "def publication(settings: Settings, snapshot: dict) -> dict | None:\n"
    assert old_snapshot.count(marker) == workspace_snapshot.count(marker) == 1
    updated = old_snapshot.split(marker)[0] + marker + workspace_snapshot.split(marker)[1]
    old_config = (CONTEXT / "modules/config.py").read_text(encoding="utf-8")
    anchor = "    auto_routing_publication_path: Path | None = None\n"
    assert old_config.count(anchor) == 1
    config = old_config.replace(anchor, anchor + "    auto_routing_publication_json: str | None = None\n")
    for leaf, old, new in (("auto_snapshot.py", old_snapshot, updated), ("config.py", old_config, config)):
        ast.parse(new, feature_version=(3, 11))
        (CONTEXT / "modules" / leaf).write_bytes(new.encode())
        write("delta/" + leaf + ".diff", "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile="reviewed-clean/" + leaf, tofile="inline-transport/" + leaf)).encode())
    expected = load(CONTEXT / "expected-files.json")
    for leaf in ("auto_snapshot.py", "config.py"):
        for prefix in ("/app/services/control-plane/src/aiflux/", "/usr/local/lib/python3.11/site-packages/aiflux/"):
            expected[prefix + leaf] = sha((CONTEXT / "modules" / leaf).read_bytes())
    (CONTEXT / "expected-files.json").write_bytes((json.dumps(expected, indent=2, sort_keys=True) + "\n").encode())
    tests = (ROOT / "scripts/deployment/auto_additive_receipt_checks.py").read_bytes()
    (CONTEXT / "receipt_checks.py").write_bytes(tests)
    docker = (CONTEXT / "Production.Dockerfile").read_bytes()
    docker += (b"COPY receipt_checks.py /tmp/auto-receipt-checks.py\n"
               b"RUN python -c \"import sys; assert sys.version_info[:2] == (3, 11)\" && python /tmp/auto-receipt-checks.py\n")
    (CONTEXT / "Production.Dockerfile").write_bytes(docker)
    current = tree(CONTEXT)
    for key in original:
        if key not in ("modules/auto_snapshot.py", "modules/config.py", "expected-files.json", "Production.Dockerfile"):
            assert current[key] == original[key], key
    assert set(current) == set(original) | {"receipt_checks.py"}
    with tarfile.open(HOME / "api.tar.gz", "x:gz") as archive:
        for name in current:
            archive.add(CONTEXT / name, arcname=name, recursive=False)
    write("source-manifest.json", {"at": now(), "files": current,
        "archive_sha256": sha((HOME / "api.tar.gz").read_bytes()), "original_archive_sha256": sha((CLEAN / "api.tar.gz").read_bytes()),
        "reviewed_clean_files": original, "added_validation_only": ["receipt_checks.py"],
        "customer_rebuild": False, "admin_rebuild": False, "ingestion_rebuild": False,
        "production_receipt_created": False, "runtime_proof": False})
    write("automated-review.json", {"raw_output_sha256": sha(REVIEW.read_bytes()), "raw_output_path": str(REVIEW),
        "kind": "actual automated scoped source review, not human or signed",
        "scope": "original clean context; inline delta tested separately, not misattributed to reviewer",
        "rejected_errors": ["13 explicit routes: actual current inventory is 22", "rollback22 to8 forbidden; restore exact current22"],
        "runtime_proof": False})
    # Local narrow check against the composed modules, not the dirty app.
    effective = HOME / "checks/effective"
    shutil.copytree(CLEAN / "checks/effective", effective, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for leaf in ("auto_snapshot.py", "config.py"):
        (effective / "services/control-plane/src/aiflux" / leaf).write_bytes((CONTEXT / "modules" / leaf).read_bytes())
    env = environment()
    env["PYTHONPATH"] = os.pathsep.join([str(effective / "services/control-plane/src"), str(ROOT / ".venv/Lib/site-packages")])
    command("receipt-delta-local", [sys.executable, "-B", "-X", "utf8", str(CONTEXT / "receipt_checks.py")], env=env)
    write("composition-result.json", {"at": now(), "status": "COMPOSED_FOCUSED_CHECKS_PASS", "files": current})
    print("COMPOSED_FOCUSED_CHECKS_PASS", flush=True)


def build():
    manifest = load(HOME / "source-manifest.json")
    assert tree(CONTEXT) == manifest["files"]
    assert sha((HOME / "api.tar.gz").read_bytes()) == manifest["archive_sha256"]
    tag = "auto-additive-20261031-" + manifest["archive_sha256"][:12]
    write("build-intent.json", {"at": now(), "pid": os.getpid(), "tag": tag, "max_submissions": 1,
        "source_manifest_sha256": sha((HOME / "source-manifest.json").read_bytes()),
        "linux311_validation_integrated": True, "separate_validation_build": False,
        "no_apply_no_config_write_no_model_calls": True})
    account = json.loads(command("build-account", CLI + ["account", "show", "-o", "json", "--only-show-errors"]))
    assert account["id"] == SUB and account["state"] == "Enabled"
    from scripts.deployment import auto_resume_current_adapter as guard
    assert account["tenantId"] == guard.TENANT
    # No local container daemon. ACR uploads ONLY the curated eleven-file folder.
    raw = command("api-build-submit", CLI + ["acr", "build", "--registry", "pocidstokenexacr", "--subscription", SUB,
        "--platform", "linux/amd64", "--timeout", "1800", "--file", "Production.Dockerfile",
        "--image", "aiflux-api:" + tag, "--no-wait", "--only-show-errors", "-o", "json", "."], cwd=CONTEXT)
    run = json.loads(raw)
    run_id = run["runId"]
    assert isinstance(run_id, str) and run_id.isalnum()
    write("original-build.json", {"at": now(), "run_id": run_id, "tag": tag, "submission": run,
        "source_manifest_sha256": sha((HOME / "source-manifest.json").read_bytes())})
    finish_build()


def reconcile_build():
    # Installed CLI --no-wait legitimately emits no JSON. Submission succeeded;
    # retain failure and bind the actual unique original run, NEVER resubmit.
    assert load(HOME / "commands/api-build-submit-result.json")["exit_code"] == 0
    assert not (HOME / "commands/api-build-submit.stdout.txt").read_bytes()
    rows = json.loads(command("original-build-lookup", CLI + ["acr", "task", "list-runs", "--registry", "pocidstokenexacr",
        "--subscription", SUB, "--top", "5", "--only-show-errors", "-o", "json"]))
    intent = load(HOME / "build-intent.json")
    matches = [r for r in rows if r["runId"] == "cm4g" and r["createTime"] >= intent["at"]]
    assert len(matches) == 1 and rows[0]["runId"] == "cm4g"
    write("original-build.json", {"at": now(), "run_id": "cm4g", "tag": intent["tag"], "submission": matches[0],
        "source_manifest_sha256": intent["source_manifest_sha256"], "empty_no_wait_output_reconciled_not_resubmitted": True})
    finish_build()


def finish_build():
    original = load(HOME / "original-build.json")
    run_id, tag = original["run_id"], original["tag"]
    manifest = load(HOME / "source-manifest.json")
    print("ORIGINAL_ACR_BUILD_ID=" + run_id, flush=True)
    # Log streaming waits for this SAME original build; never a second submit.
    command("api-build-logs", CLI + ["acr", "task", "logs", "--registry", "pocidstokenexacr", "--subscription", SUB,
        "--run-id", run_id])
    result = json.loads(command("api-build-readback", CLI + ["acr", "task", "show-run", "--registry", "pocidstokenexacr",
        "--subscription", SUB, "--run-id", run_id, "-o", "json", "--only-show-errors"]))
    assert result["status"] == "Succeeded" and len(result["outputImages"]) == 1
    output = result["outputImages"][0]
    assert output["registry"] == "pocidstokenexacr.azurecr.io" and output["repository"] == "aiflux-api" and output["tag"] == tag
    digest = output["digest"]
    meta = json.loads(command("api-manifest-readback", CLI + ["acr", "manifest", "show-metadata", "--registry", "pocidstokenexacr",
        "--subscription", SUB, "--name", "aiflux-api:" + tag, "-o", "json", "--only-show-errors"]))
    assert meta["digest"] == digest and tree(CONTEXT) == manifest["files"]
    logs = (HOME / "commands/api-build-logs.stdout.txt").read_bytes()
    assert b"AUTO_CLEAN_DUAL_PATH_ALL22_HASHES_AND_IMPORTS_PASS" in logs and b"Ran 10 tests" in logs and b"OK" in logs
    write("api-build-result.json", {"at": now(), "run_id": run_id, "status": result["status"], "digest": digest,
        "image": "pocidstokenexacr.azurecr.io/aiflux-api@" + digest, "tag": tag,
        "logs_sha256": sha(logs), "source_manifest_sha256": sha((HOME / "source-manifest.json").read_bytes()),
        "context_archive_sha256": manifest["archive_sha256"], "linux_python": "3.11", "focused_tests": 10,
        "all22_hashes_and_imports": True, "runtime_acceptance": False, "applies": 0, "model_calls": 0})
    print(json.dumps(load(HOME / "api-build-result.json")), flush=True)


def fresh_guard(label):
    """New full read, using existing projection functions, not old entrypoints."""
    target = HOME / label
    target.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location("additive_read_definitions", ROOT / ".deployment/auto-additive-live01/baseline.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    b.HOME, b.PRIVATE, b.START = target, target / "protected-rollback", time.monotonic()
    b.command = b.g.rebound(b.lib.command, write=b.write, HOME=target)
    b.credential = b.g.rebound(b.lib.credential, command=b.command, write=b.write)
    b.head = b.g.rebound(b.lib.head, write=b.write)
    b.Reader.request = b.g.rebound(b.lib.Reads.request, write=b.write)
    b.Reader.collection = b.g.rebound(b.lib.Reads.collection, write=b.write, HOME=target)
    b.Reader.cli = b.g.rebound(b.lib.Reads.cli, command=b.command, write=b.write)
    b._private_directory(b.PRIVATE)
    b.workers("before")
    token, claims = b.credential(b.a.ARM, "arm-auth")
    storage, storage_claims = b.credential(b.a.STORAGE, "storage-auth")
    reader = b.Reader(token, claims)
    try:
        opening = b.head(reader, storage, storage_claims, "opening")
        with reader.opener.open(Request(b.lib.BLOB, headers={"Authorization": "Bearer " + storage,
                "x-ms-version": "2023-11-03", "If-Match": opening["etag"]}), timeout=90) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
            assert response.status == 200 and response.geturl() == b.lib.BLOB and response.headers.get("ETag") == opening["etag"]
        state = json.loads(raw)
        assert state["serial"] == 130 and b.a.state_equal(load(b.lib.LATEST / "commands/state-after.stdout.txt"), state)
        b.write("protected-rollback/root.tfstate", raw)
        snapshot, policy, backends = b.g.rebound(b.collector.capture, ReadOnly=lambda _: reader, write=b.write)("fresh")
        prior = load(ROOT / ".deployment/auto-additive-live01/fresh-snapshot.json")
        assert not b.differences(prior, snapshot), "full protected drift"
        assert policy.encode() == (ROOT / ".deployment/auto-additive-live01/fresh-policy.xml").read_bytes()
        assert {r["name"]: b.g.digest(r) for r in backends["value"]} == load(ROOT / ".deployment/auto-additive-live01/fresh-backend-hashes.json")
        settings = b.g.continuation_settings(reader)
        b.write("protected-rollback/full-four-settings.json", settings)
        assert settings == load(ROOT / ".deployment/auto-additive-live01/protected-rollback/full-four-settings.json")
        assert "AIFLUX_AUTO_ROUTING_PUBLICATION_JSON" not in settings["api"]
        child = (ROOT / "infra/project-route/terraform.tfstate").read_bytes()
        assert child == (ROOT / ".deployment/auto-additive-live01/remaining01/protected-rollback/local-child.tfstate").read_bytes()
        b.write("protected-rollback/child.tfstate", child)
        base = b.a.ARM.rstrip("/") + b.lib.APIM
        revisions = reader.collection(base + "/apis/aiflux-dev-unified/revisions?api-version=2024-05-01")
        assert sorted((r["apiRevision"], r["isCurrent"], r["isOnline"]) for r in revisions["value"]) == [("1", True, True), ("2", False, False)]
        scopes = [("", "global"), ("/apis/aiflux-dev-unified", "active")]
        scopes += [("/apis/aiflux-dev-unified;rev=" + r["apiRevision"], "revision-" + r["apiRevision"]) for r in revisions["value"]]
        formats = []
        for suffix, scope in scopes:
            for format_ in ("xml", "rawxml"):
                url = base + suffix + "/policies/policy?format=" + format_ + "&api-version=2024-05-01"
                value = reader.get(url, optional=True)
                assert not value.get("absent")
                raw_policy = value["properties"]["value"].encode()
                b.write("protected-rollback/" + scope + "-" + format_ + ".xml", raw_policy)
                expected = ROOT / (".deployment/auto-additive-live01/remaining01/protected-rollback/" + scope + "-" + format_ + ".xml")
                assert raw_policy == expected.read_bytes(), "actual policy drift " + scope + format_
                formats.append({"scope": scope, "format": format_, "sha256": sha(raw_policy), "etag": reader.records[url]["etag"]})
        closing = b.head(reader, storage, storage_claims, "closing")
        assert opening["etag"] == closing["etag"]
        b.workers("after")
        result = {"at": now(), "status": "FRESH_FULL_PROTECTED_MATCH", "root_serial": 130, "child_serial": 191,
            "all22": sorted(b.g.advertised(b.g.xml_node(policy, exported=True))), "four_settings_equal": True,
            "policy_formats": formats, "backend": closing, "cloud_writes": 0, "model_calls": 0}
        assert len(result["all22"]) == 22
        b.write("REPORT.json", result)
        print(label + " FRESH_FULL_PROTECTED_MATCH", flush=True)
        return result
    finally:
        b.write("wire-manifest.json", {"at": now(), "responses": reader.wires, "tokens_persisted": False})


def prepare_gateway():
    target = HOME / "gateway-context"
    assert not target.exists()
    original = ROOT / ".deployment/restore22-successor-20261031/context"
    shutil.copytree(original, target, ignore=shutil.ignore_patterns(".terraform", "__pycache__"))
    module = target / "infra/project-route"
    # Actual all22 base plus only reviewed additive Auto hunks. Do not copy the
    # dirty Fireworks/POC fragments or dirty common template.
    for leaf in ("main.tf", "foundry-eight.tf", "foundry-successor22.tf", "auto-routing.tf"):
        (module / leaf).write_bytes((ROOT / "infra/project-route" / leaf).read_bytes())
    for name in ("auto-resolve.xml.tftpl", "auto-metadata.xml", "auto-error.xml"):
        (target / "gateway/policies" / name).write_bytes((ROOT / "gateway/policies" / name).read_bytes())
    frozen = ROOT / ".deployment/sgt-f05/api/gateway/catalog/acceptance-evidence/gateway/catalog/foundry-inventory-20261026.json"
    (target / "gateway/catalog/foundry-inventory-20261026.json").write_bytes(frozen.read_bytes())
    for leaf in ("auto-routing-defaults.json", "rates-20261027.json"):
        path = target / "services/control-plane/src/aiflux/pricing" / leaf
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / "services/control-plane/src/aiflux/pricing" / leaf).read_bytes())
    inputs = load(ROOT / ".deployment/restore22-successor-20261031/inputs.tfvars.json")
    inputs["route_manifest_path"] = (target / "gateway/catalog/foundry-successor22-candidate-routes.json").as_posix()
    inputs["auto_routing_enabled"] = False
    write("gateway-off.tfvars.json", inputs)
    env = environment()
    env.update(TF_CLI_CONFIG_FILE=str(ROOT / ".deployment/terraform.rc"),
               TF_DATA_DIR=str(original / "infra/project-route/.terraform"), CHECKPOINT_DISABLE="1")
    def tf(label, args, stdin=None):
        assert args[0] in ("console", "validate", "fmt", "plan", "show")
        return command(label, ["C:/Program Files/Terraform/terraform.exe", "-chdir=" + str(module), *args], stdin=stdin, env=env)
    tf("gateway-validate", ["validate", "-json"])
    expression = b'jsonencode({old=local.policy,pre=local.glm_policy,candidate=local.auto_with_error,version=local.auto_version,aliases=local.all_aliases})\n'
    raw = tf("gateway-off-render", ["console", "-no-color", "-var-file=" + str(HOME / "gateway-off.tfvars.json")], expression)
    rendered = json.loads(json.loads(raw.decode().strip()))
    from scripts.deployment import auto_resume_current_adapter as a
    current = (ROOT / ".deployment/auto-additive-live01/fresh-policy.xml").read_bytes().decode()
    assert a.xml_tree(current, True) == a.xml_tree(rendered["old"], False), "off policy must preserve actual22"
    assert len(set(rendered["aliases"])) == 22
    write("gateway-render-boundaries.json", {k: sha(rendered[k].encode()) for k in ("old", "pre", "candidate")})
    # Actual rollback package is byte-bound current22 policy/settings/state; no
    # fictitious future-state Terraform rollback binary can safely be applied.
    rollback = {"policy_sha256": sha(current.encode()), "root_serial": 130, "child_serial": 191,
        "baseline_report_sha256": sha((ROOT / ".deployment/auto-additive-live01/REPORT.json").read_bytes()),
        "restore": "fresh exact current22 policy + complete prior settings + API cm45 pin; never historical8",
        "publication": "remove newly added inline receipt and flags; preserve absent-vs-empty", "runtime_proof": False}
    write("rollback-contract.json", rollback)
    inputs["auto_routing_enabled"] = True
    inputs["auto_routing_direct_release"] = {"mode": "bounded-production-direct-v1", "defaults_sha256": rendered["version"],
        "predecessor_sha256": sha(rendered["pre"].encode()), "candidate_sha256": sha(rendered["candidate"].encode()),
        "independent_review_sha256": load(HOME / "automated-review.json")["raw_output_sha256"],
        "rollback_sha256": sha((HOME / "rollback-contract.json").read_bytes()),
        "max_auto_attempts": 2, "max_scoring_calls": 2, "max_completion_calls": 2,
        "retries": 0, "fallback": False, "runtime_validation_pending": True, "stop_on_explicit_regression": True}
    write("gateway-on.tfvars.json", inputs)
    raw = tf("gateway-on-render", ["console", "-no-color", "-var-file=" + str(HOME / "gateway-on.tfvars.json")],
        b'jsonencode({final=local.policy,native=local.native_manifest_valid,gate=local.auto_direct_release_valid,aliases=local.all_aliases})\n')
    final = json.loads(json.loads(raw.decode().strip()))
    assert final["native"] is True and final["gate"] is True and set(final["aliases"]) == set(rendered["aliases"])
    write("gateway-final-native-policy.xml", final["final"].encode())
    write("gateway-source.json", {"files": tree(target), "final_native_policy_sha256": sha(final["final"].encode()),
        "pre_wrapper_candidate_sha256": sha(rendered["candidate"].encode()), "off_actual22_semantic_equal": True,
        "review_kind": "automated scoped original-source review; exact saved-plan review still pending", "runtime_proof": False})
    print("GATEWAY_PREPARED_EXACT22_NATIVE_POLICY", flush=True)


def finish_gateway_render():
    # Original object was wholly unknown because native_manifest_valid contains
    # live data-source readiness. Render ONLY source-known policy and contract;
    # real readiness remains a plan/data-source check, never assert it here.
    assert (HOME / "commands/gateway-on-render.stdout.txt").read_bytes().strip() == b"(known after apply)"
    original = ROOT / ".deployment/restore22-successor-20261031/context/infra/project-route/.terraform"
    env = environment()
    env.update(TF_CLI_CONFIG_FILE=str(ROOT / ".deployment/terraform.rc"), TF_DATA_DIR=str(original), CHECKPOINT_DISABLE="1")
    raw = command("gateway-source-known-render", ["C:/Program Files/Terraform/terraform.exe",
        "-chdir=" + str(HOME / "gateway-context/infra/project-route"), "console", "-no-color",
        "-var-file=" + str(HOME / "gateway-on.tfvars.json")],
        stdin=b'jsonencode({final=local.policy,gate=local.auto_direct_release_valid,aliases=local.all_aliases})\n', env=env)
    final = json.loads(json.loads(raw.decode().strip()))
    assert final["gate"] is True and len(set(final["aliases"])) == 22
    write("gateway-final-native-policy.xml", final["final"].encode())
    write("gateway-source.json", {"files": tree(HOME / "gateway-context"), "final_native_policy_sha256": sha(final["final"].encode()),
        "pre_wrapper_candidate_sha256": load(HOME / "gateway-render-boundaries.json")["candidate"],
        "off_actual22_semantic_equal": True, "native_deployment_readiness": "pending actual plan data-source checks",
        "runtime_proof": False})
    print("GATEWAY_SOURCE_KNOWN_RENDER_PASS", flush=True)


def plan():
    assert load(HOME / "api-build-result.json")["status"] == "Succeeded"
    write("plan-stage-intent.json", {"at": now(), "pid": os.getpid(), "applies": 0,
        "gateway_plans": 1, "api_plans": 1, "publication_receipt": "must follow actual deployed gateway readback"})
    from scripts.deployment.auto_publication_artifact import _private_directory
    _private_directory(HOME / "private")
    user = command("local-owner", ["whoami", "/user", "/fo", "csv", "/nh"]).decode()
    sid = re.search(r"S-1-5-[0-9-]+", user).group(0)
    command("protect-local-plan-evidence", ["icacls", str(HOME), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F"])
    api_root = HOME / "api-plan-context/infra/terraform"
    previous = ROOT / ".deployment/uv-final02"
    # Exact current applied module, not workspace scaffolding.
    shutil.copytree(previous / "infra", HOME / "api-plan-context/infra", ignore=shutil.ignore_patterns(".terraform"))
    for folder in ("gateway",):
        shutil.copytree(previous / folder, HOME / "api-plan-context" / folder)
    variables = load(previous / "inputs.tfvars.json")
    variables["apps"]["api"]["image"] = load(HOME / "api-build-result.json")["image"].split("/", 1)[1]
    # Image install stays default-off. A ready inline receipt cannot truthfully
    # be planned before gateway apply/readback. No placeholder hashes allowed.
    write("api-install.tfvars.json", variables)
    env = environment()
    env.update(TF_CLI_CONFIG_FILE=str(ROOT / ".deployment/terraform.rc"), CHECKPOINT_DISABLE="1",
        TF_DATA_DIR=load(previous / "initialization-reuse.json")["TF_DATA_DIR"])
    command("api-validate", ["C:/Program Files/Terraform/terraform.exe", "-chdir=" + str(api_root), "validate", "-json"], env=env)
    # Fresh whole state/settings/policies/security immediately before sole plans.
    guard = fresh_guard("preplan")
    source = load(HOME / "gateway-source.json")
    assert tree(HOME / "gateway-context") == source["files"]
    gateway_root = HOME / "gateway-context/infra/project-route"
    genv = environment()
    genv.update(TF_CLI_CONFIG_FILE=str(ROOT / ".deployment/terraform.rc"), CHECKPOINT_DISABLE="1",
        TF_DATA_DIR=str(ROOT / ".deployment/restore22-successor-20261031/context/infra/project-route/.terraform"))
    tf = "C:/Program Files/Terraform/terraform.exe"
    # Local state owner is explicit. No backend/init/state migration.
    command("gateway-plan-once", [tf, "-chdir=" + str(gateway_root), "plan", "-input=false", "-no-color",
        "-parallelism=1", "-lock-timeout=60s", "-state=" + str(ROOT / "infra/project-route/terraform.tfstate"),
        "-var-file=" + str(HOME / "gateway-on.tfvars.json"), "-target=azapi_resource.project_policy[0]",
        "-out=" + str(HOME / "gateway.tfplan")], env=genv)
    gateway = json.loads(command("gateway-plan-show", [tf, "-chdir=" + str(gateway_root), "show", "-json", str(HOME / "gateway.tfplan")], env=genv))
    changes = [r for r in gateway["resource_changes"] if r["mode"] == "managed" and r["change"]["actions"] != ["no-op"]]
    assert gateway["applyable"] and not gateway.get("errored") and not gateway.get("deferred_changes")
    assert len(changes) == 1 and changes[0]["address"] == "azapi_resource.project_policy[0]" and changes[0]["change"]["actions"] == ["update"]
    change = changes[0]["change"]
    before, after = deepcopy(change["before"]), deepcopy(change["after"])
    def body(value):
        return json.loads(value["body"]) if isinstance(value["body"], str) else value["body"]
    expected = (HOME / "gateway-final-native-policy.xml").read_bytes().decode()
    assert body(after)["properties"] == {"format": "rawxml", "value": expected}
    from scripts.deployment import auto_resume_current_adapter as a
    assert a.xml_tree(body(before)["properties"]["value"], body(before)["properties"]["format"] == "xml") == a.xml_tree((ROOT / ".deployment/auto-additive-live01/fresh-policy.xml").read_bytes().decode(), True)
    for key in ("body", "output"):
        before.pop(key, None); after.pop(key, None)
    assert before == after, "unrelated policy attribute change"
    write("gateway-plan-review.json", {"at": now(), "binary_sha256": sha((HOME / "gateway.tfplan").read_bytes()),
        "json_sha256": sha((HOME / "commands/gateway-plan-show.stdout.txt").read_bytes()), "updates": 1,
        "only_policy_value_and_format": True, "final_native_policy_sha256": sha(expected.encode()),
        "checks": gateway.get("checks"), "exact_plan_independent_review": "pending", "runtime_proof": False})
    # Preserve exact settings; image-only target cannot advertise Auto early.
    fresh_guard("pre-api-plan")
    command("api-plan-once", [tf, "-chdir=" + str(api_root), "plan", "-input=false", "-no-color", "-parallelism=1",
        "-lock-timeout=60s", "-var-file=" + str(HOME / "api-install.tfvars.json"),
        '-target=azurerm_linux_web_app.main["api"]',
        "-out=" + str(HOME / "api-install.tfplan")], env=env)
    api = json.loads(command("api-plan-show", [tf, "-chdir=" + str(api_root), "show", "-json", str(HOME / "api-install.tfplan")], env=env))
    changes = [r for r in api["resource_changes"] if r["mode"] == "managed" and r["change"]["actions"] != ["no-op"]]
    assert api["applyable"] and not api.get("errored") and not api.get("deferred_changes")
    assert len(changes) == 1 and changes[0]["address"] == 'azurerm_linux_web_app.main["api"]' and changes[0]["change"]["actions"] == ["update"]
    before, after = deepcopy(changes[0]["change"]["before"]), deepcopy(changes[0]["change"]["after"])
    old_stack, new_stack = before["site_config"][0]["application_stack"][0], after["site_config"][0]["application_stack"][0]
    assert new_stack["docker_image_name"] == variables["apps"]["api"]["image"]
    new_stack["docker_image_name"] = old_stack["docker_image_name"]
    # AzureRM computed read-only mirror is expected to become unknown.
    unknown = changes[0]["change"].get("after_unknown", {})
    for key in ("custom_domain_verification_id", "default_hostname", "hosting_environment_id", "id", "kind",
                "outbound_ip_address_list", "outbound_ip_addresses", "possible_outbound_ip_address_list", "possible_outbound_ip_addresses",
                "site_credential", "usage", "zip_deploy_file"):
        if unknown.get(key):
            after[key] = before.get(key)
    if unknown.get("site_config"):
        for key in ("linux_fx_version",):
            after["site_config"][0][key] = before["site_config"][0].get(key)
    assert before == after, "API non-image drift"
    write("api-plan-review.json", {"at": now(), "binary_sha256": sha((HOME / "api-install.tfplan").read_bytes()),
        "json_sha256": sha((HOME / "commands/api-plan-show.stdout.txt").read_bytes()), "updates": 1,
        "only_api_image": True, "all_settings_preserved": True, "auto_advertisement": False, "checks": api.get("checks")})
    fresh_guard("postplan")
    write("PLAN-REPORT.json", {"at": now(), "status": "SAVED_FORWARD_PLANS_PENDING_EXACT_REVIEW_AND_OFFICIAL_VALIDATION",
        "build": load(HOME / "api-build-result.json"), "gateway": load(HOME / "gateway-plan-review.json"),
        "api": load(HOME / "api-plan-review.json"), "applies": 0, "model_calls": 0,
        "activation_settings_plan": "requires actual deployed gateway readback, not fabricated now",
        "rollback_saved_plan": "cannot safely bind future state before forward apply; exact baseline payload retained",
        "runtime_proof": False})
    print("SAVED_FORWARD_PLANS_NO_APPLY", flush=True)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    assert len(sys.argv) == 2 and sys.argv[1] in ("compose", "build", "reconcile-build", "gateway-prepare", "gateway-render-remaining", "plan")
    try:
        {"compose": compose, "build": build, "reconcile-build": reconcile_build,
         "gateway-prepare": prepare_gateway, "gateway-render-remaining": finish_gateway_render, "plan": plan}[sys.argv[1]]()
    except Exception as exc:
        write(sys.argv[1] + "-STOP.json", {"at": now(), "exception": type(exc).__name__,
            "reason": str(exc) if isinstance(exc, AssertionError) else "inspect original private logs; no replay",
            "applies": 0, "model_calls": 0})
        raise