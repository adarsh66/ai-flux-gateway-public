"""Bounded APIM candidate verification with exact-plan checks and finally cleanup.

No final-route activation, model deployment, RBAC or network writes. Keys/tokens
exist only in memory; sanitized evidence never includes response text or traces.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from scripts.deployment.apim_route_repair import (
    APIM, SUBSCRIBER, RepairBlocked, conservative_defaults, guard_candidate_plan,
    guard_candidate_rollback, prepare,
)

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".deployment"
TFROOT = ROOT / "infra/project-route"
GATEWAY = "https://poc-ids-token-ex-apim.azure-api.net"
CLI = [r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe", "-X", "utf8", "-IBm", "azure.cli"]


def assess_rpm(first, second, window_seconds=60):
    """A late probe is inconclusive, not failed throttling or passing acceptance.

    Use client monotonic start times, including first-request latency. A 429
    alone could be TPM exhaustion; require rate-policy attribution as well.
    """
    start = first.get("started_monotonic")
    next_start = second.get("started_monotonic")
    if start is None or next_start is None or not 0 <= next_start - start < window_seconds:
        return "inconclusive_window"
    if second["status"] == 429 and (
        second.get("failure_stage") == "rpm" or second.get("error_code") == "RateLimitExceeded"
    ):
        return "rejection_observed"
    return "rejection_not_demonstrated"


class CandidateRun:
    def __init__(self):
        ca = Path(os.environ.get("REQUESTS_CA_BUNDLE", str(Path.home() / ".azure/ca-bundle-zscaler.pem")))
        if not ca.is_file():
            raise RepairBlocked("Verified corporate CA bundle is required")
        os.environ.update(REQUESTS_CA_BUNDLE=str(ca), SSL_CERT_FILE=str(ca),
                          TF_CLI_CONFIG_FILE=str(WORK / "terraform.rc"))
        self.tls = ssl.create_default_context(cafile=str(ca))
        self.token = ""
        self.report = {"started_at": datetime.now(UTC).isoformat(), "checks": [],
                       "final_route_activated": False, "managed_identity_inference_verified": False,
                       "safety_pii_acceptance_verified": False, "monetary_ledger_verified": False}

    def tf(self, *args, text=None):
        p = subprocess.run(["terraform", "-chdir=" + str(TFROOT), *args], input=text,
                           capture_output=True, text=True, timeout=600)
        if p.returncode:
            # Terraform has no key/token arguments. Keep the detailed diagnostic
            # locally for precise policy/compiler failures, not in chat logs.
            (WORK / "project-route-tf-failure.log").write_text(p.stdout + p.stderr)
            self.report["terraform_error"] = (p.stderr or p.stdout)[-5000:]
            raise RepairBlocked("Terraform " + args[0] + " failed; captured exact local diagnostic")
        return p.stdout

    def arm(self, suffix, method="GET"):
        if not self.token:
            p = subprocess.run(CLI + ["account", "get-access-token", "--resource",
                                     "https://management.azure.com/", "-o", "json"],
                               capture_output=True, text=True, encoding="utf-8", timeout=90)
            if p.returncode:
                raise RepairBlocked("Azure CLI ARM authentication failed")
            self.token = json.loads(p.stdout.lstrip("\ufeff"))["accessToken"]
        separator = "&" if "?" in suffix else "?"
        req = urllib.request.Request("https://management.azure.com" + APIM + suffix + separator +
                                     "api-version=2024-05-01", method=method,
                                     headers={"Authorization": "Bearer " + self.token})
        with urllib.request.urlopen(req, context=self.tls, timeout=60) as response:
            return json.load(response)

    def verify_baseline(self, artifact):
        for name, suffix in (("global", "/policies/policy"),
                             ("dev", "/apis/aiflux-dev-openai/policies/policy"),
                             ("native", "/apis/aiflux-native-validation-pending/policies/policy")):
            value = self.arm(suffix + "?format=rawxml")["properties"]["value"]
            if hashlib.sha256(value.encode()).hexdigest() != artifact["baseline"][name]["sha256"]:
                raise RepairBlocked("Protected " + name + " policy baseline changed")

    def probe(self, name, path, *, key=None, body=None, origin=None, method=None, absent_text=None):
        started_at = datetime.now(UTC).isoformat()
        started = time.monotonic()
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Ocp-Apim-Subscription-Key"] = key
        if origin:
            headers["Origin"] = origin
        if method == "OPTIONS":
            headers.update({"Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "content-type,ocp-apim-subscription-key"})
        req = urllib.request.Request(GATEWAY + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     method=method)
        try:
            response = urllib.request.urlopen(req, context=self.tls, timeout=65)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(100000)
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            result = {"name": name, "at": datetime.now(UTC).isoformat(), "status": response.status,
                      "started_at": started_at, "started_monotonic": started,
                      "elapsed_seconds": round(time.monotonic() - started, 6),
                      "error_code": (data.get("error") or {}).get("code"),
                      "assistant_text": isinstance(text, str) and bool(text.strip()),
                      "allow_origin": response.headers.get("Access-Control-Allow-Origin"),
                      "retry_after": response.headers.get("Retry-After"), "usage": data.get("usage")}
            result["response_model"] = data.get("model")
            result["finish_reason"] = (data.get("choices") or [{}])[0].get("finish_reason")
            # Only fixed numeric diagnostic headers; never arbitrary headers,
            # service bodies, echoed request content or subscription keys.
            for header in ("x-aiflux-rpm-remaining", "x-aiflux-rpm-limit",
                           "x-aiflux-tpm-remaining", "x-aiflux-daily-tokens-remaining"):
                value = response.headers.get(header)
                if value is not None and value.isascii() and value.isdigit() and len(value) <= 12:
                    result[header] = int(value)
            stage = response.headers.get("x-aiflux-failure-stage")
            if stage in ("safety", "pii", "identity", "tokens", "rpm", "quota", "other"):
                result["failure_stage"] = stage
            self.report["checks"].append(result)
            if absent_text is not None:
                result["fixture_absent"] = isinstance(text, str) and absent_text.casefold() not in text.casefold()
            return result

    def wait_for_candidate(self, base, key):
        # APIM control-plane success precedes gateway configuration propagation.
        # Poll only the static models operation: NEVER retry a model POST.
        for attempt in range(25):
            result = self.probe("candidate_models", base + "/models", key=key)
            if result["status"] == 200:
                return
            # Fresh product/API bindings can reach different gateway workers
            # before subscription caches converge. Static authenticated GET
            # only: bounded propagation waiting never relaxes authentication.
            if result["status"] not in (401, 404, 503):
                raise RepairBlocked("Candidate models rejected before inference")
            if attempt < 24:
                time.sleep(5)
        raise RepairBlocked("Candidate models did not become ready within bounded propagation window")

    def run(self):
        artifact = json.loads((WORK / "project-route-baseline.json").read_text())
        variables = WORK / "project-route-candidate.tfvars.json"
        saved = WORK / "project-candidate.tfplan"
        plan = json.loads(self.tf("show", "-json", str(saved)))
        output = self.tf("console", "-no-color", "-var-file=" + str(variables), text=
                         "jsonencode({policy=local.policy,global=local.global_policy,global_format=var.global_policy_format,children=local.children})\n")
        rendered = json.loads(json.loads(output[output.find('"'):].strip()))
        snapshot = artifact["snapshot"]
        readiness = prepare(snapshot, configuration=conservative_defaults(snapshot), candidate_validation=True)
        guard_candidate_plan(plan, rendered, artifact["baseline"]["global_export"]["value"], readiness)
        status = json.loads((ROOT / ".azure/validate-status.json").read_text())
        document = (ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
        if status.get("completedStep") != "UpdateStatus" or "Candidate validation status: Validated" not in document:
            raise RepairBlocked("Current restricted-candidate validation workflow is incomplete")
        self.verify_baseline(artifact)
        self.report["candidate_plan_sha256"] = hashlib.sha256(saved.read_bytes()).hexdigest()
        # Once apply is attempted, cleanup runs even after a partial apply,
        # compiler rejection, HTTP failure or interruption.
        try:
            self.tf("apply", "-no-color", "-input=false", str(saved))
            self.report["candidate_applied"] = True
            base = "/dev/llm/validate/v1"
            secret = self.arm("/subscriptions/" + SUBSCRIBER + "/listSecrets", "POST")
            key = secret["primaryKey"]
            self.wait_for_candidate(base, key)
            missing = self.probe("missing_key", base + "/models")
            invalid = self.probe("invalid_key", base + "/models", key="invalid-validation-key")
            if missing["status"] != 401 or invalid["status"] != 401:
                raise RepairBlocked("Missing/invalid subscription rejection failed")
            body = {"model": "gpt-5.6-luna", "messages": [{"role": "user", "content": "Say hello."}],
                    "max_completion_tokens": 32, "stream": False}
            unsupported = self.probe("unsupported_model", base + "/chat/completions", key=key, body={**body, "model": "unapproved"})
            if unsupported["status"] != 400 or unsupported["error_code"] != "unsupported_request_shape":
                raise RepairBlocked("Unsupported model rejection failed")
            benign = self.probe("bounded_managed_identity_completion", base + "/chat/completions", key=key, body=body)
            self.report["managed_identity_inference_verified"] = benign["status"] == 200 and benign["assistant_text"]
            if not self.report["managed_identity_inference_verified"]:
                raise RepairBlocked("Single bounded managed-identity completion failed")
            rpm = self.probe("rpm_rejection", base + "/chat/completions", key=key, body=body)
            outcome = assess_rpm(benign, rpm)
            self.report["rpm_probe_outcome"] = outcome
            self.report["rpm_rejection_observed"] = outcome == "rejection_observed"
            if outcome != "rejection_observed":
                raise RepairBlocked("RPM acceptance not established: " + outcome)
            # Successful benign forwarding necessarily traverses original,
            # redacted and outbound safety plus PII. It is NOT proof of all
            # negative safety/PII/quota tests, so acceptance stays false.
            key = None
            secret.clear()
        finally:
            self.cleanup(plan, artifact)
            self.report["finished_at"] = datetime.now(UTC).isoformat()
            (WORK / "project-route-live-result.json").write_text(json.dumps(self.report, indent=2))

    def cleanup(self, candidate_plan, artifact):
        export = artifact["baseline"]["global_export"]
        path = WORK / "project-route-rollback.tfvars.json"
        path.write_text(json.dumps({"enabled": False, "candidate_validation": True,
                                    "global_policy_format": export["format"],
                                    "restore_global_policy": export["value"]}))
        saved = WORK / "project-route-rollback.tfplan"
        self.tf("plan", "-no-color", "-input=false", "-var-file=" + str(path), "-out=" + str(saved))
        rollback = json.loads(self.tf("show", "-json", str(saved)))
        if any(x["change"]["actions"] not in (["read"], ["no-op"]) for x in rollback.get("resource_changes", [])):
            guard_candidate_rollback(rollback, candidate_plan, export)
            self.tf("apply", "-no-color", "-input=false", str(saved))
        self.verify_baseline(artifact)
        apis = self.arm("/apis")["value"]
        backends = self.arm("/backends")["value"]
        if any(x["name"] in ("aiflux-project-validation", "aiflux-dev-unified") for x in apis) or any(
            x["name"].startswith("aiflux-project-") for x in backends
        ):
            raise RepairBlocked("Candidate absence verification failed")
        self.report["cleanup_verified"] = True


def main():
    execution = CandidateRun()
    try:
        execution.run()
        print(json.dumps(execution.report, indent=2))
        return 0
    except (RepairBlocked, urllib.error.URLError, subprocess.SubprocessError) as exc:
        execution.report["failure"] = type(exc).__name__ + ": " + str(exc)
        (WORK / "project-route-live-result.json").write_text(json.dumps(execution.report, indent=2))
        # No raw service body, key, token, request text or assistant text.
        print(json.dumps({k: v for k, v in execution.report.items() if k != "terraform_error"}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())