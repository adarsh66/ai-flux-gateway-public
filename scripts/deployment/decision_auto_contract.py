"""One exclusive, benign wire-contract probe. Never impersonates runtime MI."""
from datetime import UTC, datetime
import json
import ssl
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.deployment import runtime_rollout as rt

ENDPOINT = "https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone"


def main():
    prior = rt.HOME / "decision-auto-preflight-20261029T015732703490Z/readiness.json"
    metadata = json.loads(prior.read_text(encoding="utf-8"))
    folder = rt.HOME / ("decision-auto-contract-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    report = {"at_utc": datetime.now(UTC).isoformat(), "cloud_configuration_writes": 0,
              "runtime_managed_identity_proven": False, "inference_requests": 0}
    stage = "assignments"
    try:
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
        rows = rt.cli(["role", "assignment", "list", "--scope", rt.RG
                       + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry",
                       "--include-inherited", "--subscription", rt.SUB])
        report["assignments"] = [{k: r.get(k) for k in ("principalId", "roleDefinitionId", "roleDefinitionName", "scope", "condition")}
                                 for r in rows]
        if "--probe" in sys.argv:
            stage = "probe"
            # Exclusive budget intent is durable BEFORE the only billable request.
            budget = {"max_requests": 1, "max_choices": 2, "max_state_characters": 128,
                      "completion_requests": 0, "automatic_retries": 0, "load_tests": 0,
                      "identity": "existing_operator_not_runtime_MI", "usage_cost": "unknown_until_response",
                      "endpoint": ENDPOINT, "token_scope": "https://cognitiveservices.azure.com/.default"}
            (folder / "probe-intent.json").write_text(json.dumps(budget, indent=2), encoding="utf-8")
            deployments = metadata["decision_deployments"]
            rt.require(len(deployments) == 1 and deployments[0]["state"] == "Succeeded", "exact_deployment")
            body = {"model": deployments[0]["name"], "state": "Please greet me in one short sentence.",
                    "questions": {"route": {"type": "choice", "instructions": "Which task is requested?",
                        "criteria": {"greeting": "A short greeting", "arithmetic": "A numerical calculation"}}}}
            token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                            "--resource", "https://cognitiveservices.azure.com/"])["accessToken"]
            request = Request(ENDPOINT, data=json.dumps(body).encode(), method="POST",
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            report["inference_requests"] = 1
            with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=15) as response:
                raw = response.read(65537)
                rt.require(len(raw) <= 65536, "response_bound")
                report["http_status"] = response.status
                report["response"] = json.loads(raw)
            report["status"] = "operator_wire_probe_complete_runtime_MI_not_proven"
        else:
            report["status"] = "assignments_read_runtime_MI_not_proven"
    except Exception as exc:
        report.update(status="blocked", failed_stage=stage, error_type=type(exc).__name__,
                      http_status=getattr(exc, "code", None))
        if isinstance(exc, HTTPError):
            # Only fixed error code, not arbitrary response text or credentials.
            try:
                error = json.loads(exc.read(65536)).get("error", {})
                code = error.get("code") if isinstance(error, dict) else None
                report["error_code"] = code if isinstance(code, str) and code.isalnum() else None
            except Exception:
                pass
    (folder / "readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": folder.relative_to(rt.ROOT).as_posix(), **{k: v for k, v in report.items()
                      if k not in ("assignments", "response")}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())