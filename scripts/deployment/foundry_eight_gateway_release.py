"""Eight existing models: exclusive READ-ONLY prepare and exact saved APIM plan.

No apply/build/inference entrypoint. Existing consumed controllers and receipts
are references only. Sensitive policy/plan artifacts stay in an ACL-private new
directory; settings are never serialized, only whole-map hashes are retained.
The saved plan uses the existing LOCAL project-route state, never a new owner.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import UTC, datetime
import difflib
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import time
from types import FunctionType, SimpleNamespace
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, build_opener, HTTPSHandler, HTTPRedirectHandler
import xml.etree.ElementTree as ET
import zipfile

from scripts.deployment import ratecard_release as rate
from scripts.deployment import runtime_rollout as rt

HOME = rt.HOME / "foundry-eight-gateway-release-20261030"
CONTEXT = HOME / "context"
TFROOT = CONTEXT / "infra/project-route"
OWNER = rt.ROOT / "infra/project-route/terraform.tfstate"
PLAN = HOME / "gateway.tfplan"
OFFLINE = rt.HOME / "foundry-eight-gateway-offline-20261030T161005952049Z"
ARCHIVE = rt.HOME / "poc-fragment-bootstrap-20261028/fragment.tfplan"
RETAINED = rt.HOME / "ratecard-release-20261030"
POLICY = "azapi_resource.project_policy[0]"
BACKENDS = {
    'azapi_resource.foundry_eight_backend["anthropic"]': (
        "aiflux-project-foundry-eight-anthropic",
        "https://poc-ids-token-ex-foundry.services.ai.azure.com/anthropic/v1"),
    'azapi_resource.foundry_eight_backend["mistral"]': (
        "aiflux-project-foundry-eight-mistral",
        "https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1"),
}
TARGETS = [*BACKENDS, POLICY]
NEW = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-fast",
       "claude-haiku-5-5", "gpt-6.1-terra", "gpt-6-luna", "claude-opus-4-8", "Mistral-Large-3"}
PINS = {
    "api": "6f973e6ec8651c54beef1c0fe13d8c0c60d688ad15f66f4df735b48baafd7343",
    "admin": "5541f5e708842eb745900d2a5eb8e3868f5231943514f25eae50418cf8aae33a",
    "customer": "77a6067221a5d8c4f5e5bb62e821f20193c7354e43e2cf46c38a355bea280d1e",
    "ingestion": "fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90",
}
require = rt.require
COMMANDS: list[dict] = []
OUTPUT = HOME
ORIGINAL_CONTROLLER = "b92610b5a39c1cddf1d8d13cce317ec3fde39875b5fc03489327d54601e4fcb6"
ORIGINAL_PREPARED = "aaac2239a08d45b29ff01f3160817a0d334c45307809757190110ace9ca5c4e6"


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def exclusive(name, value):
    path = OUTPUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest(raw)


def hashes(paths):
    return {p.relative_to(rt.ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(set(paths))}


def inputs_bound():
    proof = load(OFFLINE / "result.json")
    require(proof["passed"] and proof["tests"] == 6 and proof["failures"] == proof["errors"] == proof["skips"] == 0,
            "actual_green_offline_gateway_required")
    require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in proof["owned_source_sha256"].items()),
            "offline_source_bytes_changed")
    require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in proof["protected_after"].items()),
            "offline_protected_sources_changed")
    prior = load(rt.ROOT / "gateway/catalog/fireworks-candidate-routes.json")
    candidate = load(rt.ROOT / "gateway/catalog/foundry-eight-candidate-routes.json")
    require(set(candidate["routes"]) - set(prior["routes"]) == NEW and len(prior["routes"]) == 12,
            "exact_eight_only_candidate_manifest")
    old = deepcopy(candidate)
    for alias in NEW:
        old["routes"].pop(alias)
    require(old == prior, "old_twelve_manifest_must_remain_exact")
    paths = [rt.ROOT / p for p in proof["owned_source_sha256"]]
    paths += [rt.ROOT / p for p in proof["protected_after"]]
    paths += [Path(__file__), ARCHIVE, OFFLINE / "result.json", OFFLINE / "rendered-explicit_manifest_is_exact_twenty_plus_external.xml",
              RETAINED / "verified.json", RETAINED / "review.json", RETAINED / "applied.json",
              rt.HOME / "poc-fragment-bootstrap-20261028/inputs.tfvars.json", rt.HOME / "terraform.rc"]
    paths += list((rt.ROOT / "scripts/deployment").glob("*.py"))
    paths += list((RETAINED / "gateway/policies").glob("*.xml*"))
    paths += [rt.HOME / "foundry-eight-20261030/deployments.json"]
    paths += [rt.HOME / "storage-firewall-167-103-67-80-20261030" / name
              for name in ("independent-after.json", "before.json", "result.json")]
    return hashes(paths)


def state_identity():
    state = load(OWNER)
    require(state["lineage"] == "8b19b704-7224-db80-7600-ef2a0cbeef10" and state["serial"] == 185,
            "existing_childscope_state_identity_changed")
    return {"path": OWNER.as_posix(), "sha256": digest(OWNER.read_bytes()), "lineage": state["lineage"],
            "serial": state["serial"], "managed_instances": sum(len(v["instances"]) for v in state["resources"] if v["mode"] == "managed")}


def worker_gate():
    command = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform' "
               "-and $_.CommandLine -match 'scripts.deployment|terraform.exe' } | "
               "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    require(result.returncode == 0, "worker_snapshot_failed")
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    rows = rows if isinstance(rows, list) else [rows]
    # CLI wrapper and this controller may coexist; no other release worker.
    others = [v for v in rows if v["ProcessId"] not in (os.getpid(), os.getppid())]
    require(not others, "concurrent_worker_reconcile_no_replay")
    return {"at": now(), "pid": os.getpid(), "competing_workers": 0}


def account():
    require(Path(rt.CA).is_file() and Path(rt.TF).is_file(), "installed_tools_and_strict_ca_required")
    os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA,
                      TF_CLI_CONFIG_FILE=str(rt.HOME / "terraform.rc"))
    a = rt.cli(["account", "show"])
    require(a["id"] == rt.SUB and a["tenantId"] == rt.TENANT and a["state"] == "Enabled"
            and a["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")


def xml_node(raw, exported=False):
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', raw, flags=re.S)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(r'''(\s[\w:-]+=)("[^"]*"|'[^']*')''',
                             lambda m: m[1] + m[2].replace("\n", "&#xA;").replace("\t", "&#x9;"), parts[index])
    node = ET.fromstring("".join(parts))
    if exported:
        for n in node.iter():
            for key, value in n.attrib.items():
                if value.startswith("@"):
                    n.attrib[key] = html.unescape(value)
            if n.text and n.text.startswith("@"):
                n.text = html.unescape(n.text)
    return node


def structural(node):
    return [node.tag, dict(sorted(node.attrib.items())), node.text if (node.text or "").strip() else "",
            [structural(n) for n in node]]


def advertised(node):
    rows = [json.loads(n.text)["data"] for n in node.findall("./inbound//set-body")
            if (n.text or "").startswith('{"data":')]
    require(len(rows) == 1, "single_models_catalog")
    return {v["id"] for v in rows[0]}


def policy_guard(previous, desired):
    before, after = xml_node(previous, exported=True), xml_node(desired)
    prior = set(load(rt.ROOT / "gateway/catalog/fireworks-candidate-routes.json")["routes"]) | {"glm-5.3"}
    require(advertised(before) == prior and advertised(after) == prior | NEW, "exact_old13_plus8_policy")
    for tag in ("cors", "quota-by-key", "rate-limit-by-key", "llm-token-limit", "llm-content-safety", "send-request", "forward-request", "include-fragment"):
        require([structural(n) for n in before.findall(".//" + tag)] ==
                [structural(n) for n in after.findall(".//" + tag)], "protected_policy_nodes_changed:" + tag)
    for alias in prior - {"glm-5.3"}:
        condition = '@((string)context.Variables["aiflux-model"] == "' + alias + '")'
        old = [structural(n) for n in before.findall("./inbound//when") if n.get("condition") == condition]
        new = [structural(n) for n in after.findall("./inbound//when") if n.get("condition") == condition]
        require(old and old == new, "old_dispatch_changed:" + alias)
    require(len(after.findall(".//forward-request")) == 1 and not after.findall(".//retry")
            and not after.findall(".//include-fragment") and len(after.findall(".//llm-content-safety")) == 3,
            "no_retry_detached_fragment_safety")
    # Auth header literals/references already deployed MUST not change.
    def credentials(node):
        return [structural(n) for n in node.findall(".//set-header")
                if n.get("name", "").lower() in ("authorization", "api-key", "x-api-key") and n.get("exists-action") != "delete"]
    require(credentials(before) == credentials(after), "existing_credential_binding_changed")
    return {"old13_preserved": True, "new8_only": True, "safety_passes": 3, "forwards": 1,
            "retries": 0, "fragment_attached": False, "counter_nodes_and_cors_exact": True}


def terraform(stage, *args, text=None):
    require(args and args[0] in ("fmt", "validate", "console", "plan", "show", "version", "workspace"),
            "no_mutating_terraform_command")
    require(args[0] != "workspace" or args[1:] == ("show",), "workspace_read_only")
    env = {k: v for k, v in rt.ENV.items() if not k.startswith(("TF_CLI_ARGS", "TF_LOG", "ARM_")) and k != "TF_DATA_DIR"}
    env.update(TF_IN_AUTOMATION="1", CHECKPOINT_DISABLE="1")
    argv = [rt.TF, "-chdir=" + str(TFROOT), *args]
    exclusive("commands/" + stage + "-intent.json", {"at": now(), "pid": os.getpid(), "argv": argv})
    p = subprocess.run(argv, input=text, capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=900)
    exclusive("commands/" + stage + ".stdout.txt", p.stdout.encode())
    exclusive("commands/" + stage + ".stderr.txt", p.stderr.encode())
    record = {"at": now(), "argv": argv, "exit_code": p.returncode,
              "stdout_sha256": digest(p.stdout.encode()), "stderr_sha256": digest(p.stderr.encode())}
    exclusive("commands/" + stage + "-result.json", record)
    COMMANDS.append(record)
    require(p.returncode == 0, "terraform_failed:" + stage)
    return p.stdout


class Reader:
    """Strict ARM GET only; fresh list appsettings POST is ONLY in legacy snapshot."""
    def __init__(self):
        token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                        "--resource", "https://management.azure.com/"])["accessToken"]
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        require(claims["tid"] == rt.TENANT and claims["oid"] == rt.OPERATOR
                and claims["exp"] > datetime.now(UTC).timestamp() + 600, "arm_token_identity_expiry")
        self.token, self.count = token, 0
        self.tls = ssl.create_default_context(cafile=rt.CA)
        require(self.tls.check_hostname and self.tls.verify_mode == ssl.CERT_REQUIRED, "strict_tls")

    def get(self, url, optional=False):
        require(url.startswith("https://management.azure.com" + rt.RG + "/providers/")
                and not re.search(r"listSecrets|listKeys|regenerate|/secrets/", url, re.I), "read_scope")
        self.count += 1
        name = f"reads/{self.count:03d}"
        exclusive(name + "-intent.json", {"at": now(), "method": "GET", "url": url})
        try:
            req = Request(url, headers={"Authorization": "Bearer " + self.token}, method="GET")
            with urlopen(req, context=self.tls, timeout=90) as res:
                require(res.status == 200 and res.geturl() == url, "unexpected_http_or_redirect")
                raw = res.read(16 * 1024 * 1024 + 1)
                require(len(raw) <= 16 * 1024 * 1024, "bounded_read")
                value = json.loads(raw)
                exclusive(name + "-result.json", {"at": now(), "status": res.status, "body_sha256": digest(raw),
                          "request_id": res.headers.get("x-ms-request-id")})
                return value
        except HTTPError as exc:
            exclusive(name + "-result.json", {"at": now(), "status": exc.code,
                      "request_id": exc.headers.get("x-ms-request-id")})
            if optional and exc.code == 404:
                return {"absent": True, "status": 404}
            raise RuntimeError("readonly_arm_http:" + str(exc.code)) from None

    def collection(self, url):
        result = self.get(url)
        seen = {url}
        rows = list(result["value"])
        link = result.get("nextLink")
        while link:
            require(link not in seen and len(seen) < 30, "pagination_loop_or_limit")
            seen.add(link)
            page = self.get(link)
            rows.extend(page["value"])
            link = page.get("nextLink")
        result = {k: v for k, v in result.items() if k != "nextLink"}
        result["value"] = rows
        if "count" in result:
            result["count"] = len(rows)
        return result


def live_snapshot(label, reader=None):
    exclusive(label + "-snapshot-intent.json", {"at": now(), "pid": os.getpid(),
              "settings_semantic_read_POST_authorized": True, "firewall_writes": 0})
    baseline = rate.snapshot() if reader is None else continuation_snapshot(reader)
    settings = rate.r.fs.current_settings() if reader is None else continuation_settings(reader)
    require({k: rate.r.fs.sha(v) for k, v in settings.items()} == baseline["settings_hashes"], "four_settings_race")
    require(set(settings) == set(PINS) and all(settings[k] for k in PINS), "real_four_settings_not_empty")
    flags = {k: settings["api"].get(k) for k in ("AIFLUX_GATEWAY_CONTROLS_POC_ENABLED",
             "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED", "AIFLUX_GATEWAY_SETTINGS_SCOPES")}
    require(flags == rate.r.FLAGS, "runtime_poc_true_v2_false_scopes_preserved")
    del settings
    for kind, pin in PINS.items():
        require(baseline["runtime"]["sites"][kind]["image"] ==
                "DOCKER|pocidstokenexacr.azurecr.io/aiflux-" + kind + "@sha256:" + pin, "four_current_pins:" + kind)
    require(baseline == load(RETAINED / "verified.json")["baseline"], "completed_ratecard_baseline_drift")
    reader = reader or Reader()
    apim = "https://management.azure.com" + rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
    def url(suffix):
        return apim + suffix + ("&" if "?" in suffix else "?") + "api-version=2024-05-01"
    protected = {}
    counts = {}
    for key, suffix in (("backends", "/backends"), ("subscriptions", "/subscriptions"), ("products", "/products"),
                        ("operations", "/apis/aiflux-dev-unified/operations"), ("bindings", "/apis/aiflux-dev-unified/products")):
        data = reader.collection(url(suffix))
        protected[key] = digest(data)
        counts[key] = len(data["value"])
        if key == "backends":
            require(not (set(v["name"] for v in data["value"]) & {x[0] for x in BACKENDS.values()}), "new_backend_already_present")
        if key == "products":
            for row in data["value"]:
                name = row["name"]
                protected["product_policy:" + name] = digest(reader.get(url("/products/" + name + "/policies/policy?format=xml"), optional=True))
        if key == "operations":
            for row in data["value"]:
                name = row["name"]
                protected["operation_policy:" + name] = digest(reader.get(url("/apis/aiflux-dev-unified/operations/" + name + "/policies/policy?format=xml"), optional=True))
    active = reader.get(url("/apis/aiflux-dev-unified/policies/policy?format=xml"))["properties"]["value"]
    require(not xml_node(active, exported=True).findall(".//include-fragment"), "actual_fragment_must_remain_detached")
    exclusive(label + "-policy.xml", active.encode())
    account_url = "https://management.azure.com" + rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    deployments = reader.collection(account_url + "/deployments?api-version=2025-06-01")
    retained = load(rt.HOME / "foundry-eight-20261030/deployments.json")
    require({d["name"] for d in deployments["value"]} == {d["name"] for d in retained["value"]}, "full_actual_deployment_membership_drift")
    # Exact complete observation; no synthetic accepted/gateway_validated inventory.
    require(deployments == retained, "full_actual_deployment_metadata_drift")
    exclusive(label + "-deployments.json", deployments)
    protected["deployments"] = digest(deployments)
    protected["active_policy"] = digest(active.encode())
    result = {"baseline": baseline, "supplemental": protected, "counts": counts, "runtime_flags": flags}
    exclusive(label + "-snapshot.json", result)
    exclusive(label + "-snapshot-result.json", {"at": now(), "sha256": digest(result), "fresh_four_settings": True,
              "apim_controls_attached": False, "extra_gets": reader.count, "actual_deployments": len(deployments["value"])})
    return result


def rebound(function, **bindings):
    """Private function globals only; never monkeypatch a consumed module."""
    return FunctionType(function.__code__, {**function.__globals__, **bindings},
                        function.__name__, function.__defaults__, function.__closure__)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("readonly_redirect_rejected")


class AttemptReader(Reader):
    """One snapshot: fresh reads, two bounded tries, durable endpoint categories.

    Cache is scoped to this snapshot only, avoiding redundant settings/policy
    reads. No response bodies or tokens are written to the request journal.
    """
    def __init__(self, label):
        super().__init__()
        self.label, self.cache = label, {}
        self.deadline = time.monotonic() + 2400
        self.opener = build_opener(HTTPSHandler(context=self.tls), NoRedirect())

    def request(self, url, method="GET", optional=False):
        require(url.startswith("https://management.azure.com" + rt.RG + "/providers/")
                or url.startswith("https://management.azure.com/subscriptions/" + rt.SUB
                                  + "/providers/Microsoft.Authorization/roleAssignments?"), "read_scope")
        require(not re.search(r"listSecrets|listKeys|regenerate|/secrets/", url, re.I), "no_secret_read")
        settings = re.fullmatch(re.escape("https://management.azure.com" + rt.RG)
            + r"/providers/Microsoft.Web/sites/poc-ids-token-ex-(api|admin|customer|ingestion)/config/appsettings/list\?api-version=2024-04-01", url)
        require(method == "GET" or (method == "POST" and settings is not None), "readonly_method")
        key = (method, url)
        if key in self.cache:
            return deepcopy(self.cache[key])
        category = ("settings_list:" + settings[1] if settings else
                    "role_assignments" if "/Microsoft.Authorization/" in url else
                    "arm:" + url.split("/providers/", 1)[1].split("?", 1)[0])
        for retry in range(2):
            remaining = self.deadline - time.monotonic()
            require(remaining > 0, "snapshot_total_deadline")
            self.count += 1
            name = f"reads/{self.label}-{self.count:03d}"
            timeout = min(240, remaining)
            exclusive(name + "-intent.json", {"at": now(), "pid": os.getpid(), "method": method,
                "url": url, "endpoint_category": category, "try": retry + 1, "timeout_seconds": timeout})
            started = time.monotonic()
            try:
                req = Request(url, method=method, headers={"Authorization": "Bearer " + self.token})
                with self.opener.open(req, timeout=timeout) as response:
                    require(response.status == 200 and response.geturl() == url, "unexpected_http_or_redirect")
                    raw = response.read(16 * 1024 * 1024 + 1)
                    require(len(raw) <= 16 * 1024 * 1024, "bounded_read")
                    value = json.loads(raw)
                    exclusive(name + "-result.json", {"at": now(), "status": response.status,
                        "endpoint_category": category, "elapsed_seconds": time.monotonic() - started,
                        "body_sha256": digest(raw), "request_id": response.headers.get("x-ms-request-id")})
                    self.cache[key] = value
                    return deepcopy(value)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                status = exc.code if isinstance(exc, HTTPError) else None
                cause = exc.reason if isinstance(exc, URLError) else exc
                retryable = (status in (408, 429, 500, 502, 503, 504) if status is not None
                             else isinstance(cause, (TimeoutError, ConnectionError)))
                exclusive(name + "-result.json", {"at": now(), "status": status,
                    "endpoint_category": category, "elapsed_seconds": time.monotonic() - started,
                    "error_type": type(exc).__name__, "retryable": retryable,
                    "request_id": exc.headers.get("x-ms-request-id") if isinstance(exc, HTTPError) else None})
                if optional and status == 404:
                    self.cache[key] = {"absent": True, "status": 404}
                    return deepcopy(self.cache[key])
                if retry == 0 and retryable:
                    continue
                raise RuntimeError("readonly_endpoint_failed:" + category.replace(":", "/")
                                   + ":" + str(status or type(exc).__name__)) from None

    def get(self, url, optional=False):
        return self.request(url, optional=optional)

    def arm(self, path, method="GET", raw=False):
        require(not raw, "json_reads_only")
        version = "2024-08-01" if "/Microsoft.DBforPostgreSQL/" in path else "2024-04-01"
        if "/Microsoft.KeyVault/" in path:
            version = "2023-07-01"
        return self.request("https://management.azure.com" + path + "?api-version=" + version, method)

    def cli(self, args):
        if args[:4] == ["rest", "--method", "get", "--url"] and len(args) == 5:
            return self.get(args[4])
        require(args == ["account", "show"] or args ==
                ["role", "assignment", "list", "--subscription", rt.SUB, "--all", "--include-inherited"],
                "readonly_cli_allowlist")
        category = "account_show" if args[0] == "account" else "role_assignments"
        for retry in range(2):
            self.count += 1
            name = f"reads/{self.label}-{self.count:03d}"
            require(time.monotonic() < self.deadline, "snapshot_total_deadline")
            exclusive(name + "-intent.json", {"at": now(), "pid": os.getpid(), "endpoint_category": category,
                      "argv_without_credentials": args, "try": retry + 1, "timeout_seconds": 240})
            try:
                child = subprocess.run(rt.CLI + args + ["--only-show-errors", "-o", "json"],
                    env=rt.ENV, capture_output=True, encoding="utf-8", errors="replace", timeout=240)
                exclusive(name + "-result.json", {"at": now(), "endpoint_category": category,
                          "exit_code": child.returncode})
                require(child.returncode == 0, "readonly_cli_failed:" + category)
                return json.loads(child.stdout)
            except subprocess.TimeoutExpired:
                exclusive(name + "-result.json", {"at": now(), "endpoint_category": category,
                          "error_type": "TimeoutExpired", "retryable": True})
                if retry:
                    raise RuntimeError("readonly_cli_timeout:" + category) from None


def continuation_settings(reader):
    return {k: reader.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + k
                         + "/config/appsettings/list", "POST")["properties"] for k in PINS}


def continuation_snapshot(reader):
    """Exact historical projection with private read transports and proven 5-IP ACL."""
    from scripts.deployment import project_route_product_access as product
    evidence = rt.HOME / "storage-firewall-167-103-67-80-20261030"
    approved = load(evidence / "independent-after.json")["account"]
    previous = load(evidence / "before.json")["account"]
    receipt = load(evidence / "result.json")
    require(receipt["success"] and receipt["account_comparison_passed"]
            and receipt["all_other_account_properties_exact"], "approved_storage_receipt")
    keys = ("networkAcls", "publicNetworkAccess", "allowSharedKeyAccess")
    expected = {k: approved["properties"].get(k) for k in keys}
    require({p["value"] for p in expected["networkAcls"]["ipRules"]} ==
            {"167.103.66.248", "167.103.66.93", "167.103.65.36", "167.103.63.12", "167.103.67.80"},
            "approved_exact_five_ips")
    observed = []
    storage_url = "https://management.azure.com" + rt.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=2023-05-01"

    def cli(args):
        value = reader.cli(args)
        if args == ["rest", "--method", "get", "--url", storage_url]:
            actual = {k: value["properties"].get(k) for k in keys}
            require(actual == expected, "approved_storage_baseline_drift")
            observed.append(actual)
            value = deepcopy(value)
            value["properties"].update({k: previous["properties"].get(k) for k in keys})
        return value

    transport = SimpleNamespace(**{**vars(rt), "cli": cli, "arm": reader.arm})
    portals = SimpleNamespace(**{**vars(rate.r.portals),
                               "baseline": rebound(rate.r.portals.baseline, rt=transport)})
    fs = SimpleNamespace(**{**vars(rate.r.fs), "current_settings": lambda: continuation_settings(reader)})
    protected = rebound(product.ProductRun.protected, rt=transport, portals=portals, fs=fs)

    class ReadRun(product.ProductRun):
        def __init__(self):
            pass  # No inherited worker, inference or mutation setup.

        def arm(self, suffix, method="GET"):
            require(method == "GET", "apim_get_only")
            url = "https://management.azure.com" + rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim" + suffix
            return reader.get(url + ("&" if "?" in suffix else "?") + "api-version=2024-05-01")

        def protected(self):
            value = protected(self)
            require(len(observed) == 1, "exactly_one_storage_read")
            value["state_network"] = observed[0]
            return value

    return rebound(rate.r.snapshot, rt=transport, ProductRun=ReadRun)()


def compose():
    """Retained deployed source + ONLY tested eight-model hunks; no Auto files."""
    TFROOT.mkdir(parents=True)
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name in ("main.tf", "external.tf", "fireworks.tf", "poc-controls.tf"):
            raw = archive.read("tfconfig/m-/" + name)
            exclusive("predecessor/infra/project-route/" + name, raw)
            (TFROOT / name).write_bytes(raw)
        (TFROOT / ".terraform.lock.hcl").write_bytes(archive.read(".terraform.lock.hcl"))
    # main.tf's only unrelated pending hunks are its two Auto count predicates.
    # Remove those; there is deliberately NO Auto variable/module/template bind.
    text = (rt.ROOT / "infra/project-route/main.tf").read_bytes().decode()
    for tag, count in (("rate-limit-by-key", 3), ("llm-token-limit", 2)):
        old = f'length(regexall("<{tag}", local.policy)) == (var.auto_routing_enabled ? {count} : 1)'
        require(text.count(old) == 1, "known_unrelated_main_hunk")
        text = text.replace(old, f'length(regexall("<{tag}", local.policy)) == 1')
    (TFROOT / "main.tf").write_bytes(text.encode())
    text = (rt.ROOT / "infra/project-route/foundry-eight.tf").read_bytes().decode()
    require(text.count("!var.auto_routing_enabled && ") == 1 and text.count("local.auto_policy") == 1, "known_offline_auto_off_adapter")
    text = text.replace("!var.auto_routing_enabled && ", "").replace("local.auto_policy", "local.glm_policy")
    (TFROOT / "foundry-eight.tf").write_bytes(text.encode())
    # Existing publisher changed this description before this release. Bind its
    # actual deployed predecessor value rather than plan a fragment metadata edit.
    path = TFROOT / "poc-controls.tf"
    old = b"Runtime-owned bounded POC variables and literal-call quota; stable counter identity and envelope."
    new = b"Runtime-owned bounded settings; invariant inspection and routing remain Terraform-owned."
    raw = path.read_bytes()
    require(raw.count(old) == 1, "retained_fragment_description_anchor")
    path.write_bytes(raw.replace(old, new))
    for name in ("dev-openai.xml.tftpl", "global-dev-gate.xml.tftpl", "poc-settings-defaults.xml"):
        raw = (RETAINED / "gateway/policies" / name).read_bytes()
        exclusive("predecessor/gateway/policies/" + name, raw)
        exclusive("context/gateway/policies/" + name,
                  (rt.ROOT / "gateway/policies" / name).read_bytes() if name == "dev-openai.xml.tftpl" else raw)
    for name in ("fireworks-candidate-routes.json", "foundry-eight-candidate-routes.json"):
        exclusive("context/gateway/catalog/" + name, (rt.ROOT / "gateway/catalog" / name).read_bytes())
    # Existing initialized provider metadata only; no backend/state/plan copies.
    installed = rt.ROOT / "infra/project-route/.terraform"
    if (installed / "providers").exists():
        shutil.copytree(installed / "providers", TFROOT / ".terraform/providers")
    require(not list(CONTEXT.rglob("*auto*")), "no_auto_context_files")
    require(not any(b"local.auto_" in p.read_bytes() or b"var.auto_" in p.read_bytes() for p in TFROOT.glob("*.tf")),
            "no_auto_context_bindings")
    diffs = []
    for path in (HOME / "predecessor").rglob("*"):
        if path.is_file():
            relative = path.relative_to(HOME / "predecessor")
            candidate = CONTEXT / relative
            diffs.extend(difflib.unified_diff(path.read_bytes().decode().splitlines(True), candidate.read_bytes().decode().splitlines(True),
                         fromfile="deployed/" + relative.as_posix(), tofile="eight/" + relative.as_posix()))
    exclusive("source-delta.diff", "".join(diffs).encode())
    return context_hashes()


def context_hashes():
    return hashes([p for p in CONTEXT.rglob("*") if p.is_file() and ".terraform" not in p.parts])


def render(stage, inputs):
    value = terraform(stage, "console", "-no-color", "-var-file=" + str(inputs), text="jsonencode(local.policy)\n")
    return json.loads(json.loads(value[value.find('"'):].strip()))


def tested_render():
    raw = (OFFLINE / "rendered-explicit_manifest_is_exact_twenty_plus_external.xml").read_bytes()
    require(digest(raw) == "3b6ff061f615696d6d80ca7cbd3caea03f4a019aaa66aee4af67cd3cbd98c992", "retained_render_digest")
    # The source-bound historical runner uses Path.write_text on Windows. Undo
    # EXACTLY that one LF -> CRLF serialization layer (including CRCRLF), not
    # whitespace folding or expression/newline normalization. Compare exact bytes
    # afterward. read_text's universal-newline handling loses this distinction.
    return raw.replace(b"\r\n", b"\n").decode("utf-8")


def prepare():
    require(not HOME.exists(), "existing_release_reconcile_only_never_replay")
    source = inputs_bound()
    gate = worker_gate()
    rate.r.fs.protect(HOME)
    exclusive("prepare-intent.json", {"at": now(), "pid": os.getpid(), "sources": source, "worker_gate": gate,
              "scope": "prepare_plan_only", "applies": 0, "inference": 0, "builds": 0})
    account()
    state = state_identity()
    baseline = live_snapshot("prepare")
    composed = compose()
    variables = load(rt.HOME / "poc-fragment-bootstrap-20261028/inputs.tfvars.json")
    require(variables["poc_controls_enabled"] is False and variables["poc_settings_bootstrap_enabled"] is True
            and variables["allow_product_subscriptions"] is True, "actual_prior_route_profile")
    historical = deepcopy(variables)
    historical["route_manifest_path"] = (CONTEXT / "gateway/catalog/fireworks-candidate-routes.json").as_posix()
    exclusive("historical-inputs.tfvars.json", historical)
    variables["route_manifest_path"] = (CONTEXT / "gateway/catalog/foundry-eight-candidate-routes.json").as_posix()
    exclusive("inputs.tfvars.json", variables)
    terraform("fmt", "fmt", "-check", "-no-color")
    validation = json.loads(terraform("validate", "validate", "-json"))
    require(validation["valid"] and validation["error_count"] == 0, "context_validate")
    require(terraform("workspace", "workspace", "show").strip() == "default", "default_workspace")
    old = render("historical-render", HOME / "historical-inputs.tfvars.json")
    active = (HOME / "prepare-policy.xml").read_bytes().decode()
    require(structural(xml_node(old)) == structural(xml_node(active, exported=True)), "whole_fresh_live_predecessor_mismatch")
    candidate = render("candidate-render", HOME / "inputs.tfvars.json")
    require(candidate == tested_render(),
            "candidate_must_equal_actual_tested_render")
    checks = policy_guard(active, candidate)
    exclusive("historical-policy.xml", old.encode())
    exclusive("candidate-policy.xml", candidate.encode())
    require(state_identity() == state and inputs_bound() == source and context_hashes() == composed, "prepare_binding_race")
    exclusive("prepared.json", {"at": now(), "state": state, "sources": source, "context": composed,
              "baseline_sha256": digest(baseline), "policy_guards": checks, "status": "PREPARED_NO_APPLY_NO_INFERENCE"})
    print(json.dumps({"status": "PREPARED", "settings_hashes": baseline["baseline"]["settings_hashes"],
                      "candidate_sha256": digest(candidate.encode()), "state_serial": state["serial"]}), flush=True)


def finalize_original_prepare():
    """Offline correction only: NEVER repeat snapshot, render, prepare or plan."""
    intent = load(HOME / "prepare-intent.json")
    worker_gate()
    require(not (HOME / "prepared.json").exists(), "already_prepared_no_replay")
    failures = list(HOME.glob("prepare-failure-*.json"))
    require(len(failures) == 1 and load(failures[0])["reason"] == "candidate_must_equal_actual_tested_render",
            "only_known_original_serialization_failure")
    current = inputs_bound()
    own = Path(__file__).relative_to(rt.ROOT).as_posix()
    require({k: v for k, v in current.items() if k != own} ==
            {k: v for k, v in intent["sources"].items() if k != own}, "original_noncontroller_source_drift")
    for name in ("fmt", "validate", "workspace", "historical-render", "candidate-render"):
        result = load(HOME / "commands" / (name + "-result.json"))
        require(result["exit_code"] == 0 and result["stdout_sha256"] == digest((HOME / "commands" / (name + ".stdout.txt")).read_bytes())
                and result["stderr_sha256"] == digest((HOME / "commands" / (name + ".stderr.txt")).read_bytes()), "original_command_receipt_integrity")

    def retained_render(name):
        raw = (HOME / "commands" / (name + ".stdout.txt")).read_bytes().decode()
        return json.loads(json.loads(raw[raw.find('"'):].strip()))

    historical, candidate = retained_render("historical-render"), retained_render("candidate-render")
    previous = (HOME / "prepare-policy.xml").read_bytes().decode()
    require(structural(xml_node(historical)) == structural(xml_node(previous, exported=True)), "original_actual_whole_predecessor")
    require(candidate == tested_render(), "recovered_tested_render_exact_bytes")
    checks = policy_guard(previous, candidate)
    require(json.loads((HOME / "commands/validate.stdout.txt").read_bytes())["valid"], "original_validate_required")
    require((HOME / "commands/workspace.stdout.txt").read_text().strip() == "default", "original_default_workspace")
    state = state_identity()
    require(not (HOME / "plan-intent.json").exists() and not PLAN.exists(), "no_original_plan")
    exclusive("serialization-correction.json", {"at": now(), "original_pid": intent["pid"],
              "original_failure_preserved": failures[0].name, "original_controller_sha256": intent["sources"][own],
              "corrected_controller_sha256": current[own], "all_other_sources_exact": True,
              "raw_tested_sha256": digest((OFFLINE / "rendered-explicit_manifest_is_exact_twenty_plus_external.xml").read_bytes()),
              "recovered_exact_render_sha256": digest(candidate.encode()), "normalization": "reverse_one_windows_write_text_serialization_layer_only",
              "cloud_reads": 0, "rerenders": 0, "repeated_prepares": 0})
    exclusive("historical-policy.xml", historical.encode())
    exclusive("candidate-policy.xml", candidate.encode())
    exclusive("prepared.json", {"at": now(), "state": state, "sources": current, "context": context_hashes(),
              "baseline_sha256": digest(load(HOME / "prepare-snapshot.json")), "policy_guards": checks,
              "status": "PREPARED_ORIGINAL_OUTPUTS_RECOVERED_NO_REPLAY_NO_APPLY_NO_INFERENCE"})
    print(json.dumps({"status": "PREPARED_ORIGINAL_OUTPUTS_RECOVERED", "candidate_sha256": digest(candidate.encode()),
              "fresh_settings_hashes": load(HOME / "prepare-snapshot.json")["baseline"]["settings_hashes"]}), flush=True)


def unknown(value):
    return any(unknown(v) for v in value.values()) if isinstance(value, dict) else (
        any(unknown(v) for v in value) if isinstance(value, list) else value is True)


def guard(plan, previous, desired, expected_variables, check_proof=None):
    require(plan.get("applyable") is True and not plan.get("errored") and not plan.get("deferred_changes"), "resolved_plan")
    values = {k: v["value"] for k, v in plan["variables"].items()}
    require(all(values.get(k) == v for k, v in expected_variables.items()), "explicit_inputs_exact")
    require(not any("auto_" in k for k in values) and values["poc_controls_enabled"] is False
            and values["poc_settings_bootstrap_enabled"] is True and values["allow_product_subscriptions"] is True,
            "no_auto_no_controls_toggle")
    writes = []
    for item in plan.get("resource_changes", []):
        require("auto_stage_revision" not in item["address"], "held_auto_not_in_plan_graph")
        c = item["change"]
        require(c["actions"] != ["read"] or item["mode"] == "data", "managed_read_rejected")
        if c["actions"] in (["no-op"], ["read"]):
            continue
        require(item["mode"] == "managed" and item["address"] in TARGETS, "unapproved_write")
        require(not any(unknown(v) for k, v in (c.get("after_unknown") or {}).items() if k not in ("output", "id")), "unknown_writable")
        after = c["after"]
        if item["address"] in BACKENDS:
            name, endpoint = BACKENDS[item["address"]]
            require(c["actions"] == ["create"] and c["before"] is None and after["name"] == name
                    and after["parent_id"] == rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
                    and after["type"] == "Microsoft.ApiManagement/service/backends@2024-05-01"
                    and after["body"] == {"properties": {"protocol": "http", "url": endpoint,
                        "tls": {"validateCertificateChain": True, "validateCertificateName": True}}}, "exact_new_backend")
        else:
            require(c["actions"] == ["update"], "one_existing_policy_update")
            before, after = deepcopy(c["before"]), deepcopy(after)
            old_policy = before["body"]["properties"]
            # AzAPI refresh returns format=xml with the ARM expression export
            # layer. Require EXACT fresh bytes for that format, not a second
            # normalization or a comparison as though it were rawxml source.
            require(old_policy.get("format") in ("xml", "rawxml"), "known_predecessor_format")
            if old_policy["format"] == "xml":
                require(old_policy["value"] == previous, "plan_actual_exported_predecessor_bytes")
            else:
                require(structural(xml_node(old_policy["value"])) == structural(xml_node(previous, exported=True)), "plan_actual_predecessor")
            require(after["body"] == {"properties": {"format": "rawxml", "value": desired}}, "exact_tested_candidate_body")
            after["body"], after["output"] = before["body"], before.get("output")
            require(before == after, "nonpolicy_attribute_change")
        writes.append({"address": item["address"], "actions": c["actions"]})
    require(len(writes) == 3 and {v["address"] for v in writes} == set(TARGETS), "exact_2creates_1update_0delete")
    checks = plan.get("checks")
    pending = [c for c in checks or [] if c["status"] != "pass"]
    if pending and check_proof:
        require(len(pending) == 1 and pending[0]["address"] ==
                {"kind": "var", "name": "global_policy_format", "to_display": "var.global_policy_format"}
                and pending[0]["status"] == "unknown", "only_untargeted_format_validation_resolvable")
        require(check_proof["passed"] is True and check_proof["saved_status_preserved"] == "unknown"
                and check_proof["value"] == values["global_policy_format"] == expected_variables["global_policy_format"]
                and check_proof["expression"] == 'contains(["xml", "rawxml"], var.global_policy_format)'
                and check_proof["value"] in ("xml", "rawxml")
                and check_proof["context_sha256"] == digest(context_hashes())
                and check_proof["plan_sha256"] == digest((HOME / "attempts/plan02/gateway.tfplan").read_bytes()),
                "actual_format_validation_proof_required")
    else:
        require(checks and not pending, "every_saved_plan_check_pass")
    policy_guard(previous, desired)
    return writes


def resolve_plan02_format_check():
    """Stateless console evaluates ONLY one input predicate, no resources/state."""
    require(not (TFROOT / "terraform.tfstate").exists(), "stateless_context_required")
    data = load(HOME / "attempts/plan02/plan.json")
    expression = 'contains(["xml", "rawxml"], var.global_policy_format)'
    source = (TFROOT / "main.tf").read_text()
    block = re.search(r'variable "global_policy_format" \{.*?\n\}', source, re.S)
    require(block is not None and block[0].count("condition") == 1
            and "condition     = " + expression in block[0], "exact_saved_input_validation_predicate")
    with zipfile.ZipFile(PLAN) as archive:
        require(archive.read("tfconfig/m-/main.tf") == (TFROOT / "main.tf").read_bytes(), "saved_predicate_source_exact")
    output = terraform("format-input-check", "console", "-no-color", "-var-file=" + str(HOME / "inputs.tfvars.json"),
                       text='jsonencode([var.global_policy_format, ' + expression + '])\n')
    value, passed = json.loads(json.loads(output[output.find('"'):].strip()))
    require(passed is True and value == data["variables"]["global_policy_format"]["value"], "actual_console_format_predicate")
    proof = {"at": now(), "passed": passed, "value": value, "expression": expression,
        "saved_status_preserved": "unknown", "plan_sha256": digest(PLAN.read_bytes()),
        "context_sha256": digest(context_hashes()), "predicate_block_sha256": digest(block[0].encode()),
        "console_result_sha256": digest((OUTPUT / "commands/format-input-check-result.json").read_bytes()),
        "state_reads": 0, "resource_refreshes": 0, "replans": 0, "held_auto_evaluated": False}
    exclusive("format-input-check.json", proof)
    return proof


def begin_attempt(attempt):
    global OUTPUT, PLAN
    require(attempt == "plan02", "only_explicitly_authorized_plan02")
    require(digest((HOME / "prepared.json").read_bytes()) == ORIGINAL_PREPARED, "original_prepared_receipt_changed")
    prepared = load(HOME / "prepared.json")
    own = Path(__file__).relative_to(rt.ROOT).as_posix()
    require(prepared["sources"][own] == ORIGINAL_CONTROLLER, "original_controller_provenance")
    current = inputs_bound()
    require({k: v for k, v in current.items() if k != own} ==
        {k: v for k, v in prepared["sources"].items() if k != own}, "noncontroller_sources_changed")
    require(context_hashes() == prepared["context"] and state_identity() == prepared["state"], "context_state_changed")
    failure = load(HOME / "plan-failure-162447589895.json")
    require(failure["pid"] == 34024 and failure["error_type"] == "TimeoutError"
        and (HOME / "preplan-snapshot-intent.json").exists()
        and not (HOME / "plan-intent.json").exists() and not (HOME / "gateway.tfplan").exists()
        and not (HOME / "commands/plan-intent.json").exists(), "original_failed_before_plan_only")
    gate = worker_gate()
    source_review = load(HOME / "plan02-controller-review.json")
    require(source_review["original_controller_sha256"] == ORIGINAL_CONTROLLER
        and source_review["new_controller_sha256"] == current[own]
        and source_review["original_prepared_sha256"] == ORIGINAL_PREPARED
        and source_review["original_receipt_not_rebound"] is True, "external_controller_provenance_required")
    old_artifacts = hashes([p for p in HOME.rglob("*") if p.is_file()
               and ".terraform" not in p.parts and "attempts" not in p.relative_to(HOME).parts])
    OUTPUT = HOME / "attempts" / attempt
    require(not OUTPUT.exists(), "named_attempt_consumed_reconcile_only")
    OUTPUT.mkdir(parents=True, exist_ok=False)  # Inherit existing private ACL; no permissions change.
    PLAN = OUTPUT / "gateway.tfplan"
    exclusive("attempt-intent.json", {"at": now(), "pid": os.getpid(), "attempt": attempt,
    "authorization": "explicit_new_named_readonly_plan02_after_original_timeout",
    "worker_gate": gate, "sources": current, "prepared_receipt_sha256": ORIGINAL_PREPARED,
    "old_controller_sha256": ORIGINAL_CONTROLLER, "new_controller_sha256": current[own],
    "external_controller_review_sha256": digest((HOME / "plan02-controller-review.json").read_bytes()),
    "consumed_receipts_preserved": old_artifacts, "snapshot_request_timeout_seconds": 240,
    "max_read_tries": 2, "snapshot_deadline_seconds": 2400,
    "max_plans": 1, "applies": 0, "inference": 0, "cloud_resource_writes": 0})
    return current, old_artifacts


def plan_release(attempt=None):
    prepared = load(HOME / "prepared.json")
    expected_sources, old_artifacts = begin_attempt(attempt) if attempt else (prepared["sources"], {})
    require(not (OUTPUT / "plan-intent.json").exists(), "existing_plan_attempt_reconcile_only")
    require(inputs_bound() == expected_sources and context_hashes() == prepared["context"]
            and state_identity() == prepared["state"], "source_context_state_binding")
    worker_gate()
    account()
    current = live_snapshot("preplan", AttemptReader("preplan") if attempt else None)
    require(current == load(HOME / "prepare-snapshot.json"), "fresh_full_baseline_drift")
    exclusive("plan-intent.json", {"at": now(), "pid": os.getpid(), "targets": TARGETS,
              "state": prepared["state"], "max_plans": 1, "applies": 0, "inference": 0})
    terraform("plan", "plan", "-input=false", "-no-color", "-lock-timeout=30s", "-state=" + str(OWNER),
              "-var-file=" + str(HOME / "inputs.tfvars.json"), *["-target=" + v for v in TARGETS], "-out=" + str(PLAN))
    data = json.loads(terraform("show", "show", "-json", str(PLAN)))
    exclusive("plan.json", data)
    previous = (HOME / "prepare-policy.xml").read_bytes().decode()
    desired = (HOME / "candidate-policy.xml").read_bytes().decode()
    changes = guard(data, previous, desired, load(HOME / "inputs.tfvars.json"))
    with zipfile.ZipFile(PLAN) as archive:
        expected = {"tfconfig/m-/" + p.name: p.read_bytes() for p in TFROOT.glob("*.tf")}
        require({n for n in archive.namelist() if n.startswith("tfconfig/m-/")} == set(expected), "saved_module_set")
        require(all(archive.read(n) == raw for n, raw in expected.items()) and
                archive.read(".terraform.lock.hcl") == (TFROOT / ".terraform.lock.hcl").read_bytes(), "saved_module_bytes")
        after = live_snapshot("postplan", AttemptReader("postplan") if attempt else None)
        require(after == current and state_identity() == prepared["state"] and inputs_bound() == expected_sources
            and context_hashes() == prepared["context"], "postplan_protected_state_sources_drift")
        require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in old_artifacts.items()), "consumed_receipt_changed")
        artifacts = hashes([p for p in OUTPUT.rglob("*") if p.is_file() and ".terraform" not in p.parts])
    summary = {"at": now(), "status": "EXACT_PLAN_READY_PARENT_INDEPENDENT_REVIEW_REQUIRED",
               "plan_sha256": digest(PLAN.read_bytes()), "plan_json_sha256": digest((OUTPUT / "plan.json").read_bytes()),
               "attempt": attempt, "source_sha256": digest(expected_sources), "context_sha256": digest(prepared["context"]),
               "original_prepared_receipt_sha256": digest((HOME / "prepared.json").read_bytes()),
               "controller_provenance_corrected_without_rebinding": bool(attempt),
               "candidate_policy_sha256": digest(desired.encode()), "changes": changes,
               "change_counts": {"create": 2, "update": 1, "delete": 0, "replace": 0},
               "checks": [{"address": c["address"], "status": c["status"]} for c in data["checks"]],
               "settings_hashes": current["baseline"]["settings_hashes"], "runtime_flags": current["runtime_flags"],
               "state": prepared["state"], "full_protected_snapshot_unchanged": True,
               "all_four_pins_preserved": True, "all_four_settings_preserved": True,
               "no_auto_files_or_bindings": True, "targeted_existing_childscope_only": True,
               "held_state_objects_not_targeted": ["azapi_resource.auto_stage_revision[0]", "azapi_resource.project_global_gate[0]"],
               "policy_guards": prepared["policy_guards"], "artifacts": artifacts,
               "warnings": re.findall(r"^Warning: [^\r\n]+", (OUTPUT / "commands/plan.stdout.txt").read_text(), re.M),
               "independent_review_performed": False, "official_validation_status": "NOT_STARTED_PARENT_REQUIRED",
               "cloud_resource_writes": 0, "applies": 0, "builds": 0, "inference": 0,
               "no_apply_entrypoint": True}
    exclusive("review.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("artifacts", "checks")}), flush=True)


def finalize_plan02():
    """Consume actual retained plan; NEVER invoke Terraform plan or prepare."""
    global OUTPUT, PLAN
    prepared = load(HOME / "prepared.json")
    require(digest((HOME / "prepared.json").read_bytes()) == ORIGINAL_PREPARED, "original_prepared_receipt_changed")
    folder = HOME / "attempts/plan02"
    launch = load(folder / "attempt-intent.json")
    failures = list(folder.glob("plan-failure-*.json"))
    require(len(failures) == 1 and load(failures[0])["reason"] == "plan_actual_predecessor",
            "only_proven_export_format_guard_failure")
    worker_gate()
    require(not (folder / "review.json").exists() and not (folder / "postplan-snapshot-intent.json").exists(),
            "finalizer_or_snapshot_already_consumed")
    current_sources = inputs_bound()
    own = Path(__file__).relative_to(rt.ROOT).as_posix()
    require({k: v for k, v in current_sources.items() if k != own} ==
            {k: v for k, v in launch["sources"].items() if k != own}, "only_controller_guard_correction_allowed")
    correction = load(HOME / "plan02-guard-correction-review.json")
    require(correction["plan_generator_controller_sha256"] == launch["new_controller_sha256"]
            and correction["corrected_controller_sha256"] == current_sources[own]
            and correction["plan_sha256"] == digest((folder / "gateway.tfplan").read_bytes())
            == "bb8aba49c135a58e1a84e25b8c28b36cab640bb4299bc6054f48f4e4bf33b433",
            "external_exact_plan_guard_correction_provenance")
    require(context_hashes() == prepared["context"] and state_identity() == prepared["state"], "context_state_changed")
    for stage in ("plan", "show"):
        record = load(folder / "commands" / (stage + "-result.json"))
        require(record["exit_code"] == 0 and all(record[k + "_sha256"] ==
                digest((folder / "commands" / (stage + "." + k + ".txt")).read_bytes()) for k in ("stdout", "stderr")),
                "original_plan_show_receipts_exact")
    require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in launch["consumed_receipts_preserved"].items()),
            "consumed_receipt_changed")
    OUTPUT, PLAN = folder, folder / "gateway.tfplan"
    exclusive("finalize-intent.json", {"at": now(), "pid": os.getpid(), "plan_sha256": digest(PLAN.read_bytes()),
        "sources": current_sources, "plan_generator_controller_sha256": launch["new_controller_sha256"],
        "external_correction_sha256": digest((HOME / "plan02-guard-correction-review.json").read_bytes()),
        "replans": 0, "prepares": 0, "applies": 0})
    data = load(folder / "plan.json")
    require(data == json.loads((folder / "commands/show.stdout.txt").read_bytes()), "retained_plan_json_exact_show")
    current = load(folder / "preplan-snapshot.json")
    require(current == load(HOME / "prepare-snapshot.json"), "actual_preplan_baseline_exact")
    previous = (folder / "preplan-policy.xml").read_bytes().decode()
    desired = (HOME / "candidate-policy.xml").read_bytes().decode()
    check_proof = resolve_plan02_format_check()
    changes = guard(data, previous, desired, load(HOME / "inputs.tfvars.json"), check_proof)
    with zipfile.ZipFile(PLAN) as archive:
        expected = {"tfconfig/m-/" + p.name: p.read_bytes() for p in TFROOT.glob("*.tf")}
        require({n for n in archive.namelist() if n.startswith("tfconfig/m-/")} == set(expected), "saved_module_set")
        require(all(archive.read(n) == raw for n, raw in expected.items()) and
                archive.read(".terraform.lock.hcl") == (TFROOT / ".terraform.lock.hcl").read_bytes(), "saved_module_bytes")
    account()
    after = live_snapshot("postplan", AttemptReader("postplan"))
    require(after == current and state_identity() == prepared["state"] and inputs_bound() == current_sources
            and context_hashes() == prepared["context"], "postplan_protected_state_sources_drift")
    require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in launch["consumed_receipts_preserved"].items()),
            "consumed_receipt_changed")
    artifacts = hashes([p for p in folder.rglob("*") if p.is_file()])
    summary = {"at": now(), "attempt": "plan02", "status": "EXACT_PLAN_READY_PARENT_INDEPENDENT_REVIEW_REQUIRED",
        "plan_sha256": digest(PLAN.read_bytes()), "plan_json_sha256": digest((folder / "plan.json").read_bytes()),
        "plan_generator_controller_sha256": launch["new_controller_sha256"],
        "guard_controller_sha256": current_sources[own], "original_prepared_receipt_sha256": ORIGINAL_PREPARED,
        "source_sha256": digest(current_sources), "sources": current_sources, "context_sha256": digest(prepared["context"]),
        "candidate_policy_sha256": digest(desired.encode()), "changes": changes,
        "change_counts": {"create": 2, "update": 1, "delete": 0, "replace": 0},
        "checks": [{"address": c["address"], "status": c["status"]} for c in data["checks"]],
        "check_resolution": check_proof,
        "saved_check_counts": {"pass": sum(c["status"] == "pass" for c in data["checks"]),
                       "unknown": sum(c["status"] == "unknown" for c in data["checks"])},
        "warnings": re.findall(r"^Warning: [^\r\n]+", (folder / "commands/plan.stdout.txt").read_text(), re.M),
        "state": prepared["state"], "settings_hashes": current["baseline"]["settings_hashes"],
        "runtime_flags": current["runtime_flags"], "full_protected_snapshot_unchanged": True,
        "consumed_receipts_preserved": True, "all_four_pins_preserved": True, "all_four_settings_preserved": True,
        "no_auto_files_or_bindings": True, "held_auto_absent_from_plan_graph": True,
        "targeted_existing_childscope_only": True, "saved_config_exact": True,
        "policy_guards": policy_guard(previous, desired), "artifacts": artifacts,
        "independent_review_performed": False, "official_validation_status": "NOT_STARTED_PARENT_REQUIRED",
        "replans": 0, "cloud_resource_writes": 0, "applies": 0, "builds": 0, "inference": 0,
        "no_apply_entrypoint": True}
    exclusive("review.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("artifacts", "sources", "checks")}), flush=True)


class GuardTests(unittest.TestCase):
    def test_exact_windows_serialization_recovery(self):
        value = tested_render()
        raw = (OFFLINE / "rendered-explicit_manifest_is_exact_twenty_plus_external.xml").read_bytes()
        self.assertEqual(value.replace("\n", "\r\n").encode(), raw)
        self.assertEqual(digest(value.encode()), "df871f2441e3b0c52d4f64a1a972f1280fb44abc8ad25b4eb44621aa2548986a")

    def test_candidate_exact_addition(self):
        self.assertTrue(inputs_bound())

    def test_candidate_policy_protection(self):
        historical = (OFFLINE / "rendered-historical_twelve_remain_opted_out.xml").read_text(encoding="utf-8")
        # A local render is not ARM double-encoded; encode expressions to emulate
        # the known ARM XML export without changing any other policy content.
        node = xml_node(historical)
        for n in node.iter():
            for key, value in n.attrib.items():
                if value.startswith("@"):
                    n.attrib[key] = html.escape(value, quote=False)
            if n.text and n.text.startswith("@"):
                n.text = html.escape(n.text, quote=False)
        previous = ET.tostring(node, encoding="unicode")
        desired = (OFFLINE / "rendered-explicit_manifest_is_exact_twenty_plus_external.xml").read_text(encoding="utf-8")
        self.assertTrue(policy_guard(previous, desired)["old13_preserved"])
        for changed in (desired.replace('calls="60"', 'calls="59"'), desired.replace('threshold="1"', 'threshold="2"'),
                        desired.replace('timeout="45"', 'timeout="46"'), desired.replace('"Mistral-Large-3"', '"mistral-medium-3-5"')):
            with self.assertRaises(RuntimeError):
                policy_guard(previous, changed)

    def test_no_mutating_cli_choices(self):
        with self.assertRaises(RuntimeError):
            terraform("forbidden", "apply")
        with self.assertRaises(RuntimeError):
            terraform("forbidden", "workspace", "new")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("localcheck", "prepare", "finalize-original-prepare", "plan", "finalize-plan02"))
    parser.add_argument("--attempt", choices=("plan02",))
    args = parser.parse_args()
    if args.attempt and args.action != "plan":
        parser.error("--attempt is supported only for plan")
    if args.action == "localcheck":
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
        return 0 if result.wasSuccessful() else 1
    try:
        if args.action == "plan":
            plan_release(args.attempt)
        else:
            {"prepare": prepare, "finalize-original-prepare": finalize_original_prepare,
             "finalize-plan02": finalize_plan02}[args.action]()
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-zA-Z0-9_:./\-]{1,160}", str(exc)) else "protected_detail_suppressed"
        result = {"at": now(), "action": args.action, "pid": os.getpid(), "status": "STOP_RECONCILE_ORIGINAL_NO_REPLAY",
                  "error_type": type(exc).__name__, "reason": reason, "applies": 0, "inference": 0}
        if OUTPUT.exists():
            exclusive(args.action + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())