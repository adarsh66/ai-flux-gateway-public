"""Parent-review-gated literal ARM diagnostic on the already owned revision 2.

prepare performs GETs only. No Terraform, build, inference or browser execution.
Each mutation needs a separately bound real parent review and a durable intent.
No historical executor entrypoint is invoked. Never persist bearer/raw scoring data.
"""
import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, unescape

from scripts.deployment import auto_revision_arm_once as a
from scripts.deployment.apim_route_repair import SUBSCRIBER

p = a.p
require = a.require
OUT = a.HOME / "scoring-diagnostic01"
TEMPLATE = Path(__file__).with_name("auto_diagnostic_score.xml")
CHAT_PATH = "/dev/llm/v1;rev=2/chat/completions"
POLICY_URL = "https://management.azure.com" + a.RID + "/policies/policy?api-version=" + p.VERSION
TEXT = "Please greet me in one short sentence."
IP = "167.103.63.12"
TEST = p.rt.ROOT / "tests/unit/test_auto_diagnostic_stage.py"
DOC = p.rt.ROOT / "docs/auto-diagnostic-review-20261029.md"
OWN_FILES = (Path(__file__), TEMPLATE, TEST, DOC)


def load(name):
    return a.load(OUT / name)


def save(name, value):
    p.backend.save(OUT, name, value)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def tree(value, exported=False):
    """One *observed* XML-export entity layer; never generic html.unescape.

    Only inter-element indentation is cosmetic. C# text, attribute spaces and
    entities remain significant; no whitespace collapse inside expressions.
    """
    root = ET.fromstring(value)
    if exported:
        for node in root.iter():
            node.attrib.update({k: unescape(v, {"&quot;": '"', "&apos;": "'"}) for k, v in node.attrib.items()})
            if node.text:
                node.text = unescape(node.text, {"&quot;": '"', "&apos;": "'"})
    return root


def signature(root):
    def node(n):
        text = n.text or ""
        if len(n) and not text.strip():
            text = ""
        return (n.tag, tuple(sorted(n.attrib.items())), text,
                tuple((node(c), c.tail if (c.tail or "").strip() else "") for c in n))
    return node(root)


def raw_signature(raw, expected):
    """Verify rawxml even when APIM emits unescaped C# quotes in attributes.

    Match complete source-known expression literals (or exactly XML-escaped
    literals), replace with unique markers, then parse the entire remaining
    document. No inferred delimiter repair or whitespace/entity folding.
    """
    reference = deepcopy(expected)
    expressions = {(key, value) for n in reference.iter() for key, value in n.attrib.items() if value.startswith("@")}
    for index, (key, value) in enumerate(sorted(expressions)):
        marker = "expression_" + str(index)
        matches = sum(n.attrib.get(key) == value for n in reference.iter())
        # APIM retains mixed XML escaping within an expression (e.g. &lt; but
        # literal &&). Only these three XML encodings may vary, never C# chars.
        tokens = {"&": "(?:&amp;|&)", "<": "(?:&lt;|<)", ">": "(?:&gt;|>)"}
        pattern = re.escape(key + '="') + "".join(tokens.get(c, re.escape(c)) for c in value) + '"'
        raw, count = re.subn(pattern, lambda _: key + '="' + marker + '"', raw)
        require(count == matches, "raw_export_exact_expression_literals")
        for n in reference.iter():
            if n.attrib.get(key) == value:
                n.set(key, marker)
    require(signature(tree(raw)) == signature(reference), "raw_export_complete_structure_and_text")
    return signature(expected)


def post(root):
    found = root.findall('./inbound/choose/when[@condition=\'@(context.Request.Method == "POST")\']')
    require(len(found) == 1, "single_original_POST_branch")
    return found[0]


def reject(condition, code):
    n = ET.Element("choose")
    w = ET.SubElement(n, "when", condition=condition)
    r = ET.SubElement(w, "return-response")
    ET.SubElement(r, "set-status", code="403", reason="Diagnostic closed")
    for name, value in (("Content-Type", "application/json"), ("Cache-Control", "no-store")):
        ET.SubElement(ET.SubElement(r, "set-header", name=name, **{"exists-action": "override"}), "value").text = value
    ET.SubElement(r, "set-body").text = json.dumps({"error": {"code": code}}, separators=(",", ":"))
    return n


def scope_guard(start, end):
    condition = ('@(context.Subscription == null || context.Product == null || context.Product.Id != "aiflux"'
                 + ' || context.Subscription.Id != "' + SUBSCRIBER + '" || context.Request.IpAddress != "' + IP + '"'
                 + ' || context.Api.Revision != "2" || context.Request.Method != "POST"'
                 + ' || context.Request.OriginalUrl.Path != "' + CHAT_PATH + '"'
                 + ' || DateTime.UtcNow < DateTime.Parse("' + start + '").ToUniversalTime()'
                 + ' || DateTime.UtcNow >= DateTime.Parse("' + end + '").ToUniversalTime())')
    return reject(condition, "diagnostic_scope_closed")


def fixed_guard():
    fixed = ('@{ var body = JObject.Parse((string)context.Variables["aiflux-request-json"]);'
             ' var messages = body["messages"] as JArray;'
             ' return (string)body["model"] != "gpt-5.4-mini" || messages == null || messages.Count != 1'
             ' || (string)messages[0]["role"] != "user" || (string)messages[0]["content"] != "' + TEXT + '"; }')
    return reject(fixed, "diagnostic_fixed_input_required")


def render(original, nonce, start, end):
    require(re.fullmatch(r"[a-f0-9]{32}", nonce) is not None, "diagnostic_nonce")
    begin, finish = datetime.fromisoformat(start), datetime.fromisoformat(end)
    require(begin.utcoffset() == finish.utcoffset() == timedelta(0)
            and timedelta(0) < finish - begin <= timedelta(minutes=20), "bounded_UTC_window")
    root = tree(original)
    inbound = root.find("inbound")
    require(inbound is not None and inbound[0].tag == "cors" and inbound[1].tag == "base", "copied_CORS_then_base")
    # Inherited gate is retained and still runs, never bypassed by diagnostics.
    inbound.insert(2, scope_guard(start, end))
    branch = post(root)
    index = next(i for i, n in enumerate(branch) if n.get("name") == "aiflux-model")
    branch.insert(index, fixed_guard())
    checks = [i for i, n in enumerate(branch) if n.tag == "llm-content-safety"]
    require(len(checks) == 2, "exact_two_copied_input_scans")
    stop = checks[-1] + 1
    gate = ET.Element("limit-concurrency", key='@("auto-diagnostic:' + nonce + '")', **{"max-count": "1"})
    ET.SubElement(gate, "quota-by-key", calls="1", **{"renewal-period": "3600", "counter-key": '@("auto-diagnostic:' + nonce + '")'})
    for n in tree(TEMPLATE.read_bytes()):
        gate.append(deepcopy(n))
    branch.insert(stop, gate)
    candidate = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    guard(original, candidate, nonce, start, end)
    return candidate


def guard(original, candidate, nonce, start, end):
    expected_root = tree(original)
    actual = tree(candidate)
    incoming = actual.find("inbound")
    require(incoming is not None and len(incoming) >= 3, "inbound_structure")
    require(signature(incoming[2]) == signature(scope_guard(start, end)), "exact_diagnostic_scope")
    # Reconstruct the expected delta independently from the generated candidate.
    removed_scope = incoming[2]
    require(removed_scope.tag == "choose", "scope_guard")
    incoming.remove(removed_scope)
    branch = post(actual)
    fixed = [n for n in branch if "diagnostic_fixed_input_required" in ET.tostring(n, encoding="unicode")]
    gates = branch.findall("limit-concurrency")
    require(len(fixed) == len(gates) == 1, "one_fixed_guard_one_terminal_gate")
    gate = gates[0]
    require(gate.get("key") == '@("auto-diagnostic:' + nonce + '")' and gate.get("max-count") == "1", "exclusive_nonce_gate")
    require(len(gate) == 5 and gate[0].attrib == {"calls": "1", "renewal-period": "3600", "counter-key": '@("auto-diagnostic:' + nonce + '")'}, "one_diagnostic_quota")
    require([signature(x) for x in list(gate)[1:]] == [signature(x) for x in tree(TEMPLATE.read_bytes())], "exact_fixed_scorer_block")
    safety = [i for i, n in enumerate(branch) if n.tag == "llm-content-safety"]
    require(len(safety) == 2 and list(branch).index(gate) == safety[-1] + 1, "scoring_after_redaction_safety_before_dispatch")
    require(gate[-1].tag == "return-response" and not gate.findall(".//forward-request") and not gate.findall(".//retry"), "terminal_no_completion")
    require(signature(fixed[0]) == signature(fixed_guard()), "fixed_input_closed")
    require(list(branch).index(fixed[0]) + 1 == next(i for i, n in enumerate(branch) if n.get("name") == "aiflux-model"), "fixed_guard_before_original_quota")
    branch.remove(fixed[0]); branch.remove(gate)
    require(signature(actual) == signature(expected_root), "copied_policy_safety_PII_auth_quotas_exact")
    return True


class Reads(a.Reads):
    def arm(self, suffix):
        require(suffix.startswith("/") and ".." not in suffix and "https:" not in suffix, "relative_ARM_read")
        url = "https://management.azure.com" + p.APIM + suffix
        url += ("&" if "?" in url else "?") + "api-version=" + p.VERSION
        try:
            with self.http.open(Request(url, headers={"Authorization": "Bearer " + self.token}), timeout=45) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                require(len(raw) <= 8 * 1024 * 1024, "bounded_ARM_read")
                return {"status": response.status, "etag": response.headers.get("ETag"), "body": json.loads(raw)}
        except HTTPError as exc:
            if exc.code != 404:
                raise
            exc.close()
            return {"status": 404, "etag": None, "body": None}

    def policy(self, revision, fmt):
        require(revision in ("", ";rev=2") and fmt in ("xml", "rawxml"), "policy_read_scope")
        result = self.arm("/apis/" + p.API + revision + "/policies/policy?format=" + fmt)
        require(result["status"] == 200, "existing_copied_policy_required")
        return result


def inheritance(reads):
    paths = ["/policies/policy?format=xml", "/products/aiflux/policies/policy?format=xml",
             "/apis/" + p.API + ";rev=2/products", "/apis/" + p.API + ";rev=2/operations",
             "/apis/" + p.API + ";rev=2/operations/chat/policies/policy?format=xml",
             "/apis/" + p.API + ";rev=2/operations/models/policies/policy?format=xml",
             "/diagnostics", "/apis/" + p.API + ";rev=2/diagnostics",
             "/subscriptions/" + SUBSCRIBER]
    values = {path: reads.arm(path) for path in paths}
    product = values[paths[2]]["body"]
    operations = values[paths[3]]["body"]
    require(not product.get("nextLink") and {x["name"] for x in product["value"]} == {"aiflux"}, "copied_product_association_no_broadening")
    require(not operations.get("nextLink") and {x["name"] for x in operations["value"]} == {"chat", "models"}, "exact_copied_operations")
    for path in paths[4:6]:
        require(values[path]["status"] == 404, "operation_override_requires_review")
    sub = values[paths[-1]]["body"]["properties"]
    require(sub["state"] == "active" and sub["scope"].lower() == (p.APIM + "/products/aiflux").lower(), "exact_active_Caldova_product_subscription")
    # No key retrieval; discard any incidental secret-bearing fields immediately.
    values[paths[-1]]["body"] = {"state": sub["state"], "scope": sub["scope"]}
    for path in paths[6:8]:
        rows = values[path]["body"]
        require(not rows.get("nextLink"), "complete_diagnostics")
        for item in rows["value"]:
            props = item["properties"]
            for side in ("frontend", "backend"):
                for direction in ("request", "response"):
                    capture = props.get(side, {}).get(direction, {})
                    require(capture.get("body", {}).get("bytes", 0) == 0, "no_body_capture")
                    require(not any(x.lower() in {"authorization", "ocp-apim-subscription-key", "cookie", "*"} for x in capture.get("headers", [])), "no_auth_capture")
    global_xml = values[paths[0]]["body"]["properties"]["value"]
    # Do NOT bypass a base policy or assume APIM strips revision from OriginalUrl.
    path_proven = CHAT_PATH in global_xml
    return values, path_proven


def capture(reads, label, online=False, candidate=False):
    owner = a.original_bindings()
    baseline = p.release.snapshot()
    extra = a.v.supplemental(baseline)
    require(len(baseline) == 13 and baseline == a.load(a.HOME / "protected-before.json")
            and extra == a.load(a.HOME / "supplemental-before.json"), "all13_supplemental_exact")
    flags, _ = reads.get("/revisions")
    require(not flags.get("nextLink"), "complete_revision_flags")
    rows = [p.summarize_revision(r) for r in flags["value"]]
    expected = deepcopy(a.load(a.HOME / "offline-correction02/revisions-before.json"))
    for row in expected:
        if row["revision"] == "2":
            row["is_online"] = online
    require(rows == expected, "owned2_flags_current1_unchanged")
    api, etag = reads.get(";rev=2")
    require(api["id"].lower() == a.RID.lower() and api["properties"]["apiRevisionDescription"] == p.expected_body(a.SELECTION)["properties"]["apiRevisionDescription"]
            and api["properties"]["subscriptionRequired"] is True, "owned_nonce_required")
    a.valid_etag(etag)
    current, _ = reads.get("")
    prior = a.load(a.HOME / "current-api-metadata.json")
    require({k: current["properties"].get(k) for k in prior} == prior, "current1_metadata_exact")
    head = p.backend.blob_head()
    require(all(head[k] == a.load(a.HOME / "offline-correction02/remote-head-before.json")[k] for k in a.HEAD_KEYS), "remote_state_unchanged")
    formats = {f: reads.policy(";rev=2", f) for f in ("rawxml", "xml")}
    original = formats["xml"]["body"]["properties"]["value"]
    normalized = ET.tostring(tree(original, exported=True), encoding="unicode")
    raw_signature(formats["rawxml"]["body"]["properties"]["value"], tree(normalized))
    a.valid_etag(formats["rawxml"]["etag"])
    inherited, path_proven = inheritance(reads)
    if (OUT / "manifest.json").exists():
        prior_capture = load("prepare-capture.json")
        require(inherited == prior_capture["inheritance"], "inherited_policy_product_or_capture_drift")
        require(p.release.fs.sha(current) == prior_capture["current_api_sha256"], "current_full_metadata_drift")
        if candidate:
            require(signature(tree(normalized)) == signature(tree((OUT / "diagnostic.xml").read_bytes())), "compiled_policy_readback_expression_exact")
        else:
            require(formats == prior_capture["policy_formats"], "offline_policy_predecessor_drift")
    result = {"at_utc": p.now(), "state_owner": owner, "all13_supplemental_exact": True,
              "baseline_sha256": p.release.fs.sha(baseline), "supplemental_sha256": p.release.fs.sha(extra),
              "current_api_sha256": p.release.fs.sha(current), "owned_api": api, "api_etag": etag,
              "revisions": rows, "policy_formats": formats, "inheritance": inherited,
              "revision_path_inheritance_proven": path_proven, "normalized_original": normalized,
              "remote_head": head}
    require(a.original_bindings() == owner, "state_end_read_drift")
    save(label + "-capture.json", result)
    return result


def sources():
    paths = set(OWN_FILES) | set((p.rt.ROOT / "scripts/deployment").glob("*.py"))
    paths |= {p.rt.ROOT / name for name in p.sources()}
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f) for f in sorted(paths)}


def test_counts(path):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {k: sum(int(n.get(k, 0)) for n in suites) for k in ("tests", "errors", "failures", "skipped")}
    require(counts["tests"] > 0 and not any(counts[k] for k in ("errors", "failures", "skipped")), "clean_actual_tests")
    return counts


def prepare(receipt):
    require(not OUT.exists(), "existing_package_reconcile_only")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_receipt")
    counts = test_counts(receipt)
    p.release.fs.protect(OUT)
    p.require_no_competing_workers(p.backend.workers())
    frozen = sources()
    p.persistence.transport()
    reads = Reads()
    data = capture(reads, "prepare")
    nonce = os.urandom(16).hex()
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=20)
    xml = render(data["normalized_original"], nonce, start.isoformat(), end.isoformat())
    # Exact policy body format=xml; source serializes XML escaping, not raw-invalid attributes.
    with (OUT / "diagnostic.xml").open("xb") as f:
        f.write(xml.encode())
    body = json.dumps({"properties": {"format": "xml", "value": xml}}, separators=(",", ":")).encode()
    with (OUT / "policy-put.json").open("xb") as f:
        f.write(body)
    require(frozen == sources(), "preparation_source_drift")
    save("manifest.json", {"at_utc": p.now(), "status": "PARENT_REVIEW_REQUIRED_NO_MUTATION",
        "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "owner": a.SELECTION,
        "state_owner": data["state_owner"], "nonce": nonce, "start": start.isoformat(), "end": end.isoformat(),
        "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": sha_bytes(body),
        "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": p.backend.markers(),
        "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
        "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
        "path_inheritance_proven": data["revision_path_inheritance_proven"],
        "policy_compilation": "NOT_EXECUTED_requires_reviewed_offline_PUT_and_exact_readback",
        "transport_response_bound": "ARM_reads_bounded; scoring_requires_Content-Length_<=65536_before_parse_not_transport_stream_cap",
        "terraform_proof": False, "auto_enabled": False, "cloud_writes": 0})
    print(json.dumps({"evidence": OUT.relative_to(p.rt.ROOT).as_posix(), "manifest_sha256": p.sha(OUT / "manifest.json"),
                      "xml_sha256": p.sha(OUT / "diagnostic.xml"), "source_sha256": p.release.fs.sha(frozen),
                      "tests": counts, "online_blocked_inheritance_unproven": not data["revision_path_inheritance_proven"]}))


def review(stage):
    manifest = load("manifest.json")
    require(manifest["sources"] == sources() and a.original_bindings() == manifest["state_owner"], "source_state_binding")
    require(p.sha(OUT / "prepare-capture.json") == manifest["capture_sha256"] and p.sha(OUT / "diagnostic.xml") == manifest["xml_sha256"]
            and p.sha(OUT / "policy-put.json") == manifest["put_sha256"], "bound_exact_XML_body_baseline")
    receipt = p.rt.ROOT / manifest["tests"]["path"]
    require(p.sha(receipt) == manifest["tests"]["sha256"] and test_counts(receipt) == manifest["tests"]["counts"], "test_receipt_binding")
    guard(load("prepare-capture.json")["normalized_original"], (OUT / "diagnostic.xml").read_bytes(), manifest["nonce"], manifest["start"], manifest["end"])
    r = load(stage + "-parent-review.json")
    require(r.get("approved") is True and r.get("independent_native_review") is True
            and r.get("stage") == stage and r.get("manifest_sha256") == p.sha(OUT / "manifest.json"), "actual_parent_stage_review_required")
    age = datetime.now(UTC) - datetime.fromisoformat(r["at_utc"])
    require(timedelta(0) <= age < timedelta(minutes=20), "fresh_review_required")
    transcript = (OUT / r["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and transcript.is_file() and p.sha(transcript) == r["transcript_sha256"], "actual_review_transcript_binding")
    require(not (OUT / (stage + "-intent.json")).exists(), "existing_intent_NO_RETRY")
    p.require_no_competing_workers(p.backend.workers())
    markers = p.backend.markers()
    require(all(markers.get(k) == v for k, v in manifest["markers"].items())
            and all(k.startswith(OUT.relative_to(p.rt.ROOT).as_posix() + "/") for k in markers.keys() - manifest["markers"].keys()), "foreign_intent_or_history_drift")
    return manifest, r


def mutation_request(stage, etag, token):
    require(stage in {"policy-put", "online", "offline"}, "literal_stage_only")
    url = POLICY_URL if stage == "policy-put" else a.URL
    body = (OUT / "policy-put.json").read_bytes() if stage == "policy-put" else (
        b'{"properties":{"isOnline":true}}' if stage == "online" else a.BODY)
    return Request(url, method="PUT" if stage == "policy-put" else "PATCH", data=body,
                   headers={"Authorization": "Bearer " + token, "If-Match": a.valid_etag(etag),
                            "Content-Type": "application/json", "Accept": "application/json"})


def wire_child(connection, stage, etag, token):
    try:
        try:
            with a.opener(p.rt.CA).open(mutation_request(stage, etag, token), timeout=45) as response:
                result = a.safe_http(response.status, response.headers)
        except HTTPError as exc:
            result = a.safe_http(exc.code, exc.headers)
            exc.close()  # No ARM error text or policy expressions printed/persisted.
        connection.send(result)
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__})
    finally:
        connection.close()


def once(stage, etag, token):
    context = multiprocessing.get_context("spawn")
    rx, tx = context.Pipe(duplex=False)
    child = context.Process(target=wire_child, args=(tx, stage, etag, token))
    try:
        child.start(); tx.close()
        return rx.recv() if rx.poll(60) else {"transport_error": "WallClockTimeout", "outcome": "unknown_no_retry"}
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill(); child.join(5)
        rx.close(); tx.close()


def execute(stage):
    manifest, receipt = review(stage)
    p.persistence.transport()
    reads = Reads()
    data = capture(reads, stage + "-before", online=stage == "offline", candidate=stage != "policy-put")
    if stage != "offline":
        require(datetime.fromisoformat(manifest["start"]) <= datetime.now(UTC) < datetime.fromisoformat(manifest["end"]) - timedelta(minutes=2), "diagnostic_window_remaining")
    if stage == "online":
        compilation = load("policy-put-verification.json")
        require(compilation["exact_both_formats"] is True and compilation["http_status"] in (200, 201), "actual_offline_APIM_compilation_required")
        require(data["revision_path_inheritance_proven"], "STOP_inherited_global_gate_revision_path_unproven_NO_base_bypass")
        require((OUT / "offline-parent-review.json").is_file(), "cleanup_review_prepared_before_online")
    review(stage)
    etag = data["policy_formats"]["rawxml"]["etag"] if stage == "policy-put" else data["api_etag"]
    require(datetime.now(UTC) - datetime.fromisoformat(data["at_utc"]) < timedelta(minutes=2), "fresh_actual_etag_and_baseline")
    request = mutation_request(stage, etag, reads.token)
    with (OUT / (stage + "-intent.json")).open("x", encoding="utf-8") as f:
        json.dump({"at_utc": p.now(), "pid": os.getpid(), "stage": stage, "url": request.full_url, "method": request.method,
                   "body_sha256": sha_bytes(request.data), "manifest_sha256": p.sha(OUT / "manifest.json"),
                   "review_sha256": p.sha(OUT / (stage + "-parent-review.json")), "etag": etag,
                   "attempt_budget": 1, "retries": 0, "redirects": 0, "terraform": False}, f)
        f.flush(); os.fsync(f.fileno())
    result = once(stage, etag, reads.token)
    save(stage + "-result.json", {"at_utc": p.now(), **result, "no_retry": True})
    require(result.get("http_status") in (200, 201), "STOP_mutation_failure_or_ambiguous_never_retry")
    after = capture(reads, stage + "-after", online=stage == "online", candidate=True)
    raw = after["policy_formats"]["rawxml"]["body"]["properties"]["value"]
    xml = after["policy_formats"]["xml"]["body"]["properties"]["value"]
    # Require both exports to preserve EXACT expression chars, not html/space folding.
    expected = signature(tree((OUT / "diagnostic.xml").read_bytes()))
    require(raw_signature(raw, tree((OUT / "diagnostic.xml").read_bytes())) == signature(tree(xml, exported=True)) == expected, "both_formats_expression_preservation")
    save(stage + "-verification.json", {"at_utc": p.now(), "http_status": result["http_status"],
        "exact_both_formats": True, "revision2_online": stage == "online", "revision2_current": False,
        "current1_unchanged": True, "all13_supplemental_exact": True, "terraform": False,
        "scoring_requests_by_controller": 0, "completion_requests": 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "policy-put", "online", "offline"))
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    try:
        if args.stage == "prepare":
            require(args.tests is not None, "actual_test_receipt_required")
            prepare(args.tests)
        else:
            execute(args.stage)
        return 0
    except Exception as exc:
        result = {"at_utc": p.now(), "stage": args.stage, "type": type(exc).__name__,
                  "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", "retry_authorized": False}
        if OUT.exists():
            # Exclusive failure records; no overwrite of a previous outcome.
            save(args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())