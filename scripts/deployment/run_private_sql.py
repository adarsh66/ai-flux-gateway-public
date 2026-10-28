"""Approved, fixed-scope temporary ACI SQL operator runner (Windows Python 3.13).

No secrets in command arguments, build context, reports or temporary files. ARM
requests carry secureValue properties in memory over verified HTTPS. The API UAMI
is attached for AcrPull only; SQL uses the explicitly supplied human operator token.
Only this run's journaled, ownership-marked resources may be deleted. Subnets do
not support tags, so their delegation name is the ownership marker instead.

Usage: --preflight (read only), --execute, or --cleanup-run RUN_ID.
Operation/status polling implements the ARM LRO protocol with bounded deadlines;
it is not terminal/process polling. Credentials persist outside the repository.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[2]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
CA = ("C:/Users/p4032099/AppData/Local/Temp/"
      "zscaler-login-7860c54ccee94b5d8fa181e004a50458/azure-cli-combined-ca.pem")
SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
OPERATOR = "dd928302-055b-4516-9b8e-b06ae823057b"
RG = f"/subscriptions/{SUB}/resourceGroups/IDS-TOKEN-EXCHANGE-POC"
LOCATION = "southeastasia"
PREFIX = "poc-ids-token-ex"
VNET = f"{RG}/providers/Microsoft.Network/virtualNetworks/{PREFIX}-vnet"
SUBNET = f"{VNET}/subnets/{PREFIX}-sql-runner"
NAT = f"{RG}/providers/Microsoft.Network/natGateways/{PREFIX}-runner-nat"
IP = f"{RG}/providers/Microsoft.Network/publicIPAddresses/{PREFIX}-runner-ip"
ACI = f"{RG}/providers/Microsoft.ContainerInstance/containerGroups/{PREFIX}-sql-runner"
SQL = f"{RG}/providers/Microsoft.Sql/servers/{PREFIX}-sql"
REGISTRY = "pocidstokenexacr"
REGISTRY_HOST = REGISTRY + ".azurecr.io"
IMAGE_TAG = "sql-runner-20261023-r1"
BASE_TAG = "sql-poc-20261022-r1"
NET_API = "2024-05-01"
ACI_API = "2023-05-01"
HOME = Path.home() / ".aiflux-poc"
OWNER_KEY = "aiflux-private-sql-run"
CIDR = "10.240.5.0/24"
DATABASE_URL = (f"mssql+pyodbc://@{PREFIX}-sql.database.windows.net:1433/aiflux?"
                "driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no")
CHECKS = frozenset({"configuration_validated", "private_dns_validated", "odbc18_available",
                    "operator_database_verified", "migration_head_schema_verified",
                    "runtime_dml_identity_verified", "four_portal_accounts_verified",
                    "api_managed_identity_authenticated", "api_managed_identity_dml_verified",
                    "api_managed_identity_ddl_denied"})


class RunnerError(Exception):
    """Only sanitized structured fields are emitted; never stringify exceptions."""

    def __init__(self, code: str, **details: object):
        self.code = code
        self.details = details
        super().__init__(code)


class Redactor:
    def __init__(self) -> None:
        self.values: list[str] = []

    def add(self, value: str) -> str:
        if value:
            self.values.append(value)
        return value

    def text(self, value: str) -> str:
        for secret in sorted(self.values, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
                       "[REDACTED_JWT]", value)
        return value[:4000]


def cli(args: list[str], redactor: Redactor, timeout: int = 180) -> object:
    env = os.environ.copy()
    env.update(REQUESTS_CA_BUNDLE=CA, SSL_CERT_FILE=CA,
               AZURE_CORE_COLLECT_TELEMETRY="false", AZURE_CORE_ONLY_SHOW_ERRORS="true")
    # No caller may pass secret-bearing options; token results are captured only.
    if any(arg in {"--debug", "--verbose", "--body", "--password", "--secure-environment-variables"}
           for arg in args):
        raise RunnerError("unsafe_cli_arguments")
    # get-access-token forbids specifying both tenant and subscription.
    context = [] if "--tenant" in args else ["--subscription", SUB]
    result = subprocess.run([AZ, *args, *context, "--only-show-errors", "-o", "json"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # CLI errors for token acquisition must never echo any of its output.
        details = {} if args[:2] == ["account", "get-access-token"] else {
            "message": redactor.text(result.stderr)}
        raise RunnerError("azure_cli_failed", command=args[:2], exit_code=result.returncode, **details)
    return json.loads(result.stdout) if result.stdout.strip() else None


def current_sid() -> str:
    result = subprocess.run([r"C:\Windows\System32\whoami.exe", "/user", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, check=True)
    sid = next(csv.reader(io.StringIO(result.stdout)))[1]
    if not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
        raise RunnerError("local_sid_rejected")
    return sid


def protect_directory(path: Path) -> None:
    """Remove inherited ACLs before writing any secret; grant only current SID."""
    if os.name != "nt" or path.is_symlink():
        raise RunnerError("windows_secure_directory_required")
    path.mkdir(parents=True, exist_ok=True)
    sid = current_sid()
    # A pre-existing directory might contain explicit grants. Fail closed unless
    # its DACL consists solely of this user's allow ACE (checked with Win32 API).
    import ctypes
    from ctypes import wintypes

    result = subprocess.run([r"C:\Windows\System32\icacls.exe", str(path), "/inheritance:r",
                             "/grant:r", f"*{sid}:(OI)(CI)F"], capture_output=True, check=False)
    if result.returncode:
        raise RunnerError("secure_directory_acl_failed")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    status = advapi.GetNamedSecurityInfoW(wintypes.LPWSTR(str(path)), 1, 4, None, None,
                                         ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if status or not dacl.value:
        raise RunnerError("secure_directory_acl_unverified")
    try:
        class ACL_SIZE_INFORMATION(ctypes.Structure):
            _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD),
                        ("AclBytesFree", wintypes.DWORD)]

        info = ACL_SIZE_INFORMATION()
        if not advapi.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
            raise RunnerError("secure_directory_acl_unverified")
        if info.AceCount != 1:
            raise RunnerError("secure_directory_has_other_grants")
        ace = ctypes.c_void_p()
        if not advapi.GetAce(dacl, 0, ctypes.byref(ace)):
            raise RunnerError("secure_directory_acl_unverified")
        if ctypes.c_ubyte.from_address(ace.value).value != 0:
            raise RunnerError("secure_directory_acl_unverified")
        sid_text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(ctypes.c_void_p(ace.value + 8), ctypes.byref(sid_text)):
            raise RunnerError("secure_directory_acl_unverified")
        try:
            if sid_text.value != sid:
                raise RunnerError("secure_directory_acl_unverified")
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
    finally:
        ctypes.windll.kernel32.LocalFree(descriptor)


def credentials(redactor: Redactor) -> tuple[Path, dict]:
    protect_directory(HOME)
    path = HOME / "credentials.json"
    if path.is_symlink():
        raise RunnerError("credentials_symlink_rejected")
    if path.exists():
        # Existing files must inherit ONLY the secured parent, not explicit grants.
        result = subprocess.run([r"C:\Windows\System32\icacls.exe", str(path), "/reset"],
                                capture_output=True, check=False)
        if result.returncode:
            raise RunnerError("credentials_acl_failed")
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        # This continuation must never rotate credentials, including after a
        # partial seed commit. Recovery requires the existing protected file.
        raise RunnerError("existing_credentials_required")
    if value.get("tenant_id") != TENANT or value.get("database") != "aiflux":
        raise RunnerError("credentials_context_mismatch")
    for user in value["portal_seed_users"]:
        redactor.add(user["password"])
    redactor.add(value["portal_login_secret"])
    return path, value


class Arm:
    def __init__(self, redactor: Redactor):
        self.redactor = redactor
        self.session = requests.Session()
        self.session.verify = CA
        token = cli(["account", "get-access-token", "--resource", "https://management.azure.com/",
                     "--tenant", TENANT], redactor)
        self.session.headers.update(Authorization="Bearer " + redactor.add(token["accessToken"]))
        self.session.headers.update({"Content-Type": "application/json"})

    def request(self, method: str, resource: str, version: str = NET_API,
                body: dict | None = None, missing: bool = False) -> requests.Response:
        url = resource if resource.startswith("https://") else (
            "https://management.azure.com" + resource + "?api-version=" + version)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "management.azure.com":
            raise RunnerError("arm_url_rejected")
        response = self.session.request(method, url, json=body, timeout=(15, 90), allow_redirects=False)
        if missing and response.status_code == 404:
            return response
        if response.status_code not in (200, 201, 202, 204):
            try:
                error = response.json().get("error", {})
            except ValueError:
                error = {}
            raise RunnerError("arm_request_failed", http_status=response.status_code,
                              azure_code=self.redactor.text(str(error.get("code", "unknown"))),
                              message=self.redactor.text(str(error.get("message", "not_json"))),
                              method=method, resource=resource.split("?")[0])
        return response

    def get(self, resource: str, version: str = NET_API) -> dict | None:
        result = self.request("GET", resource, version, missing=True)
        return None if result.status_code == 404 else result.json()

    def operation(self, method: str, resource: str, version: str = NET_API,
                  body: dict | None = None, timeout: int = 1200) -> None:
        response = self.request(method, resource, version, body, missing=method == "DELETE")
        if response.status_code == 404:
            return
        deadline = time.monotonic() + timeout
        poll_url = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
        while time.monotonic() < deadline:
            if poll_url:
                progress = self.request("GET", poll_url)
                data = progress.json() if progress.content else {}
                state = data.get("status", data.get("properties", {}).get("provisioningState"))
                if state in {"Failed", "Canceled", "Cancelled"}:
                    error = data.get("error", {})
                    raise RunnerError("arm_operation_failed", resource=resource,
                                      azure_code=self.redactor.text(str(error.get("code", state))),
                                      message=self.redactor.text(str(error.get("message", ""))))
                if state == "Succeeded":
                    return
            else:
                data = self.get(resource, version)
                if method == "DELETE" and data is None:
                    return
                state = (data or {}).get("properties", {}).get("provisioningState")
                if method != "DELETE" and state == "Succeeded":
                    return
                if state in {"Failed", "Canceled"}:
                    raise RunnerError("arm_operation_failed", resource=resource, azure_code=state)
            # ARM service polling, bounded above; never spin or poll terminals.
            time.sleep(min(10, max(1, int(response.headers.get("Retry-After", "5")))))
        raise RunnerError("arm_operation_timeout", resource=resource)


def preflight(arm: Arm, redactor: Redactor) -> dict:
    account = cli(["account", "show"], redactor)
    if account["id"] != SUB or account["tenantId"] != TENANT or account["user"]["type"] != "user":
        raise RunnerError("azure_account_mismatch")
    provider = arm.get(f"/subscriptions/{SUB}/providers/Microsoft.ContainerInstance", "2021-04-01")
    if provider["registrationState"] != "Registered":
        raise RunnerError("aci_provider_not_registered")
    vnet = arm.get(VNET)
    if not vnet or vnet["location"] != LOCATION:
        raise RunnerError("vnet_context_mismatch")
    candidate = ipaddress.ip_network(CIDR)
    if not any(candidate.subnet_of(ipaddress.ip_network(prefix))
               for prefix in vnet["properties"]["addressSpace"]["addressPrefixes"]):
        raise RunnerError("runner_subnet_outside_vnet")
    for subnet in vnet["properties"].get("subnets", []):
        props = subnet["properties"]
        prefixes = props.get("addressPrefixes", []) + ([props["addressPrefix"]]
                                                       if props.get("addressPrefix") else [])
        if any(candidate.overlaps(ipaddress.ip_network(prefix)) for prefix in prefixes):
            raise RunnerError("runner_subnet_not_vacant", subnet=subnet["id"])
    for resource, version in [(ACI, ACI_API), (SUBNET, NET_API), (NAT, NET_API), (IP, NET_API)]:
        if arm.get(resource, version) is not None:
            raise RunnerError("runner_name_preexists", resource=resource)
    sql = arm.get(SQL, "2023-08-01")
    if sql["properties"].get("publicNetworkAccess") != "Disabled":
        raise RunnerError("sql_public_network_not_disabled")
    admin = arm.get(SQL + "/administrators/ActiveDirectory", "2023-08-01")
    if admin["properties"]["sid"].lower() != OPERATOR:
        raise RunnerError("sql_operator_admin_mismatch")
    site = arm.get(RG + f"/providers/Microsoft.Web/sites/{PREFIX}-api", "2023-12-01")
    identities = site["identity"].get("userAssignedIdentities", {})
    if len(identities) != 1:
        raise RunnerError("api_pull_identity_ambiguous")
    identity_id, identity = next(iter(identities.items()))
    roles = cli(["role", "assignment", "list", "--assignee-object-id", identity["principalId"],
                 "--scope", RG + "/providers/Microsoft.ContainerRegistry/registries/" + REGISTRY,
                 "--include-inherited"], redactor)
    if not any(role.get("roleDefinitionName") == "AcrPull" for role in roles):
        raise RunnerError("api_identity_missing_acrpull")
    # Ensure the existing SQL zone links to the actual VNet; DNS is also validated in-job.
    links = arm.get(RG + "/providers/Microsoft.Network/privateDnsZones/"
                    "privatelink.database.windows.net/virtualNetworkLinks", "2020-06-01")
    if not any(link["properties"].get("virtualNetwork", {}).get("id", "").lower() == VNET.lower()
               and link["properties"].get("provisioningState") == "Succeeded"
               for link in links.get("value", [])):
        raise RunnerError("sql_private_dns_link_missing")
    return {"provider": "Registered", "vacant_subnet": CIDR, "vnet_id": VNET,
            "sql_public_network_access": "Disabled", "operator_admin_verified": True,
            "identity_id": identity_id, "api_client_id": identity["clientId"],
            "acrpull_verified": True, "private_dns_link_verified": True}


def build_image(redactor: Redactor, image_tag: str = IMAGE_TAG) -> dict:
    if not re.fullmatch(r"sql-runner-[0-9]{8}-r[1-9][0-9]*", image_tag):
        raise RunnerError("runner_image_tag_rejected")
    tags = cli(["acr", "repository", "list", "--name", REGISTRY], redactor)
    if "aiflux-sql-runner" in tags:
        existing = cli(["acr", "repository", "show-tags", "--name", REGISTRY,
                        "--repository", "aiflux-sql-runner"], redactor)
        if image_tag in existing:
            raise RunnerError("runner_image_tag_preexists", tag=image_tag)
    base = cli(["acr", "repository", "show", "--name", REGISTRY,
                "--image", "aiflux-api:" + BASE_TAG], redactor)
    digest = base["digest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RunnerError("base_image_digest_rejected")
    # Deliberately upload only two public reviewed files, never the whole workspace.
    with tempfile.TemporaryDirectory(prefix="aiflux-public-build-") as directory:
        context = Path(directory)
        target = context / "scripts/deployment/private_sql_job.py"
        target.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts/deployment/private_sql_job.py", target)
        shutil.copyfile(ROOT / "scripts/deployment/private_sql_diagnostic.py",
                target.with_name("private_sql_diagnostic.py"))
        dockerfile = (ROOT / "infra/sql/private-runner.Dockerfile").read_text(encoding="utf-8")
        dockerfile += ('\nCOPY --chown=10001:10001 scripts/deployment/private_sql_diagnostic.py '
                   '/app/scripts/deployment/private_sql_diagnostic.py\n')
        dockerfile += ('\nRUN python -c "import aiflux, alembic, pyodbc; from pathlib import Path; '
                       "assert Path('/app/services/control-plane/alembic.ini').is_file(); "
                       "assert Path('/app/services/control-plane/migrations/versions').is_dir(); "
                       "assert 'ODBC Driver 18 for SQL Server' in pyodbc.drivers()" + '"\n')
        (context / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        result = cli(["acr", "build", "--registry", REGISTRY, "--image", "aiflux-sql-runner:" + image_tag,
                      "--file", str(context / "Dockerfile"), "--build-arg", "API_IMAGE=" + REGISTRY_HOST +
                      "/aiflux-api@" + digest, "--no-logs", str(context)], redactor, timeout=2400)
    built = cli(["acr", "repository", "show", "--name", REGISTRY,
                 "--image", "aiflux-sql-runner:" + image_tag], redactor)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", built["digest"]):
        raise RunnerError("runner_image_digest_rejected")
    return {"base_image": REGISTRY_HOST + "/aiflux-api@" + digest,
            "image": REGISTRY_HOST + "/aiflux-sql-runner@" + built["digest"],
            "tag": image_tag, "build_id": (result or {}).get("runId"),
            "build_status": (result or {}).get("status")}


def container_body(run_id: str, identity_id: str, client_id: str, image: str,
                   token: str, expiry: int, seeds: str) -> dict:
    command = ["python", "/app/scripts/deployment/private_sql_diagnostic.py", "migrate", "--seed",
               "--verify-api-mi",
               "--sql-host", PREFIX + "-sql.database.windows.net", "--sql-database", "aiflux",
               "--tenant-id", TENANT, "--operator-object-id", OPERATOR,
               "--api-client-id", client_id, "--private-cidr", "10.240.3.0/24"]
    return {"location": LOCATION, "tags": {OWNER_KEY: run_id, "purpose": "temporary-sql-migration"},
            "identity": {"type": "UserAssigned", "userAssignedIdentities": {identity_id: {}}},
            "properties": {"osType": "Linux", "restartPolicy": "Never",
                           "subnetIds": [{"id": SUBNET}],
                           "dnsConfig": {"nameServers": ["168.63.129.16"]},
                           "imageRegistryCredentials": [{"server": REGISTRY_HOST,
                                                          "identity": identity_id}],
                           "containers": [{"name": "sql-migrate", "properties": {
                               "image": image, "command": command,
                               "resources": {"requests": {"cpu": 1, "memoryInGB": 1.5}},
                               "environmentVariables": [
                                   {"name": "AIFLUX_DATABASE_URL", "value": DATABASE_URL},
                                   {"name": "AIFLUX_SQL_OPERATOR_TOKEN", "secureValue": token},
                                   {"name": "AIFLUX_SQL_OPERATOR_TOKEN_EXPIRES_AT",
                                    "secureValue": str(expiry)},
                                   {"name": "AIFLUX_PORTAL_SEED_USERS", "secureValue": seeds}]}}]}}


def sql_token(redactor: Redactor) -> tuple[str, int]:
    result = cli(["account", "get-access-token", "--resource", "https://database.windows.net/",
                  "--tenant", TENANT], redactor)
    token = redactor.add(result["accessToken"])
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if (claims.get("oid") != OPERATOR or claims.get("tid") != TENANT
            or claims.get("aud") not in {"https://database.windows.net", "https://database.windows.net/"}
            or claims.get("exp", 0) - time.time() < 900):
        raise RunnerError("operator_sql_token_rejected_or_short_lived")
    return token, claims["exp"]


def parse_job_log(content: str) -> dict:
    # Raw logs and ACI events may contain arbitrary text; emit only a valid fixed
    # job-status schema. Never relay an unrecognized line, even on failure.
    for line in reversed(content.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict) or value.get("status") not in {"ok", "failed"}:
            continue
        checks = value.get("checks")
        if not isinstance(checks, list) or any(not isinstance(x, str) or x not in CHECKS for x in checks):
            continue
        result = {"status": value["status"], "checks": checks}
        if value["status"] == "failed":
            # Match the runner's declared fixed error vocabulary, not arbitrary JSON.
            source = (ROOT / "scripts/deployment/private_sql_job.py").read_text(encoding="utf-8")
            import ast
            module = ast.parse(source)
            codes = next(ast.literal_eval(node.value.args[0]) for node in module.body
                         if isinstance(node, ast.Assign) and any(
                             isinstance(t, ast.Name) and t.id == "ERROR_CODES" for t in node.targets))
            code = value.get("code")
            result["code"] = code if code in codes or code == "job_failed" else "unrecognized_job_error"
        return result
    return {"status": "unverified", "checks": []}


def parse_diagnostic(content: str) -> dict:
    for line in content.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict) or value.get("diagnostic") != "sql_driver":
            continue
        state = value.get("sqlstate")
        numbers = value.get("native_codes")
        if state is not None and (not isinstance(state, str) or not re.fullmatch(r"[0-9A-Z]{5}", state)):
            continue
        if not isinstance(numbers, list) or any(type(n) is not int or not 0 <= n <= 999999 for n in numbers):
            continue
        result = {"sqlstate": state, "native_codes": numbers}
        from scripts.deployment.private_sql_job import SQL_STAGES
        stage = value.get("stage")
        if type(stage) is str and stage in SQL_STAGES:
            result["stage"] = stage
        return result
    return {}


def parse_runtime_evidence(content: str) -> list[dict]:
    """Only a finite denial vocabulary can cross from untrusted container logs."""
    result = []
    for line in content.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict) or value.get("runtime_probe") != "SQL_DENY_DDL":
            continue
        operation = value.get("operation")
        numbers = value.get("native_codes")
        if (operation not in {"create_table", "create_sequence", "create_type"}
                or value.get("sqlstate") != "42000" or not isinstance(numbers, list)
                or not numbers or any(type(n) is not int or n not in {229, 262, 2760, 15247} for n in numbers)):
            continue
        result.append({"result": "SQL_DENY_DDL", "operation": operation,
                       "sqlstate": "42000", "native_codes": numbers})
    return result


class Execution:
    def __init__(self, arm: Arm, redactor: Redactor, run_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise RunnerError("run_id_rejected")
        self.arm, self.redactor, self.run_id = arm, redactor, run_id
        self.journal_path = HOME / f"private-sql-{run_id}.json"
        self.report: dict = {"run_id": run_id, "status": "running", "resources": [], "cleanup": []}

    def save(self) -> None:
        # The report only contains explicitly selected, sanitized non-secret fields.
        self.journal_path.write_text(json.dumps(self.report, indent=2), encoding="utf-8")

    def create(self, resource: str, body: dict, version: str = NET_API) -> None:
        if self.arm.get(resource, version) is not None:
            raise RunnerError("runner_name_preexists", resource=resource)
        self.report["resources"].append({"id": resource, "version": version})
        self.save()  # Journal BEFORE PUT; failed/partially-created resources need cleanup too.
        self.arm.operation("PUT", resource, version, body)

    def cleanup(self) -> None:
        # Dependency order: ACI releases subnet, then subnet releases NAT, then IP.
        owned = {item["id"]: item["version"] for item in self.report["resources"]}
        for resource in (ACI, SUBNET, NAT, IP):
            if resource not in owned:
                continue
            version = owned[resource]
            try:
                value = self.arm.get(resource, version)
                if value is not None:
                    if resource == SUBNET:
                        props = value["properties"]
                        delegations = props.get("delegations", [])
                        matches = (len(delegations) == 1 and delegations[0]["name"] ==
                                   "aiflux-run-" + self.run_id and props.get("addressPrefix") == CIDR
                                   and props.get("natGateway", {}).get("id", "").lower() == NAT.lower())
                    else:
                        matches = value.get("tags", {}).get(OWNER_KEY) == self.run_id
                    if not matches:
                        raise RunnerError("cleanup_ownership_mismatch", resource=resource)
                    self.arm.operation("DELETE", resource, version, timeout=1200)
                if self.arm.get(resource, version) is not None:
                    raise RunnerError("cleanup_resource_remains", resource=resource)
                self.report["cleanup"].append({"id": resource, "status": "verified_absent"})
            except RunnerError as error:
                self.report["cleanup"].append({"id": resource, "status": "failed",
                                               "code": error.code, **error.details})
            except Exception:
                self.report["cleanup"].append({"id": resource, "status": "failed",
                                               "code": "cleanup_transport_or_local_failure"})
            self.save()

    def collect_evidence(self) -> None:
        """Collect fixed-schema results even when ACI's provisioning LRO failed."""
        if not any(item["id"] == ACI for item in self.report["resources"]):
            return
        try:
            group = self.arm.get(ACI, ACI_API)
            if not group:
                return
            props = group["properties"]
            containers = props.get("containers", [])
            states = [item["properties"].get("instanceView", {}).get("currentState", {})
                      for item in containers]
            state = states[0] if states else {}
            self.report["runtime"] = {
                "state": state.get("state"), "exit_code": state.get("exitCode"),
                "provisioning_state": props.get("provisioningState")}
            events = props.get("instanceView", {}).get("events", [])
            for container in containers:
                events += container["properties"].get("instanceView", {}).get("events", [])
            self.report["aci_events"] = [
                {"name": self.redactor.text(str(event.get("name", ""))),
                 "message": self.redactor.text(str(event.get("message", "")))} for event in events]
            logs = self.arm.request("GET", ACI + "/containers/sql-migrate/logs", ACI_API).json()
            self.report["job"] = parse_job_log(logs.get("content", ""))
            self.report["sql_diagnostic"] = parse_diagnostic(logs.get("content", ""))
            self.report["runtime_probes"] = parse_runtime_evidence(logs.get("content", ""))
        except RunnerError as error:
            self.report["evidence_error"] = {"code": error.code, **error.details}
        except Exception:
            self.report["evidence_error"] = {"code": "evidence_unavailable"}

    def execute(self, image_tag: str = IMAGE_TAG) -> None:
        try:
            self.report["preflight"] = preflight(self.arm, self.redactor)
            path, value = credentials(self.redactor)
            self.report["credentials_path"] = str(path)
            self.report["build"] = build_image(self.redactor, image_tag)
            tags = {OWNER_KEY: self.run_id, "purpose": "temporary-sql-migration"}
            self.create(IP, {"location": LOCATION, "tags": tags, "sku": {"name": "Standard"},
                             "properties": {"publicIPAllocationMethod": "Static",
                                            "publicIPAddressVersion": "IPv4"}})
            self.create(NAT, {"location": LOCATION, "tags": tags, "sku": {"name": "Standard"},
                              "properties": {"idleTimeoutInMinutes": 4,
                                             "publicIpAddresses": [{"id": IP}]}})
            self.create(SUBNET, {"properties": {"addressPrefix": CIDR, "natGateway": {"id": NAT},
                                 "delegations": [{"name": "aiflux-run-" + self.run_id,
                                      "properties": {"serviceName": "Microsoft.ContainerInstance/containerGroups"}}]}})
            token, expiry = sql_token(self.redactor)
            seeds = self.redactor.add(json.dumps(value["portal_seed_users"]))
            pre = self.report["preflight"]
            body = container_body(self.run_id, pre["identity_id"], pre["api_client_id"],
                                  self.report["build"]["image"], token, expiry, seeds)
            self.create(ACI, body, ACI_API)
            del body, token, seeds, value
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                group = self.arm.get(ACI, ACI_API)
                containers = group["properties"].get("containers", [])
                states = [item["properties"].get("instanceView", {}).get("currentState", {})
                          for item in containers]
                if states and states[0].get("state") == "Terminated":
                    self.report["runtime"] = {
                        "state": "Terminated", "exit_code": states[0].get("exitCode"),
                        "provisioning_state": group["properties"].get("provisioningState")}
                    logs = self.arm.request("GET", ACI + "/containers/sql-migrate/logs", ACI_API).json()
                    self.report["job"] = parse_job_log(logs.get("content", ""))
                    probes = parse_runtime_evidence(logs.get("content", ""))
                    expected_operations = {"create_table", "create_sequence", "create_type"}
                    if (states[0].get("exitCode") != 0
                            or self.report["job"]["status"] != "ok"
                            or set(self.report["job"]["checks"]) != CHECKS
                            or {p["operation"] for p in probes} != expected_operations):
                        raise RunnerError("sql_job_not_verified")
                    self.report["status"] = "succeeded"
                    break
                time.sleep(10)  # Bounded ARM workload-state polling, no terminal waits.
            else:
                raise RunnerError("sql_job_timeout")
        except RunnerError as error:
            self.report.update(status="failed", error={"code": error.code, **error.details})
        except Exception as error:
            # Do not render exceptions/tracebacks; request objects may contain tokens.
            self.report.update(status="failed", error={"code": "transport_or_local_failure",
                                                       "exception_type": type(error).__name__})
        finally:
            self.collect_evidence()
            self.cleanup()
            if any(item["status"] != "verified_absent" for item in self.report["cleanup"]):
                self.report["status"] = "cleanup_failed"
            self.save()


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--cleanup-run")
    parser.add_argument("--image-tag", default=IMAGE_TAG,
                        help="New immutable runner tag; existing tags are never overwritten")
    args = parser.parse_args(argv)
    redactor = Redactor()
    try:
        arm = Arm(redactor)
        if args.preflight:
            print(json.dumps(preflight(arm, redactor), indent=2))
            return 0
        protect_directory(HOME)
        execution = Execution(arm, redactor, args.cleanup_run or uuid4().hex)
        if args.cleanup_run:
            execution.report = json.loads(execution.journal_path.read_text(encoding="utf-8"))
            if execution.report.get("run_id") != execution.run_id:
                raise RunnerError("journal_run_id_mismatch")
            execution.cleanup()
        else:
            execution.execute(args.image_tag)
        print(json.dumps(execution.report, indent=2))
        print(json.dumps({"report_path": str(execution.journal_path)}))
        return 0 if execution.report["status"] == "succeeded" else 1
    except RunnerError as error:
        print(json.dumps({"status": "failed", "code": error.code, **error.details}))
    except Exception as error:
        print(json.dumps({"status": "failed", "code": "transport_or_local_failure",
                          "exception_type": type(error).__name__}))
    return 1


if __name__ == "__main__":
    sys.exit(main())