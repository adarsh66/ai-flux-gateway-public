"""Pure exact-delta guards. No Azure writes, role grants or deployment entrypoint."""
from copy import deepcopy
import re
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.poc_controls_preflight import ACTIONS, FRAGMENT_NAME


def expected_policy(before):
    root = ET.fromstring(before)
    quotas = root.findall(".//quota-by-key")
    rt.require(len(quotas) == 1 and quotas[0].attrib == {
        "calls": "1000", "renewal-period": "86400",
        "counter-key": '@("project-demo:" + context.Subscription.Id)'}, "exact_original_call_counter")
    quota = quotas[0]
    quota.tag = "include-fragment"
    quota.attrib.clear()
    quota.set("fragment-id", FRAGMENT_NAME)
    rate = root.findall(".//rate-limit-by-key")
    tokens = root.findall(".//llm-token-limit")
    rt.require(len(rate) == len(tokens) == 1, "singular_existing_limiters")
    changes = [(rate[0], "calls", "60", "aiflux-poc-rpm"),
               (tokens[0], "tokens-per-minute", "2048", "aiflux-poc-tpm"),
               (tokens[0], "token-quota", "10000", "aiflux-poc-token-quota")]
    for node, attribute, old, variable in changes:
        rt.require(node.get(attribute) == old, "exact_existing_limits")
        node.set(attribute, f'@(context.Variables.GetValueOrDefault<int>("{variable}", {old}))')
    scans = root.findall(".//llm-content-safety")
    rt.require(len(scans) == 3, "three_mandatory_safety_passes")
    for scan in scans:
        for category, variable in [("Hate", "hate"), ("Violence", "violence"),
                                   ("Sexual", "sexual"), ("SelfHarm", "self-harm")]:
            matches = scan.findall(f".//*[@name='{category}']")
            rt.require(len(matches) == 1 and matches[0].get("threshold") == "1", "exact_safety_category")
            matches[0].set("threshold", f'@(context.Variables.GetValueOrDefault<int>("aiflux-{variable}-threshold", 1))')
    return ET.tostring(root, encoding="unicode")


def guard_policy(before, desired):
    rt.require(policy_structure(expected_policy(before)) == policy_structure(desired),
               "unapproved_policy_delta")


def guard_protected(before, after, before_settings, after_settings, images):
    """Allow only two image pins and three explicit API flags, never hash exclusions."""
    rt.require(set(images) == {"api", "admin"}, "exact_api_admin_images")
    expected = deepcopy(before)
    for name, image in images.items():
        rt.require(re.fullmatch(r"pocidstokenexacr\.azurecr\.io/aiflux-" + name + r"@sha256:[a-f0-9]{64}", image),
                   "immutable_expected_image")
        expected["runtime"]["sites"][name]["image"] = "DOCKER|" + image
    settings = deepcopy(before_settings)
    settings["api"].update({"AIFLUX_GATEWAY_CONTROLS_POC_ENABLED": "true",
                            "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED": "false",
                            "AIFLUX_GATEWAY_SETTINGS_SCOPES": '["dev-unified"]'})
    # Hashes are recomputed over complete maps. No key/value can be ignored.
    from scripts.deployment.finops_function_stage import sha
    expected["settings_hashes"] = {key: sha(value) for key, value in settings.items()}
    rt.require(after_settings == settings and after == expected, "protected_release_baseline_changed")


def require_publisher(preflight):
    rt.require(preflight.get("publisher_fragment_permission_verified") is True,
               "missing_exact_publisher_fragment_permission_no_rbac_authorization")
    selected = preflight.get("selected_publisher_principal_id")
    matches = [p for p in preflight.get("publisher_permissions", []) if p["principal_id"] == selected]
    rt.require(bool(selected) and len(matches) == 1 and all(
        matches[0]["fragment_actions"].get(action) is True for action in ACTIONS)
        and set(matches[0]["fragment_actions"]) == set(ACTIONS), "selected_publisher_grant_required")