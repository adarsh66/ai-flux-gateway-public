import pytest

from scripts.deployment import backend_connection_restore_oct29 as r


def baseline():
    return {"id": r.RID, "properties": {"provisioningState": "Succeeded", "publicNetworkAccess": "Enabled",
        "allowSharedKeyAccess": True, "networkAcls": {"defaultAction": "Deny", "bypass": "AzureServices",
        "ipRules": [{"value": ip, "action": "Allow"} for ip in sorted(r.PRIOR)],
        "ipv6Rules": [], "virtualNetworkRules": [], "resourceAccessRules": []}}}


def test_single_add_preserves_full_account_and_concurrent_rules():
    before = baseline()
    before["properties"]["networkAcls"]["ipRules"].append({"value": "203.0.113.8", "action": "Allow"})
    after = r.expected_account(before)
    assert r.assert_only_approved(before, after)
    assert len(before["properties"]["networkAcls"]["ipRules"]) == 4
    assert len(after["properties"]["networkAcls"]["ipRules"]) == 5


@pytest.mark.parametrize("field,value", [("defaultAction", "Allow"), ("bypass", "None"),
    ("ipv6Rules", [{"value": "2001:db8::/64", "action": "Allow"}]),
    ("virtualNetworkRules", [{"id": "changed"}]), ("resourceAccessRules", [{"resourceId": "changed"}])])
def test_rejects_other_acl_deltas(field, value):
    before = baseline()
    after = r.expected_account(before)
    after["properties"]["networkAcls"][field] = value
    with pytest.raises(RuntimeError, match="unapproved_account_delta"):
        r.assert_only_approved(before, after)


@pytest.mark.parametrize("field,value", [("publicNetworkAccess", "Disabled"), ("allowSharedKeyAccess", False),
                                        ("unrelatedSetting", True)])
def test_rejects_other_account_changes(field, value):
    before = baseline()
    after = r.expected_account(before)
    after["properties"][field] = value
    with pytest.raises(RuntimeError, match="unapproved_account_delta"):
        r.assert_only_approved(before, after)


def test_rejects_missing_prior_rule():
    before = baseline()
    before["properties"]["networkAcls"]["ipRules"].pop()
    with pytest.raises(RuntimeError, match="prior_rules_missing"):
        r.validate_before(before)


def test_existing_exact_rule_is_noop():
    before = r.expected_account(baseline())
    assert r.validate_before(before)
    assert r.expected_account(before) == before


def test_rejects_concurrent_rule_loss():
    before = baseline()
    before["properties"]["networkAcls"]["ipRules"].append({"value": "203.0.113.8", "action": "Allow"})
    after = r.expected_account(before)
    after["properties"]["networkAcls"]["ipRules"].pop(-2)
    with pytest.raises(RuntimeError, match="unapproved_account_delta"):
        r.assert_only_approved(before, after)


def test_existing_intent_prevents_restore_replay_before_any_request(tmp_path):
    (tmp_path / "write-intent.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="existing_write_intent_never_replay"):
        r.restore(tmp_path)