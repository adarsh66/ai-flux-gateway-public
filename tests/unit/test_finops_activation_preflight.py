"""A source/build hash or row count cannot substitute for catalog acceptance."""
from copy import deepcopy
import json

import pytest

from scripts.deployment import finops_activation_preflight as gate


ROUTES = {"m" + str(n): {} for n in range(10)}
ALIASES = [*ROUTES, "glm-5.3"]


def catalog(aliases=ALIASES):
    return {"models": [{"id": a, "enabled": True} for a in aliases]}


def test_exact_membership_is_not_runtime_or_capability_acceptance():
    data = catalog()
    before = deepcopy(data)
    result = gate.membership(data, ROUTES, ALIASES)
    assert result["membership_matches"] is True
    assert result["catalog_accepted"] is False
    assert result["missing_from_package"] == result["package_not_live"] == []
    assert data == before


def test_same_count_with_wrong_alias_is_blocked():
    result = gate.membership(catalog([*ROUTES, "obsolete"]), ROUTES, ALIASES)
    assert result["membership_matches"] is False
    assert result["missing_from_package"] == ["glm-5.3"]
    assert result["package_not_live"] == ["obsolete"]
    assert result["catalog_accepted"] is False


@pytest.mark.parametrize("aliases", [ALIASES[:-1], ALIASES + ["auto"], ALIASES[:-1] + ["foreign"]])
def test_live_membership_must_be_exact(aliases):
    with pytest.raises(RuntimeError, match="live_published_membership_not_approved"):
        gate.membership(catalog(), ROUTES, aliases)


def test_duplicate_packaged_alias_is_rejected():
    with pytest.raises(RuntimeError, match="duplicate_packaged_alias"):
        gate.membership(catalog(ALIASES + [ALIASES[0]]), ROUTES, ALIASES)


def test_enabled_placeholder_is_rejected():
    data = catalog()
    data["models"][0]["placeholder"] = True
    with pytest.raises(RuntimeError, match="enabled_placeholder"):
        gate.membership(data, ROUTES, ALIASES)


def test_disabled_extra_is_not_enabled_acceptance():
    data = catalog()
    data["models"].append({"id": "auto", "enabled": False})
    assert gate.membership(data, ROUTES, ALIASES)["membership_matches"]


def test_raw_policy_expression_is_not_treated_as_xml():
    policy = '<policies><when condition="@(x < 3 && y > 0)"/><set-body>' + json.dumps({
        "data": [{"id": a} for a in ALIASES]}) + '</set-body></policies>'
    assert gate.published_aliases(policy) == ALIASES


@pytest.mark.parametrize("policy", ["<policies/>", "<set-body>@(dynamic)</set-body>",
    '<set-body>{"data":[]}</set-body><set-body>{"data":[]}</set-body>'])
def test_missing_or_ambiguous_discovery_is_rejected(policy):
    with pytest.raises(RuntimeError, match="single_literal_discovery_required"):
        gate.published_aliases(policy)