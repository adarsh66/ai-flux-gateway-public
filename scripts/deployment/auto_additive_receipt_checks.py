"""Focused offline publication transport checks; fixtures are NOT release evidence.

Runs against the modules on sys.path, including the actual Linux overlay during
image build. No pytest/dependency installation, database, network or model calls.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiflux import auto_snapshot as reader
from aiflux.config import Settings


class ReceiptTransport(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(_env_file=None, environment="testing",
            auto_routing_enabled=True, auto_routing_direct_validation_enabled=True,
            auto_routing_published_policy_sha256="1" * 64)
        self.snapshot = {"version": "2" * 64}
        # Deliberately synthetic UNIT FIXTURE, never emitted as a live receipt.
        self.receipt = {"schema": 2, "snapshot_version": self.snapshot["version"],
            "policy_sha256": "1" * 64, "authorization_evidence_sha256": "3" * 64,
            "endpoint": reader.ENDPOINT, "deployment": "Decision-1",
            "gateway_principal": reader.GATEWAY_PRINCIPAL, "gateway_client": reader.GATEWAY_CLIENT,
            "response_contract": "systemone-choice-probabilities-v1",
            "runtime_verified": False, "validation_mode": "bounded-production-direct-v1",
            "budget": {"auto_attempts": 2, "scoring_calls": 2, "completion_calls": 2,
                       "retries": 0, "fallback": False}, "stop_on_explicit_regression": True,
            "independent_review_sha256": "4" * 64, "policy_readback_sha256": "5" * 64,
            "rollback_sha256": "6" * 64}

    def read(self, receipt=None):
        self.settings.auto_routing_publication_json = json.dumps(self.receipt if receipt is None else receipt)
        return reader.publication(self.settings, self.snapshot)

    def test_inline_schema2_pending_not_runtime_proof(self):
        self.assertEqual(self.read(), self.receipt)
        self.assertIs(self.read()["runtime_verified"], False)

    def test_no_transport_closed(self):
        self.assertIsNone(reader.publication(self.settings, self.snapshot))

    def test_ambiguous_transport_closed(self):
        self.settings.auto_routing_publication_path = Path("must-not-be-read")
        with patch.object(Path, "read_text", side_effect=AssertionError("ambiguous file read")):
            self.assertIsNone(self.read())

    def test_path_compatibility(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.json"
            path.write_text(json.dumps(self.receipt), encoding="utf-8")
            self.settings.auto_routing_publication_path = path
            self.assertEqual(reader.publication(self.settings, self.snapshot), self.receipt)

    def test_malformed_empty_oversized_and_duplicate_closed(self):
        for raw in ("", "{", "[]", "null", " " * 8193,
                    '{"schema":2,"schema":2}', '{"budget":{"retries":0,"retries":1}}'):
            with self.subTest(raw_length=len(raw)):
                self.settings.auto_routing_publication_json = raw
                self.assertIsNone(reader.publication(self.settings, self.snapshot))

    def test_direct_flag_required(self):
        self.settings.auto_routing_direct_validation_enabled = False
        self.assertIsNone(self.read())

    def test_every_evidence_binding_and_identity_required(self):
        for key in ("policy_sha256", "authorization_evidence_sha256", "independent_review_sha256",
                    "policy_readback_sha256", "rollback_sha256", "snapshot_version", "endpoint",
                    "deployment", "gateway_principal", "gateway_client", "response_contract"):
            with self.subTest(key=key):
                receipt = copy.deepcopy(self.receipt)
                receipt[key] = "invalid"
                self.assertIsNone(self.read(receipt))

    def test_no_fabricated_runtime_proof(self):
        for key, value in (("runtime_verified", True), ("gateway_runtime_evidence_sha256", "7" * 64),
                           ("schema", True), ("stop_on_explicit_regression", False)):
            with self.subTest(key=key):
                receipt = {**self.receipt, key: value}
                self.assertIsNone(self.read(receipt))

    def test_budget_exact_and_typed(self):
        for key, value in (("auto_attempts", True), ("scoring_calls", 3), ("completion_calls", 1),
                           ("retries", False), ("retries", 1), ("fallback", 0), ("fallback", True)):
            with self.subTest(key=key, value=value):
                receipt = copy.deepcopy(self.receipt)
                receipt["budget"][key] = value
                self.assertIsNone(self.read(receipt))

    def test_environment_json_is_plain_string(self):
        with patch.dict("os.environ", {"AIFLUX_AUTO_ROUTING_PUBLICATION_JSON": json.dumps(self.receipt)}):
            settings = Settings(_env_file=None, environment="testing")
            self.assertEqual(json.loads(settings.auto_routing_publication_json), self.receipt)


if __name__ == "__main__":
    unittest.main(verbosity=2)