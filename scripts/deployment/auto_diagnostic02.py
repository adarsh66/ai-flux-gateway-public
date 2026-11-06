"""Audited successor to the consumed diagnostic01; prepare or offline PUT only.

Historical source/evidence stays immutable. Reuse its exact baseline, ownership,
ETag, review, exclusive intent and readback guards under temporary bindings.
No online/scoring/TF/build entrypoint. Spawned writer explicitly rebinds OUT.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import multiprocessing
import os
from pathlib import Path
import re
from urllib.error import HTTPError

from scripts.deployment import auto_diagnostic_stage as core

p = core.p
require = core.require
OLD = core.a.HOME / "scoring-diagnostic01"
OUT = core.a.HOME / "scoring-diagnostic02"
DOC = p.rt.ROOT / "docs/auto-diagnostic02-review-20261029.md"
TEST = p.rt.ROOT / "tests/unit/test_auto_diagnostic02.py"
PRODUCTION = p.rt.ROOT / "gateway/policies/auto-resolve.xml.tftpl"
ALLOWLIST_URL = "https://learn.microsoft.com/en-us/azure/api-management/api-management-policy-expressions"
# Explicit lexical inventory of the real XML (including unreachable copied code).
# This is a conservative source-review guard, NOT a C# compiler/type checker.
MEMBER_GROUPS = {
    "APIM documented context/IResponse/IMessageBody/dictionary extension": {
        "Api", "Body", "Headers", "Id", "IpAddress", "LastError", "Method",
        "OriginalUrl", "Path", "PolicyId", "Product", "Query", "Reason",
        "Request", "RequestId", "Response", "Revision", "Source", "StatusCode",
        "Subscription", "Url", "Variables", "GetValueOrDefault", "As"},
    "Newtonsoft.Json.Linq all members and Formatting all": {
        "Boolean", "CreateNull", "Float", "Formatting", "Integer", "Json",
        "Name", "None", "Properties", "String", "Type", "Value", "Remove"},
    "System.String/StringComparison/numeric/List/dictionary/Enumerable all": {
        "Add", "Any", "ContainsKey", "Count", "Equals", "IndexOf",
        "IsNullOrWhiteSpace", "Join", "Keys", "Length", "MaxValue",
        "OrdinalIgnoreCase", "Parse", "Substring", "ToString", "Trim", "TryParse"},
    "System.Math and System.Text.Encoding all": {
        "Abs", "Min", "Encoding", "GetByteCount", "Text", "UTF8"},
    "DateTime explicit UtcNow/Ticks; DateTimeOffset all": {
        "UtcNow", "Ticks", "ToUnixTimeSeconds"},
}
ALLOWED_MEMBERS = set().union(*MEMBER_GROUPS.values())


def utc_ticks(value):
    stamp = datetime.fromisoformat(value)
    require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0), "explicit_UTC_required")
    delta = stamp - datetime(1, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def scope_guard(start, end):
    begin, finish = utc_ticks(start), utc_ticks(end)
    require(0 < finish - begin <= 20 * 60 * 10_000_000, "bounded_UTC_window")
    condition = ('@(context.Subscription == null || context.Product == null || context.Product.Id != "aiflux"'
                 + ' || context.Subscription.Id != "' + core.SUBSCRIBER + '" || context.Request.IpAddress != "' + core.IP + '"'
                 + ' || context.Api.Revision != "2" || context.Request.Method != "POST"'
                 + ' || context.Request.OriginalUrl.Path != "' + core.CHAT_PATH + '"'
                 + ' || DateTime.UtcNow.Ticks < ' + str(begin) + 'L'
                 + ' || DateTime.UtcNow.Ticks >= ' + str(finish) + 'L)')
    return core.reject(condition, "diagnostic_scope_closed")


@contextmanager
def bindings():
    names = {"OUT": OUT, "scope_guard": scope_guard, "once": once,
             "OWN_FILES": (*core.OWN_FILES, Path(__file__), TEST, DOC, PRODUCTION,
                           *sorted(OLD.iterdir()))}
    previous = {name: getattr(core, name) for name in names}
    try:
        for name, value in names.items():
            setattr(core, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(core, name, value)


def predecessor():
    result = core.a.load(OLD / "policy-put-result.json")
    intent = core.a.load(OLD / "policy-put-intent.json")
    require(result["http_status"] == 400 and result["no_retry"] is True
            and intent["stage"] == "policy-put" and intent["attempt_budget"] == 1,
            "consumed_diagnostic01_preserved")
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f) for f in sorted(OLD.iterdir()) if f.is_file()}


def strip_literals(value):
    # C# quoted strings/characters and comments only; preserve all code tokens.
    return re.sub(r'@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*', '""', value)


def expressions(xml):
    for index, node in enumerate(core.tree(xml).iter()):
        for key, value in [*node.attrib.items(), ("text", node.text or "")]:
            if value.strip().startswith(("@(", "@{")):
                yield index, node.tag, key, value


def expression_audit(xml):
    rows = []
    for index, tag, key, value in expressions(xml):
        code = strip_literals(value)
        members = set(re.findall(r"\.\s*([A-Za-z_]\w*)", code))
        require(members <= ALLOWED_MEMBERS, "unreviewed_expression_member")
        require(not re.search(r"\bDateTime\s*\.\s*(?!UtcNow\b)\w+", code), "DateTime_only_UtcNow_Ticks")
        require(not re.search(r"\.\s*(?:ToUniversalTime|ToLocalTime|ParseExact|SpecifyKind|ToBinary|ToFileTime)\b", code),
                "unsupported_DateTime_member")
        rows.append({"element": index, "tag": tag, "field": key,
                     "expression_sha256": core.sha_bytes(value.encode()), "members": sorted(members)})
    require(rows, "nonempty_expression_inventory")
    return {"official_allowlist": ALLOWLIST_URL, "expression_count": len(rows),
            "member_groups": {k: sorted(v) for k, v in MEMBER_GROUPS.items()}, "expressions": rows,
            "scope": "every expression attribute and text, all branches including outbound/on-error",
            "result": "lexical_inventory_reviewed_NOT_APIM_compile_or_runtime_proof"}


def production_audit():
    text = PRODUCTION.read_text(encoding="utf-8")
    # Terraform placeholders prevent parsing it as standalone XML. Inspect all
    # date-related C# calls and retain exact production source hash for review.
    calls = re.findall(r"\bDateTime(?:Offset)?\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", text)
    require(calls == ["DateTime.UtcNow.Ticks", "DateTime.UtcNow.Ticks"], "production_DateTime_review")
    require("ToUniversalTime" not in text and "ParseExact" not in text, "production_no_unsupported_date_conversion")
    return {"path": PRODUCTION.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(PRODUCTION),
            "date_expressions": calls, "change_required": False, "APIM_compile_proven": False}


def prepare(receipt):
    require(not OUT.exists(), "existing_package_reconcile_only")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_receipt")
    counts = core.test_counts(receipt)
    history = predecessor()
    p.release.fs.protect(OUT)
    p.require_no_competing_workers(p.backend.workers())
    with bindings():
        frozen = core.sources()
        p.persistence.transport()
        data = core.capture(core.Reads(), "prepare")
        nonce = os.urandom(16).hex()
        start = datetime.now(UTC).replace(microsecond=0)
        end = start + timedelta(minutes=20)
        xml = core.render(data["normalized_original"], nonce, start.isoformat(), end.isoformat())
        audit = expression_audit(xml)
        audit["production_date_audit"] = production_audit()
        audit["xml_sha256"] = core.sha_bytes(xml.encode())
        core.save("expression-audit.json", audit)
        with (OUT / "diagnostic.xml").open("xb") as stream:
            stream.write(xml.encode())
        body = json.dumps({"properties": {"format": "xml", "value": xml}}, separators=(",", ":")).encode()
        with (OUT / "policy-put.json").open("xb") as stream:
            stream.write(body)
        require(frozen == core.sources() and history == predecessor(), "preparation_source_history_drift")
        core.save("manifest.json", {"at_utc": p.now(), "status": "PARENT_REVIEW_REQUIRED_NO_MUTATION",
            "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "owner": core.a.SELECTION,
            "state_owner": data["state_owner"], "nonce": nonce, "start": start.isoformat(), "end": end.isoformat(),
            "start_UTC_ticks": utc_ticks(start.isoformat()), "end_UTC_ticks": utc_ticks(end.isoformat()),
            "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": core.sha_bytes(body),
            "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": p.backend.markers(),
            "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
            "predecessor": history, "expression_audit_sha256": p.sha(OUT / "expression-audit.json"),
            "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
            "controller_scoring_budget": 0, "allowed_stages": ["prepare", "policy-put"],
            "path_inheritance_proven": data["revision_path_inheritance_proven"],
            "policy_compilation": "NOT_EXECUTED_requires_parent_reviewed_offline_PUT_and_exact_readback",
            "terraform_proof": False, "auto_enabled": False, "cloud_writes": 0})
    print(json.dumps({"evidence": OUT.relative_to(p.rt.ROOT).as_posix(),
                      "manifest_sha256": p.sha(OUT / "manifest.json"), "xml_sha256": p.sha(OUT / "diagnostic.xml"),
                      "source_sha256": p.release.fs.sha(frozen), "tests": counts, "expressions": len(audit["expressions"]),
                      "start": start.isoformat(), "end": end.isoformat(), "no_mutations": True}), flush=True)


def safe_compilation_error(raw):
    """Never return arbitrary ARM messages/expressions/headers, only known syntax."""
    result = {"error_body_retained": False}
    if len(raw) > 65536:
        return result
    try:
        value = json.loads(raw)
        error = value.get("error", value)
        code = error.get("code")
        if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", code):
            result["arm_error_code"] = code
        # Walk only known ARM message/detail fields, never echo a message.
        messages = []
        def walk(node, depth=0):
            if depth > 6 or not isinstance(node, dict):
                return
            if isinstance(node.get("message"), str):
                messages.append(node["message"])
            for item in node.get("details", [])[:32] if isinstance(node.get("details"), list) else []:
                walk(item, depth + 1)
        walk(error)
        matches = []
        for message in messages:
            for member, kind in re.findall(r"Usage of member '([A-Za-z0-9_.()]{1,128})' of type '([A-Za-z0-9_.]{1,128})' is not supported within expressions", message):
                matches.append({"member": member, "type": kind})
        if matches:
            result["unsupported_members"] = matches[:32]
    except (ValueError, TypeError, AttributeError):
        pass
    return result


def wire_child(connection, stage, etag, token):
    try:
        require(stage == "policy-put", "offline_policy_put_only")
        with bindings():
            request = core.mutation_request(stage, etag, token)
        try:
            with core.a.opener(p.rt.CA).open(request, timeout=45) as response:
                result = core.a.safe_http(response.status, response.headers)
        except HTTPError as exc:
            result = core.a.safe_http(exc.code, exc.headers)
            try:
                result.update(safe_compilation_error(exc.read(65537)))
            finally:
                exc.close()
        connection.send(result)
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__})
    finally:
        connection.close()


def once(stage, etag, token):
    require(stage == "policy-put", "offline_policy_put_only")
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


def check_package():
    manifest = core.a.load(OUT / "manifest.json")
    require(predecessor() == manifest["predecessor"], "immutable_consumed_predecessor")
    require(p.sha(OUT / "expression-audit.json") == manifest["expression_audit_sha256"], "bound_member_audit")
    audit = core.a.load(OUT / "expression-audit.json")
    actual = expression_audit((OUT / "diagnostic.xml").read_bytes())
    require(all(audit[key] == value for key, value in actual.items()), "exact_member_inventory")
    require(audit["production_date_audit"] == production_audit(), "production_source_exact")
    return manifest


def execute(stage):
    require(stage == "policy-put", "offline_policy_put_only")
    with bindings():
        check_package()
        core.execute(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "policy-put"))
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
            p.backend.save(OUT, args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())