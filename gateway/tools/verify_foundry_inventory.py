"""Read public Foundry metadata only; emit a snapshot, never enable routes.

Project deployments use the azure-ai-projects 2.9.0 documented v1 contract:
GET {projectEndpoint}/deployments?api-version=v1 (audience https://ai.azure.com).
Parent ARM deployments are not the Foundry model catalog. With no connections,
the verified project's parent account is the supported deployment scope.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


class InventoryReadError(RuntimeError):
    def __init__(self, stage: str, *, permission_denied: bool = False):
        super().__init__(f"Foundry inventory read failed at {stage}; no usable snapshot produced")
        self.permission_denied = permission_denied


def collect(project_endpoint: str, project_resource_id: str, read) -> dict:
    account, separator, project = project_resource_id.rpartition("/projects/")
    if not separator or not project or not account:
        raise InventoryReadError("project scope")
    expected = f"https://{account.rsplit('/', 1)[-1].lower()}.services.ai.azure.com/api/projects/{project}"
    if project_endpoint.rstrip("/") != expected:
        raise InventoryReadError("project endpoint mismatch")
    arm = "https://management.azure.com"
    version = "?api-version=2025-06-01"
    parent = read(arm + account + version, "account", None)
    resource = read(arm + project_resource_id + version, "project", None)
    for data, expected_id in ((parent, account), (resource, project_resource_id)):
        if data.get("id", "").lower() != expected_id.lower():
            raise InventoryReadError("resource identity")
        if data.get("properties", {}).get("provisioningState") != "Succeeded":
            raise InventoryReadError("resource state")
    advertised = resource["properties"].get("endpoints", {}).get("AI Foundry API")
    if advertised != project_endpoint.rstrip("/"):
        raise InventoryReadError("advertised endpoint")

    def pages(url: str, stage: str, audience=None) -> list[dict]:
        items = []
        seen = set()
        while url:
            if url in seen:
                raise InventoryReadError(stage + " pagination loop")
            seen.add(url)
            data = read(url, stage, audience)
            values = data.get("value", data.get("data"))
            if not isinstance(values, list):
                raise InventoryReadError(stage + " malformed response")
            items.extend(values)
            following = data.get("nextLink")
            if following and (
                urlsplit(following).scheme != "https"
                or urlsplit(following).netloc != urlsplit(url).netloc
                or urlsplit(following).path != urlsplit(url).path
            ):
                raise InventoryReadError(stage + " pagination scope")
            url = following
        return items

    connections = pages(arm + project_resource_id + "/connections" + version, "connections")
    if connections:
        raise InventoryReadError("connected resources require explicit joined deployment evidence")
    deployments = pages(arm + account + "/deployments" + version, "deployments")
    project_read = "Succeeded"
    try:
        # Enumerate all pages, but do not mistake deployment discovery for ARM state.
        pages(project_endpoint.rstrip("/") + "/deployments?api-version=v1", "project deployments",
              "https://ai.azure.com")
    except InventoryReadError as exc:
        if not exc.permission_denied:
            raise
        project_read = "PermissionDenied"
    result = []
    for deployment in deployments:
        props = deployment.get("properties", {})
        model = props.get("model", {})
        name = deployment.get("name", "")
        if deployment.get("id", "").lower() != (account + "/deployments/" + name).lower():
            raise InventoryReadError("deployment scope")
        result.append({
            "id": deployment["id"], "name": name,
            "model_name": model.get("name", ""), "model_version": model.get("version", ""),
            "model_format": model.get("format", ""),
            "provisioning_state": props.get("provisioningState", "Unknown"),
            "deployment_state": props.get("deploymentState"),
            "capacity": props.get("currentCapacity", 0),
            "chat_completion": props.get("capabilities", {}).get("chatCompletion") == "true",
            "decision": props.get("capabilities", {}).get("decision") == "true",
            "sku": deployment.get("sku", {}).get("name"),
        })
    return {
        "schema_version": 1, "verified_at": datetime.now(UTC).isoformat(),
        "project_endpoint": project_endpoint.rstrip("/"), "project_resource_id": project_resource_id,
        "account_resource_id": parent["id"], "account_read": "Succeeded", "project_read": "Succeeded",
        "connections_read": "Succeeded", "connection_ids": [],
        "project_deployments_read": project_read, "deployments": result,
        # Gateway acceptance is a separate review; existence NEVER enables inference.
        "routes": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-endpoint", required=True)
    parser.add_argument("--project-resource-id", required=True)
    parser.add_argument("--azure-cli", default="az")
    args = parser.parse_args()
    command = [args.azure_cli]
    bundled = Path(args.azure_cli).parent.parent / "python.exe"
    if args.azure_cli.lower().endswith("az.cmd") and bundled.is_file():
        command = [str(bundled), "-X", "utf8", "-IBm", "azure.cli"]

    def read(url: str, stage: str, audience: str | None):
        argv = command + ["rest", "--method", "get", "--url", url, "--output", "json"]
        if audience:
            argv += ["--resource", audience]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=60)
            if proc.returncode:
                # Never print raw CLI output, tokens, keys, or connection properties.
                denied = (
                    stage == "project deployments"
                    # az rest can omit the service's explanatory message; accept
                    # only its structured PermissionDenied code, not generic
                    # AuthorizationFailed, 401, network errors, or an empty list.
                    and re.search(r'"code"\s*:\s*"PermissionDenied"', proc.stderr) is not None
                )
                raise InventoryReadError(stage, permission_denied=denied)
            return json.loads(proc.stdout.lstrip("\ufeff"))
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise InventoryReadError(stage) from exc

    try:
        print(json.dumps(collect(args.project_endpoint, args.project_resource_id, read), indent=2))
        return 0
    except InventoryReadError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())