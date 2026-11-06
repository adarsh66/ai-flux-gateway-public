"""Offline-only tests of the rate-card release's approved storage read adapter."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.deployment import ratecard_release as release
from scripts.deployment import project_route_product_access as product


def historical_protected(self):
    value = rt.cli(["rest", "--method", "get", "--url",  # noqa: F821
                    "https://management.azure.com" + rt.RG  # noqa: F821
                    + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=2023-05-01"])
    assert len(value["properties"]["networkAcls"]["ipRules"]) == 4
    return {"state_network": value["properties"], "unchanged": "preserved"}


def historical_snapshot():
    return ProductRun().protected()  # noqa: F821


@pytest.mark.parametrize("drift", [None, "extra_ip", "shared_key"])
def test_exact_approved_storage_only(monkeypatch, drift):
    ips = ["167.103.66.248", "167.103.66.93", "167.103.65.36", "167.103.63.12"]
    before = {"properties": {"networkAcls": {"defaultAction": "Deny", "ipRules": [
        {"value": ip, "action": "Allow"} for ip in ips]},
        "publicNetworkAccess": "Enabled", "allowSharedKeyAccess": True}}
    approved = deepcopy(before)
    approved["properties"]["networkAcls"]["ipRules"].append({"value": "167.103.67.80", "action": "Allow"})
    actual = deepcopy(approved)
    if drift == "extra_ip":
        actual["properties"]["networkAcls"]["ipRules"].append({"value": "1.2.3.4", "action": "Allow"})
    elif drift == "shared_key":
        actual["properties"]["allowSharedKeyAccess"] = False
    calls = []

    def cli(args):
        calls.append(args)
        return actual

    def load(path):
        if path.name == "result.json":
            return {"success": True, "account_comparison_passed": True, "all_other_account_properties_exact": True}
        return {"account": before if path.name == "before.json" else approved}

    # All cloud dependencies are replaced. This cannot make network requests.
    monkeypatch.setattr(release, "load", load)
    monkeypatch.setattr(release.r, "rt", SimpleNamespace(HOME=release.HOME.parent,
                        RG="/subscriptions/test/resourceGroups/test", cli=cli, require=release.r.rt.require))
    monkeypatch.setattr(product.ProductRun, "__init__", lambda self: None)
    monkeypatch.setattr(product.ProductRun, "protected", historical_protected)
    monkeypatch.setattr(release.r, "snapshot", historical_snapshot)
    if drift:
        with pytest.raises(RuntimeError, match="approved_storage_baseline_drift"):
            release.snapshot()
    else:
        result = release.snapshot()
        assert result == {"state_network": approved["properties"], "unchanged": "preserved"}
        assert actual == approved  # No mutation of the actual response.
    assert len(calls) == 1


def test_three_image_variables_preserve_other_inputs(monkeypatch):
    images = {k: "registry/" + k + "@sha256:" + "a" * 64 for k in release.KINDS}
    baseline = {"sites": "retained"}

    def legacy(pair, current):
        assert pair == {k: images[k] for k in ("api", "admin")}
        assert current is baseline
        return {"apps": {"api": {"image": pair["api"].split("/", 1)[1]},
                         "admin": {"image": pair["admin"].split("/", 1)[1]},
                         "customer": {"image": "old", "other": "unchanged"}}, "preserved": True}

    monkeypatch.setattr(release.r, "runtime_variables", legacy)
    value = release.runtime_variables(images, baseline)
    assert value["apps"]["customer"] == {"image": images["customer"].split("/", 1)[1], "other": "unchanged"}
    assert value["preserved"] is True
    with pytest.raises(RuntimeError, match="exact_three_runtime_images"):
        release.runtime_variables({"api": images["api"]}, baseline)