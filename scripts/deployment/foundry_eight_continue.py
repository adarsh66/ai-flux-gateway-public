"""Explicit, exclusive GET-only recovery of the interrupted eight-model baseline.

Never invokes the original collector or a release entrypoint. Settings/list POSTs
in the historical snapshot are deliberately NOT allowed: try the resource GET,
and record an incomplete baseline if the provider will not serve that read.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import foundry_eight_preflight as original

HOME = rt.HOME / "foundry-eight-20261030"
APIM = rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
API = APIM + "/apis/aiflux-dev-unified"
KINDS = ("api", "admin", "customer", "ingestion")
ORIGINAL_FILES = ("read-intent.json", "deployments.json", "requested.json")
FIVE_IPS = {"167.103.66.248", "167.103.66.93", "167.103.65.36", "167.103.63.12", "167.103.67.80"}
SAFE_FLAGS = ("AIFLUX_GATEWAY_CONTROLS_POC_ENABLED", "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED",
              "AIFLUX_GATEWAY_SETTINGS_SCOPES", "AIFLUX_APIM_PRODUCT_ID",
              "AzureWebJobs.ingest_usage.Disabled", "AIFLUX_INGESTION_START_AT")


def stamp():
    return datetime.now(UTC).isoformat()


def sha(value):
    if not isinstance(value, bytes):
        # Match finops_function_stage.sha used by the retained rate-card proof.
        value = json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def exclusive(folder, name, value):
    """Creation, flush and fsync precede the read that an intent authorizes."""
    with (folder / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def failure(error):
    """Only fixed categories; never serialize exception messages or response text."""
    if isinstance(error, HTTPError):
        return {"category": "http_error", "http_status": error.code}
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return {"category": "timeout"}
    if isinstance(error, ssl.SSLError):
        return {"category": "tls_error"}
    if isinstance(error, URLError):
        return {"category": "tls_error" if isinstance(error.reason, ssl.SSLError) else "transport_error"}
    if isinstance(error, json.JSONDecodeError):
        return {"category": "invalid_json"}
    if isinstance(error, FileExistsError):
        return {"category": "exclusive_receipt_exists_no_replay"}
    if isinstance(error, FileNotFoundError):
        return {"category": "required_local_file_missing"}
    if isinstance(error, ET.ParseError):
        return {"category": "xml_parse_error"}
    if isinstance(error, RuntimeError) and re.fullmatch(r"[a-z_]+", str(error)):
        return {"category": str(error)}
    return {"category": "local_validation_error", "type": type(error).__name__}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def scrub(value):
    """APIM GET may contain credentials, including subscription keys. Drop them."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(
            r"credentials|password|primarykey|secondarykey|access.?token|connection.?string|clientsecret|authorization", k, re.I)
            else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        # Preserve named-value references/expressions, not literal credential headers.
        value = re.sub(r'(<set-header\b[^>]*name=["\'](?:Authorization|api-key|Ocp-Apim-Subscription-Key)["\'][^>]*(?<!/)>).*?(</set-header>)',
                       r"\1<value>[REDACTED]</value>\2", value, flags=re.I | re.S)
        value = re.sub(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}", "Bearer [REDACTED]", value, flags=re.I)
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Reader:
    def __init__(self, folder):
        self.folder = folder
        self.cache = {}
        self.errors = []
        self.sequence = 0
        self.token = ""
        self.opener = None

    def guard(self):
        require(Path(rt.CA).is_file() and rt.ENV.get("REQUESTS_CA_BUNDLE") == rt.CA
                and rt.ENV.get("SSL_CERT_FILE") == rt.CA, "strict_existing_ca_required")
        require(str(rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "")).lower()
                not in ("1", "true", "yes"), "tls_verification_required")
        account = rt.cli(["account", "show"])
        require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
                and account["state"] == "Enabled"
                and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope_mismatch")
        token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                        "--resource", "https://management.azure.com/"])["accessToken"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        require(claims.get("tid") == rt.TENANT and claims.get("oid") == rt.OPERATOR
                and claims.get("aud", "").rstrip("/") in
                ("https://management.azure.com", "https://management.core.windows.net")
                and claims.get("exp", 0) > datetime.now(UTC).timestamp() + 120, "token_identity_mismatch")
        self.token = token
        context = ssl.create_default_context(cafile=rt.CA)
        require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "strict_tls_required")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
        exclusive(self.folder, "scope-guard.json", {"at": stamp(), "subscription": rt.SUB,
            "tenant": rt.TENANT, "operator": rt.OPERATOR, "account_enabled": True,
            "ca_sha256": sha(Path(rt.CA).read_bytes()), "tls_verified": True,
            "token_expires_at": datetime.fromtimestamp(claims["exp"], UTC).isoformat()})

    @staticmethod
    def validate_url(url):
        parts = urlsplit(url)
        require(parts.scheme == "https" and parts.netloc == "management.azure.com"
                and not parts.fragment and not parts.username, "read_url_rejected")
        require(parts.path.startswith(rt.RG + "/providers/") or parts.path ==
                "/subscriptions/" + rt.SUB + "/providers/Microsoft.Authorization/roleAssignments", "read_scope_rejected")
        require(not re.search(r"listkeys|listsecrets|regenerate|/deployments(?:/|$)|/namedvalues(?:/|$)",
                              parts.path, re.I), "forbidden_read_endpoint")

    def get(self, path):
        url = path if path.startswith("https://") else "https://management.azure.com" + path
        self.validate_url(url)
        if url in self.cache:
            return self.cache[url]
        self.sequence += 1
        name = f"read-{self.sequence:03d}"
        exclusive(self.folder, name + "-intent.json", {"at": stamp(), "method": "GET", "url": url})
        try:
            require(self.token and self.opener is not None, "fresh_scope_guard_required")
            request = Request(url, method="GET", headers={"Authorization": "Bearer " + self.token})
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                require(len(raw) <= 8 * 1024 * 1024, "response_size_exceeded")
                value = json.loads(raw)
                receipt = {"at": stamp(), "http_status": response.status, "response_sha256": sha(raw),
                           "request_id": response.headers.get("x-ms-request-id")}
            self.cache[url] = value
            exclusive(self.folder, name + "-result.json", receipt)
            return value
        except Exception as error:
            exclusive(self.folder, name + "-failure.json", {"at": stamp(), **failure(error)})
            raise

    def collection(self, path):
        url = "https://management.azure.com" + path
        expected = urlsplit(url).path
        seen, rows = set(), []
        while url:
            require(url not in seen and len(seen) < 100 and urlsplit(url).path == expected,
                    "pagination_scope_or_cycle")
            seen.add(url)
            page = self.get(url)
            require(isinstance(page.get("value"), list), "collection_shape_invalid")
            rows.extend(page["value"])
            url = page.get("nextLink")
        return {"value": rows, "pages": len(seen), "complete": True}

    def section(self, name, collect):
        print(json.dumps({"at": stamp(), "reading": name}), flush=True)
        try:
            value = collect()
            exclusive(self.folder, name + ".json", scrub(value))
            return value
        except Exception as error:
            item = {"at": stamp(), "section": name, **failure(error)}
            self.errors.append(item)
            exclusive(self.folder, name + "-failure.json", item)
            return None


def settings_projection(settings):
    return {"settings_sha256": sha(settings), "setting_names": sorted(settings),
            "safe_flags": {k: settings.get(k) for k in SAFE_FLAGS}}


def optional_policy(reader, path):
    try:
        return reader.get(path + "/policies/policy?format=xml&api-version=2024-05-01")
    except HTTPError as error:
        if error.code == 404:
            return {"absent": True, "http_status": 404}
        raise


def runtime(reader):
    """Same protected site fields as ratecard_release.snapshot/portal_fix.baseline.

    Use GETs exclusively, cache each response, keep raw settings only in memory.
    A refused appsettings GET is a durable limitation, not permission for POST.
    """
    from scripts.deployment import portal_fix
    sites, settings = {}, {}
    # Read the projection's field lists from the existing safe baseline, not a
    # historical image pin or a stale hardcoded site-name substitute.
    prior = load(rt.HOME / "ratecard-release-20261030/verified.json")["baseline"]
    for kind in KINDS:
        rid = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        app = reader.section(kind + "-site", lambda: reader.get(rid + "?api-version=2024-04-01"))
        web = reader.section(kind + "-web", lambda: reader.get(rid + "/config/web?api-version=2024-04-01"))
        # This is intentionally not /appsettings/list and NEVER a POST.
        def read_settings():
            values = reader.get(rid + "/config/appsettings?api-version=2024-04-01")["properties"]
            settings[kind] = values
            return settings_projection(values)
        reader.section(kind + "-settings", read_settings)
        if app and web:
            props, config = app["properties"], web["properties"]
            template = prior["runtime"]["sites"][kind]["protected"]
            protected = {k: props.get(k) for k in template if k not in ("identity", "web")}
            protected["identity"] = app.get("identity")
            protected["web"] = {k: config.get(k) for k in template["web"]}
            image = config.get("linuxFxVersion", "")
            require(re.fullmatch(r"DOCKER\|pocidstokenexacr.azurecr.io/aiflux-" + kind
                                 + r"@sha256:[a-f0-9]{64}", image), "immutable_pin_required")
            sites[kind] = {"name": app["name"], "image": image, "protected": protected}
    # Module hash makes the reused projection contract auditable without running
    # its release entrypoint or its settings/list POST implementation.
    return {"sites": sites, "settings_hashes": {k: sha(v) for k, v in settings.items()},
            "safe_flags": {k: settings["api"].get(k) for k in SAFE_FLAGS} if "api" in settings else {},
            "projection_source_sha256": sha(Path(portal_fix.__file__).read_bytes()),
            "settings_get_only": True, "all_four_settings_fresh": set(settings) == set(KINDS)}


def storage(reader):
    value = reader.get(rt.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=2023-05-01")
    props = value["properties"]
    actual = {k: props.get(k) for k in ("networkAcls", "publicNetworkAccess", "allowSharedKeyAccess")}
    approved = load(rt.HOME / "storage-firewall-167-103-67-80-20261030/independent-after.json")["account"]
    expected = {k: approved["properties"].get(k) for k in actual}
    return {"id": value["id"], "state_network": actual, "approved_account_projection_equal": actual == expected,
            "exact_five_ips": {r["value"] for r in actual["networkAcls"]["ipRules"]} == FIVE_IPS}


def policy_summary(value):
    tree = ET.fromstring(value["properties"]["value"])
    catalogs = []
    for node in tree.findall(".//set-body"):
        try:
            body = json.loads(node.text or "")
        except ValueError:
            continue
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            catalogs.extend(row["id"] for row in body["data"] if isinstance(row, dict) and "id" in row)
    return {"catalog_aliases": sorted(catalogs), "fragment_references": sorted(
        node.get("fragment-id") for node in tree.findall(".//include-fragment")),
        "forward_requests": len(tree.findall(".//forward-request")), "retry_nodes": len(tree.findall(".//retry")),
        "safety_passes": len(tree.findall(".//llm-content-safety")),
        "managed_identity_audiences": sorted({n.get("resource") for n in tree.findall(".//authentication-managed-identity")}),
        "variable_names": sorted({n.get("name") for n in tree.findall(".//set-variable")}),
        "backend_ids": sorted({n.get("backend-id") for n in tree.findall(".//set-backend-service") if n.get("backend-id")})}


def retained_routing():
    """Selected nonsecret variables from the immutable, already-used ratecard sources."""
    home = rt.HOME / "ratecard-release-20261030"
    proof = load(home / "verified.json")
    return {"ratecard_proof_sha256": sha((home / "verified.json").read_bytes()),
            "ratecard_plan_sha256": proof["plan_sha256"],
            "routing": load(home / "gateway/catalog/fireworks-candidate-routes.json"),
            "retained_api_runtime_config": {k: load(home / "infra/terraform/ratecard_preserved.tf.json")
                ["locals"]["ratecard_settings"]["api"].get(k) for k in SAFE_FLAGS},
            "retained_snapshot": {k: proof["baseline"][k] for k in
                ("active_policy_sha256", "fragment_xml_sha256", "configured_product", "timer_disabled", "cutoff")},
            "routing_files": {str(p.relative_to(rt.ROOT)).replace("\\", "/"): sha(p.read_bytes())
                for p in (home / "gateway/catalog").glob("*.json")}}


def comparison(reader):
    prior = load(rt.HOME / "ratecard-release-20261030/verified.json")["baseline"]
    current = load(reader.folder / "runtime.json")
    sites = {k: {name: v[name] for name in ("image", "protected")} for k, v in current["sites"].items()}
    exact = {"runtime_sites": sites == prior["runtime"]["sites"],
             "settings_hashes": current["settings_hashes"] == prior["settings_hashes"]}
    for path, name, oldkey in ((API + "/policies/policy?format=xml&api-version=2024-05-01", "policy", "active_policy_sha256"),
            (APIM + "/policyFragments/aiflux-dev-unified-poc-settings?format=rawxml&api-version=2024-05-01",
             "poc_fragment", "fragment_xml_sha256")):
        value = reader.cache["https://management.azure.com" + path]
        exact[name] = hashlib.sha256(value["properties"]["value"].encode()).hexdigest() == prior[oldkey]
    state = load(reader.folder / "storage.json")
    exact["storage"] = state["approved_account_projection_equal"] and state["exact_five_ips"]
    flags = current["safe_flags"]
    summary = load(reader.folder / "policy-summary.json")
    return {"at": stamp(), "ratecard_baseline_comparisons": exact,
            "compared_components_equal": all(exact.values()),
            "poc_controls_runtime_enabled": flags.get("AIFLUX_GATEWAY_CONTROLS_POC_ENABLED") == "true",
            "v2_runtime_enabled": flags.get("AIFLUX_GATEWAY_CONTROLS_V2_ENABLED") == "true",
            "poc_fragment_attached_to_active_policy": "aiflux-dev-unified-poc-settings" in summary["fragment_references"],
            "runtime": current, "storage": state,
            "scope": "GET-only metadata baseline; not inference or rollout acceptance"}


def collect(reader):
    for name, suffix in {
        "policy": "/apis/aiflux-dev-unified/policies/policy?format=rawxml",
        "policy-xml": "/apis/aiflux-dev-unified/policies/policy?format=xml",
        "global": "/policies/policy?format=rawxml",
        "global-xml": "/policies/policy?format=xml",
        "api": "/apis/aiflux-dev-unified",
        "gateway": "",
        "legacy-policy": "/apis/aiflux-dev-openai/policies/policy?format=rawxml",
        "native-policy": "/apis/aiflux-native-validation-pending/policies/policy?format=rawxml",
    }.items():
        reader.section(name, lambda suffix=suffix: reader.get(APIM + suffix +
            ("&" if "?" in suffix else "?") + "api-version=2024-05-01"))
    for name, suffix in {"backends": "/backends", "fragments": "/policyFragments", "products": "/products",
                         "subscriptions": "/subscriptions", "operations": "/apis/aiflux-dev-unified/operations",
                         "binding": "/products/aiflux/apis"}.items():
        reader.section(name, lambda suffix=suffix: reader.collection(APIM + suffix + "?api-version=2024-05-01"))
    reader.section("product", lambda: reader.get(APIM + "/products/aiflux?api-version=2024-05-01"))
    for collection, prefix in (("products", "/products/"), ("operations", "/apis/aiflux-dev-unified/operations/")):
        path = reader.folder / (collection + ".json")
        for index, row in enumerate(load(path)["value"] if path.exists() else []):
            require(row["id"].startswith(APIM + prefix), "policy_child_scope_rejected")
            reader.section(f"{collection}-{index:02d}-policy", lambda row=row: optional_policy(reader, row["id"]))
    fragments = load(reader.folder / "fragments.json") if (reader.folder / "fragments.json").exists() else {"value": []}
    for index, row in enumerate(fragments["value"]):
        require(row["id"].startswith(APIM + "/policyFragments/"), "fragment_scope_rejected")
        for fmt in ("rawxml", "xml"):
            reader.section(f"fragment-{index:02d}-{fmt}", lambda row=row, fmt=fmt:
                reader.get(row["id"] + f"?format={fmt}&api-version=2024-05-01"))
    reader.section("runtime", lambda: runtime(reader))
    reader.section("storage", lambda: storage(reader))
    for name, suffix, version in (
        ("vault", "/Microsoft.KeyVault/vaults/pocidstokenexkv", "2023-07-01"),
        ("postgres", "/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg", "2024-08-01"),
        ("postgres-rules", "/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules", "2024-08-01"),
        ("jwt-reference", "/Microsoft.Web/sites/poc-ids-token-ex-api/config/configreferences/appsettings", "2024-04-01"),
    ):
        def read_protected(suffix=suffix, version=version, name=name):
            value = reader.get(rt.RG + "/providers" + suffix + "?api-version=" + version)
            if name == "jwt-reference":
                return rt.reference_metadata(value)
            if name == "postgres-rules":
                require(not value.get("nextLink"), "protected_pagination_incomplete")
                return value
            keys = ("network", "authConfig", "publicNetworkAccess", "networkAcls", "privateEndpointConnections", "enableRbacAuthorization")
            return {k: value["properties"].get(k) for k in keys}
        reader.section(name, read_protected)
    reader.section("role-assignments", lambda: reader.collection("/subscriptions/" + rt.SUB +
        "/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01"))
    reader.section("policy-summary", lambda: policy_summary(load(reader.folder / "policy-xml.json")))
    reader.section("retained-routing", retained_routing)
    reader.section("protected-snapshot", lambda: comparison(reader))


def main():
    folder = HOME / "continuation01"
    # Permanent owner: never auto-resume this continuation or original entrypoint.
    bindings = {name: sha((HOME / name).read_bytes()) for name in ORIGINAL_FILES}
    require(not (HOME / "read-complete.json").exists(), "original_already_complete")
    exclusive(HOME, "continuation-intent.json", {"at": stamp(), "pid": os.getpid(),
        "original_artifacts": bindings, "original_source_sha256": sha(Path(original.__file__).read_bytes()),
        "continuation_source_sha256": sha(Path(__file__).read_bytes()), "method": "GET", "writes": 0,
        "inference": 0, "original_error": "unknown_no_failure_receipt",
        "stop_location": "first_apim_policy_get_or_validation_before_policy_artifact"})
    folder.mkdir()
    reader = Reader(folder)
    try:
        reader.guard()
        retained = load(HOME / "requested.json")
        require(set(retained) == original.ALIASES, "retained_requested_aliases_mismatch")
        collect(reader)
        require(bindings == {name: sha((HOME / name).read_bytes()) for name in ORIGINAL_FILES},
                "original_artifact_changed")
        result = {"at": stamp(), "status": "complete" if not reader.errors else "incomplete",
            "failures": reader.errors, "original_artifacts_unchanged": True, "deployments_reread": False,
            "writes": 0, "inference": 0, "browser_actions": 0, "http_method": "GET",
            "artifacts": {p.name: sha(p.read_bytes()) for p in sorted(folder.glob("*.json"))}}
        exclusive(folder, "result.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "artifacts"}), flush=True)
        return 0 if not reader.errors else 2
    except Exception as error:
        result = {"at": stamp(), "status": "blocked", **failure(error), "writes": 0, "inference": 0}
        exclusive(folder, "failure.json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())