"""Offline safety evidence for the explicitly authorized plan02 continuation."""
from copy import deepcopy
import io
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError

from scripts.deployment import foundry_eight_gateway_release as release


class Plan02Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        binding = patch.object(release, "OUTPUT", self.output)
        binding.start()
        self.addCleanup(binding.stop)
        self.reader = release.AttemptReader.__new__(release.AttemptReader)
        self.reader.label, self.reader.cache, self.reader.count = "test", {}, 0
        self.reader.deadline = release.time.monotonic() + 2400
        self.reader.token, self.reader.opener = "offline-not-a-token", Mock()
        self.url = ("https://management.azure.com" + release.rt.RG
                    + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/appsettings/list?api-version=2024-04-01")

    def response(self, value):
        response = Mock()
        response.status, response.headers = 200, {}
        response.geturl.return_value = self.url
        response.read.return_value = json.dumps(value).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_timeout_retry_is_bounded_and_settings_not_logged(self):
        value = {"properties": {"PRIVATE_SETTING": "do-not-serialize"}}
        self.reader.opener.open.side_effect = [TimeoutError(), self.response(value)]
        self.assertEqual(self.reader.request(self.url, "POST"), value)
        self.assertEqual(self.reader.opener.open.call_count, 2)
        self.assertEqual(self.reader.opener.open.call_args.kwargs["timeout"], 240)
        journal = b"".join(p.read_bytes() for p in (self.output / "reads").glob("*"))
        self.assertNotIn(b"do-not-serialize", journal)
        self.assertNotIn(b"offline-not-a-token", journal)
        self.assertIn(b"settings_list:api", journal)
        # A duplicate projection in one snapshot reuses the actual observation.
        self.reader.request(self.url, "POST")["properties"]["PRIVATE_SETTING"] = "changed-local-copy"
        self.assertEqual(self.reader.request(self.url, "POST"), value)
        self.assertEqual(self.reader.opener.open.call_count, 2)

    def test_two_timeouts_stop_no_third_request(self):
        self.reader.opener.open.side_effect = TimeoutError()
        with self.assertRaisesRegex(RuntimeError, "readonly_endpoint_failed"):
            self.reader.request(self.url, "POST")
        self.assertEqual(self.reader.opener.open.call_count, 2)
        self.assertEqual(len(list((self.output / "reads").glob("*-result.json"))), 2)

    def test_certificate_failure_not_retried(self):
        self.reader.opener.open.side_effect = URLError(ssl.SSLCertVerificationError("offline"))
        with self.assertRaises(RuntimeError):
            self.reader.request(self.url, "POST")
        self.assertEqual(self.reader.opener.open.call_count, 1)

    def test_nonread_and_wrong_scope_fail_before_wire(self):
        for url, method in ((self.url, "PUT"), (self.url.replace("/appsettings/list", "/appsettings"), "POST"),
                            (self.url.replace(release.rt.SUB, "different-sub"), "GET"),
                            (self.url.replace("/appsettings/list", "/listKeys"), "GET"),
                            (self.url.replace("management.azure.com", "evil.example"), "GET")):
            with self.assertRaises(RuntimeError):
                self.reader.request(url, method)
        self.reader.opener.open.assert_not_called()

    def test_optional_404_and_redirect_rejection(self):
        self.reader.opener.open.side_effect = HTTPError(self.url, 404, "offline", {}, io.BytesIO())
        self.assertEqual(self.reader.request(self.url, optional=True), {"absent": True, "status": 404})
        with self.assertRaisesRegex(RuntimeError, "readonly_redirect_rejected"):
            release.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")

    def test_expired_snapshot_has_no_request(self):
        self.reader.deadline = release.time.monotonic() - 1
        with self.assertRaisesRegex(RuntimeError, "snapshot_total_deadline"):
            self.reader.request(self.url)
        self.reader.opener.open.assert_not_called()

    def test_cli_write_and_other_attempt_names_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "readonly_cli_allowlist"):
            self.reader.cli(["account", "set", "--subscription", "other"])
        with self.assertRaisesRegex(RuntimeError, "only_explicitly_authorized_plan02"):
            release.begin_attempt("plan03")

    def test_exclusive_receipt_no_overwrite(self):
        release.exclusive("consumed.json", {"first": True})
        with self.assertRaises(FileExistsError):
            release.exclusive("consumed.json", {"first": False})
        self.assertEqual(release.load(self.output / "consumed.json"), {"first": True})

    def fixture(self):
        previous = (release.HOME / "prepare-policy.xml").read_bytes().decode()
        desired = (release.HOME / "candidate-policy.xml").read_bytes().decode()
        variables = release.load(release.HOME / "inputs.tfvars.json")
        changes = []
        for address, (name, endpoint) in release.BACKENDS.items():
            changes.append({"address": address, "mode": "managed", "change": {"actions": ["create"], "before": None,
                "after": {"name": name, "parent_id": release.rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim",
                          "type": "Microsoft.ApiManagement/service/backends@2024-05-01",
                          "body": {"properties": {"protocol": "http", "url": endpoint,
                              "tls": {"validateCertificateChain": True, "validateCertificateName": True}}}},
                "after_unknown": {"id": True, "output": True}}})
        before = {"name": "policy", "output": {}, "body": {"properties": {"format": "rawxml",
                  "value": (release.HOME / "historical-policy.xml").read_bytes().decode()}}}
        after = deepcopy(before)
        after["body"]["properties"]["value"] = desired
        changes.append({"address": release.POLICY, "mode": "managed", "change": {
            "actions": ["update"], "before": before, "after": after, "after_unknown": {"output": True}}})
        plan = {"applyable": True, "variables": {k: {"value": v} for k, v in variables.items()},
                "resource_changes": changes, "checks": [{"address": "offline", "status": "pass"}]}
        return plan, previous, desired, variables

    def test_exact_three_target_fixture_passes(self):
        self.assertEqual(len(release.guard(*self.fixture())), 3)

    def test_held_auto_even_noop_and_extra_writes_rejected(self):
        for address, actions in (("azapi_resource.auto_stage_revision[0]", ["no-op"]),
                                 ("azapi_resource.unapproved[0]", ["delete"])):
            fixture = self.fixture()
            fixture[0]["resource_changes"].append({"address": address, "mode": "managed", "change": {"actions": actions}})
            with self.assertRaises(RuntimeError):
                release.guard(*fixture)

    def test_unknown_backend_and_bad_checks_rejected(self):
        fixture = self.fixture()
        fixture[0]["resource_changes"][0]["change"]["after_unknown"]["body"] = True
        with self.assertRaisesRegex(RuntimeError, "unknown_writable"):
            release.guard(*fixture)
        fixture = self.fixture()
        fixture[0]["checks"][0]["status"] = "unknown"
        with self.assertRaisesRegex(RuntimeError, "every_saved_plan_check_pass"):
            release.guard(*fixture)

    def test_actual_retained_plan_xml_export_requires_exact_fresh_bytes(self):
        folder = release.HOME / "attempts/plan02"
        plan = release.load(folder / "plan.json")
        previous = (folder / "preplan-policy.xml").read_bytes().decode()
        desired = (release.HOME / "candidate-policy.xml").read_bytes().decode()
        variables = release.load(release.HOME / "inputs.tfvars.json")
        change = next(x["change"] for x in plan["resource_changes"] if x["address"] == release.POLICY)
        self.assertEqual(change["before"]["body"]["properties"]["format"], "xml")
        self.assertEqual(change["before"]["body"]["properties"]["value"], previous)
        # Actual target leaves this unused variable validation unknown. Never
        # relabel the saved status as pass or accept other unresolved checks.
        with self.assertRaisesRegex(RuntimeError, "every_saved_plan_check_pass"):
            release.guard(plan, previous, desired, variables)
        proof = {"passed": True, "saved_status_preserved": "unknown", "value": "xml",
                 "expression": 'contains(["xml", "rawxml"], var.global_policy_format)',
                 "context_sha256": release.digest(release.context_hashes()),
                 "plan_sha256": release.digest((folder / "gateway.tfplan").read_bytes())}
        self.assertEqual(len(release.guard(plan, previous, desired, variables, proof)), 3)
        bad = deepcopy(proof)
        bad["plan_sha256"] = "wrong"
        with self.assertRaisesRegex(RuntimeError, "actual_format_validation_proof_required"):
            release.guard(plan, previous, desired, variables, bad)
        change["before"]["body"]["properties"]["value"] += "\n"
        with self.assertRaisesRegex(RuntimeError, "plan_actual_exported_predecessor_bytes"):
            release.guard(plan, previous, desired, variables, proof)

    def test_finalizer_has_no_terraform_or_prepare_call(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(release.finalize_plan02))
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(called & {"terraform", "plan_release", "prepare", "begin_attempt"})


if __name__ == "__main__":
    unittest.main(verbosity=2)