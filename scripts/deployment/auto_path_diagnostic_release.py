"""Fresh-baseline, review-gated, one-shot path diagnostic release.

Preparation is read-only. activate/reserve/claim/cleanup are explicit commands;
none run from prepare. No Terraform, image build or browser Send is invoked.
Permanent intents forbid retry even after an unknown transport outcome.
"""
import argparse
import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import secrets
import subprocess
import xml.etree.ElementTree as ET
from urllib.error import HTTPError
from urllib.request import Request

from scripts.deployment import auto_diagnostic_stage as c
from scripts.deployment import customer_send_release as r

a, p = c.a, c.p
ROOT = r.rt.ROOT
PROPOSAL = ROOT / "scripts/proposals/auto_global_path_exception.mjs"
BRIDGE = Path(__file__).with_name("auto_path_diagnostic_render.mjs")
BROWSER = Path(__file__).with_name("auto_diagnostic_browser06.mjs")
PATH_BROWSER = Path(__file__).with_name("auto_path_diagnostic_browser.mjs")
FIXTURE = a.HOME / "scoring-diagnostic06/diagnostic.xml"
TEST = ROOT / "tests/unit/test_auto_path_diagnostic_release.py"
DOC = ROOT / "docs/auto-path-diagnostic-release.md"
GLOBAL_SHA = "936a862488c18ea2f11d27bfbe99f653b26edead85546eda171cdb7229600d31"
REVISION_SHA = "1897a95092b04282ae75b30194a5c7f0915230235d35114fa03dd3c1464df930"
CUSTOMER = "5f55df7d5fbc094f37011906c503e96b8c01e329978d6bca9ac9a7d8318eb589"
API = "29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64"
IP = "167.103.66.248"
SCOPE = "AUTO_PATH_DIAGNOSTIC_ONE_NEW_ATTEMPT"
STAGES = ("install-global", "install-revision", "online", "reserve", "offline", "restore-global")
CLEANUP = {"offline", "restore-global"}
GLOBAL_URL = "https://management.azure.com" + p.APIM + "/policies/policy?api-version=" + p.VERSION
URLS = {"install-global": GLOBAL_URL, "restore-global": GLOBAL_URL,
        "install-revision": c.POLICY_URL, "online": a.URL, "offline": a.URL}
require = a.require


def now():
    return datetime.now(UTC)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load(path):
    return json.loads(path.read_bytes())


def exclusive(path, value):
    """Never overwrite, including partially written/crashed attempt records."""
    require(not path.is_symlink() and not path.parent.is_symlink(), "no_symlink_artifact")
    data = value if isinstance(value, bytes) else encode(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def window(start, end):
    pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    require(all(isinstance(x, str) and re.fullmatch(pattern, x) for x in (start, end)), "literal_UTC_seconds")
    begin, finish = (datetime.fromisoformat(x) for x in (start, end))
    require(timedelta(0) < finish - begin <= timedelta(minutes=30), "window_at_most_30_minutes")
    return begin, finish


def expression(start, end):
    begin, finish = window(start, end)
    def ticks(at):
        delta = at - datetime(1, 1, 1, tzinfo=UTC)
        return str((delta.days * 86400 + delta.seconds) * 10_000_000) + "L"
    return ('context.Api != null && (context.Api.Id == "aiflux-dev-unified"'
            ' || context.Api.Id == "aiflux-dev-unified;rev=2") && context.Api.Revision == "2"'
            ' && context.Subscription != null && context.Product != null'
            ' && context.Product.Id == "aiflux" && context.Subscription.Id == "' + c.SUBSCRIBER + '"'
            ' && context.Request.Method == "POST" && context.Request.IpAddress == "' + IP + '"'
            ' && (context.Request.OriginalUrl.Path == "/dev/llm/v1/chat/completions"'
            ' || context.Request.OriginalUrl.Path == "/dev/llm/v1;rev=2/chat/completions")'
            ' && DateTime.UtcNow.Ticks >= ' + ticks(begin) + ' && DateTime.UtcNow.Ticks < ' + ticks(finish))


def render(global_export, revision, start, end, nonce):
    """One proposal span each; new quota identity, not a historical-count claim.

    The proposal global is an EXPORT, not a wire document. Parse its observed
    extra layer, independently prove C# text, then serialize standard XML once.
    """
    require(sha(global_export) == GLOBAL_SHA and sha(revision) == REVISION_SHA, "known_policy_predecessors_only")
    require(re.fullmatch(r"[a-f0-9]{32}", nonce) is not None, "fresh_counter_nonce")
    result = subprocess.run(["node", str(BRIDGE)], input=encode({
        "global": base64.b64encode(global_export).decode(), "revision": base64.b64encode(revision).decode(),
        "window": {"start": start, "end": end}}), capture_output=True, timeout=30, check=False)
    require(result.returncode == 0, "offline_proposal_renderer_failed")
    output = json.loads(result.stdout)
    expected = expression(start, end)
    require(output["expression"] == expected, "independent_exact_CSharp_predicate")
    global_tree = c.tree(base64.b64decode(output["global"]), exported=True)
    original_tree = c.tree(global_export, exported=True)
    old_guard = original_tree.find("./inbound/choose/when")
    new_guard = global_tree.find("./inbound/choose/when")
    old = old_guard.get("condition")
    require(new_guard.get("condition") == "@((" + old[2:-1] + ") && !(" + expected + "))",
            "decoded_global_CSharp_not_double_serialized")
    new_guard.set("condition", old)
    require(c.signature(global_tree) == c.signature(original_tree), "global_only_exact_predicate_delta")
    new_guard.set("condition", "@((" + old[2:-1] + ") && !(" + expected + "))")
    diagnostic = c.tree(base64.b64decode(output["revision"]))
    original = c.tree(revision)
    scope = diagnostic.find("./inbound")[2].find("when")
    require(scope.get("condition") == "@(!(" + expected + "))", "revision_exact_conjunction")
    scope.set("condition", original.find("./inbound")[2].find("when").get("condition"))
    require(c.signature(diagnostic) == c.signature(original), "revision_only_exact_predicate_delta")
    scope.set("condition", "@(!(" + expected + "))")
    gate = c.post(diagnostic).find("limit-concurrency")
    old_key = gate.get("key")
    require(gate.get("max-count") == "1" and gate[0].attrib == {
        "calls": "1", "renewal-period": "3600", "counter-key": old_key}, "original_one_call_quota")
    key = '@("auto-diagnostic:' + nonce + '")'
    require(key != old_key, "new_counter_not_historical_reuse")
    gate.set("key", key)
    gate[0].set("counter-key", key)
    require(gate[-1].tag == "return-response" and not gate.findall(".//retry")
            and not gate.findall(".//forward-request"), "terminal_scorer_no_completion")
    def xml(tree):
        value = ET.tostring(tree, encoding="utf-8")
        require(c.signature(c.tree(value)) == c.signature(tree), "wire_XML_roundtrip")
        return value
    return {"global.xml": xml(global_tree), "revision.xml": xml(diagnostic),
            "restore-global.xml": xml(original_tree), "proposal-diffs.json": encode(output["diffs"])}


def verify_formats(formats, wire=None):
    tree = c.tree(formats["xml"]["body"]["properties"]["value"], exported=True)
    # APIM rawxml also emits unescaped C# TEXT, not just attributes. Replace
    # complete known expressions only, then compare the entire remaining tree.
    reference = deepcopy(tree)
    raw = formats["rawxml"]["body"]["properties"]["value"]
    tokens = {"&": "(?:&amp;|&)", "<": "(?:&lt;|<)", ">": "(?:&gt;|>)"}
    expressions = {(key, value) for n in reference.iter() for key, value in n.attrib.items() if value.startswith("@")}
    expressions |= {(None, n.text) for n in reference.iter() if (n.text or "").startswith("@")}
    for index, (key, value) in enumerate(sorted(expressions, key=lambda x: (x[0] or "", x[1]))):
        marker = "path_expression_" + str(index)
        literal = "".join(tokens.get(ch, re.escape(ch)) for ch in value)
        if key is None:
            count_expected = sum(n.text == value for n in reference.iter())
            raw, count = re.subn(">" + literal + "<", lambda _: ">" + marker + "<", raw)
            for n in reference.iter():
                if n.text == value:
                    n.text = marker
        else:
            count_expected = sum(n.attrib.get(key) == value for n in reference.iter())
            raw, count = re.subn(re.escape(key + '=\"') + literal + '\"', lambda _: key + '=\"' + marker + '\"', raw)
            for n in reference.iter():
                if n.attrib.get(key) == value:
                    n.set(key, marker)
        require(count == count_expected, "raw_exact_known_expressions")
    require(c.signature(c.tree(raw)) == c.signature(reference), "raw_complete_structure")
    if wire is not None:
        require(c.signature(tree) == c.signature(c.tree(wire)), "both_policy_formats_match_wire")
    return tree


def policy_values(formats):
    return {fmt: item["body"]["properties"]["value"] for fmt, item in formats.items()}


@contextmanager
def read_transport():
    """Existing full13/settings-list helpers, strict TLS and no redirects.

    Settings values are reduced to existing hashes by snapshot(), never saved.
    No mutation command is allowed through the CLI wrapper.
    """
    from scripts.deployment import poc_publisher_recheck_oct29 as reads_module
    old_module = r.persistence.old
    backend = r.persistence.backend
    saved = [(module, "urlopen", module.urlopen) for module in (reads_module, old_module, backend, r.rt)]
    original_arm = r.rt.arm
    try:
        strict_open = lambda req, **kw: a.opener(r.rt.CA).open(req, timeout=kw.get("timeout", 90))
        for module, name, _ in saved:
            setattr(module, name, strict_open)
        with r.read_transport():
            old_cli = r.rt.cli
            def cli(args):
                if args[:3] == ["rest", "--method", "get"]:
                    url = args[args.index("--url") + 1]
                    require(url.startswith("https://management.azure.com/subscriptions/" + r.rt.SUB + "/")
                            or url.startswith("https://management.azure.com/providers/Microsoft.Authorization/roleDefinitions/"),
                            "bounded_ARM_read_scope")
                    token = backend.token("https://management.azure.com/")
                    with strict_open(Request(url, headers={"Authorization": "Bearer " + token}), timeout=90) as response:
                        raw = response.read(8 * 1024 * 1024 + 1)
                        require(len(raw) <= 8 * 1024 * 1024, "bounded_ARM_metadata")
                        return json.loads(raw)
                return old_cli(args)
            def arm(rid, method="GET", *args, **kwargs):
                require(not args and not kwargs, "finite_metadata_read_signature")
                settings = {r.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + k
                            + "/config/appsettings/list" for k in ("api", "admin", "customer", "ingestion")}
                require(method == "GET" or (method == "POST" and rid in settings), "read_or_exact_four_settings_list_only")
                # Preserve the established API-version selection, operator
                # identity validation and response bounds; replace transport only.
                return original_arm(rid, method)
            r.rt.cli, r.rt.arm = cli, arm
            yield
    finally:
        r.rt.arm = original_arm
        for module, name, value in saved:
            setattr(module, name, value)


def remote_state():
    url = "https://projpoctokenex.blob.core.windows.net/tfstate/poc-ids-token-ex/main.tfstate"
    request = Request(url, headers={"Authorization": "Bearer " + r.persistence.backend.token("https://storage.azure.com/"),
                                   "x-ms-version": "2023-11-03"})
    with a.opener(r.rt.CA).open(request, timeout=90) as response:
        raw = response.read(32 * 1024 * 1024 + 1)
        require(len(raw) <= 32 * 1024 * 1024, "bounded_runtime_state")
        state = json.loads(raw)
        return {"lineage": state["lineage"], "serial": state["serial"], "sha256": sha(raw),
                "etag": response.headers.get("ETag"), "length": len(raw),
                "last_modified": response.headers.get("Last-Modified")}


def collect():
    """Fresh actual reads, NEVER compare to original pre-cm38 baseline."""
    started = now().isoformat()
    r.gate.require_no_competing_workers(r.persistence.backend.workers())
    project = a.state_owner()
    reads = c.Reads()
    flat, _ = reads.get("/revisions")
    require(not flat.get("nextLink"), "complete_revision_list")
    rows = [p.summarize_revision(row) for row in flat["value"]]
    current, _ = reads.get("")
    owned, etag = reads.get(";rev=2")
    require(owned["id"].lower() == a.RID.lower() and owned["properties"]["apiRevision"] == "2"
            and owned["properties"]["apiRevisionDescription"] == p.expected_body(a.SELECTION)["properties"]["apiRevisionDescription"]
            and owned["properties"]["path"] == "dev/llm/v1"
            and owned["properties"]["subscriptionRequired"] is True, "owned_revision_nonce_path_auth")
    inherited, _ = c.inheritance(reads)
    formats = {kind: {fmt: (reads.arm("/policies/policy?format=" + fmt) if kind == "global"
        else reads.policy(";rev=2", fmt)) for fmt in ("rawxml", "xml")} for kind in ("global", "revision")}
    for pair in formats.values():
        verify_formats(pair)
    with read_transport():
        r.login.account()
        baseline = r.persistence.release.snapshot()
        extra = r.supplemental(baseline)
        storage = r.persistence.backend.arm_read()["account"]
        head = r.persistence.backend.blob_head()
        runtime = remote_state()
    require(len(baseline) == 13 and len(baseline["settings_hashes"]) == 4, "complete_full13_four_settings")
    for kind, digest in (("customer", CUSTOMER), ("api", API)):
        require(baseline["runtime"]["sites"][kind]["image"] ==
                "DOCKER|pocidstokenexacr.azurecr.io/aiflux-" + kind + "@sha256:" + digest, "current_cm38_inventory_pins")
    require(project["serial"] == 185 and runtime["serial"] == 111
            and runtime["lineage"] == "b05cbf70-2d31-0e6e-34b7-c97e8f617ed6", "current_project185_runtime111")
    require(head["lease_state"] == "available" and head["lease_status"] == "unlocked"
            and head["etag"] == runtime["etag"] and int(head["content_length"]) == runtime["length"]
            and head["last_modified"] == runtime["last_modified"], "runtime_unlocked_consistent_reads")
    require(a.state_owner() == project, "project_state_stable")
    r.gate.require_no_competing_workers(r.persistence.backend.workers())
    # No settings values, bearer, subscription keys, state resources or scorer body.
    return {"started_at_utc": started, "at_utc": now().isoformat(), "baseline": baseline,
            "supplemental": extra, "project": project, "runtime": runtime,
            "storage_sha256": r.fs.sha(storage), "revisions": rows,
            "current_api_sha256": r.fs.sha(current), "owned_api": owned, "api_etag": etag,
            "inheritance": inherited, "formats": formats}


def initial(capture):
    rows = capture["revisions"]
    require(len(rows) == 2 and {row["revision"] for row in rows} == {"1", "2"}, "exact_two_revisions")
    for row in rows:
        require(row["is_current"] is (row["revision"] == "1")
                and row["is_online"] is (row["revision"] == "1"), "current1_online_revision2_offline")
    require(sha(policy_values(capture["formats"]["global"])["xml"].encode()) == GLOBAL_SHA,
            "fresh_global_original_not_adopted")
    verify_formats(capture["formats"]["global"])
    require(capture["baseline"]["apim"]["global"] == sha(policy_values(capture["formats"]["global"])["rawxml"].encode()),
            "initial_full13_global_binding")
    verify_formats(capture["formats"]["revision"], FIXTURE.read_bytes())


def sources():
    files = set((ROOT / "scripts/deployment").glob("*.py"))
    files |= {PROPOSAL, BRIDGE, BROWSER, TEST, DOC, FIXTURE,
              ROOT / "tests/auto_global_path_exception.test.mjs", ROOT / "tests/auto_diagnostic_browser06.test.mjs"}
    files |= {PATH_BROWSER, ROOT / "tests/auto_path_diagnostic_browser.test.mjs"}
    files |= set((ROOT / "infra/project-route").glob("*.tf"))
    files |= {ROOT / "packages/ui/src/pages/PlaygroundPage.tsx", ROOT / "packages/ui/src/chat.ts"}
    return {f.relative_to(ROOT).as_posix(): sha(f.read_bytes()) for f in sorted(files)}


def test_receipt(path):
    path = path.resolve()
    require(path.is_relative_to(ROOT) and not path.is_symlink(), "workspace_test_receipt")
    # Native Node JUnit emits direct testcase children without suite counters.
    # Count leaves for both formats; never double count nested suite totals.
    cases = list(ET.parse(path).getroot().iter("testcase"))
    counts = {"tests": len(cases), **{key: sum(case.find(tag) is not None or tag in case.attrib for case in cases)
              for key, tag in (("errors", "error"), ("failures", "failure"), ("skipped", "skipped"))}}
    require(counts["tests"] > 0 and not any(counts[k] for k in ("errors", "failures", "skipped")), "clean_actual_tests")
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes()), "counts": counts}


def prepare(folder, receipt, capture_fn=collect, clock=now, node_receipts=()):
    require(not folder.exists(), "existing_package_never_refresh")
    tests, frozen = test_receipt(receipt), sources()
    native_tests = [test_receipt(path) for path in node_receipts]
    # Fresh full capture completes BEFORE the single <=30-minute window freezes.
    before = capture_fn()
    initial(before)
    frozen_at = clock()
    require(timedelta(0) <= frozen_at - datetime.fromisoformat(before["at_utc"]) < timedelta(seconds=30), "fresh_prepare_capture")
    start = frozen_at.replace(microsecond=0)
    end = start + timedelta(minutes=30)
    start_text, end_text = (x.strftime("%Y-%m-%dT%H:%M:%SZ") for x in (start, end))
    payloads = render(policy_values(before["formats"]["global"])["xml"].encode(), FIXTURE.read_bytes(),
                      start_text, end_text, secrets.token_hex(16))
    require(sources() == frozen, "stable_sources_during_prepare")
    folder.mkdir(parents=False, exist_ok=False)
    r.fs.protect(folder)
    for name, value in payloads.items():
        exclusive(folder / name, value)
    exclusive(folder / "fresh-before.json", before)
    exclusive(folder / "browser-source.js", browser_source().encode())
    artifacts = {f.name: sha(f.read_bytes()) for f in folder.iterdir() if f.is_file()}
    exclusive(folder / "manifest.json", {"at_utc": clock().isoformat(), "status": "PREPARED_NOT_REVIEWED_NO_WRITES",
        "start": start_text, "end": end_text, "sources": frozen, "artifacts": artifacts, "tests": tests, "native_tests": native_tests,
        "stages": list(STAGES), "scope": SCOPE, "scoring_budget": 1, "completion_budget": 0,
        "retry_budget": 0, "historical_scoring_request_count": None, "cleanup_expiry_independent": True,
        "cloud_mutations": 0, "browser_executed": False})
    return localcheck(folder)


def browser_source():
    result = subprocess.run(["node", str(PATH_BROWSER), "--source"], capture_output=True, timeout=30, check=False)
    require(result.returncode == 0, "offline_browser_source_export")
    return result.stdout.decode("utf-8")


def localcheck(folder):
    manifest = load(folder / "manifest.json")
    require(manifest["sources"] == sources(), "source_drift")
    require(manifest["stages"] == list(STAGES) and manifest["scope"] == SCOPE
            and manifest["scoring_budget"] == 1 and manifest["completion_budget"] == manifest["retry_budget"] == 0,
            "fixed_stages_and_budget")
    require(manifest["tests"] == test_receipt(ROOT / manifest["tests"]["path"]), "test_receipt_drift")
    require(all(item == test_receipt(ROOT / item["path"]) for item in manifest["native_tests"]), "native_test_receipt_drift")
    for name, digest in manifest["artifacts"].items():
        require(Path(name).name == name and not (folder / name).is_symlink()
                and sha((folder / name).read_bytes()) == digest, "artifact_drift")
    window(manifest["start"], manifest["end"])
    initial(load(folder / "fresh-before.json"))
    return manifest


def review(folder, stage, clock=now):
    require(stage in STAGES, "finite_stage")
    manifest = localcheck(folder)
    receipt = load(folder / "parent-review.json")
    require(receipt.get("approved") is True and receipt.get("independent_native_review") is True
            and receipt.get("parent_says_cleanup") is True
            and receipt.get("manifest_sha256") == sha((folder / "manifest.json").read_bytes())
            and receipt.get("stages") == list(STAGES), "actual_review_all_stages_required")
    transcript = (folder / receipt["transcript"]).resolve()
    require(transcript.is_relative_to(folder.resolve()) and transcript.is_file()
            and sha(transcript.read_bytes()) == receipt["transcript_sha256"], "actual_review_transcript")
    at = datetime.fromisoformat(receipt["at_utc"])
    require(datetime.fromisoformat(manifest["at_utc"]) <= at <= clock(), "review_after_preparation")
    if stage not in CLEANUP:
        start, end = window(manifest["start"], manifest["end"])
        require(start <= clock() < end - timedelta(seconds=90)
                and clock() - at < timedelta(minutes=30), "window_and_cleanup_reserve")
        require(not any((folder / (s + "-intent.json")).exists() for s in CLEANUP), "cleanup_started")
    require(not (folder / (stage + "-intent.json")).exists(), "existing_intent_NO_RETRY")
    return manifest


def guarded(before, current, folder, global_installed, revision_installed, online):
    """All13, state, storage, inheritance, flags and both formats; no resets.

    Global is NOT hidden behind a broad baseline exclusion. It is compared in
    both formats separately; every other baseline field must remain identical.
    """
    for key in ("supplemental", "project", "runtime", "storage_sha256", "current_api_sha256"):
        require(current[key] == before[key], "protected_drift:" + key)
    prior_baseline, actual_baseline = deepcopy(before["baseline"]), deepcopy(current["baseline"])
    for capture, baseline in ((before, prior_baseline), (current, actual_baseline)):
        require(baseline["apim"]["global"] == sha(policy_values(capture["formats"]["global"])["rawxml"].encode()),
                "full13_global_raw_hash_binding")
    # This ONE field is checked independently in both formats below. Nothing
    # else is masked: current API/roles/backends/fragments/settings stay exact.
    actual_baseline["apim"]["global"] = prior_baseline["apim"]["global"]
    require(actual_baseline == prior_baseline, "protected_drift:baseline")
    rows = deepcopy(before["revisions"])
    for row in rows:
        if row["revision"] == "2":
            row["is_online"] = online
    require(current["revisions"] == rows, "all_revision_flags_exact")
    owned = deepcopy(current["owned_api"])
    original = deepcopy(before["owned_api"])
    # The detail endpoint may omit flags; the flat list above is authoritative.
    for item in (owned, original):
        item["properties"].pop("isOnline", None)
    require(owned == original, "owned_metadata_exact")
    inherited = deepcopy(current["inheritance"])
    previous = deepcopy(before["inheritance"])
    path = "/policies/policy?format=xml"
    for value in (inherited, previous):
        value.pop(path)
    require(inherited == previous, "all_other_inheritance_exact")
    for kind, installed in (("global", global_installed), ("revision", revision_installed)):
        if installed:
            verify_formats(current["formats"][kind], (folder / (kind + ".xml")).read_bytes())
        else:
            require(c.signature(verify_formats(current["formats"][kind])) ==
                    c.signature(verify_formats(before["formats"][kind])), "exact_original_both_formats:" + kind)


def mutation_request(stage, body, etag, token):
    require(stage in URLS, "finite_mutation_target")
    if stage in ("online", "offline"):
        require(body == encode({"properties": {"isOnline": stage == "online"}}), "literal_online_offline_only")
    else:
        parsed = json.loads(body)
        require(set(parsed) == {"properties"} and set(parsed["properties"]) == {"format", "value"}
                and parsed["properties"]["format"] == "xml", "XML_policy_body_only")
        c.tree(parsed["properties"]["value"])
    return Request(URLS[stage], method="PATCH" if stage in ("online", "offline") else "PUT", data=body,
        headers={"Authorization": "Bearer " + token, "If-Match": a.valid_etag(etag),
                 "Content-Type": "application/json", "Accept": "application/json"})


def wire_child(connection, stage, body, etag, token, ca):
    """One strict open, no response body reads, redirects or retry pipeline."""
    try:
        request = mutation_request(stage, body, etag, token)
        try:
            with a.opener(ca).open(request, timeout=45) as response:
                result = {"http_status": int(response.status)}
        except HTTPError as exc:
            result = {"http_status": int(exc.code)}
            exc.close()
        connection.send(result)
    except Exception:
        connection.send({"transport_error": "TransportFailureUnknown"})
    finally:
        connection.close()


def send_once(stage, body, etag, token):
    # Validate in the parent too. Spawn arguments are in memory, never CLI/files.
    mutation_request(stage, body, etag, token)
    context = multiprocessing.get_context("spawn")
    rx, tx = context.Pipe(duplex=False)
    child = context.Process(target=wire_child, args=(tx, stage, body, etag, token, r.rt.CA))
    try:
        child.start()
        tx.close()
        return rx.recv() if rx.poll(60) else {"transport_error": "WallClockTimeoutUnknown"}
    except Exception:
        return {"transport_error": "TransportFailureUnknown"}
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        rx.close()
        tx.close()


def stage_body(folder, stage):
    require(stage in STAGES, "finite_stage")
    if stage in ("online", "offline"):
        return encode({"properties": {"isOnline": stage == "online"}})
    if stage == "reserve":
        return None
    name = {"install-global": "global.xml", "install-revision": "revision.xml",
            "restore-global": "restore-global.xml"}[stage]
    return encode({"properties": {"format": "xml", "value": (folder / name).read_bytes().decode("utf-8")}})


class ProductionAdapter:
    """Full strict reads, then a short exact revalidation, NOT a second capture.

    last() returns the SAME capture object with its actual final-target-read
    timestamp. All metadata and both formats are compared before updating it.
    Global policy reads are service-scoped through c.Reads.arm, never API paths.
    """
    def __init__(self, folder, clock=now):
        self.folder, self.clock = folder, clock
        self.value = None
        self.ready = None

    def capture(self):
        self.ready = None
        self.value = collect()
        self.captured = deepcopy(self.value)
        return self.value

    def last(self, stage):
        require(stage in STAGES and self.value is not None and self.value == self.captured,
                "unmodified_capture_required")
        reads = c.Reads()
        current, _ = reads.get("")
        owned, api_etag = reads.get(";rev=2")
        flat, _ = reads.get("/revisions")
        require(not flat.get("nextLink") and [p.summarize_revision(x) for x in flat["value"]] == self.value["revisions"]
                and owned == self.value["owned_api"] and r.fs.sha(current) == self.value["current_api_sha256"],
                "last_exact_API_metadata_and_flags")
        for kind in ("global", "revision"):
            pair = {fmt: reads.arm("/policies/policy?format=" + fmt) if kind == "global"
                    else reads.policy(";rev=2", fmt) for fmt in ("rawxml", "xml")}
            verify_formats(pair)
            require(pair == self.value["formats"][kind], "last_policy_metadata_both_formats:" + kind)
        # The final read is the ACTUAL mutation target, with an opaque ETag.
        if stage in ("install-global", "restore-global"):
            target = reads.arm("/policies/policy?format=xml")
            require(target == self.value["formats"]["global"]["xml"], "last_global_target_drift")
            etag = target["etag"]
        elif stage == "install-revision":
            target = reads.policy(";rev=2", "xml")
            require(target == self.value["formats"]["revision"]["xml"], "last_revision_target_drift")
            etag = target["etag"]
        else:
            target, etag = reads.get(";rev=2")
            require(target == owned and etag == api_etag == self.value["api_etag"], "last_API_target_drift")
        a.valid_etag(etag)
        self.value["at_utc"] = self.clock().isoformat()
        self.token = reads.token
        self.ready = (stage, etag, self.value["at_utc"])
        return self.value, etag

    def send(self, stage, body, etag):
        require(self.ready is not None and self.ready[:2] == (stage, etag)
                and timedelta(0) <= self.clock() - datetime.fromisoformat(self.ready[2]) < timedelta(seconds=30),
                "send_requires_fresh_last_target")
        require(body == stage_body(self.folder, stage), "exact_stage_body_hash")
        intent = load(self.folder / (stage + "-intent.json"))
        require(intent["body_sha256"] == sha(body) and intent["etag"] == etag
                and intent["manifest_sha256"] == sha((self.folder / "manifest.json").read_bytes())
                and intent["review_sha256"] == sha((self.folder / "parent-review.json").read_bytes()), "durable_wire_binding")
        self.ready = None  # Consumed even if token acquisition or spawning fails.
        return send_once(stage, body, etag, self.token)


class Stages:
    """Review-gated state machine; fake transports are offline tests only."""
    def __init__(self, folder, adapter, clock=now):
        self.folder, self.adapter, self.clock = folder, adapter, clock

    def activate(self):
        """One activation, first cleanup on failure; NEVER replay cleanup.

        Cleanup failures retain permanent intents and an unresolved receipt;
        neither a supervisor restart nor an ambiguous result permits replay.
        """
        review(self.folder, "install-global", self.clock)
        browser_preflight(self.folder, self.clock)
        exclusive(self.folder / "activation-intent.json", {
            "at_utc": self.clock().isoformat(),
            "manifest_sha256": sha((self.folder / "manifest.json").read_bytes()),
            "review_sha256": sha((self.folder / "parent-review.json").read_bytes()), "attempts": 1})
        try:
            for stage in ("install-global", "install-revision", "online"):
                self.execute(stage)
        except Exception:
            # A global send might have happened even if response/verification
            # failed. Fresh cleanup recognizes only exact original/candidate.
            if (self.folder / "install-global-intent.json").exists():
                cleanup = {"at_utc": self.clock().isoformat(), "automatic_replay": False}
                try:
                    for stage in ("offline", "restore-global"):
                        require(not (self.folder / (stage + "-intent.json")).exists(), "cleanup_already_consumed_RECONCILE_ONLY")
                        self.execute(stage)
                    cleanup["status"] = "OFFLINE_AND_ORIGINAL_GLOBAL_INDEPENDENTLY_VERIFIED"
                except Exception:
                    cleanup["status"] = "UNRESOLVED_STOP_FRESH_READS_NO_REPLAY"
                exclusive(self.folder / "activation-cleanup.json", cleanup)
            raise

    def cleanup(self):
        # No resume/replay if the first cleanup intent already exists.
        review(self.folder, "offline", self.clock)
        for stage in ("offline", "restore-global"):
            self.execute(stage)

    def execute(self, stage):
        manifest = review(self.folder, stage, self.clock)
        before = load(self.folder / "fresh-before.json")
        def verified(name):
            path = self.folder / (name + "-verified.json")
            if not path.exists():
                return False
            value = load(path)
            require(value["manifest_sha256"] == sha((self.folder / "manifest.json").read_bytes())
                    and value["intent_sha256"] == sha((self.folder / (name + "-intent.json")).read_bytes()),
                    "stage_receipt_binding")
            return True
        g, d, on = verified("install-global"), verified("install-revision"), verified("online")
        if stage not in CLEANUP:
            needed = {"install-global": (), "install-revision": (g,), "online": (g, d), "reserve": (g, d, on)}
            require(all(needed[stage]), "stage_dependency")
        if stage == "restore-global":
            require(verified("offline"), "independent_offline_before_global_restore")
        actual = self.adapter.capture()
        # Cleanup does not trust success receipts: an earlier PUT/PATCH could
        # have succeeded remotely and failed locally. Exact fresh content decides.
        if stage in CLEANUP:
            g, d = (c.signature(verify_formats(actual["formats"][kind])) !=
                    c.signature(verify_formats(before["formats"][kind])) for kind in ("global", "revision"))
            owned_rows = [x for x in actual["revisions"] if x["revision"] == "2"]
            require(len(owned_rows) == 1 and type(owned_rows[0]["is_online"]) is bool, "explicit_cleanup_flag")
            on = owned_rows[0]["is_online"]
        guarded(before, actual, self.folder, g, d, on)
        latest, etag = self.adapter.last(stage)
        require(latest == actual and timedelta(0) <= self.clock() - datetime.fromisoformat(latest["at_utc"])
                < timedelta(seconds=30), "last_read_fresh_full_comparison")
        exclusive(self.folder / (stage + "-before.json"), actual)
        review(self.folder, stage, self.clock)
        if stage == "reserve":
            require(not (self.folder.parent / "auto-path-diagnostic-attempt-owner.json").exists(), "attempt_already_consumed")
            parent = load(self.folder / "browser-send-intent.json")
            preflight = browser_preflight(self.folder, self.clock)
            require(parent.get("manifest_sha256") == sha((self.folder / "manifest.json").read_bytes())
                    and parent.get("browser_responsive_preflight") is True
                    and parent.get("preflight_sha256") == preflight
                    and parent.get("parent_says_cleanup") is True
                    and parent.get("scope") == SCOPE, "actual_parent_browser_intent_required")
            exclusive(self.folder.parent / "auto-path-diagnostic-attempt-owner.json", {
                "scope": SCOPE, "manifest_sha256": parent["manifest_sha256"],
                "parent_intent_sha256": sha((self.folder / "browser-send-intent.json").read_bytes()),
                "at_utc": self.clock().isoformat(), "scoring_budget": 1, "completion_budget": 0})
        body = stage_body(self.folder, stage)
        no_wire = stage == "reserve" or (stage == "offline" and not on) or (stage == "restore-global" and not g)
        if body is not None:
            a.valid_etag(etag)
        exclusive(self.folder / (stage + "-intent.json"), {"at_utc": self.clock().isoformat(), "stage": stage,
            "manifest_sha256": sha((self.folder / "manifest.json").read_bytes()),
            "review_sha256": sha((self.folder / "parent-review.json").read_bytes()),
            "etag": etag, "body_sha256": sha(body) if body else None, "no_wire": no_wire, "retries": 0, "redirects": 0})
        try:
            result = self.adapter.send(stage, body, etag) if not no_wire else {"http_status": 200, "no_wire": True}
            # Only finite metadata is ever persisted; never raw ARM errors/body.
            result = {k: v for k, v in result.items() if k in {"http_status", "transport_error", "no_wire"}}
            exclusive(self.folder / (stage + "-result.json"), result)
            require(result.get("http_status") in (200, 201, 204), "mutation_failed_or_ambiguous_NO_RETRY")
            after = self.adapter.capture()
            guarded(before, after, self.folder,
                    False if stage == "restore-global" else (g or stage == "install-global"),
                    d or stage == "install-revision", False if stage == "offline" else (on or stage == "online"))
            localcheck(self.folder)
            exclusive(self.folder / (stage + "-after.json"), after)
            exclusive(self.folder / (stage + "-verified.json"), {
                "manifest_sha256": sha((self.folder / "manifest.json").read_bytes()),
                "intent_sha256": sha((self.folder / (stage + "-intent.json")).read_bytes()),
                "at_utc": self.clock().isoformat(), "all13_exact": True,
                "after_sha256": sha((self.folder / (stage + "-after.json")).read_bytes()), "no_wire": no_wire})
            if stage == "reserve":
                reservation = {"manifest_sha256": sha((self.folder / "manifest.json").read_bytes()),
                    "review_sha256": sha((self.folder / "parent-review.json").read_bytes()),
                    "end": manifest["end"], "IP": IP, "attempt_budget": 1, "scoring_budget": 1,
                    "completion_budget": 0, "retry_budget": 0, "fixed_text": c.TEXT, "model": "gpt-5.4-mini",
                    "path": c.CHAT_PATH, "nonce": secrets.token_hex(16),
                    "browser_source_sha256": sha((self.folder / "browser-source.js").read_bytes())}
                exclusive(self.folder / "browser-reservation.json", reservation)
        except Exception:
            exclusive(self.folder / (stage + "-cleanup-required.json"), {
                "offline_then_restore_global": True, "automatic_replay": False,
                "independent_cleanup_after_expiry": True, "outcome": "UNKNOWN_UNTIL_FRESH_READ"})
            raise


def browser_preflight(folder, clock=now):
    """Parent-observed REAL safe-event evidence; unit/VM fixtures are not proof.

    The parent creates this receipt only after observing normal UI events with
    no Send. The evidence file hash binds the actual retained browser result.
    """
    receipt = load(folder / "browser-preflight.json")
    path = (folder / receipt["evidence"]).resolve()
    require(path.is_relative_to(folder.resolve()) and not path.is_symlink() and path.is_file()
            and sha(path.read_bytes()) == receipt["evidence_sha256"], "actual_preflight_file_hash")
    require(receipt.get("parent_observed") is True and receipt.get("safe_events_observed") is True
            and receipt.get("fixture") is False and receipt.get("send_invoked") is False
            and receipt.get("source_sha256") == sha((folder / "browser-source.js").read_bytes())
            and receipt.get("manifest_sha256") == sha((folder / "manifest.json").read_bytes())
            and isinstance(receipt.get("page_id"), str) and len(receipt["page_id"]) == 36,
            "actual_safe_browser_events_required_NOT_fixture")
    require(timedelta(0) <= clock() - datetime.fromisoformat(receipt["at_utc"]) < timedelta(minutes=30),
            "fresh_real_browser_preflight")
    return sha((folder / "browser-preflight.json").read_bytes())


def reserve(folder, adapter, clock=now):
    review(folder, "reserve", clock)
    preflight = browser_preflight(folder, clock)
    # Parent intent precedes all reservation captures and the shared owner.
    exclusive(folder / "browser-send-intent.json", {
        "at_utc": clock().isoformat(), "scope": SCOPE, "parent_says_cleanup": True,
        "manifest_sha256": sha((folder / "manifest.json").read_bytes()),
        "review_sha256": sha((folder / "parent-review.json").read_bytes()),
        "preflight_sha256": preflight, "browser_responsive_preflight": True})
    Stages(folder, adapter, clock).execute("reserve")
    # The full after-capture may take two minutes. Claim freshness starts only
    # in the separate fast local claim command, not during cloud collection.
    return load(folder / "browser-reservation.json")


def claim(folder, clock=now):
    manifest = localcheck(folder)
    reservation = load(folder / "browser-reservation.json")
    verified = load(folder / "reserve-verified.json")
    owner_path = folder.parent / "auto-path-diagnostic-attempt-owner.json"
    owner = load(owner_path)
    mh = sha((folder / "manifest.json").read_bytes())
    ih = sha((folder / "browser-send-intent.json").read_bytes())
    require(reservation["manifest_sha256"] == verified["manifest_sha256"] == owner["manifest_sha256"] == mh
            and owner["parent_intent_sha256"] == ih and owner["scope"] == SCOPE
            and verified["intent_sha256"] == sha((folder / "reserve-intent.json").read_bytes())
            and verified["all13_exact"] is True
            and reservation["review_sha256"] == sha((folder / "parent-review.json").read_bytes())
            and reservation["browser_source_sha256"] == sha((folder / "browser-source.js").read_bytes()),
            "claim_exact_local_reservation_bindings")
    at = clock()
    require(timedelta(0) <= at - datetime.fromisoformat(verified["at_utc"]) < timedelta(minutes=2)
            and window(manifest["start"], manifest["end"])[0] <= at < window(manifest["start"], manifest["end"])[1] - timedelta(seconds=90)
            and not any((folder / (s + "-intent.json")).exists() for s in CLEANUP), "fresh_reservation_no_cleanup")
    preflight = browser_preflight(folder, clock)
    require(load(folder / "browser-send-intent.json")["preflight_sha256"] == preflight, "bound_preflight_unchanged")
    exclusive(folder / "browser-claim-intent.json", {"at_utc": at.isoformat(), "manifest_sha256": mh,
        "reservation_sha256": sha((folder / "browser-reservation.json").read_bytes()), "attempts": 1})
    binding = {"scope": SCOPE, "correction_of": "GLOBAL_ORIGINAL_PATH_CONJUNCTION",
        "parent_disk_verified": True, "parent_claim_durable": True, "prerequisite_offline_verified": True,
        "manifest_sha256": mh, "parent_intent_sha256": ih, "shared_owner_sha256": sha(owner_path.read_bytes()),
        "reservation_sha256": sha((folder / "browser-reservation.json").read_bytes()),
        "review_sha256": reservation["review_sha256"], "claim_sha256": sha((folder / "browser-claim-intent.json").read_bytes()),
        "browser_source_sha256": reservation["browser_source_sha256"], "nonce": reservation["nonce"],
        "end": manifest["end"], "verified_at_utc": at.isoformat(), "reservation": reservation}
    exclusive(folder / "browser-binding.json", binding)
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "localcheck", "activate", "reserve", "claim", "cleanup"))
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    parser.add_argument("--proposal-tests", type=Path)
    args = parser.parse_args()
    folder = args.package.resolve()
    require(folder.parent == r.rt.HOME.resolve() and folder.name.startswith("auto-path-diagnostic-"), "new_unbound_package_only")
    if args.stage == "prepare":
        require(all(x is not None for x in (args.tests, args.browser_tests, args.proposal_tests)), "actual_test_receipts_required")
        prepare(folder, args.tests, node_receipts=(args.browser_tests, args.proposal_tests))
    elif args.stage == "localcheck":
        localcheck(folder)
    elif args.stage == "activate":
        Stages(folder, ProductionAdapter(folder)).activate()
    elif args.stage == "cleanup":
        Stages(folder, ProductionAdapter(folder)).cleanup()
    elif args.stage == "reserve":
        reserve(folder, ProductionAdapter(folder))
    else:
        claim(folder)
    print(json.dumps({"status": "COMPLETED_" + args.stage.upper(),
                      "manifest_sha256": sha((folder / "manifest.json").read_bytes())}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # No raw Azure error, token, body or exception text on CLI failure.
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)