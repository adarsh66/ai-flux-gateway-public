"""One bounded metadata-only observation of the ALREADY consumed Mistral response.

No inference transport, ARM mutations, body columns, retries or redirects. An
exclusive intent consumes this collector too; reconcile retained files on error.
"""
import base64
from datetime import datetime
import json
from pathlib import Path
import sys

import requests
from requests.adapters import HTTPAdapter

from scripts.deployment import foundry_eight_acceptance_successor03 as s

a = s.a
HOME = a.rt.HOME / "mistral-existing-probe-readonly-20261031"
WORKSPACE = "004a359b-dde6-40fb-843c-4d5651785e17"
START = "2026-10-30T17:13:10Z"
END = "2026-10-30T17:13:30Z"
RECEIPT = s.HOME / "probes/08-Mistral-Large-3-response.json"


def queries(row):
    a.require(row["alias"] == "Mistral-Large-3"
              and all(a.clean_id(row[k]) == row[k] for k in ("response_id", "correlation_id")),
              "exact_safe_existing_ids_required")
    scope = (f"\n| where TimeGenerated between (datetime({START}) .. datetime({END}))"
             f"\n| where _ResourceId == '{a.APIM}'"
             f"\n| where CorrelationId == '{row['correlation_id']}'")
    return {
        "llm": ("ApiManagementGatewayLlmLog" + scope
                + f"\n| where RequestId == '{row['response_id']}'"
                + "\n| project TimeGenerated, CorrelationId, RequestId, ModelName, DeploymentName,"
                  " PromptTokens, CompletionTokens, TotalTokens, IsStreamCompletion, SequenceNumber\n| take 2"),
        "gateway": ("ApiManagementGatewayLogs" + scope
                    + "\n| project TimeGenerated, CorrelationId, ResponseCode, BackendResponseCode,"
                      " ApiId, OperationId, ApiRevision\n| take 2"),
    }


def table_rows(body):
    a.require(set(body) == {"tables"} and len(body["tables"]) == 1, "complete_single_query_table_required")
    table = body["tables"][0]
    columns = [c["name"] for c in table["columns"]]
    a.require(len(columns) == len(set(columns)) and len(table["rows"]) == 1,
              "exactly_one_existing_metadata_row_required")
    a.require(len(table["rows"][0]) == len(columns), "metadata_column_shape")
    return dict(zip(columns, table["rows"][0]))


def validate(row, evidence):
    llm, gateway = evidence["llm_row"], evidence["gateway_row"]
    a.require(evidence["llm_row_count_returned"] == evidence["gateway_row_count_returned"] == 1
              and evidence["original_receipt_sha256"] == a.sha(RECEIPT.read_bytes())
              and evidence["original_response_sha256"] == row["response_sha256"]
              and evidence["workspace"] == WORKSPACE
              and evidence["event_time_start_utc"] == START and evidence["event_time_end_utc"] == END,
              "exact_existing_metadata_provenance")
    a.require(llm["RequestId"] == row["response_id"]
              and llm["CorrelationId"] == gateway["CorrelationId"] == row["correlation_id"]
              and llm["DeploymentName"] == row["alias"] == "Mistral-Large-3"
              and llm["ModelName"] == row["response_model"] == "mistral-large-3"
              and gateway["ResponseCode"] == gateway["BackendResponseCode"] == row["status"] == 200
              and gateway["ApiId"] == "aiflux-dev-unified" and gateway["OperationId"] == "chat"
              and llm["TimeGenerated"] == gateway["TimeGenerated"]
              and datetime.fromisoformat(START) <= datetime.fromisoformat(llm["TimeGenerated"]) <= datetime.fromisoformat(END)
              and llm["IsStreamCompletion"] in (False, 0) and llm["SequenceNumber"] == 0,
              "exact_Mistral_correlated_identity_required")
    for key, field in (("prompt_tokens", "PromptTokens"), ("completion_tokens", "CompletionTokens"),
                       ("total_tokens", "TotalTokens")):
        a.require(type(llm[field]) is int and llm[field] == row["usage"][key], "exact_Mistral_correlated_usage")


def collect():
    a.require(not HOME.exists(), "metadata_collector_consumed_no_replay")
    gate = a.applied.reader.worker_gate()
    row = s.bind_receipt(s.HOME, 8, "Mistral-Large-3")
    before = {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes())
              for folder in (s.HOME, s.LEDGER) for p in folder.rglob("*") if p.is_file()}
    HOME.mkdir(exist_ok=False)
    a.write(HOME / "intent.json", {"at": a.now(), "worker_gate": gate, "max_queries": 2,
            "max_rows_per_query": 2, "inference_sends": 0, "retry": 0, "redirects": 0,
            "original_receipt_sha256": a.sha(RECEIPT.read_bytes()), "source_sha256": a.sha(Path(__file__).read_bytes())})
    token = None
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=0))
    session.verify = a.rt.CA
    try:
        a.require(Path(a.rt.CA).is_file(), "trusted_CA_required")
        token = a.cli(["account", "get-access-token", "--subscription", a.rt.SUB,
                       "--resource", "https://api.loganalytics.io"])["accessToken"]
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        a.require(claims["tid"] == a.rt.TENANT and claims["oid"] == a.rt.OPERATOR
                  and claims["exp"] > datetime.now().timestamp() + 120, "existing_identity_only")
        rows = {}
        for name, query in queries(row).items():
            a.write(HOME / (name + "-query.kql"), query.encode())
            response = session.get(f"https://api.loganalytics.azure.com/v1/workspaces/{WORKSPACE}/query",
                params={"query": query, "timespan": START + "/" + END},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                timeout=(15, 60), allow_redirects=False, stream=True)
            with response:
                a.require(response.status_code == 200, "metadata_query_failed_no_retry:" + str(response.status_code))
                raw = response.raw.read(65537)
            a.require(len(raw) <= 65536, "bounded_metadata_response_required")
            a.write(HOME / (name + "-response.json"), raw)
            rows[name] = table_rows(json.loads(raw))
        evidence = {"at": a.now(), "workspace": WORKSPACE, "event_time_start_utc": START,
            "event_time_end_utc": END, "original_receipt_sha256": a.sha(RECEIPT.read_bytes()),
            "original_response_sha256": row["response_sha256"], "llm_row_count_returned": 1,
            "gateway_row_count_returned": 1, "llm_row": rows["llm"], "gateway_row": rows["gateway"],
            "capture_kind": "actual_Entra_authenticated_GET_query_responses_retained",
            "inference_sends": 0, "body_or_message_columns_projected": False,
            "new_policy_observation": False, "tls_bypass": False}
        validate(row, evidence)
        a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in before.items()), "original_bytes_changed")
        a.write(HOME / "evidence.json", evidence)
        a.write(HOME / "integrity.json", {"at": a.now(), "passed": True, "historical_hashes": before,
            "files": {p.name: a.sha(p.read_bytes()) for p in HOME.iterdir() if p.is_file()},
            "queries": 2, "inference_sends": 0, "retry_permitted": False})
        print(json.dumps({"passed": True, "llm_row": rows["llm"], "gateway_row": rows["gateway"], "inference_sends": 0}))
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