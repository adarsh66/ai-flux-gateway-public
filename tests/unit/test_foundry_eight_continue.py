"""Offline safety checks. No cloud, original collector, or release invocation."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.deployment import foundry_eight_continue as c
from scripts.deployment import foundry_eight_recover_tail as tail
from scripts.deployment import foundry_eight_finalize as final


class ContinuationTests(unittest.TestCase):
    def test_empty_settings_get_is_unknown_not_live_hash(self):
        result = final.settings_evidence(c.settings_projection({}))
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["settings_sha256"])
        self.assertIsNone(result["safe_flags"])

    def test_nonempty_settings_projection_preserves_hash(self):
        projection = c.settings_projection({"AIFLUX_GATEWAY_CONTROLS_POC_ENABLED": "true"})
        self.assertEqual(final.settings_evidence(projection)["settings_sha256"], projection["settings_sha256"])

    def test_redacted_policy_is_unknown_not_equal(self):
        result = final.retained_text_comparison({"properties": {"value": "[REDACTED]"}}, "ignored")
        self.assertIsNone(result["equal"])

    def test_unredacted_policy_exact_byte_comparison(self):
        result = final.retained_text_comparison({"properties": {"value": "XML\r\n"}}, final.text_hash("XML\r\n"))
        self.assertTrue(result["equal"])
        self.assertNotEqual(final.text_hash("XML\r\n"), final.text_hash("XML\n"))

    def test_exact_arm_fragment_casing_is_canonicalized(self):
        path = c.APIM + "/policyFragments/aiflux-dev-unified-poc-settings"
        self.assertEqual(tail.fragment_path({"name": "aiflux-dev-unified-poc-settings",
            "id": path.replace("/policyFragments/", "/policyfragments/")}), path)

    def test_fragment_identity_not_prefix_match(self):
        for name, rid in (("../other", c.APIM + "/policyFragments/../other"),
                          ("name", c.APIM + "/policyFragments/name/other"),
                          ("name", c.APIM.replace("POC", "OTHER") + "/policyFragments/name")):
            with self.assertRaises(RuntimeError):
                tail.fragment_path({"name": name, "id": rid})

    def test_exact_apim_path_allowed(self):
        c.Reader.validate_url("https://management.azure.com" + c.API +
                              "/policies/policy?format=rawxml&api-version=2024-05-01")

    def test_scope_and_secret_endpoints_denied(self):
        for path in ("http://management.azure.com" + c.API, "https://evil.test" + c.API,
                     "https://management.azure.com/other/providers/x", "https://management.azure.com" + c.APIM + "/namedValues",
                     "https://management.azure.com" + c.API + "/listSecrets",
                     "https://management.azure.com" + c.rt.RG + "/providers/Microsoft.CognitiveServices/accounts/x/deployments"):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                c.Reader.validate_url(path)

    def test_exclusive_never_overwrites(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            c.exclusive(folder, "intent.json", {"first": True})
            before = (folder / "intent.json").read_bytes()
            with self.assertRaises(FileExistsError):
                c.exclusive(folder, "intent.json", {"second": True})
            self.assertEqual(before, (folder / "intent.json").read_bytes())

    def test_errors_do_not_contain_response_or_secrets(self):
        error = HTTPError("https://secret.test", 403, "SECRET_VALUE", {}, io.BytesIO(b"SECRET_BODY"))
        self.assertEqual(c.failure(error), {"category": "http_error", "http_status": 403})
        self.assertNotIn("SECRET", json.dumps(c.failure(RuntimeError("SECRET raw message"))))

    def test_scrub_credentials_and_subscription_keys(self):
        value = {"credentials": {"header": {"api-key": "secret"}}, "primaryKey": "secret", "secondaryKey": "secret",
                 "properties": {"value": '<set-header name="Authorization"><value>secret</value></set-header>'}}
        text = json.dumps(c.scrub(value))
        self.assertNotIn("secret", text)
        self.assertIn("REDACTED", text)

    def test_settings_projection_contains_no_values(self):
        result = c.settings_projection({"PASSWORD": "SECRET", "AIFLUX_GATEWAY_CONTROLS_POC_ENABLED": "true"})
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["safe_flags"]["AIFLUX_GATEWAY_CONTROLS_POC_ENABLED"], "true")

    def test_pagination_not_reread_and_complete(self):
        with tempfile.TemporaryDirectory() as name:
            reader = c.Reader(Path(name))
            path = c.APIM + "/backends?api-version=2024-05-01"
            url = "https://management.azure.com" + c.APIM + "/backends?next=1"
            with patch.object(reader, "get", side_effect=[{"value": [1], "nextLink": url}, {"value": [2]}]) as get:
                self.assertEqual(reader.collection(path), {"value": [1, 2], "pages": 2, "complete": True})
                self.assertEqual(get.call_count, 2)

    def test_pagination_cross_scope_or_cycle_blocked(self):
        for link in ("https://evil.test/foreign", "https://management.azure.com" + c.APIM + "/subscriptions",
                     "https://management.azure.com" + c.APIM + "/backends?api-version=2024-05-01"):
            with tempfile.TemporaryDirectory() as name:
                reader = c.Reader(Path(name))
                with patch.object(reader, "get", return_value={"value": [], "nextLink": link}), self.assertRaises(RuntimeError):
                    reader.collection(c.APIM + "/backends?api-version=2024-05-01")

    def test_section_failure_is_durable_and_sanitized(self):
        with tempfile.TemporaryDirectory() as name:
            reader = c.Reader(Path(name))
            def fail():
                raise ValueError("SECRET")
            self.assertIsNone(reader.section("example", fail))
            result = (Path(name) / "example-failure.json").read_text()
            self.assertNotIn("SECRET", result)
            self.assertEqual(len(reader.errors), 1)

    def test_no_scope_guard_no_wire(self):
        with tempfile.TemporaryDirectory() as name:
            reader = c.Reader(Path(name))
            with self.assertRaisesRegex(RuntimeError, "fresh_scope_guard_required"):
                reader.get(c.API + "?api-version=2024-05-01")
            self.assertTrue((Path(name) / "read-001-failure.json").is_file())

    def test_get_only_cache_and_receipt(self):
        with tempfile.TemporaryDirectory() as name:
            reader = c.Reader(Path(name))
            reader.token = "not-a-real-token"
            response = unittest.mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = b'{"value": []}'
            response.status = 200
            response.headers = {}
            reader.opener = unittest.mock.Mock()
            reader.opener.open.return_value = response
            path = c.APIM + "/backends?api-version=2024-05-01"
            self.assertEqual(reader.get(path), reader.get(path))
            self.assertEqual(reader.opener.open.call_count, 1)
            self.assertEqual(reader.opener.open.call_args.args[0].method, "GET")
            text = "".join(p.read_text() for p in Path(name).glob("*.json"))
            self.assertNotIn("not-a-real-token", text)

    def test_optional_404_is_absence_not_permission_for_write(self):
        reader = unittest.mock.Mock()
        reader.get.side_effect = HTTPError("https://management.azure.com", 404, "secret", {}, None)
        self.assertEqual(c.optional_policy(reader, c.API), {"absent": True, "http_status": 404})
        self.assertEqual(reader.get.call_count, 1)

    def test_policy_summary_extracts_actual_controls(self):
        value = {"properties": {"value": '<policies><inbound><include-fragment fragment-id="aiflux-dev-unified-poc-settings"/>'
                 '<set-body>{"data":[{"id":"model"}]}</set-body></inbound><backend><forward-request/></backend></policies>'}}
        result = c.policy_summary(value)
        self.assertEqual(result["catalog_aliases"], ["model"])
        self.assertEqual(result["forward_requests"], 1)
        self.assertEqual(result["retry_nodes"], 0)
        self.assertEqual(result["fragment_references"], ["aiflux-dev-unified-poc-settings"])

    def test_redirect_is_not_followed(self):
        self.assertIsNone(c.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))


if __name__ == "__main__":
    unittest.main()