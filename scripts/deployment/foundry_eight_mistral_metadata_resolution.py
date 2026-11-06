"""Sole remaining metadata query; join existing LLM/gateway rows, never inference.

The first collector retained an empty table (exact resource-ID casing filter).
Azure resource IDs use case-insensitive comparison; deployment/model names do NOT.
Only ONE additional query is permitted: two queries total across both captures.
"""
import base64
from datetime import datetime
import json
from pathlib import Path
import sys

import requests
from requests.adapters import HTTPAdapter

from scripts.deployment import foundry_eight_mistral_metadata as prior

a, s = prior.a, prior.s
HOME = a.rt.HOME / "mistral-existing-probe-resolution-20261031"


def query(row):
    original = prior.queries(row)
    scope = (f"\n| where TimeGenerated between (datetime({prior.START}) .. datetime({prior.END}))"
             f"\n| where _ResourceId =~ '{a.APIM}'"
             f"\n| where CorrelationId == '{row['correlation_id']}'")
    return ("let gateway = ApiManagementGatewayLogs" + scope
            + "\n| project GatewayTime=TimeGenerated, CorrelationId, ResponseCode, BackendResponseCode, ApiId, OperationId, ApiRevision;\n"
            + original["llm"].replace("_ResourceId ==", "_ResourceId =~").replace("\n| take 2", "")
            + "\n| join kind=inner gateway on CorrelationId\n| take 2")


def collect():
    a.require(not HOME.exists(), "resolution_query_consumed_no_replay")
    a.require(a.load(prior.HOME / "llm-response.json")["tables"][0]["rows"] == []
              and not (prior.HOME / "gateway-response.json").exists()
              and a.load(prior.HOME / "failure.json")["reason"] == "exactly_one_existing_metadata_row_required",
              "sole_first_query_empty_table_required")
    gate = a.applied.reader.worker_gate()
    row = s.bind_receipt(s.HOME, 8, "Mistral-Large-3")
    HOME.mkdir(exist_ok=False)
    a.write(HOME / "intent.json", {"at": a.now(), "worker_gate": gate, "max_queries": 1,
        "total_queries_across_both_collectors": 2, "inference_sends": 0, "retry": 0, "redirects": 0,
        "previous_failed_capture": prior.HOME.relative_to(a.ROOT).as_posix(),
        "source_sha256": a.sha(Path(__file__).read_bytes())})
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=0))
    session.verify = a.rt.CA
    token = None
    try:
        a.require(Path(a.rt.CA).is_file(), "trusted_CA_required")
        token = a.cli(["account", "get-access-token", "--subscription", a.rt.SUB,
                       "--resource", "https://api.loganalytics.io"])["accessToken"]
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        a.require(claims["tid"] == a.rt.TENANT and claims["oid"] == a.rt.OPERATOR
                  and claims["exp"] > datetime.now().timestamp() + 120, "existing_identity_only")
        text = query(row)
        a.write(HOME / "joined-query.kql", text.encode())
        response = session.get(f"https://api.loganalytics.azure.com/v1/workspaces/{prior.WORKSPACE}/query",
            params={"query": text, "timespan": prior.START + "/" + prior.END},
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            timeout=(15, 60), allow_redirects=False, stream=True)
        with response:
            a.require(response.status_code == 200, "metadata_query_failed_no_retry:" + str(response.status_code))
            raw = response.raw.read(65537)
        a.require(len(raw) <= 65536, "bounded_metadata_response_required")
        a.write(HOME / "joined-response.json", raw)
        joined = prior.table_rows(json.loads(raw))
        gateway = {k: joined[k] for k in ("CorrelationId", "ResponseCode", "BackendResponseCode", "ApiId", "OperationId", "ApiRevision")}
        gateway["TimeGenerated"] = joined["GatewayTime"]
        llm = {k: v for k, v in joined.items() if k not in gateway and k not in ("GatewayTime", "CorrelationId1")}
        llm.update(TimeGenerated=joined["TimeGenerated"], CorrelationId=joined["CorrelationId"])
        evidence = {"at": a.now(), "workspace": prior.WORKSPACE,
            "event_time_start_utc": prior.START, "event_time_end_utc": prior.END,
            "original_receipt_sha256": a.sha(prior.RECEIPT.read_bytes()),
            "original_response_sha256": row["response_sha256"], "llm_row_count_returned": 1,
            "gateway_row_count_returned": 1, "llm_row": llm, "gateway_row": gateway,
            "capture_kind": "actual_Entra_authenticated_GET_joined_query_response_retained",
            "inference_sends": 0, "body_or_message_columns_projected": False,
            "resource_id_comparison_only_case_insensitive": True, "model_identity_comparison": "exact_case_sensitive",
            "new_policy_observation": False, "tls_bypass": False}
        prior.validate(row, evidence)
        a.write(HOME / "evidence.json", evidence)
        a.write(HOME / "integrity.json", {"at": a.now(), "passed": True,
            "files": {p.name: a.sha(p.read_bytes()) for p in HOME.iterdir() if p.is_file()},
            "prior_failed_capture_files": {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes())
                                           for p in prior.HOME.iterdir() if p.is_file()},
            "queries_total": 2, "inference_sends": 0, "retry_permitted": False})
        print(json.dumps({"passed": True, "llm_row": llm, "gateway_row": gateway, "inference_sends": 0}))
    except Exception as error:
        a.write(HOME / "failure.json", {"at": a.now(), "error_type": type(error).__name__,
            "reason": str(error) if isinstance(error, a.AcceptanceError) else "sensitive_details_suppressed",
            "retry_permitted": False, "inference_sends": 0})
        raise
    finally:
        token = None
        session.close()


if __name__ == "__main__":
    a.require(sys.argv[1:] == ["collect"], "explicit_metadata_read_only")
    collect()