"""Source-only pricing delta against the retained accepted 46-read baseline.

No live reads, policy publication, build submission or inference. Retained exports
are historical proof, not a claim about today's cloud state.
"""
import base64
import copy
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from test_auto_gateway_policy import render

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".deployment/auto-shared-ratecard-20261101-01/baseline01"


def snapshot(policy):
    node = policy.find('.//set-variable[@name="aiflux-auto-snapshot"]')
    encoded = re.search(r'FromBase64String\("([A-Za-z0-9+/=]+)"\)', node.get("value")).group(1)
    return json.loads(base64.b64decode(encoded))


def fingerprint(node):
    # Accepted ARM transport escapes expressions a second time. Decode only
    # that documented representation; no normalization of C# semantics.
    return (node.tag, tuple(sorted((k, html.unescape(v).replace("\r\n", "\n")) for k, v in node.attrib.items())),
            html.unescape(node.text or "").strip().replace("\r\n", "\n"), tuple(fingerprint(c) for c in node))


@pytest.fixture(scope="module")
def retained():
    report = json.loads((BASELINE / "REPORT.json").read_text())
    assert report["ARM_requests"] == 46 and report["cloud_writes"] == report["paid_calls"] == 0
    assert len(report["all22"]) == 22
    tree = ET.parse(BASELINE / "policy.xml").getroot()
    assert not tree.findall('.//set-variable[@name="aiflux-auto-price-only"]')
    return tree


def test_exact_accepted_embedded_fallback_six_descriptors_and_three_profiles(retained):
    rendered = render([
        f"-var=route_manifest_path={ROOT / 'gateway/catalog/foundry-successor22-candidate-routes.json'}",
        "-var=glm_enabled=true",
    ])
    expected = snapshot(retained)
    actual = json.loads(base64.b64decode(rendered["snapshot"]))
    assert actual == expected  # Including full original price and provenance.
    assert len(actual["candidates"]) == 6
    assert set(actual["profiles"]) == {"balanced", "cost", "quality"}
    assert {"Decision-1", "auto"}.isdisjoint(actual["candidates"])


def test_price_only_inclusion_is_before_criteria_and_mode_reset_without_quota():
    source = (ROOT / "gateway/policies/auto-resolve.xml.tftpl").read_text()
    tree = ET.fromstring("<fragment>" + source + "</fragment>")
    branch = tree.find("choose/when")
    nodes = list(branch)
    include = branch.find("include-fragment")
    pos = nodes.index(include)
    assert nodes[pos - 1].attrib == {"name": "aiflux-auto-price-only", "value": "@(true)"}
    assert nodes[pos + 1].attrib == {"name": "aiflux-auto-price-only", "value": "@(false)"}
    assert include.get("fragment-id") == "${pricing_fragment}"
    assert pos < nodes.index(branch.find('.//send-request[@id="aiflux-auto-resolver"]'))
    assert not tree.findall(".//quota-by-key")
    assert not tree.findall(".//llm-content-safety")
    assert not tree.findall(".//retry")


def test_backend_envelope_preserves_detached_controls_exactly_in_otherwise():
    # Coordinate read-only with the implemented backend contract. No edits.
    from aiflux import auto_pricing
    controls = (ROOT / "gateway/policies/poc-settings-defaults.xml").read_text()
    default = json.loads((ROOT / "services/control-plane/src/aiflux/pricing/auto-routing-defaults.json").read_text())
    value = {"schema": 1, "pool_version": "a" * 64, "rate_card_version": 1, "revision": "rate-card-v1",
             "source": "rate-card", "prices": {alias: None for alias in default["candidates"]}}
    import hashlib
    value["sha256"] = hashlib.sha256(auto_pricing.compact(value).encode()).hexdigest()
    wrapped = ET.fromstring(auto_pricing.envelope(controls, value))
    when = wrapped.find("choose/when")
    assert when.get("condition") == '@(context.Variables.GetValueOrDefault<bool>("aiflux-auto-price-only", false))'
    assert len(when) == 1 and when[0].get("name") == "aiflux-auto-price-projection"
    assert not when.findall(".//quota-by-key") and not when.findall(".//return-response")
    expected = ET.fromstring(controls)
    actual = ET.Element("fragment")
    for child in wrapped.find("choose/otherwise"):
        actual.append(copy.deepcopy(child))
    assert fingerprint(actual) == fingerprint(expected)
    assert len(auto_pricing.envelope(controls, value).encode()) <= 65536


def test_runtime_fragment_lifecycle_does_not_revert_last_good_or_create_authority():
    source = (ROOT / "infra/project-route/poc-controls.tf").read_text()
    lifecycle = source.split("lifecycle {", 1)[1]
    assert "prevent_destroy = true" in lifecycle
    assert "ignore_changes = [body.properties.value]" in lifecycle
    assert "ignore_changes = all" not in source
    auto = (ROOT / "infra/project-route/auto-routing.tf").read_text()
    assert "pricing_fragment     = local.poc_fragment_name" in auto
    assert 'resource "' not in auto and 'data "' not in auto
    assert "!var.poc_controls_enabled" in auto and "!var.admin_settings_enabled" in auto


def test_preservation_of_all22_auth_safety_quota_finops_outside_reviewed_delta(retained):
    from test_auto_additive_release import project_explicit
    rendered = render([
        f"-var=route_manifest_path={ROOT / 'gateway/catalog/foundry-successor22-candidate-routes.json'}",
        "-var=glm_enabled=true",
    ])
    # Compare protected nodes with the accepted policy, after removing ONLY
    # Auto branches. This retains exact auth, provider body dialect and FinOps.
    before = project_explicit(ET.tostring(retained, encoding="unicode"))
    after = project_explicit(rendered["final"])
    # Compare the final native-provider boundary, not pre-native local on.
    for tag in ("validate-jwt", "quota-by-key", "rate-limit-by-key", "llm-token-limit", "llm-content-safety"):
        assert [fingerprint(n) for n in before.iter(tag)] == [fingerprint(n) for n in after.iter(tag)], tag
    for name in ("aiflux-finops-usage",):
        old = before.findall(f'.//set-variable[@name="{name}"]')
        new = after.findall(f'.//set-variable[@name="{name}"]')
        assert len(old) == len(new) and len(old) > 0, name
        for a, b in zip(old, new):
            # Literal newlines in XML attributes normalize to spaces at parse.
            # This checks transport text parity ONLY, not native C# semantics:
            # accepted comments MUST keep actual newlines during live delta.
            assert html.unescape(a.get("value")).replace("\r\n", "\n").replace("\n", " ") == html.unescape(b.get("value")), name