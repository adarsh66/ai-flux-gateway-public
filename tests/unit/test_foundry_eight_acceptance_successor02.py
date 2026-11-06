"""Offline exact zero-send/content-negotiation successor checks."""
import unittest
from unittest.mock import patch

from scripts.deployment import foundry_eight_acceptance_successor02 as s


class Offline(unittest.TestCase):
    def test_all_consumed_predecessors_remain_exact_and_zero_send(self):
        self.assertTrue(s.predecessor())
        self.assertNotEqual(s.HOME, s.prior.HOME)
        self.assertNotEqual(s.HOME, s.a.HOME)

    def test_explicit_json_accept_strict_ca_zero_adapter_retries(self):
        with patch.object(s.a, "cli", return_value={"id": s.a.rt.SUB, "tenantId": s.a.rt.TENANT, "state": "Enabled"}) as cli:
            client = s.JSONClient()
        self.assertEqual(cli.call_count, 1)
        self.assertEqual(client.session.headers["Accept"], "application/json")
        self.assertEqual(client.session.verify, s.a.rt.CA)
        self.assertEqual(client.session.get_adapter("https://management.azure.com/").max_retries.total, 0)
        self.assertIsNone(client.token)
        client.close()

    def test_inference_transport_and_validation_not_replaced(self):
        self.assertIs(s.JSONClient.send, s.a.Client.send)
        self.assertIs(s.JSONClient.wire, s.a.Client.wire)
        self.assertIs(s.JSONClient.arm, s.prior.FreshClient.arm)


if __name__ == "__main__":
    unittest.main()