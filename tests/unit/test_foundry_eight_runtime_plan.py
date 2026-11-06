"""Offline exact-four negative guards; no Azure/Terraform/subprocess execution."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.deployment import foundry_eight_runtime_plan as p


def fixture():
    images = {k: p.builds.HOST + "/aiflux-" + k + "@sha256:" + p.DIGESTS[k] for k in p.KINDS}
    baseline = {"runtime": {"sites": {}}}
    rows = []
    for address, kind in p.ADDRESSES.items():
        image = "aiflux-" + kind + "@sha256:" + p.builds.PINS[kind]
        baseline["runtime"]["sites"][kind] = {"image": "DOCKER|" + p.builds.HOST + "/" + image}
        stack = ({"docker": [{"image_name": "aiflux-ingestion@sha256", "image_tag": p.builds.PINS[kind],
                  "registry_url": "https://" + p.builds.HOST, "registry_username": "", "registry_password": ""}]}
                 if kind == "ingestion" else {"docker_image_name": image, "docker_registry_url": "https://" + p.builds.HOST})
        old = {"id": p.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind,
               "name": "poc-ids-token-ex-" + kind, "enabled": True,
               "app_settings": {"timer": "false", "watermark": "original", "POC": "true", "V2": "false"},
               "identity": [{"type": "UserAssigned", "identity_ids": ["original"]}],
               "site_config": [{"application_stack": [stack], "always_on": True, "ip_restriction": ["original"]}]}
        new = deepcopy(old)
        if kind == "ingestion":
            new["site_config"][0]["application_stack"][0]["docker"][0]["image_tag"] = p.DIGESTS[kind]
        else:
            new["site_config"][0]["application_stack"][0]["docker_image_name"] = images[kind].split("/", 1)[1]
        rows.append({"address": address, "mode": "managed", "change": {"actions": ["update"], "before": old,
                    "after": new, "after_unknown": {}}})
    return {"applyable": True, "errored": False, "resource_changes": rows,
            "checks": [{"address": {"kind": "resource"}, "status": "pass"}]}, images, baseline


class FourImageGuard(unittest.TestCase):
    def test_exact_four(self):
        data, images, before = fixture()
        self.assertEqual(len(p.guard(data, images, before)), 4)

    def test_noop_noise_and_data_reads(self):
        data, images, before = fixture()
        data["resource_changes"] += [{"mode": "managed", "change": {"actions": ["no-op"]}},
                                     {"mode": "data", "change": {"actions": ["read"]}}]
        self.assertEqual(len(p.guard(data, images, before)), 4)

    def test_every_nonimage_leaf_rejected(self):
        for index in range(4):
            for field in ("app_settings", "identity", "enabled", "tags", "public_network_access_enabled",
                          "virtual_network_subnet_id", "content_share_force_disabled"):
                with self.subTest(index=index, field=field):
                    data, images, before = fixture()
                    data["resource_changes"][index]["change"]["after"][field] = "changed"
                    with self.assertRaises(RuntimeError):
                        p.guard(data, images, before)

    def test_every_protected_site_setting_rejected(self):
        for index in range(4):
            for field in ("always_on", "ip_restriction", "app_command_line", "container_registry_use_managed_identity"):
                with self.subTest(index=index, field=field):
                    data, images, before = fixture()
                    data["resource_changes"][index]["change"]["after"]["site_config"][0][field] = "changed"
                    with self.assertRaises(RuntimeError):
                        p.guard(data, images, before)

    def test_write_noise_delete_replace_create_read_forbidden(self):
        for actions in (["update"], ["delete"], ["create"], ["delete", "create"], ["read"]):
            data, images, before = fixture()
            data["resource_changes"].append({"address": "azapi_resource.auto[0]", "mode": "managed", "change": {"actions": actions}})
            with self.assertRaises(RuntimeError):
                p.guard(data, images, before)

    def test_missing_duplicate_or_wrong_actions(self):
        for variant in ("missing", "duplicate", "create", "delete", "replace", "import"):
            data, images, before = fixture()
            if variant == "missing":
                data["resource_changes"].pop()
            elif variant == "duplicate":
                data["resource_changes"].append(deepcopy(data["resource_changes"][0]))
            elif variant == "import":
                data["resource_changes"][0]["change"]["importing"] = {"id": "new"}
            else:
                data["resource_changes"][0]["change"]["actions"] = {"create": ["create"], "delete": ["delete"], "replace": ["delete", "create"]}[variant]
            with self.subTest(variant=variant), self.assertRaises(RuntimeError):
                p.guard(data, images, before)

    def test_wrong_pins_tags_registry_or_predecessor(self):
        for kind in p.KINDS:
            for variant in ("tag", "registry", "predecessor", "id"):
                data, images, before = fixture()
                row = next(r for r in data["resource_changes"] if p.ADDRESSES[r["address"]] == kind)
                if variant == "tag":
                    images[kind] = p.builds.HOST + "/aiflux-" + kind + ":latest"
                elif variant == "registry":
                    images[kind] = "elsewhere.invalid/aiflux-" + kind + "@sha256:" + p.DIGESTS[kind]
                elif variant == "predecessor":
                    before["runtime"]["sites"][kind]["image"] += "0"
                else:
                    row["change"]["after"]["id"] += "-new"
                with self.subTest(kind=kind, variant=variant), self.assertRaises(RuntimeError):
                    p.guard(data, images, before)

    def test_function_other_docker_leaves_rejected(self):
        for field in ("image_name", "registry_url", "registry_username", "registry_password"):
            data, images, before = fixture()
            data["resource_changes"][3]["change"]["after"]["site_config"][0]["application_stack"][0]["docker"][0][field] = "changed"
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                p.guard(data, images, before)

    def test_unknown_writable_failed_deferred_drift_rejected(self):
        for variant in ("unknown", "check", "deferred", "errored", "applyable", "drift"):
            data, images, before = fixture()
            if variant == "unknown":
                data["resource_changes"][0]["change"]["after_unknown"] = {"app_settings": True}
            elif variant == "check":
                data["checks"][0]["status"] = "unknown"
            elif variant == "deferred":
                data["deferred_changes"] = ["unknown"]
            elif variant == "drift":
                data["resource_drift"] = ["changed"]
            else:
                data[variant] = variant == "errored"
            with self.subTest(variant=variant), self.assertRaises(RuntimeError):
                p.guard(data, images, before)

    def test_no_mutating_terraform_entrypoint(self):
        for args in (("apply",), ("destroy",), ("import",), ("state", "push"), ("workspace", "new")):
            with self.subTest(args=args), patch.object(p, "command") as command:
                with self.assertRaises(RuntimeError):
                    p.terraform("forbidden", *args)
                command.assert_not_called()

    def test_build_freezes_locally_bind_original_four(self):
        self.assertEqual(set(p.build_binding(remote=False)), set(p.KINDS))


if __name__ == "__main__":
    unittest.main()