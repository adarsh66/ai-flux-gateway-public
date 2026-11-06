"""Offline exact22 rendering/projection checks, never runtime scoring proof."""
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from test_auto_gateway_policy import render

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def all22():
    # Existing Terraform console evaluates locals; enabled=false, no refresh.
    return render([
        f"-var=route_manifest_path={ROOT / 'gateway/catalog/foundry-successor22-candidate-routes.json'}",
        "-var=glm_enabled=true",
    ])


def project_explicit(policy):
    """Remove only reviewed Auto hooks; retain exact remaining XML/C# text.

    Limit relocation and validator additions are checked separately, not silently
    normalized away here. Native provider wrapping is common to both policies.
    """
    tree = ET.fromstring(policy)
    parents = {c: p for p in tree.iter() for c in p}
    for node in list(tree.iter("choose")):
        when = node.find("when")
        if when is not None and when.get("condition") == '@(context.LastError.PolicyId == "aiflux-auto-auth" || context.LastError.PolicyId == "aiflux-auto-resolver" || context.LastError.PolicyId == "aiflux-auto-metadata")':
            parents[node].remove(node)
            continue
        if when is not None and when.get("condition") in (
            '@((bool)context.Variables["aiflux-auto"])',
            '@(context.Response.StatusCode == 200 && context.Request.Method == "POST" && context.Variables.GetValueOrDefault<bool>("aiflux-auto", false))',
        ):
            if node.find("otherwise") is not None:
                parent = parents[node]
                index = list(parent).index(node)
                for child in list(node.find("otherwise")):
                    parent.insert(index, copy.deepcopy(child))
                    index += 1
            parents[node].remove(node)
    return tree


def test_all22_off_identity_exact_membership_and_no_pool_expansion(all22):
    expected = set(json.loads((ROOT / "gateway/catalog/foundry-successor22-candidate-routes.json").read_bytes())["routes"]) | {"glm-5.3"}
    assert len(expected) == 22 and set(all22["aliases"]) == expected
    assert all22["off"] == all22["old"]
    assert len(all22["candidates"]) == 6
    assert not set(all22["candidates"]) & {"Decision-1", "auto", "glm-5.3", "mistral-medium-3-5"}


def test_explicit_scoring_outage_independence_and_route_payloads_unchanged(all22):
    old, candidate = ET.fromstring(all22["old"]), project_explicit(all22["on"])
    def fingerprint(node):
        return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(),
                tuple(fingerprint(c) for c in node))
    # Every explicit backend dispatch and provider body conversion is identical.
    for tag in ("set-backend-service", "authentication-managed-identity", "set-body",
                "llm-content-safety", "quota-by-key", "rate-limit-by-key", "llm-token-limit", "forward-request"):
        before = [fingerprint(n) for n in old.iter(tag)]
        after = [fingerprint(n) for n in candidate.iter(tag)]
        assert before == after, tag
    assert list(candidate.iter("send-request"))  # PII request still exists.
    assert candidate.find('.//send-request[@id="aiflux-auto-resolver"]') is None
    assert "aiflux-auto-response" not in ET.tostring(candidate, encoding="unicode")
    assert len(old.findall(".//quota-by-key")) == 1
    # This helper exposes the PRE-forward-wrapper composition. The module's
    # final forward_policy removes the historical shared retry wrapper.
    assert [n.attrib for n in candidate.findall(".//retry")] == [n.attrib for n in old.findall(".//retry")]
    module = (ROOT / "infra/project-route/main.tf").read_text()
    assert 'forward_policy = replace(local.attempt_policy, "/(?s)<backend>.*?</backend>/"' in module


@pytest.mark.parametrize("failure", ["timeout", "bad-schema", "denied"])
def test_scorer_failures_live_only_under_exact_auto_predicate(all22, failure):
    tree = ET.fromstring(all22["on"])
    parents = {c: p for p in tree.iter() for c in p}
    request = tree.find('.//send-request[@id="aiflux-auto-resolver"]')
    branch = parents[request]
    assert branch.get("condition") == '@((bool)context.Variables["aiflux-auto"])'
    assert tree.find('.//set-variable[@name="aiflux-auto"]').get("value") == '@((string)context.Variables["aiflux-model"] == "auto")'
    parser = branch.find('set-variable[@name="aiflux-auto-result"]').get("value")
    assert "response == null || response.StatusCode != 200" in parser
    assert 'catch { return ""; }' in parser
    rejection = branch.find("choose/when/return-response")
    assert rejection.find("set-status").get("code") == "503"
    assert not branch.findall(".//retry") and not branch.findall(".//set-backend-service")
    for alias in all22["aliases"]:
        assert alias != "auto"  # Exact predicate is false irrespective of scorer failure.


def test_auto_model_limits_keep_original_keys_values_and_shared_quota(all22):
    tree = ET.fromstring(all22["on"])
    original = ET.fromstring("<root>" + all22["model_limits"] + "</root>")
    branches = tree.findall('.//when[@condition=\'@((bool)context.Variables["aiflux-auto"])\']')
    selected = next(b for b in branches if b.find('send-request[@id="aiflux-auto-resolver"]') is not None)
    for node in original:
        assert selected.find(node.tag).attrib == node.attrib
    assert len(tree.findall(".//quota-by-key")) == 1
    text = all22["on"].split("</inbound>")[0]
    assert text.index("<quota-by-key") < text.index("auto-admission:") < text.index("<llm-content-safety")
    assert text.rindex("<llm-content-safety") < text.index('id="aiflux-auto-resolver"')


def test_direct_release_gate_accepts_exact_binding_and_rejects_drift(all22):
    import base64
    binding = {
        "mode": "bounded-production-direct-v1",
        "defaults_sha256": json.loads(base64.b64decode(all22["snapshot"]))["version"],
        "predecessor_sha256": hashlib.sha256(all22["old"].encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(all22["on"].encode()).hexdigest(),
        "independent_review_sha256": "a" * 64, "rollback_sha256": "b" * 64,
        "max_auto_attempts": 2, "max_scoring_calls": 2, "max_completion_calls": 2,
        "retries": 0, "fallback": False, "runtime_validation_pending": True,
        "stop_on_explicit_regression": True,
    }
    variables = [f"-var=route_manifest_path={ROOT / 'gateway/catalog/foundry-successor22-candidate-routes.json'}",
                 "-var=glm_enabled=true", "-var=auto_routing_enabled=true"]
    enabled = render([*variables, "-var=auto_routing_direct_release=" + json.dumps(binding)])
    assert enabled["off"] == enabled["on"]
    final = ET.fromstring(enabled["final"])
    assert enabled["native_valid"] is True
    assert not final.findall(".//retry")
    assert len(final.findall(".//forward-request")) == 1
    assert len(final.findall('.//send-request[@id="aiflux-auto-resolver"]')) == 1
    assert set(enabled["aliases"]) == set(all22["aliases"])
    binding["candidate_sha256"] = "0" * 64
    with pytest.raises(AssertionError, match="Auto requires"):
        render([*variables, "-var=auto_routing_direct_release=" + json.dumps(binding)])