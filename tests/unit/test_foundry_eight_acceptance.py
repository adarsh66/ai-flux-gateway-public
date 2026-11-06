"""Synthetic offline acceptance guards; never instantiate the Azure client."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts.deployment import foundry_eight_acceptance as a


def response(alias, *, usage=None, status=200, text="Hello."):
    body = {"id": "synthetic-response", "object": "chat.completion", "model": alias,
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": usage if usage is not None else {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12}}
    return status, {"x-aiflux-request-id": str(uuid4())}, json.dumps(body).encode()


class Offline(unittest.TestCase):
    def binding(self):
        return {"policy_sha256": "a" * 64, "normalizer_sha256": "b" * 64,
                "fast_proof_method": "synthetic test guard binding"}

    def test_exact_case_membership_and_order(self):
        self.assertEqual(len(a.ALIASES), 8)
        self.assertEqual(set(a.ALIASES), a.applied.reader.NEW)
        self.assertIn("Mistral-Large-3", a.ALIASES)
        self.assertNotIn("mistral-medium-3-5", a.ALIASES)

    def test_intent_exclusive_and_fsynced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "intent.json"
            a.write(path, {"consumed": True})
            with self.assertRaises(FileExistsError):
                a.write(path, {"consumed": False})
            self.assertEqual(a.load(path), {"consumed": True})

    def test_actual_retained_policy_strict_speed_guard(self):
        raw = (a.applied.EVIDENCE / "postapply-policy.xml").read_bytes().decode()
        binding = a.policy_binding({"properties": {"value": raw}})
        self.assertTrue(binding["semantic_guard"]["strict_native_response_normalization"])
        self.assertFalse(binding["speed_inferred_from_latency"])
        self.assertFalse(binding["speed_exposed_in_public_usage"])
        with self.assertRaises(a.AcceptanceError):
            a.policy_binding({"properties": {"value": raw.replace("Invalid provider speed", "waived")}})

    def test_sanitized_response_has_no_text_or_headers(self):
        status, headers, raw = response(a.ALIASES[0], text="synthetic sensitive text")
        headers["Authorization"] = "synthetic key"
        record = a.summary(a.ALIASES[0], status, headers, raw)
        a.validate_probe(record)
        self.assertNotIn("synthetic sensitive text", json.dumps(record))
        self.assertNotIn("synthetic key", json.dumps(record))
        self.assertIsNone(record["usage"]["cached_input_tokens"])

    def test_missing_native_cache_is_unknown_not_zero(self):
        alias = a.ALIASES[0]
        r = a.summary(alias, *response(alias, usage={"prompt_tokens": None, "completion_tokens": 3,
            "total_tokens": None, "prompt_tokens_details": {"cached_tokens": None, "cache_write_tokens": None}}))
        a.validate_probe(r)
        self.assertIsNone(r["usage"]["prompt_tokens"])
        self.assertIsNone(r["usage"]["total_tokens"])
        r["alias"] = "gpt-6-luna"
        r["response_model"] = r["alias"]
        with self.assertRaises(a.AcceptanceError):
            a.validate_probe(r)

    def test_invalid_usage_and_failure_contracts(self):
        alias = a.ALIASES[0]
        for usage in ({"prompt_tokens": 9, "completion_tokens": 129, "total_tokens": 138},
                      {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 13},
                      {"prompt_tokens": True, "completion_tokens": 3, "total_tokens": 4},
                      {"prompt_tokens": 9, "completion_tokens": -1, "total_tokens": 8},
                      {"prompt_tokens": 9, "completion_tokens": 0, "total_tokens": 9}):
            with self.subTest(usage=usage), self.assertRaises(a.AcceptanceError):
                a.validate_probe(a.summary(alias, *response(alias, usage=usage)))
        for key, value in (("status", 503), ("response_model", None), ("assistant_nonempty", False),
                           ("finish_reason", "length"), ("correlation_id", None)):
            r = a.summary(alias, *response(alias))
            r[key] = value
            with self.subTest(key=key), self.assertRaises(a.AcceptanceError):
                a.validate_probe(r)

    def test_eight_intents_before_send_no_ninth_and_no_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            calls = []

            class Fake:
                def send(self, alias, key, request_id):
                    i = len(calls) + 1
                    intent = a.load(home / "probes" / f"{i:02d}-{alias}-intent.json")
                    assert intent["client_request_id"] == request_id
                    assert intent["consumed_before_send"] and intent["retries"] == 0
                    calls.append(alias)
                    return response(alias)

            result = a.probes(Fake(), "synthetic ephemeral key", home, self.binding())
            self.assertEqual(calls, list(a.ALIASES))
            self.assertEqual(len(result), 8)
            self.assertIn("fast_speed_proof", result[2])
            with self.assertRaises(FileExistsError):
                a.probes(Fake(), "synthetic ephemeral key", home, self.binding())
            self.assertEqual(len(calls), 8)
            self.assertNotIn("synthetic ephemeral key", "".join(p.read_text() for p in home.rglob("*.json")))

    def test_first_failure_consumes_and_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []

            class Fake:
                def send(self, alias, key, request_id):
                    calls.append(alias)
                    return 503, {}, b'{"error":"normalizer internal detail must not persist"}'

            with self.assertRaises(a.AcceptanceError):
                a.probes(Fake(), "never persisted", Path(folder), self.binding())
            self.assertEqual(calls, [a.ALIASES[0]])
            self.assertEqual(len(list(Path(folder).rglob("*-intent.json"))), 1)
            self.assertFalse((Path(folder) / "accepted-context").exists())
            self.assertNotIn("normalizer internal detail", "".join(p.read_text() for p in Path(folder).rglob("*.json")))

    def test_ambiguous_transport_error_never_retries_or_leaks(self):
        with tempfile.TemporaryDirectory() as folder:
            class Fake:
                def send(self, alias, key, request_id):
                    raise RuntimeError("synthetic secret in arbitrary transport error")

            with self.assertRaises(a.AcceptanceError):
                a.probes(Fake(), "never persisted", Path(folder), self.binding())
            self.assertEqual(len(list(Path(folder).rglob("*-intent.json"))), 1)
            self.assertNotIn("synthetic secret", "".join(p.read_text() for p in Path(folder).rglob("*.json")))

    def fixtures(self):
        old = a.load(a.CATALOG / "foundry-inventory-20261026.json")
        candidate = a.load(a.CATALOG / "foundry-eight-candidate-routes.json")
        live = a.load(a.rt.HOME / "foundry-eight-20261030/deployments.json")
        return old, candidate, live

    def test_metadata_selection_excludes_ninth_and_preserves_old(self):
        old, candidate, live = self.fixtures()
        additions, scope = a.metadata_guard(old, live, candidate)
        self.assertEqual(len(additions), 8)
        self.assertEqual(scope["selected_count"], 21)
        self.assertEqual(scope["excluded_names"], ["mistral-medium-3-5"])
        wrong = deepcopy(live)
        wrong["value"][0]["properties"]["model"]["version"] = "wrong"
        with self.assertRaises(a.AcceptanceError):
            a.metadata_guard(old, wrong, candidate)
        wrong = deepcopy(live)
        wrong["nextLink"] = "another-page"
        with self.assertRaises(a.AcceptanceError):
            a.metadata_guard(old, wrong, candidate)

    def test_new_context_explicit_profile_official_schema_grandfather(self):
        old, candidate, live = self.fixtures()
        original = deepcopy(old)
        additions, _ = a.metadata_guard(old, live, candidate)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / "synthetic-acceptance-only"
            for name in ("approved_catalog.py", "catalog-bindings.json"):
                a.write(root / "services/usage-ingestion" / name,
                        (a.ROOT / "services/usage-ingestion" / name).read_bytes())

            class Fake:
                def send(self, alias, key, request_id):
                    return response(alias)

            results = a.probes(Fake(), "synthetic", home, self.binding())
            with patch.object(a, "ROOT", root):
                artifacts = a.promote(home, old, additions, results, candidate, {})
            self.assertEqual(old, original)
            accepted = a.load(root / artifacts["accepted_inventory"])
            self.assertEqual(accepted["verified_at"], old["verified_at"])
            self.assertEqual(accepted["deployments"][:13], old["deployments"])
            for before, after in zip(old["routes"], accepted["routes"][:12]):
                self.assertEqual({**before, "endpoint_url": a.GATEWAY}, after)
            catalog = a.load(root / artifacts["accepted_catalog"])
            self.assertEqual(sum(m["enabled"] for m in catalog["models"]), 21)
            self.assertEqual((home / "accepted-context/gateway/catalog/external-inventory.json").read_bytes(),
                             (a.CATALOG / "external-inventory.json").read_bytes())
            self.assertFalse(next(m for m in catalog["models"] if m["id"] == "Decision-1")["enabled"])

    def test_no_promotion_on_partial_probes(self):
        old, candidate, live = self.fixtures()
        additions, _ = a.metadata_guard(old, live, candidate)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(a.AcceptanceError):
            a.promote(Path(folder), old, additions, [], candidate, {})

    def test_outbound_exact_benign_cap_and_no_extra_credentials(self):
        client = a.Client.__new__(a.Client)
        with patch.object(client, "wire", return_value=(200, {}, b"{}")) as wire:
            client.send("Mistral-Large-3", "synthetic", "synthetic-id")
            args, kw = wire.call_args
            self.assertEqual(args, ("POST", a.GATEWAY + "/chat/completions"))
            self.assertEqual(kw["body"], {"model": "Mistral-Large-3", "messages": [{"role": "user",
                "content": "Reply with a short greeting."}], "max_completion_tokens": 128, "stream": False})
            self.assertEqual(set(kw["headers"]), {"Ocp-Apim-Subscription-Key", "Content-Type", "x-ms-client-request-id"})
            self.assertEqual(wire.call_count, 1)

    def test_secret_allowlist_only_existing_subscription(self):
        client = a.Client.__new__(a.Client)
        client.token = "synthetic bearer"
        with patch.object(client, "wire", return_value=(200, {}, b'{"primaryKey":"synthetic"}')) as wire:
            path = a.APIM + "/subscriptions/" + a.SUBSCRIBER + "/listSecrets"
            self.assertEqual(client.arm(path, secret=True)["primaryKey"], "synthetic")
            self.assertEqual(wire.call_args.args[0], "POST")
            with self.assertRaises(a.AcceptanceError):
                client.arm(a.APIM + "/subscriptions/other/listSecrets", secret=True)
            with self.assertRaises(a.AcceptanceError):
                client.arm(path)
            self.assertEqual(wire.call_count, 1)


if __name__ == "__main__":
    unittest.main()