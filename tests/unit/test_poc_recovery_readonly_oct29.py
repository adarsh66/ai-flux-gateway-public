"""Pure recovery comparison checks: no credentials, Azure, or publication."""
import pytest

from scripts.deployment.poc_recovery_readonly_oct29 import (
    compare, desired_configuration, extract_bindings, fingerprint, render,
)


def bindings():
    return [
        {"subscription_id": "11111111-1111-4111-8111-111111111111",
         "organization_id": "85d2748e-83b4-4349-a611-131742918afa"},
        {"subscription_id": "22222222-2222-4222-8222-222222222222",
         "organization_id": "85d2748e-83b4-4349-a611-131742918afa"},
    ]


def test_roundtrip_is_not_stored_revision_binding_proof():
    xml = render(desired_configuration(), bindings())
    extracted, rebuilt, proof = compare(xml)
    assert extracted == bindings()
    assert fingerprint(xml) == fingerprint(rebuilt)
    assert proof["canonical_match_using_extracted_current_bindings"]
    assert not proof["revision10_stored_bindings_observed"]
    assert not proof["revision10_exact_ownership_match_proven"]
    assert not proof["reconcile_will_skip_put_proven"]


def test_identical_config_different_binding_requires_different_fingerprint():
    config = desired_configuration()
    altered = bindings()
    altered[0]["organization_id"] = "33333333-3333-4333-8333-333333333333"
    assert fingerprint(render(config, bindings())) != fingerprint(render(config, altered))


def test_json_binding_order_is_not_normalized_by_xml_canonicalizer():
    config = desired_configuration()
    assert fingerprint(render(config, bindings())) != fingerprint(render(config, list(reversed(bindings()))))


def test_changed_safety_detected():
    config = desired_configuration().model_copy(deep=True)
    config.overrides[0].safety.self_harm = 1
    assert not compare(render(config, bindings()))[2]["canonical_match_using_extracted_current_bindings"]


def test_unknown_ownership_expression_fails_closed():
    xml = render(desired_configuration(), bindings()).replace("var owners", "var different")
    with pytest.raises(RuntimeError, match="ownership_expression_shape"):
        extract_bindings(xml)