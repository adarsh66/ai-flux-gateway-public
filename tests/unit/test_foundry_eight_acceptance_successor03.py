"""Offline exact-identity, historical evidence and global exhaustion regression."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import foundry_eight_acceptance_successor03 as s
from tests.unit.test_foundry_eight_acceptance import response

a = s.a


class Offline(unittest.TestCase):
    def setUp(self):
        self.additions = a.load(s.previous.HOME / "metadata.json")["additions"]
        self.binding = a.load(s.previous.HOME / "policy-binding.json")

    def record(self, alias, model=None):
        status, headers, raw = response(alias)
        body = json.loads(raw)
        body["id"] = "synthetic-response-" + alias
        body["model"] = model if model is not None else alias
        return s.summary(alias, status, headers, json.dumps(body).encode())

    def seed(self, base):
        home = base / "foundry-eight-acceptance-synthetic-prior"
        for i, alias in enumerate(a.ALIASES[:5], 1):
            a.write(home / "probes" / f"{i:02d}-{alias}-intent.json", {
                "alias": alias, "client_request_id": "synthetic-" + alias, "consumed_before_send": True,
                "max_requests": 1, "retries": 0, "fallback": False})
        ledger = base / "global-ledger"
        s.seed_ledger(base, ledger)
        return ledger

    def test_exact_canonical_mapping_and_sanitizer_retention(self):
        for alias in ("gpt-6.1-terra", "gpt-6-luna"):
            d = next(d for d in self.additions if d["name"] == alias)
            canonical = d["model_name"] + "-" + d["model_version"]
            for model in (alias, canonical):
                row = self.record(alias, model)
                self.assertEqual(row["response_model"], model)
                self.assertEqual(row["canonical_alias"], alias)
                s.validate_probe(row, self.additions)
            for model in (canonical + "-extra", alias + "-2026-01-01", "gpt-6", "other-model"):
                with self.subTest(model=model), self.assertRaises(a.AcceptanceError):
                    s.validate_probe(self.record(alias, model), self.additions)

    def test_anthropic_and_mistral_cannot_use_dated_identity(self):
        for d in self.additions:
            if d["model_format"] != "OpenAI":
                s.validate_probe(self.record(d["name"]), self.additions)
                with self.assertRaises(a.AcceptanceError):
                    s.validate_probe(self.record(d["name"], d["model_name"] + "-" + d["model_version"]), self.additions)

    def test_unknown_unsafe_and_unbound_identity_rejected(self):
        alias = "gpt-6-luna"
        for model in ("unsafe model with spaces", "secret\nvalue", "x" * 161):
            row = self.record(alias, model)
            self.assertIsNone(row["response_model"])
            with self.assertRaises(a.AcceptanceError):
                s.validate_probe(row, self.additions)
        for field, value in (("id", a.ACCOUNT + "/deployments/other"), ("provisioning_state", "Failed"), ("capacity", 0)):
            wrong = deepcopy(self.additions)
            next(d for d in wrong if d["name"] == alias)[field] = value
            with self.assertRaises(a.AcceptanceError):
                s.validate_probe(self.record(alias), wrong)
        for field in ("response_id", "correlation_id"):
            row = self.record(alias)
            row[field] = None
            with self.assertRaises(a.AcceptanceError):
                s.validate_probe(row, self.additions)

    def test_actual_first_five_and_terra_evidence_preserved(self):
        before = s.historical_hashes()
        results, additions, binding = s.predecessors()
        self.assertEqual(len(results), 5)
        self.assertEqual(additions, self.additions)
        self.assertIsNone(results[4]["response_model"])
        self.assertFalse(results[4]["raw_response_model_captured"])
        self.assertEqual(results[4]["identity_model"], "gpt-6.1-terra-2026-10-26")
        self.assertEqual(results[2]["fast_speed_proof"]["normalizer_sha256"], binding["normalizer_sha256"])
        self.assertEqual(s.historical_hashes(), before)

    def test_terra_requires_exact_response_correlation_deployment_and_usage(self):
        original = s.bind_receipt(s.previous.HOME, 5, a.ALIASES[4])
        evidence = a.load(s.TELEMETRY / "evidence.json")
        for field, value in (("RequestId", "unbound"), ("CorrelationId", "unbound"),
                             ("DeploymentName", "gpt-6-luna"), ("TotalTokens", 18),
                             ("ModelName", "gpt-6.1-terra-2026-10-27")):
            wrong = deepcopy(evidence)
            wrong["llm_row"][field] = value
            with self.subTest(field=field), self.assertRaises(a.AcceptanceError):
                s.resolve_terra(original, self.additions, wrong)

    def test_global_ledger_first_five_and_claim_exhaustion(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            ledger = self.seed(base)
            for alias in a.ALIASES[:5]:
                with self.assertRaises(a.AcceptanceError):
                    s.claim(base, ledger, alias, "never")
            for alias in s.REMAINING:
                s.claim(base, ledger, alias, "one")
                with self.assertRaises(FileExistsError):
                    s.claim(base, ledger, alias, "two")
            self.assertEqual({p.stem for p in ledger.glob("*.json")}, set(a.ALIASES))
            with self.assertRaises(FileExistsError):
                s.seed_ledger(base, ledger)

    def test_duplicate_prior_intent_stops_before_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            ledger = self.seed(base)
            source = next(base.rglob("*-intent.json"))
            a.write(base / "foundry-eight-acceptance-duplicate/probes/duplicate-intent.json", source.read_bytes())
            with self.assertRaises(a.AcceptanceError):
                s.claim(base, ledger, s.REMAINING[0], "never")

    def test_three_one_shot_sends_retained_dated_model_no_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            ledger = self.seed(base)
            home = base / "foundry-eight-acceptance-synthetic-successor"
            calls = []

            class Fake:
                def send(inner, alias, key, request_id):
                    self.assertTrue((ledger / (alias + ".json")).is_file())
                    intent = a.load(home / "probes" / f"{len(calls) + 6:02d}-{alias}-intent.json")
                    self.assertEqual(intent["client_request_id"], request_id)
                    calls.append(alias)
                    status, headers, raw = response(alias)
                    body = json.loads(raw)
                    if alias == "gpt-6-luna":
                        body["model"] = "gpt-6-luna-2026-09-22"
                    return status, headers, json.dumps(body).encode()

            with patch.object(a.rt, "HOME", base):
                rows = s.probes(Fake(), "synthetic-secret", home, ledger, self.additions, self.binding)
                self.assertEqual(rows[0]["response_model"], "gpt-6-luna-2026-09-22")
                with self.assertRaises(a.AcceptanceError):
                    s.probes(Fake(), "synthetic-secret", home, ledger, self.additions, self.binding)
            self.assertEqual(calls, list(s.REMAINING))
            self.assertNotIn("synthetic-secret", "".join(p.read_text() for p in base.rglob("*.json")))

    def test_failed_or_unknown_send_stops_and_consumes(self):
        for unknown in (False, True):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                ledger = self.seed(base)
                home = base / "foundry-eight-acceptance-synthetic-successor"
                calls = []

                class Fake:
                    def send(inner, alias, key, request_id):
                        calls.append(alias)
                        if unknown:
                            raise RuntimeError("sensitive value")
                        return 503, {}, b'{"secret":"sensitive value"}'

                with patch.object(a.rt, "HOME", base), self.assertRaises(a.AcceptanceError):
                    s.probes(Fake(), "synthetic", home, ledger, self.additions, self.binding)
                self.assertEqual(calls, [s.REMAINING[0]])
                with self.assertRaises(a.AcceptanceError):
                    s.claim(base, ledger, s.REMAINING[0], "again")
                self.assertNotIn("sensitive value", "".join(p.read_text() for p in base.rglob("*.json")))

    def test_packaging_actual_five_plus_synthetic_three_offline(self):
        results, additions, _ = s.predecessors()
        results.extend(self.record(alias) for alias in s.REMAINING)
        before = s.historical_hashes()
        old = a.load(a.CATALOG / "foundry-inventory-20261026.json")
        candidate = a.load(a.CATALOG / "foundry-eight-candidate-routes.json")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / "synthetic-offline-only"
            for name in ("approved_catalog.py", "catalog-bindings.json"):
                a.write(root / "services/usage-ingestion" / name, (a.ROOT / "services/usage-ingestion" / name).read_bytes())
            with patch.object(a, "ROOT", root):
                artifacts = s.promote(home, old, additions, results, candidate, {})
            accepted = a.load(root / artifacts["accepted_inventory"])
            self.assertEqual(accepted["verified_at"], old["verified_at"])
            self.assertEqual(accepted["deployments"][:13], old["deployments"])
            for old_route, route in zip(old["routes"], accepted["routes"]):
                self.assertEqual(route, {**old_route, "endpoint_url": a.GATEWAY})
            catalog = a.load(root / artifacts["accepted_catalog"])
            self.assertEqual(sum(m["enabled"] for m in catalog["models"]), 21)
            self.assertEqual(len(a.load(home / "rates-proof.json")["rates"]), 8)
        self.assertEqual(s.historical_hashes(), before)


if __name__ == "__main__":
    unittest.main()