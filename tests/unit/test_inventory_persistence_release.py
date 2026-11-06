"""Independent exact-delta guards: no Azure calls, no production mutation."""
from copy import deepcopy
import json

import pytest

from scripts.deployment import inventory_persistence_release as r


def fixture():
    entries = [{"path": n, "sha256": "a" * 64} for n in sorted({r.DOCKER, *("modules/" + n for n in r.MODULES)})]
    return {"base_image": r.old.IMAGE, "changed_modules": {n: "a" * 64 for n in r.MODULES}, "entries": entries}


def test_exact_package_only_two_inventory_modules():
    value = fixture()
    r.package_guard(value, value["entries"], r.dockerfile())
    assert r.dockerfile().count("COPY ") == 4
    assert "python3.11/site-packages/aiflux/" in r.dockerfile()


@pytest.mark.parametrize("name", ["app.py", "config.py", "schemas.py", "decision_router.py", "Dockerfile", "gateway/catalog/changed.json", "settings.json"])
def test_arbitrary_dirty_file_rejected(name):
    value = fixture()
    entries = value["entries"] + [{"path": name, "sha256": "b" * 64}]
    with pytest.raises(RuntimeError):
        r.package_guard(value, entries, r.dockerfile())


@pytest.mark.parametrize("name", ["app.py", "config.py", "schemas.py", "decision_auth.py"])
def test_module_allowlist_cannot_be_substituted(name):
    value = fixture()
    value["changed_modules"].pop("external_inventory.py")
    value["changed_modules"][name] = "a" * 64
    with pytest.raises(RuntimeError):
        r.package_guard(value, value["entries"], r.dockerfile())


@pytest.mark.parametrize("suffix", ["\nENV AUTO=true\n", "\nRUN pip install changed\n", "\nCOPY . /app\n", "\nUSER root\n"])
def test_docker_settings_dependencies_or_broad_copy_rejected(suffix):
    value = fixture()
    with pytest.raises(RuntimeError):
        r.package_guard(value, value["entries"], r.dockerfile() + suffix)


def test_base_image_cannot_change():
    value = fixture()
    value["base_image"] = value["base_image"].replace("b489df", "a489df")
    with pytest.raises(RuntimeError):
        r.package_guard(value, value["entries"], r.dockerfile())


def test_source_byte_drift_rejected():
    value = fixture()
    entries = deepcopy(value["entries"])
    entries[0]["sha256"] = "c" * 64
    with pytest.raises(RuntimeError):
        r.package_guard(value, entries, r.dockerfile())


def test_immutable_intent_never_overwritten(tmp_path):
    r.save(tmp_path, "intent.json", {"source": "a" * 64})
    with pytest.raises(FileExistsError):
        r.save(tmp_path, "intent.json", {"source": "b" * 64})
    assert json.loads((tmp_path / "intent.json").read_text())["source"] == "a" * 64


def test_no_apply_entrypoint_in_fresh_workflow():
    from pathlib import Path
    source = Path(r.__file__).read_text()
    assert '"apply":' not in source
    assert 'fs.terraform(root, "apply"' not in source


def plan_fixture():
    from test_poc_reliability_release import plan, baseline, IMAGE
    return plan(), baseline(), IMAGE


def test_exact_api_saved_plan_only():
    plan, baseline, image = plan_fixture()
    r.strict(plan, image, baseline)


@pytest.mark.parametrize("defect", ["settings", "identity", "always_on", "registry", "admin", "fragment", "create", "unknown", "check", "predecessor", "errored", "no_checks"])
def test_independent_plan_delta_mutations_fail(defect):
    plan, baseline, image = plan_fixture()
    change = plan["resource_changes"][0]["change"]
    if defect == "settings":
        change["after"]["app_settings"]["flag"] = "different"
    elif defect == "identity":
        change["after"]["identity"] = {}
    elif defect == "always_on":
        change["after"]["site_config"][0]["always_on"] = False
    elif defect == "registry":
        change["after"]["site_config"][0]["application_stack"][0]["docker_registry_url"] = "https://foreign.invalid"
    elif defect in ("admin", "fragment"):
        plan["resource_changes"].append({"mode": "managed", "address": defect, "change": {"actions": ["update"]}})
    elif defect == "create":
        change["actions"] = ["create"]
    elif defect == "unknown":
        change["after_unknown"] = {"app_settings": True}
    elif defect == "check":
        plan["checks"][0]["status"] = "unknown"
    elif defect == "no_checks":
        plan.pop("checks")
    elif defect == "predecessor":
        change["before"]["site_config"][0]["application_stack"][0]["docker_image_name"] = "foreign"
    else:
        plan["errored"] = True
    with pytest.raises(RuntimeError):
        r.strict(plan, image, baseline)